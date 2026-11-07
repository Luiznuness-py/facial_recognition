import {
  state,
  $,
  el,
  link,
  button,
  info,
  heading,
  panel,
  failure,
  notice,
  can,
  icon
} from './ui.js';
import {
  api,
  discover
} from './api.js';
import {
  loginView,
  stageView,
  passwordStart,
  stopCamera,
  resume
} from './auth.js';
import {
  accounts,
  newAccount,
  accountDetail,
  requests,
  newRequest,
  requestDetail,
  audit
} from './admin.js';
import {
  agents,
  newAgent,
  agentDetail,
  validationDetail,
  reportForm,
  reports,
  vault,
  dossier
} from './science.js';
import {
  publications,
  publicationDetail
} from './public.js';
const menus = [
  [
    'amostras',
    'Amostras',
    'agents.read'
  ],
  [
    'revisoes',
    'Revisões',
    'validations.review'
  ],
  [
    'envios',
    'Enviadas ao N3',
    'reports.read'
  ],
  [
    'cofre',
    'Cofre de dossiês',
    'vault.read'
  ],
  [
    'publicacoes',
    'Publicações',
    'publications.read'
  ],
  [
    'solicitacoes',
    'Solicitações de acesso',
    'accounts.request.read'
  ],
  [
    'contas',
    'Contas',
    'accounts.manage'
  ],
  [
    'auditoria',
    'Auditoria administrativa',
    'audit.read'
  ]
];
const permissionFor = {
  amostras: 'agents.read',
  revisoes: 'validations.review',
  investigacoes: 'validations.read',
  envios: 'reports.read',
  cofre: 'vault.read',
  publicacoes: 'publications.read',
  solicitacoes: 'accounts.request.read',
  contas: 'accounts.manage',
  auditoria: 'audit.read'
};
let generation = 0, lastHash = location.hash || '#/noticias', restoring = true;
let firstRender = true, nextNotice = null;
function home() {
  return '#/' + (menus.find(([, , permission]) => can(permission))?.[0] || 'inicio');
}
function shell(section) {
  const institutional = Boolean(state.user) && !state.stage && ![
    'noticias',
    'login'
  ].includes(section);
  document.body.classList.toggle('institutional', institutional);
  document.body.classList.toggle('public-page', section === 'noticias');
  document.body.classList.toggle('auth-page', !institutional && section !== 'noticias');
  $('sidebar').hidden = !institutional;
  $('layout').toggleAttribute('data-ui', institutional);
  $('top-nav').replaceChildren(link('Notícias', '#/noticias'), state.user && !state.stage ? link('Área institucional', home(), 'button secondary') : link('Acesso institucional', '#/login', 'button secondary'));
  if (state.user || state.stage)
    $('top-nav').append(button('Sair', logout, 'quiet'));
  if (institutional) {
    const navIcons = {
      amostras: 'samples',
      revisoes: 'review',
      envios: 'send',
      cofre: 'vault',
      publicacoes: 'news',
      solicitacoes: 'requests',
      contas: 'users',
      auditoria: 'audit'
    };
    const active = section === 'investigacoes' ? state.user.role === 'N2' ? 'revisoes' : 'amostras' : section;
    const accountLink = link('Alterar senha', '#/senha');
    accountLink.prepend(icon('key'));
    const initials = state.user.name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('');
    $('sidebar').replaceChildren(el('div', { class: 'sidebar-intro' }, el('strong', {}, 'Espaço de trabalho'), el('span', {}, 'Biossegurança ambiental')), el('nav', { 'aria-label': 'Menu institucional' }, ...menus.filter(([, , permission]) => can(permission)).map(([path, title]) => el('a', {
      href: '#/' + path,
      'aria-current': active === path ? 'page' : null
    }, icon(navIcons[path]), el('span', {}, title)))), el('div', { class: 'sidebar-bottom' }, el('nav', {
      class: 'account-nav',
      'aria-label': 'Sua conta'
    }, accountLink), el('div', { class: 'identity' }, el('span', {
      class: 'identity-avatar',
      'aria-hidden': 'true'
    }, initials), el('div', {}, el('strong', {}, state.user.name), el('span', {}, state.user.role + ' · ' + (state.user.team?.name || 'Institucional'))))));
  } else
    $('sidebar').replaceChildren();
}
async function logout() {
  if (state.busy || !window.confirm(state.dirty ? 'Há alterações não salvas. Sair e descartá-las?' : 'Encerrar seu acesso ao laboratório?'))
    return;
  state.busy = true;
  try {
    await api('/auth/logout', 'POST', null, { private: false });
    state.user = null;
    state.stage = null;
    state.operation = null;
    state.dirty = false;
    stopCamera();
    location.hash = '#/login';
    await render();
    notice('Acesso encerrado.');
  } catch (error) {
    notice(error.message, true);
  } finally {
    state.busy = false;
  }
}
async function render() {
  if (restoring)
    return;
  const current = ++generation;
  stopCamera();
  $('notice').hidden = true;
  const [pathname, query = ''] = location.hash.replace(/^#\/?/, '').split('?');
  let segments;
  try {
    segments = pathname.split('/').map(decodeURIComponent);
  } catch {
    segments = ['pagina-invalida'];
  }
  const [section = 'noticias', id, action] = segments;
  const params = new URLSearchParams(query);
  if (!params.has('page'))
    params.set('page', '1');
  if (!/^\d+$/.test(params.get('page')) || Number(params.get('page')) < 1)
    params.set('page', '1');
  if (section !== 'noticias' && section !== 'login' && !state.user && !state.stage) {
    location.hash = '#/login';
    return;
  }
  if (state.stage && section !== 'acesso') {
    location.hash = '#/acesso';
    return;
  }
  if (section === 'login' && state.user && !state.stage) {
    location.hash = home();
    return;
  }
  shell(section);
  const view = $('view');
  view.setAttribute('aria-busy', 'true');
  view.replaceChildren(el('p', {
    class: 'loading',
    role: 'status'
  }, 'Carregando…'));
  try {
    let nodes;
    const needed = permissionFor[section];
    if (needed && !can(needed))
      nodes = [
        heading('Acesso não permitido'),
        info('Área restrita', 'Seu papel não permite consultar esta área.'),
        link('Voltar à sua área', home())
      ];
    else
      switch (section) {
      case 'noticias':
        nodes = id ? await publicationDetail(id) : await publications(params);
        break;
      case 'login':
        nodes = loginView();
        document.title = 'Acesso institucional · Biossegurança Ambiental';
        break;
      case 'acesso':
        nodes = stageView();
        break;
      case 'senha':
        nodes = passwordStart();
        break;
      case 'contas':
        nodes = id === 'nova' ? can('accounts.manage') ? await newAccount() : info('Acesso negado', 'Sem permissão.') : id ? await accountDetail(id) : await accounts(params);
        break;
      case 'solicitacoes':
        nodes = id === 'nova' ? can('accounts.request') ? await newRequest() : info('Acesso negado', 'Sem permissão.') : id ? await requestDetail(id) : await requests(params);
        break;
      case 'auditoria':
        nodes = await audit(params);
        break;
      case 'amostras':
        nodes = id === 'nova' ? can('agents.create') ? newAgent() : info('Acesso negado', 'Sem permissão para cadastrar.') : id ? await agentDetail(id, params) : await agents(params);
        break;
      case 'revisoes':
        nodes = await agents(params, true);
        break;
      case 'investigacoes':
        nodes = id ? action === 'envio' ? can('reports.send') ? await reportForm(id) : info('Acesso negado', 'Sem permissão para encaminhar relatórios.') : await validationDetail(id) : info('Selecione uma investigação', 'Abra uma amostra para consultar suas investigações.');
        break;
      case 'envios':
        nodes = await reports(params);
        break;
      case 'cofre':
        nodes = id ? await dossier(id) : await vault(params);
        break;
      case 'publicacoes':
        nodes = id ? await publicationDetail(id, true) : await publications(params, true);
        break;
      case 'inicio':
        nodes = [
          heading('Área institucional', 'Seu acesso foi confirmado pelo servidor.'),
          panel(el('p', {}, 'Nenhuma área está disponível nas suas permissões atuais. Consulte o administrador.'))
        ];
        break;
      default:
        nodes = [
          heading('Página não encontrada'),
          link('Voltar ao início', '#/noticias')
        ];
      }
    if (current !== generation)
      return;
    view.replaceChildren(...[nodes].flat().filter(Boolean));
  } catch (error) {
    if (current === generation)
      view.replaceChildren(failure(error, reload));
  } finally {
    if (current === generation) {
      view.setAttribute('aria-busy', 'false');
      const title = view.querySelector('h1,h2');
      if (title && !firstRender) {
        title.tabIndex = -1;
        title.focus({ preventScroll: true });
      }
      firstRender = false;
      if (nextNotice) {
        notice(nextNotice, true);
        nextNotice = null;
      }
    }
  }
}
function expired() {
  generation++;
  stopCamera();
  state.user = null;
  state.stage = null;
  state.operation = null;
  state.dirty = false;
  const box = $('action-dialog');
  if (box.open)
    box.close();
  nextNotice = 'Sua sessão expirou ou foi encerrada. Entre novamente para continuar.';
  if (location.hash === '#/login')
    render();
  else
    location.hash = '#/login';
}
window.addEventListener('session-expired', expired);
window.addEventListener('authenticated', () => {
  state.dirty = false;
  if (location.hash === home())
    render();
  else
    location.hash = home();
});
async function reload() {
  await discover();
  await render();
}
window.addEventListener('render-page', reload);
window.addEventListener('hashchange', () => {
  if (location.hash === '#content' || location.hash === '#publicacoes' || location.hash === '#sobre-projeto')
    return;
  if (state.dirty && !window.confirm('Há alterações não salvas. Descartar e mudar de página?')) {
    history.replaceState(null, '', lastHash);
    return;
  }
  state.dirty = false;
  lastHash = location.hash;
  window.scrollTo(0, 0);
  render();
});
document.addEventListener('click', event => {
  const a = event.target.closest('a');
  if (!a)
    return;
  if (a.getAttribute('href') === '#content' || a.getAttribute('href') === '#publicacoes' || a.getAttribute('href') === '#sobre-projeto') {
    event.preventDefault();
    const node = $(a.hash.slice(1));
    if (node) {
      node.scrollIntoView();
      node.focus({ preventScroll: true });
    }
    return;
  }
  if (a.hash?.startsWith('#/') && a.origin === location.origin && state.busy) {
    event.preventDefault();
    notice('Aguarde a conclusão da operação antes de mudar de tela.');
  }
});
window.addEventListener('beforeunload', event => {
  if (state.dirty || state.busy) {
    event.preventDefault();
    event.returnValue = '';
  }
});
async function start() {
  await discover();
  try {
    state.user = await api('/auth/me', 'GET', null, { private: false });
  } catch (error) {
    if (error.status === 401) {
      try {
        await api('/auth/refresh', 'POST', null, { private: false });
        state.user = await api('/auth/me', 'GET', null, { private: false });
      } catch (refreshError) {
        if (refreshError.status === 401 || refreshError.status === 403) {
          try {
            await resume();
          } catch (flowError) {
            if (flowError.status !== 401 && flowError.status !== 403)
              notice(flowError.message, true);
          }
        } else
          notice(refreshError.message, true);
      }
    } else
      notice(error.message, true);
  }
  restoring = false;
  if (state.stage)
    location.hash = '#/acesso';
  else if (!location.hash)
    location.hash = state.user ? home() : '#/noticias';
  await render();
}
start();
