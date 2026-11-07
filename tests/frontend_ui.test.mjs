/** Contratos DOM isolados; não substituem teste visual, leitor de tela ou motores reais. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { beforeEach, test } from 'node:test';

// Modelo mínimo das APIs DOM usadas pelos formulários, sem dependências de execução.
class Element extends EventTarget {
  constructor(tag = '#text', content = '') {
    super();
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.parentElement = null;
    this.attributes = new Map();
    this.style = {};
    this.id = this.name = this.className = this.type = this.htmlFor = '';
    this._value = tag === 'select' ? null : '';
    this.content = content;
    this.hidden = false;
    this._disabled = this._required = false;
    this.observers = [];
    this.rect = { left: 20, top: 100, bottom: 148, width: 280 };
    this.classList = {
      add: name => this.classList.toggle(name, true),
      toggle: (name, value) => {
        const classes = new Set(this.className.split(' ').filter(Boolean));
        const on = value ?? !classes.has(name);
        if (on) classes.add(name); else classes.delete(name);
        this.className = [...classes].join(' ');
      }
    };
  }
  get options() { return this.children.filter(child => child.tagName === 'OPTION'); }
  get selectedIndex() { return this._value === null ? 0 : this.options.findIndex(option => option.value === this._value); }
  get value() { return this.tagName === 'SELECT' ? this.options[this.selectedIndex]?.value ?? '' : this._value; }
  set value(value) { this._value = String(value); }
  get disabled() { return this._disabled; }
  set disabled(value) { this._disabled = value; this.changed('disabled'); }
  get required() { return this._required; }
  set required(value) { this._required = value; this.changed('required'); }
  get form() { return this.closest('form'); }
  get textContent() { return this.content + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this.content = String(value); this.children = []; }
  changed(name) { for (const observer of this.observers) if (observer.attributes.includes(name)) queueMicrotask(observer.callback); }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  removeAttribute(name) { this.attributes.delete(name); }
  append(...nodes) {
    for (const node of nodes) {
      assert.ok(node !== this && !node.contains(this), 'Hierarquia DOM inválida');
      if (node.parentElement)
        node.parentElement.children.splice(node.parentElement.children.indexOf(node), 1);
      this.children.push(node);
      node.parentElement = this;
    }
  }
  replaceWith(node) {
    const parent = this.parentElement;
    assert.ok(parent && !node.contains(parent), 'Substituição DOM inválida');
    parent.children.splice(parent.children.indexOf(this), 1, node);
    node.parentElement = parent;
    this.parentElement = null;
  }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  closest(tag) { return this.tagName === tag.toUpperCase() ? this : this.parentElement?.closest(tag) ?? null; }
  matches(selector) {
    if (selector === ':disabled') return this.disabled || !!this.parentElement?.matches(':disabled');
    if (selector === ':invalid') return !this.matches(':disabled') && this.required && !this.value;
    return this.tagName === selector.toUpperCase();
  }
  querySelector(selector) {
    return descendants(this).find(node => selector === 'label' ? node.tagName === 'LABEL' :
      ['INPUT', 'SELECT', 'TEXTAREA'].includes(node.tagName) && node.matches(':invalid')) ?? null;
  }
  focus() {
    const previous = document.activeElement;
    document.activeElement = this;
    if (previous !== this) {
      previous?.dispatchEvent(new Event('blur'));
      this.dispatchEvent(new Event('focus'));
    }
  }
  click() { if (!this.matches(':disabled')) this.dispatchEvent(new Event('click')); }
  getBoundingClientRect() { return this.rect; }
  scrollIntoView() { this.scrolled = true; }
  showPopover() { this.popoverOpen = true; }
  hidePopover() {
    const event = new Event('beforetoggle');
    Object.defineProperty(event, 'newState', { value: 'closed' });
    this.dispatchEvent(event);
    this.popoverOpen = false;
  }
  dispatchEvent(event) {
    const result = super.dispatchEvent(event);
    if (event.bubbles) this.parentElement?.dispatchEvent(event);
    return result;
  }
  reportValidity() {
    const invalid = descendants(this).filter(node => ['INPUT', 'SELECT', 'TEXTAREA'].includes(node.tagName) && node.matches(':invalid'));
    const unhandled = invalid.filter(node => node.dispatchEvent(new Event('invalid', { cancelable: true })));
    queueMicrotask(() => unhandled[0]?.focus());
    return invalid.length === 0;
  }
  reset() {
    descendants(this).filter(node => node.tagName === 'SELECT').forEach(node => { node.value = ''; });
    this.dispatchEvent(new Event('reset'));
  }
}
function descendants(node) { return node.children.flatMap(child => [child, ...descendants(child)]); }
globalThis.Node = globalThis.HTMLElement = Element;
globalThis.MutationObserver = class {
  constructor(callback) { this.callback = callback; }
  observe(node, options) { node.observers.push({ callback: this.callback, attributes: options.attributeFilter }); }
};
globalThis.document = {
  createElement: tag => new Element(tag),
  createTextNode: text => new Element('#text', text)
};
globalThis.window = new EventTarget();
Object.assign(window, { innerWidth: 390, innerHeight: 700 });
globalThis.location = { hash: '#/amostras' };
const source = readFileSync(new URL('../facial_recognition/frontend/static/ui.js', import.meta.url), 'utf8');
const { form, collectionFilters, pager, state } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const find = (node, className) => descendants(node).find(child => child.className.split(' ').includes(className));
function key(node, value, options = {}) {
  const event = new Event('keydown', { cancelable: true });
  for (const [name, property] of Object.entries({ key: value, ...options })) Object.defineProperty(event, name, { value: property });
  node.dispatchEvent(event);
  return event;
}
const choices = [['water', 'Água'], ['birds', 'Aves'], ['soil', 'Solo']];
beforeEach(() => { state.dirty = false; document.activeElement = null; window.innerWidth = 390; window.innerHeight = 700; });

test('seleção usa teclado sem alterar o valor até confirmar, e preserva input/change', () => {
  const f = form([{ name: 'material', label: 'Material', options: choices }]);
  const trigger = find(f.node, 'select-trigger');
  const native = f.controls.material;
  let changes = 0;
  native.addEventListener('change', () => changes++);
  trigger.focus();
  key(trigger, 'ArrowDown');
  key(trigger, 'ArrowDown');
  assert.equal(trigger.getAttribute('aria-expanded'), 'true');
  assert.equal(native.value, '');
  key(trigger, 'Enter');
  assert.deepEqual(f.values(), { material: 'water' });
  assert.equal(trigger.getAttribute('aria-expanded'), 'false');
  assert.equal(changes, 1);
  assert.equal(state.dirty, true);
  assert.equal(document.activeElement, trigger);
  assert.equal(find(f.node, 'select-menu').children[1].getAttribute('aria-selected'), 'true');
});

test('Escape cancela; End e Tab confirmam; busca reconhece acentos e letras repetidas', () => {
  const f = form([{ name: 'material', label: 'Material', options: choices }], { material: 'soil' });
  const trigger = find(f.node, 'select-trigger');
  key(trigger, 'Home');
  assert.equal(key(trigger, 'Escape').defaultPrevented, true);
  assert.equal(f.controls.material.value, 'soil');
  key(trigger, 'a');
  assert.match(trigger.getAttribute('aria-activedescendant'), /option-1$/);
  key(trigger, 'a');
  assert.match(trigger.getAttribute('aria-activedescendant'), /option-2$/);
  key(trigger, 'End');
  const tab = key(trigger, 'Tab');
  assert.equal(tab.defaultPrevented, false);
  assert.equal(f.controls.material.value, 'soil');
  assert.equal(trigger.getAttribute('aria-expanded'), 'false');
  assert.equal(state.dirty, false, 'Confirmar o mesmo valor não deve alterar o rascunho');
});

test('clique e bloqueio de fieldset preservam o contrato nativo', () => {
  const f = form([{ name: 'material', label: 'Material', options: choices }]);
  const trigger = find(f.node, 'select-trigger');
  f.fields.disabled = true;
  trigger.click();
  assert.equal(trigger.getAttribute('aria-expanded'), 'false');
  f.fields.disabled = false;
  trigger.click();
  find(f.node, 'select-menu').children[2].click();
  assert.equal(f.controls.material.value, 'birds');
  assert.equal(find(f.node, 'select-value').textContent, 'Aves');
  trigger.click();
  key(trigger, 'ArrowDown');
  find(f.node, 'select-menu').hidePopover();
  assert.equal(f.controls.material.value, 'soil', 'Clique externo confirma a opção em exploração');
});

test('required mostra erro no primeiro campo, disabled/required e reset são sincronizados', async () => {
  const f = form([{ name: 'material', label: 'Material', options: choices }, { name: 'other', label: 'Outro', options: choices }]);
  assert.equal(f.node.reportValidity(), false);
  await new Promise(resolve => setTimeout(resolve, 0));
  const trigger = find(f.node, 'select-trigger');
  assert.equal(document.activeElement, trigger);
  assert.equal(trigger.getAttribute('aria-invalid'), 'true');
  f.controls.material.value = 'water';
  f.controls.material.dispatchEvent(new Event('change'));
  assert.equal(trigger.getAttribute('aria-invalid'), null);
  f.controls.material.disabled = true;
  f.controls.material.required = false;
  await Promise.resolve();
  assert.equal(trigger.disabled, true);
  assert.equal(trigger.getAttribute('aria-required'), 'false');
  assert.equal('material' in f.values(), false);
  f.controls.material.disabled = false;
  f.node.reset();
  await Promise.resolve();
  assert.equal(find(f.node, 'select-value').textContent, 'Selecione…');
});

test('primeiro menu obrigatório mantém foco após a validação nativa de um campo posterior', async () => {
  const f = form([{ name: 'material', label: 'Material', options: choices }, { name: 'password', label: 'Senha', type: 'password' }]);
  assert.equal(f.node.reportValidity(), false);
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(document.activeElement.id, find(f.node, 'select-trigger').id);
});

test('foco automático ou programático no select nativo é encaminhado ao controle visível', () => {
  const f = form([{ name: 'material', label: 'Material', options: choices }]);
  f.controls.material.focus();
  assert.equal(document.activeElement.id, find(f.node, 'select-trigger').id);
});

test('popup abre para cima e fica dentro da largura móvel; scroll externo fecha', () => {
  const f = form([{ name: 'material', label: 'Material', options: choices }]);
  const trigger = find(f.node, 'select-trigger');
  trigger.rect = { left: 250, top: 620, bottom: 668, width: 250 };
  trigger.click();
  const menu = find(f.node, 'select-menu');
  assert.match(menu.className, /opens-upwards/);
  assert.ok(Number.parseFloat(menu.style.left) + Number.parseFloat(menu.style.width) <= window.innerWidth - 8);
  assert.ok(Number.parseFloat(menu.style.maxHeight) <= 320);
  window.dispatchEvent(new Event('scroll'));
  assert.equal(trigger.getAttribute('aria-expanded'), 'false');
  assert.equal(menu.popoverOpen, false);
});

test('Mostrar/Ocultar mantém senha intacta e não marca o formulário como alterado', () => {
  const secret = '  Senha!Com espaços  ';
  const f = form([{ name: 'password', label: 'Senha', type: 'password' }], { password: secret });
  const toggle = find(f.node, 'password-toggle');
  toggle.click();
  assert.equal(f.controls.password.type, 'text');
  assert.equal(toggle.getAttribute('aria-pressed'), 'true');
  assert.equal(f.values().password, secret);
  assert.equal(state.dirty, false);
  toggle.click();
  assert.equal(f.controls.password.type, 'password');
});

test('filtros têm opção abrangente e ação de limpeza, sem marcar rascunho', () => {
  location.hash = '#/amostras?status=ACTIVE&page=2';
  const filters = collectionFilters([{ name: 'status', label: 'Situação', options: [['ACTIVE', 'Ativa']] }], new URLSearchParams('status=ACTIVE'));
  const clear = descendants(filters).find(node => node.tagName === 'BUTTON' && node.textContent === 'Limpar filtros');
  assert.ok(clear);
  clear.click();
  assert.equal(location.hash, '#/amostras');
  assert.equal(state.dirty, false);
  assert.match(pager(new URLSearchParams(), 1).textContent, /1 registro$/);
});

test('sem Popover API, o select nativo continua visível e utilizável', () => {
  const show = Element.prototype.showPopover;
  try {
    Element.prototype.showPopover = undefined;
    const f = form([{ name: 'material', label: 'Material', options: choices }], { material: 'water' });
    assert.equal(find(f.node, 'select-trigger'), undefined);
    assert.equal(f.controls.material.getAttribute('aria-hidden'), null);
    assert.equal(f.values().material, 'water');
  } finally { Element.prototype.showPopover = show; }
});
