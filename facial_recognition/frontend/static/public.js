import {
  el,
  heading,
  panel,
  link,
  info,
  badge,
  date,
  textSection,
  details,
  group,
  button,
  dialog,
  reasonFields,
  can,
  collectionFilters,
  pager,
  failure,
  pathId,
  notice,
  icon
} from './ui.js';
import { api } from './api.js';
import { query } from './admin.js';
import { photograph } from './photos.js';
const refresh = () => window.dispatchEvent(new Event('render-page'));
export async function publications(params, internal = false) {
  const box = el('section', {
    class: internal ? 'panel' : 'bulletin-list',
    'aria-label': 'Publicações'
  });
  const intro = internal ? heading('Publicações', 'Consulte as notícias autorizadas e gerencie retiradas.') : el('section', { class: 'public-intro' }, el('div', { class: 'public-masthead' }, photograph('amazonia', true), photograph('tucano')), el('div', { class: 'public-cover' }, el('div', { class: 'public-context' }, el('p', {}, 'Fauna, saúde e ambiente.'), el('p', {}, 'Um projeto acadêmico sobre investigação e divulgação responsável.'), el('small', {}, 'Fotografias ilustrativas de fauna e ecossistemas.'), link('Conheça o projeto', '#sobre-projeto')), el('div', { class: 'public-title' }, el('h1', {}, 'Investigar para preservar.'), el('p', {}, 'Da análise de uma amostra ao conhecimento compartilhado. Acompanhe as publicações autorizadas do laboratório.'), el('a', {
    class: 'button',
    href: '#publicacoes'
  }, 'Explorar publicações', icon('arrow')))));
  const filterSpecs = [{
      name: 'search',
      label: 'Buscar publicação'
    }];
  if (internal)
    filterSpecs.push({
      name: 'status',
      label: 'Situação',
      options: [
        [
          'PUBLISHED',
          'Publicada'
        ],
        [
          'WITHDRAWN',
          'Retirada'
        ]
      ]
    });
  try {
    const data = await api((internal ? '/publications' : '/public/publications') + '?' + query(params, internal ? [
      'search',
      'status'
    ] : ['search']), 'GET', null, { private: internal });
    box.append(data.items.length ? el('div', {}, ...data.items.map(p => el('article', { class: 'news-item' }, el('div', { class: 'news-meta' }, badge(p.risk_category), el('time', { dateTime: p.published_at }, date(p.published_at)), internal ? badge(p.status) : null), el('h2', {}, link(p.title, (internal ? '#/publicacoes/' : '#/noticias/') + pathId(p.id))), p.subtitle ? el('p', {}, p.subtitle) : null, link('Ler publicação', (internal ? '#/publicacoes/' : '#/noticias/') + pathId(p.id))))) : info('Nenhuma publicação encontrada', 'Quando houver notícias autorizadas, elas aparecerão nesta área.'), pager(params, data.total));
  } catch (error) {
    box.append(failure(error, refresh));
  }
  return [
    intro,
    el('section', {
      id: 'publicacoes',
      class: 'publication-search'
    }, internal ? null : el('h2', {}, 'Publicações do laboratório'), collectionFilters(filterSpecs, params)),
    box,
    !internal ? el('section', {
      class: 'public-about',
      id: 'sobre-projeto',
      tabIndex: -1
    }, el('h2', {}, 'Pesquisa com propósito.'), el('div', {}, el('p', {}, 'Investigar, revisar e decidir o que compartilhar. Este laboratório fictício acompanha cada etapa da pesquisa, preservando os registros e os limites de acesso.'), el('p', {}, 'As notícias desta página passam por autorização. Relatórios, dados da equipe e informações reservadas permanecem na área institucional.'), el('a', {
      href: '#/login',
      class: 'button secondary'
    }, 'Acessar o laboratório', icon('arrow')))) : null,
    !internal ? el('section', {
      class: 'public-landscapes', 'aria-label': 'Ecossistemas brasileiros · fotografias ilustrativas'
    }, photograph('anavilhanas'), photograph('mata-atlantica')) : null
  ];
}
export async function publicationDetail(id, internal = false) {
  const p = await api((internal ? '/publications/' : '/public/publications/') + pathId(id), 'GET', null, { private: internal });
  const controls = group();
  if (internal && can('publications.publish') && p.status === 'PUBLISHED')
    controls.append(button('Retirar publicação', () => dialog('Retirar publicação', 'A notícia deixará de ser exibida ao público. Não poderá ser editada ou republicada. O motivo será reservado ao N3.', reasonFields, data => api('/publications/' + pathId(id) + '/withdraw', 'POST', data), () => {
      notice('Publicação retirada.');
      refresh();
    }), 'danger'));
  return [
    link('Voltar às publicações', internal ? '#/publicacoes' : '#/noticias', 'back-link'),
    el('article', { class: 'news-detail' }, heading(p.title, p.subtitle), el('div', { class: 'news-meta' }, badge(p.risk_category), el('time', { dateTime: p.published_at }, 'Publicado em ' + date(p.published_at)), internal ? badge(p.status) : null), el('p', { class: 'prose news-body' }, p.body)),
    internal ? panel(details([
      [
        'Situação',
        p.status === 'WITHDRAWN' ? 'Retirada' : 'Publicada'
      ],
      [
        'Retirada em',
        date(p.withdrawn_at)
      ]
    ]), p.withdrawal_reason ? textSection('Motivo reservado da retirada', p.withdrawal_reason) : null, controls) : null
  ];
}
