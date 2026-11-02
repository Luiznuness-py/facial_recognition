import {
  state,
  el,
  heading,
  panel,
  form,
  submit,
  info,
  link,
  button,
  group,
  badge,
  date,
  percent,
  details,
  textSection,
  table,
  dialog,
  confirmAction,
  reasonFields,
  can,
  pathId,
  collectionFilters,
  pager,
  failure,
  notice
} from './ui.js';
import {
  api,
  allPages,
  pendingMessage
} from './api.js';
import { query } from './admin.js';
const refresh = () => window.dispatchEvent(new Event('render-page'));
const agentFields = [
  {
    name: 'provisional_label',
    label: 'Identificação provisória',
    max: 120
  },
  {
    name: 'material_type',
    label: 'Tipo de material',
    max: 100
  },
  {
    name: 'collection_location',
    label: 'Local da coleta',
    max: 255
  },
  {
    name: 'collected_on',
    label: 'Data da coleta',
    type: 'date',
    maxValue: new Date().toLocaleDateString('en-CA')
  },
  {
    name: 'initial_observations',
    label: 'Observações iniciais',
    type: 'textarea',
    max: 1500
  },
  {
    name: 'investigation_reason',
    label: 'Motivo da investigação',
    type: 'textarea',
    max: 1500
  },
  {
    name: 'known_information',
    label: 'Informações já conhecidas',
    type: 'textarea',
    max: 1500,
    optional: true
  }
];
const analysisFields = [
  {
    name: 'assessments_performed',
    label: 'Avaliações realizadas',
    type: 'textarea',
    max: 1500
  },
  {
    name: 'observed_results',
    label: 'Resultados observados',
    type: 'textarea',
    max: 5000
  },
  {
    name: 'technical_opinion',
    label: 'Parecer técnico',
    type: 'textarea',
    max: 5000
  },
  {
    name: 'recommendation',
    label: 'Recomendação',
    type: 'textarea',
    max: 5000
  },
  {
    name: 'estimated_risk_percentage',
    label: 'Risco estimado (%)',
    type: 'number',
    min: 0,
    maxValue: 100,
    step: '0.01',
    optional: true,
    hint: 'Deixe vazio quando não determinado. De 0 a 100, com até duas casas decimais.'
  }
];
const statuses = [
  [
    'OPEN',
    'Em preparação'
  ],
  [
    'IN_REVIEW',
    'Em revisão'
  ],
  [
    'RETURNED',
    'Devolvida'
  ],
  [
    'REPORTED',
    'Aguardando N3'
  ],
  [
    'PUBLISHED',
    'Publicada'
  ],
  [
    'CLOSED',
    'Encerrada'
  ]
];
export async function agents(params, review = false) {
  const box = panel();
  const actions = can('agents.create') ? link('Cadastrar amostra', '#/amostras/nova', 'button') : null;
  const result = [
    heading(review ? 'Revisões da equipe' : 'Amostras', review ? 'Selecione uma amostra para consultar suas investigações em revisão.' : 'Cadastros e investigações disponíveis para o seu acesso.', actions),
    collectionFilters([
      {
        name: 'search',
        label: 'Buscar amostra'
      },
      {
        name: 'status',
        label: 'Situação da amostra',
        options: [
          [
            'ACTIVE',
            'Ativa'
          ],
          [
            'INACTIVE',
            'Inativa'
          ]
        ]
      }
    ], params),
    box
  ];
  try {
    const data = await api('/biological-agents?' + query(params, [
      'search',
      'status'
    ]));
    box.append(data.items.length ? table([
      'Amostra',
      'Material',
      'Coleta',
      'Situação',
      'Investigações'
    ], data.items.map(a => [
      el('div', {}, el('strong', {}, a.provisional_label), el('small', {}, a.code)),
      a.material_type,
      date(a.collected_on),
      badge(a.status),
      link(review ? 'Ver revisões' : 'Abrir amostra', '#/amostras/' + pathId(a.id) + (review ? '?status=IN_REVIEW' : ''))
    ]), review ? 'Amostras para revisão' : 'Amostras autorizadas') : info('Nenhuma amostra encontrada', can('agents.create') ? 'Cadastre uma amostra para iniciar a primeira investigação.' : 'Ajuste os filtros ou aguarde uma investigação autorizada.'), pager(params, data.total));
  } catch (error) {
    box.replaceChildren(failure(error, refresh));
  }
  return result;
}
export function newAgent() {
  const f = form(agentFields);
  submit(f, 'Cadastrar e iniciar investigação', data => api('/biological-agents', 'POST', data), {
    after: data => {
      location.hash = '#/investigacoes/' + pathId(data.validation.id);
      notice('Amostra cadastrada e primeira investigação criada.');
    }
  });
  const pending = pendingMessage('/biological-agents', 'POST');
  return [
    heading('Cadastrar amostra', 'Não é necessário conhecer o nome científico. O cadastro cria a primeira investigação sob sua responsabilidade.'),
    pending ? info('Pendente no backend', pending) : null,
    panel(f.node)
  ];
}
export async function agentDetail(id, params) {
  const target = '/biological-agents/' + pathId(id);
  const a = await api(target);
  const box = panel();
  const actions = group();
  let cards;
  try {
    cards = await api(target + '/validations?' + query(params, ['status']));
  } catch (error) {
    box.append(failure(error, refresh));
  }
  if (can('agents.update') && (state.user.role === 'N2' || a.created_by === state.user.id) && a.can_edit === true)
    actions.append(button('Corrigir cadastro', () => dialog('Salvar cadastro', 'A correção só é permitida antes da primeira entrega da amostra. O servidor verifica essa condição.', agentFields, data => api(target, 'PATCH', data), refresh, a)));
  if (can('agents.manage'))
    actions.append(confirmAction(a.status === 'ACTIVE' ? 'Inativar amostra' : 'Reativar amostra', 'Alterar a situação da amostra? Inativação exige ausência de investigação em andamento e não retira notícias.', () => api(target + '/status', 'PATCH', { status: a.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE' }), refresh));
  if (can('validations.create') && a.status === 'ACTIVE')
    actions.append(button('Nova investigação', () => chooseResponsible(a)));
  if (cards)
    box.append(el('h2', {}, 'Investigações'), collectionFilters([{
        name: 'status',
        label: 'Situação da investigação',
        options: statuses
      }], params), cards.items.length ? el('div', { class: 'investigations' }, ...cards.items.map(v => el('article', { class: 'investigation' }, badge(v.status), el('h3', {}, 'Investigação de ' + date(v.created_at)), el('p', {}, 'Responsável: ' + v.responsible.name), v.return_reason ? info('Correção solicitada', v.return_reason) : null, v.closure_reason ? info('Encerramento', v.closure_reason) : null, v.new_validation_request ? info('Pedido de nova investigação', v.new_validation_request.reason) : null, link(v.can_edit ? 'Continuar análise' : 'Consultar investigação', '#/investigacoes/' + pathId(v.id), 'button secondary')))) : info('Nenhuma investigação neste filtro', 'Somente investigações autorizadas são exibidas.'), pager(params, cards.total));
  return [
    heading(a.provisional_label, a.code, link('Voltar às amostras', '#/amostras', 'button secondary')),
    panel(badge(a.status), details([
      [
        'Material',
        a.material_type
      ],
      [
        'Local da coleta',
        a.collection_location
      ],
      [
        'Data da coleta',
        date(a.collected_on)
      ]
    ]), textSection('Observações iniciais', a.initial_observations), textSection('Motivo da investigação', a.investigation_reason), textSection('Informações já conhecidas', a.known_information), actions),
    box
  ];
}
export async function chooseResponsible(agent, validationId = null, request = null) {
  try {
    const candidates = await allPages('/biological-agents/' + pathId(agent.id) + '/responsible-candidates');
    if (!candidates.length) {
      notice('Não há N1 ativo disponível na equipe.', true);
      return;
    }
    const specs = [{
        name: 'responsible_user_id',
        label: 'Responsável N1',
        options: candidates.map(c => [
          c.id,
          c.name
        ])
      }];
    if (!validationId && !request)
      specs.push({
        name: 'request_vault_id',
        label: 'Identificador do pedido N3',
        optional: true,
        hint: 'Informe o identificador do pedido pendente, se houver. Use preferencialmente o acesso em Enviadas ao N3.'
      });
    dialog(validationId ? 'Trocar responsável' : 'Abrir investigação', validationId ? 'O responsável anterior passará a colaborador de leitura.' : request ? 'Atender ao pedido do N3: ' + request.reason : 'A amostra deve estar ativa e não pode ter outra investigação em andamento.', specs, data => {
      if (request)
        data.request_vault_id = request.vault_id;
      else if (!data.request_vault_id)
        delete data.request_vault_id;
      return api(validationId ? '/validations/' + pathId(validationId) + '/responsible' : '/biological-agents/' + pathId(agent.id) + '/validations', validationId ? 'PATCH' : 'POST', data);
    }, data => {
      if (validationId)
        refresh();
      else {
        location.hash = '#/investigacoes/' + pathId(data.id);
        notice('Investigação criada.');
      }
    });
  } catch (error) {
    notice(error.message, true);
  }
}
function analysisRead(a) {
  return el('div', {}, ...analysisFields.filter(s => s.type === 'textarea').map(s => textSection(s.label, a[s.name])), details([[
      'Risco estimado',
      percent(a.estimated_risk_percentage)
    ]]));
}
function submissionHistory(v) {
  return panel(el('h2', {}, 'Entregas preservadas'), v.submissions?.length ? el('div', {}, ...v.submissions.map(s => el('details', { class: 'submission' }, el('summary', {}, 'Entrega ' + s.submission_number + ' · ' + date(s.submitted_at)), analysisRead(s), textSection('Participantes nesta entrega', (s.participants_snapshot || []).map(p => p.name).join(', ')), s.return_reason ? info('Motivo da devolução', s.return_reason) : null))) : el('p', {}, 'Nenhuma entrega enviada. O rascunho ainda pode ser preparado.'));
}
export async function validationDetail(id) {
  const target = '/validations/' + pathId(id);
  const v = await api(target);
  const responsible = v.responsible.id === state.user.id;
  const open = [
    'OPEN',
    'RETURNED'
  ].includes(v.status);
  const edit = can('analyses.write') && responsible && open;
  const analysis = panel(el('h2', {}, edit ? 'Preparar análise' : 'Análise da investigação'));
  if (v.new_validation_request)
    analysis.append(info('Pedido do N3', v.new_validation_request.reason));
  const lastReturn = v.submissions?.filter(s => s.return_reason).at(-1)?.return_reason;
  if (v.status === 'RETURNED' && lastReturn)
    analysis.append(info('Correção solicitada', lastReturn));
  if (v.closure_reason)
    analysis.append(info('Motivo do encerramento', v.closure_reason));
  if (edit) {
    const f = form(analysisFields.map(s => ({
      ...s,
      optional: true
    })), v);
    const save = submit(f, 'Salvar rascunho', async data => {
      await api(target + '/analysis', 'PATCH', data);
    }, { success: 'Rascunho salvo no servidor.' });
    const send = el('button', {
      type: 'submit',
      class: 'secondary'
    }, 'Salvar e enviar ao N2');
    f.node.append(send);
    // O envio só ocorre após persistir o formulário; falha mantém os campos e não avança.
    send.addEventListener('click', async event => {
      event.preventDefault();
      if (state.busy)
        return;
      for (const s of analysisFields.filter(s => s.type === 'textarea'))
        if (!f.controls[s.name].value.trim()) {
          f.error.textContent = 'Preencha avaliações, resultados, parecer e recomendação antes de enviar.';
          f.error.hidden = false;
          f.controls[s.name].focus();
          return;
        }
      if (!f.node.reportValidity() || !window.confirm('Salvar e enviar a análise ao N2? Uma entrega será preservada e a edição ficará bloqueada.'))
        return;
      const values = f.values();
      f.fields.disabled = true;
      let saved = false;
      state.busy = true;
      send.disabled = true;
      save.disabled = true;
      f.error.hidden = true;
      try {
        await api(target + '/analysis', 'PATCH', values);
        saved = true;
        state.dirty = false;
        await api(target + '/submit', 'POST');
        notice('Análise entregue ao N2.');
        refresh();
      } catch (error) {
        f.error.textContent = (saved ? 'O rascunho está salvo, mas o envio não foi concluído. ' : '') + error.message;
        f.error.hidden = false;
        f.error.focus();
      } finally {
        state.busy = false;
        send.disabled = false;
        save.disabled = false;
        f.fields.disabled = false;
      }
    });
    analysis.append(f.node);
  } else
    analysis.append(info('Somente leitura', state.user.role === 'N1' && !responsible ? 'Você participa como colaborador. Apenas o responsável pode editar e enviar.' : 'O conteúdo está preservado nesta etapa.'), analysisRead(v));
  const participants = panel(el('h2', {}, 'Equipe da investigação'), details([[
      'Responsável',
      v.responsible.name
    ]]));
  const list = el('ul', { class: 'participant-list' });
  for (const p of v.participants || []) {
    const row = el('li', {}, el('span', {}, p.name + ' · Leitura'));
    if (open && can('validations.participants.manage'))
      row.append(confirmAction('Remover', 'Remover o acesso atual deste colaborador? As entregas anteriores serão preservadas.', () => api(target + '/participants/' + pathId(p.user_id), 'DELETE'), refresh));
    list.append(row);
  }
  participants.append(list);
  if (open && can('validations.share') && (responsible || state.user.role === 'N2'))
    participants.append(button('Adicionar colaborador', async () => {
      try {
        const candidates = await allPages(target + '/participant-candidates');
        if (!candidates.length) {
          notice('Nenhum colaborador elegível disponível.', true);
          return;
        }
        dialog('Adicionar colaborador', 'O acesso será somente de leitura nesta investigação.', [{
            name: 'user_id',
            label: 'Colaborador N1',
            options: candidates.map(c => [
              c.id,
              c.name
            ])
          }], data => api(target + '/participants', 'POST', data), refresh);
      } catch (error) {
        notice(error.message, true);
      }
    }));
  if (open && can('validations.participants.manage'))
    participants.append(button('Trocar responsável', () => chooseResponsible(v.agent, v.id)));
  const actions = group();
  if (v.status === 'IN_REVIEW' && can('validations.review'))
    actions.append(button('Devolver para correção', () => dialog('Devolver análise', 'Explique o que precisa ser corrigido. O motivo será visível à equipe autorizada.', reasonFields, data => api(target + '/return', 'POST', data), refresh)), button('Encerrar investigação', () => dialog('Encerrar investigação', 'A tarefa será encerrada sem envio ao N3. O motivo ficará disponível à equipe.', reasonFields, data => api(target + '/close', 'POST', data), refresh), 'danger'));
  if (v.status === 'IN_REVIEW' && can('reports.send'))
    actions.append(link('Preparar envio ao N3', '#/investigacoes/' + pathId(id) + '/envio', 'button'));
  return [
    heading(v.agent.provisional_label, 'Investigação · ' + v.agent.code, link('Ver amostra', '#/amostras/' + pathId(v.agent.id), 'button secondary')),
    el('div', { class: 'record-status' }, badge(v.status), el('span', {}, 'Responsável: ' + v.responsible.name)),
    analysis,
    actions,
    participants,
    submissionHistory(v)
  ];
}
export async function reportForm(id) {
  const v = await api('/validations/' + pathId(id));
  if (v.status !== 'IN_REVIEW')
    return [
      heading('Envio ao N3'),
      info('Situação incompatível', 'Apenas uma investigação em revisão pode ser enviada ao N3.'),
      link('Voltar à investigação', '#/investigacoes/' + pathId(id))
    ];
  const f = form([
    { heading: 'Relatório interno' },
    {
      name: 'title',
      label: 'Título interno',
      max: 120
    },
    {
      name: 'final_conclusion',
      label: 'Conclusão final',
      type: 'textarea',
      max: 5000
    },
    {
      name: 'final_risk_percentage',
      label: 'Percentual final de risco',
      type: 'number',
      min: 0,
      maxValue: 100,
      step: '0.01'
    },
    { heading: 'Notícia preparada para divulgação' },
    {
      name: 'public_title',
      label: 'Título público',
      max: 120
    },
    {
      name: 'public_subtitle',
      label: 'Subtítulo',
      max: 200,
      optional: true
    },
    {
      name: 'public_risk_category',
      label: 'Categoria pública de risco',
      options: [
        [
          'LOW',
          'Baixo'
        ],
        [
          'MODERATE',
          'Moderado'
        ],
        [
          'HIGH',
          'Alto'
        ]
      ],
      hint: 'Escolha editorial do N2. Não é calculada automaticamente a partir do percentual.'
    },
    {
      name: 'public_body',
      label: 'Texto da notícia',
      type: 'textarea',
      max: 5000
    }
  ]);
  const preview = panel(el('h2', {}, 'Prévia pública'), el('p', {}, 'Preencha a ficha para visualizar a notícia. Não inclua nomes da equipe, local exato ou conteúdo reservado.'));
  const update = () => {
    const d = f.values();
    preview.replaceChildren(...[
      el('h2', {}, 'Prévia pública'),
      el('h3', {}, d.public_title || 'Título da notícia'),
      d.public_subtitle ? el('p', {}, d.public_subtitle) : null,
      d.public_risk_category ? badge(d.public_risk_category) : null,
      el('p', { class: 'prose' }, d.public_body || 'Texto da notícia')
    ].filter(Boolean));
  };
  f.node.addEventListener('input', update);
  f.node.addEventListener('change', update);
  submit(f, 'Selar e enviar ao N3', data => api('/validations/' + pathId(id) + '/report/send', 'POST', data), {
    confirm: 'Enviar definitivamente ao cofre? Relatório e notícia serão selados. Você não poderá reabrir ou editar esse conteúdo.',
    after: data => {
      f.node.reset();
      location.hash = '#/envios';
      notice('Envio concluído. Protocolo: ' + data.protocol);
    }
  });
  return [
    heading('Preparar envio ao N3', v.agent.provisional_label, link('Voltar', '#/investigacoes/' + pathId(id), 'button secondary')),
    info('Conteúdo selado', 'Após o envio, o N2 acompanha somente título, amostra, protocolo e situação da decisão.'),
    panel(f.node),
    preview
  ];
}
export async function reports(params) {
  const box = panel();
  try {
    const data = await api('/reports/sent?' + query(params, [
      'search',
      'decision_status'
    ]));
    box.append(data.items.length ? el('div', { class: 'report-list' }, ...data.items.map(r => el('article', { class: 'report-item' }, badge(r.decision_status), el('h2', {}, r.title), el('p', {}, r.agent.provisional_label), details([[
        'Protocolo',
        r.protocol
      ]]), r.new_validation_request ? info('Pedido de nova investigação', r.new_validation_request.reason) : null, r.new_validation_request && !r.new_validation_request.fulfilled_validation_id ? button('Atender pedido do N3', () => chooseResponsible(r.agent, null, {
      vault_id: r.vault_id,
      reason: r.new_validation_request.reason
    })) : null, r.new_validation_request?.fulfilled_validation_id ? link('Consultar nova investigação', '#/investigacoes/' + pathId(r.new_validation_request.fulfilled_validation_id)) : null, link('Consultar amostra', '#/amostras/' + pathId(r.agent.id))))) : info('Nenhum envio encontrado', 'Os envios concluídos ao N3 aparecerão aqui.'), pager(params, data.total));
  } catch (error) {
    box.replaceChildren(failure(error, refresh));
  }
  return [
    heading('Enviadas ao N3', 'Acompanhe decisões e pedidos sem acessar o conteúdo selado.'),
    collectionFilters([
      {
        name: 'search',
        label: 'Buscar envio'
      },
      {
        name: 'decision_status',
        label: 'Decisão',
        options: [
          [
            'WAITING_N3',
            'Aguardando N3'
          ],
          [
            'PUBLISHED',
            'Publicada'
          ],
          [
            'RESTRICTED',
            'Sigilo'
          ],
          [
            'NEW_VALIDATION_REQUESTED',
            'Nova investigação'
          ],
          [
            'WITHDRAWN',
            'Retirada'
          ]
        ]
      }
    ], params),
    box
  ];
}
export async function vault(params) {
  const box = panel();
  try {
    const data = await api('/vault/dossiers?' + query(params, [
      'protocol',
      'decision_status'
    ]));
    box.append(data.items.length ? table([
      'Dossiê',
      'Protocolo',
      'Recebido em',
      'Decisão',
      'Conteúdo'
    ], data.items.map(d => [
      el('div', {}, d.title, el('small', {}, d.agent.provisional_label)),
      d.protocol,
      date(d.sent_at),
      badge(d.decision_status),
      link('Abrir dossiê', '#/cofre/' + pathId(d.id))
    ]), 'Dossiês do cofre') : info('Cofre sem resultados', 'Não há dossiês neste filtro.'), pager(params, data.total));
  } catch (error) {
    box.replaceChildren(failure(error, refresh));
  }
  return [
    heading('Cofre de dossiês', 'Relatórios preservados para decisão da autoridade N3.'),
    collectionFilters([
      {
        name: 'protocol',
        label: 'Protocolo'
      },
      {
        name: 'decision_status',
        label: 'Decisão',
        options: [
          [
            'WAITING_N3',
            'Aguardando decisão'
          ],
          [
            'PUBLISHED',
            'Publicada'
          ],
          [
            'RESTRICTED',
            'Sigilo'
          ],
          [
            'NEW_VALIDATION_REQUESTED',
            'Nova investigação'
          ]
        ]
      }
    ], params),
    box
  ];
}
export async function dossier(id) {
  const target = '/vault/dossiers/' + pathId(id), d = await api(target);
  const actions = group();
  if (d.decision_status === 'WAITING_N3') {
    if (can('publications.publish'))
      actions.append(confirmAction('Autorizar publicação', 'Publicar exatamente a notícia preparada? A decisão é final e o relatório interno permanecerá reservado.', () => api(target + '/publish', 'POST'), () => {
        notice('Notícia publicada.');
        refresh();
      }));
    if (can('vault.decide'))
      actions.append(button('Manter em sigilo', () => dialog('Manter em sigilo', 'A investigação será encerrada. Este motivo será consultado somente pelo N3.', reasonFields, data => api(target + '/keep-restricted', 'POST', data), refresh)), button('Solicitar outra investigação', () => dialog('Solicitar outra investigação', 'A investigação atual será encerrada. O motivo será enviado ao N2 e à equipe da próxima tarefa.', reasonFields, data => api(target + '/request-validation', 'POST', data), refresh)));
  }
  return [
    heading(d.title, d.protocol, link('Voltar ao cofre', '#/cofre', 'button secondary')),
    panel(badge(d.decision_status), details([
      [
        'Amostra',
        d.agent.provisional_label
      ],
      [
        'Enviado em',
        date(d.sent_at)
      ],
      [
        'Decidido em',
        date(d.decided_at)
      ]
    ])),
    panel(el('h2', {}, 'Entrega científica preservada'), analysisRead(d.submission), textSection('Equipe da entrega', (d.submission.participants_snapshot || []).map(p => p.name).join(', '))),
    panel(el('h2', {}, 'Relatório interno'), textSection('Conclusão final', d.final_conclusion), details([[
        'Percentual final de risco',
        percent(d.final_risk_percentage)
      ]])),
    panel(el('h2', {}, 'Notícia preparada'), el('h3', {}, d.public_title), d.public_subtitle ? el('p', {}, d.public_subtitle) : null, badge(d.public_risk_category), el('p', { class: 'prose' }, d.public_body)),
    d.restricted_reason ? info('Motivo reservado do sigilo', d.restricted_reason) : null,
    d.new_validation_request_reason ? info('Pedido de nova investigação', d.new_validation_request_reason) : null,
    actions
  ];
}
