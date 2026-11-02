export const state = {
  user: null,
  stage: null,
  operation: null,
  dirty: false,
  busy: false
};
export const $ = id => document.getElementById(id);
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false)
      continue;
    if (key.startsWith('on'))
      node.addEventListener(key.slice(2), value);
    else if (key === 'class')
      node.className = value;
    else if (key in node && !key.startsWith('aria-'))
      node[key] = value;
    else
      node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined)
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
export function icon(name) {
  const shapes = {
    samples: [
      'M4 7h16v13H4z',
      'M8 7V4h8v3',
      'M8 12h8M8 16h5'
    ],
    review: [
      'M9 4H5v17h14V4h-4',
      'M9 3h6v4H9z',
      'm8 14 3 3 5-6'
    ],
    send: [
      'm3 4 18 8-18 8 4-8-4-8Z',
      'M7 12h14'
    ],
    vault: [
      'M4 4h16v16H4z',
      'M8 4v16',
      'M14 9v6M11 12h6'
    ],
    news: [
      'M4 4h16v16H4z',
      'M8 8h8M8 12h8M8 16h4'
    ],
    users: [
      'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2',
      'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8',
      'M20 21v-2a4 4 0 0 0-3-4',
      'M16 3a4 4 0 0 1 0 8'
    ],
    requests: [
      'M4 6h16v14H4z',
      'm4 6 8 7 8-7'
    ],
    audit: ['M3 12h4l3-8 4 16 3-8h4'],
    key: [
      'M15 3a6 6 0 1 0 4 10',
      'm10 10-7 7v4h4v-3h3l3-3'
    ],
    arrow: [
      'M4 12h16',
      'm14 6 6 6-6 6'
    ],
    globe: [
      'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
      'M3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18'
    ],
    logout: [
      'M9 4H4v16h5',
      'M9 12h12',
      'm17 8 4 4-4 4'
    ],
    alert: [
      'm12 3 10 18H2L12 3Z',
      'M12 9v4M12 17h.01'
    ]
  };
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  for (const [key, value] of Object.entries({
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': '1.7',
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      'aria-hidden': 'true',
      focusable: 'false',
      class: 'icon'
    }))
    svg.setAttribute(key, value);
  for (const d of shapes[name] || shapes.samples) {
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', d);
    svg.append(path);
  }
  return svg;
}
export const link = (text, href, cls = '') => el('a', {
  href,
  class: cls
}, text);
export const button = (text, onclick, cls = 'secondary') => el('button', {
  type: 'button',
  class: cls,
  onclick
}, text);
export const group = (...nodes) => el('div', { class: 'actions' }, ...nodes);
export const panel = (...nodes) => el('section', { class: 'panel' }, ...nodes);
export function heading(title, description, actions) {
  document.title = title + ' · Biossegurança Ambiental';
  return el('div', { class: 'page-heading' }, el('div', { class: 'heading-copy' }, el('h1', {}, title), description ? el('p', {}, description) : null), actions);
}
const names = {
  OPEN: 'Em preparação',
  IN_REVIEW: 'Em revisão',
  RETURNED: 'Devolvida para correção',
  REPORTED: 'Aguardando N3',
  PUBLISHED: 'Publicada',
  CLOSED: 'Encerrada',
  ACTIVE: 'Ativa',
  INACTIVE: 'Inativa',
  PENDING_ACTIVATION: 'Ativação pendente',
  PENDING: 'Pendente',
  APPROVED: 'Aprovada',
  REJECTED: 'Rejeitada',
  WAITING_N3: 'Aguardando decisão',
  RESTRICTED: 'Mantida em sigilo',
  NEW_VALIDATION_REQUESTED: 'Nova investigação solicitada',
  WITHDRAWN: 'Retirada',
  LOW: 'Baixo',
  MODERATE: 'Moderado',
  HIGH: 'Alto'
};
export const label = value => names[value] || value || 'Não informado';
export const badge = value => el('span', { class: 'badge ' + (/RETURNED|PENDING|WAITING|IN_REVIEW|HIGH/.test(value || '') ? 'attention' : '') }, label(value));
export function date(value) {
  if (!value)
    return 'Não informado';
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const d = new Date(dateOnly ? value + 'T12:00:00' : value);
  return Number.isNaN(d.getTime()) ? 'Data inválida' : new Intl.DateTimeFormat('pt-BR', dateOnly ? { dateStyle: 'medium' } : {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(d);
}
export const percent = value => value === null || value === undefined ? 'Não determinado' : new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 }).format(value) + '%';
export function info(title, text, cls = '') {
  return el('div', { class: 'info ' + cls }, el('strong', {}, title), el('p', {}, text));
}
export function notice(text, error = false) {
  const node = $('notice');
  node.textContent = text;
  node.hidden = false;
  node.className = error ? 'error' : 'success';
  node.setAttribute('tabindex', '-1');
  if (error)
    node.focus();
}
export function failure(error, retry) {
  const titles = {
    401: 'Sessão expirada',
    403: 'Acesso não permitido',
    404: 'Registro não encontrado',
    409: 'A situação do registro mudou',
    429: 'Aguarde para tentar novamente',
    503: 'Serviço indisponível'
  };
  return el('section', { class: 'panel empty-state' }, el('div', { class: 'empty-symbol' }, icon(error.pending ? 'news' : 'alert')), el('div', {}, el('h2', {}, error.pending ? 'Funcionalidade pendente' : titles[error.status] || 'Não foi possível carregar'), el('p', {}, error.message), retry ? button('Tentar novamente', retry, 'secondary') : null));
}
export function details(items) {
  return el('dl', { class: 'details' }, ...items.flatMap(([title, value]) => [
    el('dt', {}, title),
    el('dd', {}, value ?? 'Não informado')
  ]));
}
export function textSection(title, text) {
  return el('section', { class: 'text-section' }, el('h3', {}, title), el('p', { class: 'prose' }, text || 'Não informado'));
}
let fieldId = 0;
// Pequeno construtor compartilhado para manter os formulários nativos e os campos explícitos.
export function form(specs, initial = {}, {
  track = true
} = {}) {
  const node = el('form', { class: 'form' });
  const controls = {};
  const fields = el('fieldset', { class: 'form-fields' });
  node.append(fields);
  for (const spec of specs) {
    if (spec.heading) {
      fields.append(el('h3', {}, spec.heading));
      continue;
    }
    const id = 'field-' + ++fieldId;
    const attrs = {
      id,
      name: spec.name,
      required: !spec.optional,
      autocomplete: spec.autocomplete || 'off',
      disabled: spec.disabled,
      maxLength: spec.max,
      minLength: spec.minLength
    };
    let input;
    if (spec.options) {
      input = el('select', attrs, el('option', { value: '' }, spec.placeholder || 'Selecione…'), ...spec.options.map(([value, text]) => el('option', { value }, text)));
    } else if (spec.type === 'textarea')
      input = el('textarea', {
        ...attrs,
        rows: spec.rows || 4
      });
    else
      input = el('input', {
        ...attrs,
        type: spec.type || 'text',
        min: spec.min,
        max: spec.type === 'number' || spec.type === 'date' ? spec.maxValue : undefined,
        step: spec.step,
        spellcheck: spec.type !== 'email',
        placeholder: spec.placeholder
      });
    input.value = initial[spec.name] ?? '';
    if (spec.type === 'email')
      input.autocomplete = 'email';
    const hint = spec.hint || (spec.max ? `Até ${ spec.max.toLocaleString('pt-BR') } caracteres.` : '');
    const wrapper = el('div', { class: 'field' }, el('label', { htmlFor: id }, spec.label, spec.optional ? el('span', { class: 'optional' }, ' (opcional)') : null), input);
    if (hint) {
      wrapper.append(el('small', { id: id + '-hint' }, hint));
      input.setAttribute('aria-describedby', id + '-hint');
    }
    fields.append(wrapper);
    controls[spec.name] = input;
  }
  const error = el('div', {
    class: 'form-error',
    role: 'alert',
    hidden: true,
    tabIndex: -1
  });
  node.append(error);
  if (track)
    node.addEventListener('input', () => {
      state.dirty = true;
    });
  return {
    node,
    controls,
    fields,
    error,
    values() {
      const data = {};
      for (const spec of specs) {
        if (!spec.name || controls[spec.name].disabled)
          continue;
        const value = controls[spec.name].value;
        data[spec.name] = spec.type === 'number' ? value === '' ? null : Number(value) : spec.optional && value === '' ? null : spec.type === 'password' ? value : value.trim();
      }
      return data;
    }
  };
}
export function submit(f, text, task, {
  confirm: question,
  success,
  after
} = {}) {
  const btn = el('button', { type: 'submit' }, text);
  f.node.append(btn);
  f.node.addEventListener('submit', async event => {
    event.preventDefault();
    if (!f.node.reportValidity() || state.busy)
      return;
    if (question && !window.confirm(question))
      return;
    const values = f.values();
    f.error.hidden = true;
    f.fields.disabled = true;
    state.busy = true;
    btn.disabled = true;
    btn.textContent = 'Aguarde…';
    f.node.setAttribute('aria-busy', 'true');
    try {
      const data = await task(values, event.submitter);
      state.dirty = false;
      if (success)
        notice(success);
      if (after)
        await after(data);
    } catch (error) {
      f.error.textContent = error.message;
      f.error.hidden = false;
      f.error.focus();
    } finally {
      state.busy = false;
      btn.disabled = false;
      btn.textContent = text;
      f.fields.disabled = false;
      f.node.removeAttribute('aria-busy');
    }
  });
  return btn;
}
export function confirmAction(text, description, task, after) {
  return button(text, async event => {
    if (state.busy || !window.confirm(description))
      return;
    state.busy = true;
    event.currentTarget.disabled = true;
    try {
      const data = await task();
      state.dirty = false;
      if (after)
        await after(data);
    } catch (error) {
      notice(error.message, true);
    } finally {
      state.busy = false;
      event.target.disabled = false;
    }
  });
}
export function dialog(title, description, specs, task, after, initial = {}) {
  if (state.dirty && !window.confirm('Há alterações não salvas. Descartar e continuar?'))
    return;
  state.dirty = false;
  const f = form(specs, initial);
  const box = $('action-dialog');
  const cancel = button('Cancelar', () => {
    if (!state.busy && (!state.dirty || window.confirm('Descartar os campos desta ação?')))
      box.close();
  });
  $('dialog-body').replaceChildren(el('h2', { id: 'dialog-title' }, title), el('p', {}, description), f.node, cancel);
  submit(f, title, task, {
    after: async data => {
      box.close();
      if (after)
        await after(data);
    }
  });
  box.showModal();
  box.oncancel = event => {
    if (state.busy || state.dirty && !window.confirm('Descartar os campos desta ação?'))
      event.preventDefault();
  };
  box.onclose = () => {
    state.dirty = false;
    $('dialog-body').replaceChildren();
  };
}
export function table(headers, rows, caption) {
  const node = el('table', {}, el('caption', { class: 'sr-only' }, caption), el('thead', {}, el('tr', {}, ...headers.map(h => el('th', { scope: 'col' }, h)))), el('tbody', {}, ...rows.map(row => el('tr', {}, ...row.map((cell, i) => el('td', { 'data-label': headers[i] }, cell))))));
  return el('div', {
    class: 'table-scroll',
    tabIndex: 0,
    role: 'region',
    'aria-label': caption
  }, node);
}
export const reasonFields = [{
    name: 'reason',
    label: 'Motivo',
    type: 'textarea',
    max: 1500
  }];
