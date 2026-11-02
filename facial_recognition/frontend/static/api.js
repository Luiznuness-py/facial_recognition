import { state } from './ui.js';
let routes = null, refreshTask = null;
export class ApiError extends Error {
  constructor(message, status, pending = false) {
    super(message);
    this.status = status;
    this.pending = pending;
  }
}
export async function discover() {
  try {
    const response = await fetch('/openapi.json', {
      credentials: 'same-origin',
      cache: 'no-store'
    });
    if (response.ok)
      routes = (await response.json()).paths;
  } catch {
    routes = null;
  }
}
function routeEntry(path) {
  if (!routes)
    return null;
  const url = '/api/v1' + path.split('?')[0].replace(/\/$/, '');
  return Object.entries(routes).find(([pattern]) => {
    const segments = pattern.replace(/\/$/, '').split('/'), target = url.split('/');
    return segments.length === target.length && segments.every((part, i) => part.startsWith('{') || part === target[i]);
  });
}
export function available(path, method = 'GET') {
  if (!routes)
    return null;
  return Boolean(routeEntry(path)?.[1][method.toLowerCase()]);
}
export function pendingMessage(path, method = 'GET') {
  return available(path, method) === false ? 'Esta funcionalidade ainda depende da implementação do backend. Os campos estão preparados, mas nenhuma operação foi executada.' : null;
}
async function raw(path, method = 'GET', body = null) {
  const entry = routeEntry(path);
  // FastAPI expõe alguns catálogos com barra final; evita redirecionar mutações.
  const [base, query] = path.split('?');
  const target = entry?.[0].endsWith('/') ? base.replace(/\/$/, '') + '/' : base;
  const headers = {};
  if (method !== 'GET') {
    const csrf = await raw('/auth/csrf');
    headers['X-CSRF-Token'] = csrf.csrf_token;
  }
  if (body !== null && !(body instanceof FormData))
    headers['Content-Type'] = 'application/json';
  let response;
  try {
    response = await fetch('/api/v1' + target + (query ? '?' + query : ''), {
      method,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
      body: body === null ? undefined : body instanceof FormData ? body : JSON.stringify(body)
    });
  } catch {
    throw new ApiError('Não foi possível conectar ao servidor. Confira a conexão e tente novamente.', 0);
  }
  if (response.status === 204)
    return null;
  let result;
  try {
    result = await response.json();
  } catch {
    throw new ApiError('O servidor retornou uma resposta inesperada. Tente novamente.', response.status);
  }
  if (!response.ok || result.success === false) {
    const fallbacks = {
      401: 'Sua sessão ou etapa expirou. Entre novamente.',
      403: 'Você não tem permissão para esta ação.',
      404: 'Registro não encontrado ou fora do seu acesso.',
      409: 'A situação mudou. Atualize a tela antes de tentar novamente.',
      422: 'Confira os campos e seus limites.',
      429: 'Muitas tentativas. Aguarde antes de tentar novamente.',
      503: 'Serviço indisponível. Tente novamente mais tarde.'
    };
    throw new ApiError(result.error?.message || fallbacks[response.status] || 'Não foi possível concluir a operação.', response.status);
  }
  if (!Object.hasOwn(result, 'data'))
    throw new ApiError('Resposta incompatível com o contrato da aplicação.', response.status);
  return result.data;
}
export async function api(path, method = 'GET', body = null, {
  private: needsSession = true,
  retry = true
} = {}) {
  if (available(path, method) === false)
    throw new ApiError(pendingMessage(path, method), 501, true);
  try {
    return await raw(path, method, body);
  } catch (error) {
    if (error.status === 401 && needsSession && retry && state.user) {
      try {
        if (!refreshTask)
          refreshTask = raw('/auth/refresh', 'POST').finally(() => {
            refreshTask = null;
          });
        await refreshTask;
      } catch (refreshError) {
        if (refreshError.status === 401 || refreshError.status === 403)
          window.dispatchEvent(new Event('session-expired'));
        throw refreshError;
      }
      return api(path, method, body, {
        private: needsSession,
        retry: false
      });
    }
    if (error.status === 401 && needsSession && state.user)
      window.dispatchEvent(new Event('session-expired'));
    throw error;
  }
}
export async function allPages(path) {
  const result = [];
  let page = 1, total;
  do {
    const data = await api(path + (path.includes('?') ? '&' : '?') + 'per_page=100&page=' + page++);
    result.push(...data.items);
    total = data.total;
    if (!data.items.length)
      break;
  } while (result.length < total);
  return result;
}