export const temporaryField = {
  name: 'temporary_password',
  label: 'Senha temporária',
  type: 'password',
  minLength: 8,
  max: 128,
  autocomplete: 'new-password',
  hint: 'Entre 8 e 128 caracteres. Entregue pessoalmente; o sistema não envia email.'
};
export function can(permission) {
  return state.user?.permissions?.includes(permission) === true;
}
export function pathId(value) {
  return encodeURIComponent(value);
}
export function collectionFilters(specs, params) {
  const f = form(specs.map(s => ({
    ...s,
    optional: true
  })), Object.fromEntries(params), { track: false });
  const btn = el('button', {
    type: 'submit',
    class: 'secondary'
  }, 'Filtrar');
  f.node.classList.add('filters');
  f.node.append(btn);
  f.node.addEventListener('submit', event => {
    event.preventDefault();
    const query = new URLSearchParams();
    for (const [k, v] of Object.entries(f.values()))
      if (v !== null && v !== '')
        query.set(k, v);
    location.hash = location.hash.split('?')[0] + (query.size ? '?' + query : '');
  });
  return f.node;
}
export function pager(params, total) {
  const page = Number(params.get('page') || 1), per = 20;
  const href = next => {
    const p = new URLSearchParams(params);
    p.set('page', next);
    return location.hash.split('?')[0] + '?' + p;
  };
  return el('nav', {
    class: 'pagination',
    'aria-label': 'Paginação'
  }, page > 1 ? link('Anterior', href(page - 1), 'button secondary') : null, el('span', {}, `Página ${ page } · ${ total } registro(s)`), page * per < total ? link('Próxima', href(page + 1), 'button secondary') : null);
}
