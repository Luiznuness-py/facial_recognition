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
  details,
  table,
  dialog,
  confirmAction,
  reasonFields,
  temporaryField,
  can,
  pathId,
  collectionFilters,
  pager,
  failure,
  notice
} from './ui.js';
import {
  api,
  allPages
} from './api.js';
const refresh = () => window.dispatchEvent(new Event('render-page'));
export async function accountForm(initial = {}, edit = false) {
  const teams = await allPages('/teams');
  const specs = [
    {
      name: 'name',
      label: 'Nome completo'
    },
    {
      name: 'email',
      label: 'Email institucional',
      type: 'email'
    },
    {
      name: 'role_code',
      label: 'Papel institucional',
      options: [
        [
          'N1',
          'N1 · Pesquisador'
        ],
        [
          'N2',
          'N2 · Supervisor'
        ],
        [
          'N3',
          'N3 · Autoridade responsável'
        ]
      ]
    },
    {
      name: 'team_id',
      label: 'Equipe',
      options: teams.map(t => [
        t.id,
        t.name
      ])
    }
  ];
  if (!edit)
    specs.push(temporaryField);
  const f = form(specs, initial);
  const updateTeam = () => {
    const noTeam = f.controls.role_code.value === 'N3';
    f.controls.team_id.disabled = noTeam;
    f.controls.team_id.required = !noTeam;
    if (noTeam)
      f.controls.team_id.value = '';
  };
  f.controls.role_code.addEventListener('change', updateTeam);
  updateTeam();
  return f;
}
export async function accounts(params) {
  const filters = collectionFilters([
    {
      name: 'search',
      label: 'Nome ou email'
    },
    {
      name: 'status',
      label: 'Ativação',
      options: [
        [
          'ACTIVE',
          'Ativa'
        ],
        [
          'PENDING_ACTIVATION',
          'Pendente'
        ]
      ]
    },
    {
      name: 'soft_delete',
      label: 'Contas',
      options: [
        [
          'false',
          'Vigentes'
        ],
        [
          'true',
          'Desativadas'
        ]
      ]
    }
  ], params);
  const box = panel();
  const result = [
    heading('Contas', 'Gerencie o acesso institucional preservando o histórico.', link('Nova conta', '#/contas/nova', 'button')),
    filters,
    box
  ];
  try {
    const data = await api('/users?' + query(params, [
      'search',
      'status',
      'soft_delete'
    ]));
    box.append(data.items.length ? table([
      'Pessoa',
      'Papel',
      'Situação',
      'Acesso'
    ], data.items.map(u => [
      el('div', {}, link(u.name, '#/contas/' + pathId(u.id)), el('small', {}, u.email)),
      u.role_code,
      u.soft_delete ? 'Desativada' : badge(u.status),
      link('Gerenciar', '#/contas/' + pathId(u.id))
    ]), 'Contas institucionais') : info('Nenhuma conta encontrada', 'Ajuste os filtros para consultar outras contas.'), pager(params, data.total));
  } catch (error) {
    box.replaceChildren(failure(error, refresh));
  }
  return result;
}
export function query(params, keys = []) {
  const p = new URLSearchParams({
    page: params.get('page') || '1',
    per_page: '20'
  });
  for (const key of keys)
    if (params.get(key))
      p.set(key, params.get(key));
  return p;
}
export async function newAccount() {
  const f = await accountForm();
  submit(f, 'Criar conta', data => api('/access-requests', 'POST', {
    ...data,
    team_id: data.role_code === 'N3' ? null : data.team_id
  }), {
    confirm: 'Criar uma conta aprovada? A senha temporária deverá ser entregue pessoalmente.',
    after: () => {
      location.hash = '#/contas';
      notice('Conta criada. Entregue a senha temporária pessoalmente; ela vale por 24 horas.');
    }
  });
  return [
    heading('Nova conta', 'Cadastro direto pelo administrador. A aprovação reserva a vaga institucional.'),
    panel(f.node)
  ];
}
export async function accountDetail(id) {
  const u = await api('/users/' + pathId(id));
  const target = '/users/' + pathId(id);
  const actions = group();
  if (u.role_code !== 'ADMIN' && can('accounts.manage')) {
    actions.append(button('Corrigir dados', async () => {
      try {
        const f = await accountForm(u, true);
        const box = document.getElementById('action-dialog');
        if (state.dirty && !window.confirm('Descartar as alterações não salvas?'))
          return;
        state.dirty = false;
        document.getElementById('dialog-body').replaceChildren(el('h2', { id: 'dialog-title' }, 'Corrigir conta'), el('p', {}, 'Alterações institucionais podem encerrar as sessões da pessoa.'), f.node, button('Cancelar', () => {
          if (!state.busy && (!state.dirty || window.confirm('Descartar alterações?')))
            box.close();
        }, 'quiet'));
        submit(f, 'Salvar alterações', data => {
          if (data.role_code === 'N3')
            delete data.team_id;
          return api(target, 'PATCH', data);
        }, {
          after: () => {
            box.close();
            refresh();
          }
        });
        box.oncancel = e => {
          if (state.busy || state.dirty && !window.confirm('Descartar alterações?'))
            e.preventDefault();
        };
        box.onclose = () => {
          state.dirty = false;
          document.getElementById('dialog-body').replaceChildren();
        };
        box.showModal();
      } catch (error) {
        notice(error.message, true);
      }
    }));
    if (u.soft_delete)
      actions.append(button('Reativar conta', () => dialog('Reativar conta', 'A pessoa precisará definir nova senha e recadastrar o rosto quando exigido.', [
        temporaryField,
        ...reasonFields
      ], data => api(target + '/reactivate', 'POST', data), refresh)));
    else {
      actions.append(button('Desativar conta', () => dialog('Desativar conta', 'O acesso será bloqueado e as sessões serão revogadas. O histórico será preservado.', reasonFields, data => api(target + '/deactivate', 'POST', data), refresh), 'danger'));
      if (u.status === 'PENDING_ACTIVATION')
        actions.append(confirmAction('Revalidar senha temporária', 'Renovar a validade da mesma senha temporária por 24 horas e cancelar tentativas anteriores?', () => api(target + '/activation/revalidate', 'POST'), refresh));
      actions.append(button('Autorizar recuperação', () => {
        dialog('Autorizar recuperação', 'Esta ação revoga credenciais. Entregue a temporária pessoalmente quando aplicável.', [
          {
            name: 'mode',
            label: 'Recuperar',
            options: [
              [
                'PASSWORD',
                'Senha'
              ],
              [
                'BIOMETRIC',
                'Cadastro facial'
              ],
              [
                'BOTH',
                'Senha e cadastro facial'
              ]
            ]
          },
          ...reasonFields,
          {
            ...temporaryField,
            optional: true
          }
        ], data => {
          if (data.mode === 'BIOMETRIC')
            delete data.temporary_password;
          else if (!data.temporary_password)
            throw new Error('Informe a senha temporária para este modo.');
          return api(target + '/recovery', 'POST', data);
        }, refresh);
        const mode = document.querySelector('[name=mode]'), password = document.querySelector('[name=temporary_password]');
        if (mode)
          mode.addEventListener('change', () => {
            password.disabled = mode.value === 'BIOMETRIC';
            password.required = mode.value !== 'BIOMETRIC';
            if (password.disabled)
              password.value = '';
          });
      }));
    }
  }
  return [
    heading(u.name, u.email, link('Voltar às contas', '#/contas', 'button secondary')),
    panel(details([
      [
        'Papel',
        u.role_code
      ],
      [
        'Equipe',
        u.team_id || 'Sem equipe'
      ],
      [
        'Situação',
        u.soft_delete ? 'Desativada' : labelAccount(u.status)
      ],
      [
        'Primeira ativação',
        date(u.activated_at)
      ],
      [
        'Cadastro facial exigido',
        u.biometric_enrollment_required ? 'Sim' : 'Não'
      ],
      [
        'Troca de senha exigida',
        u.password_change_required ? 'Sim' : 'Não'
      ]
    ]), actions),
    info('Separação de acesso', 'A administração de contas não concede acesso a análises científicas ou ao cofre.')
  ];
}
function labelAccount(status) {
  return status === 'ACTIVE' ? 'Ativa' : 'Ativação pendente';
}
export async function requests(params) {
  const box = panel();
  const result = [
    heading('Solicitações de acesso', state.user.role === 'ADMIN' ? 'Avalie pedidos de contas institucionais.' : 'Acompanhe seus pedidos de acesso.', link(state.user.role === 'ADMIN' ? 'Nova conta' : 'Solicitar acesso', state.user.role === 'ADMIN' ? '#/contas/nova' : '#/solicitacoes/nova', 'button')),
    collectionFilters([{
        name: 'status',
        label: 'Situação',
        options: [
          [
            'PENDING',
            'Pendente'
          ],
          [
            'APPROVED',
            'Aprovada'
          ],
          [
            'REJECTED',
            'Rejeitada'
          ]
        ]
      }], params),
    box
  ];
  try {
    const data = await api('/access-requests?' + query(params, ['status']));
    box.append(data.items.length ? table([
      'Pessoa',
      'Situação',
      'Solicitada em',
      'Detalhes'
    ], data.items.map(r => [
      el('div', {}, r.requested_name, el('small', {}, r.requested_email)),
      badge(r.status),
      date(r.created_at),
      link('Abrir pedido', '#/solicitacoes/' + pathId(r.id))
    ]), 'Solicitações de acesso') : info('Nenhuma solicitação', 'Os pedidos autorizados aparecerão aqui.'), pager(params, data.total));
  } catch (error) {
    box.replaceChildren(failure(error, refresh));
  }
  return result;
}
export async function newRequest() {
  const n2 = state.user.role === 'N2';
  const specs = [
    {
      name: 'name',
      label: 'Nome completo'
    },
    {
      name: 'email',
      label: 'Email institucional',
      type: 'email'
    },
    temporaryField
  ];
  if (!n2) {
    const teams = await allPages('/teams');
    specs.push({
      name: 'team_id',
      label: 'Equipe do supervisor N2',
      options: teams.map(t => [
        t.id,
        t.name
      ])
    });
  }
  const f = form(specs);
  submit(f, 'Enviar solicitação', data => api('/access-requests', 'POST', data), {
    confirm: 'Solicitar esta conta ao administrador? A senha temporária será entregue fora do sistema após a aprovação.',
    after: () => {
      location.hash = '#/solicitacoes';
      notice('Solicitação enviada ao administrador.');
    }
  });
  return [
    heading('Solicitar acesso', n2 ? 'Solicite um pesquisador N1 para sua equipe.' : 'Solicite um supervisor N2. O administrador decide a aprovação.'),
    panel(f.node)
  ];
}
export async function requestDetail(id) {
  const r = await api('/access-requests/' + pathId(id));
  const actions = group();
  if (r.status === 'PENDING' && can('accounts.approve'))
    actions.append(confirmAction('Aprovar conta', 'Aprovar e reservar a vaga? A senha temporária terá validade de 24 horas.', () => api('/access-requests/' + pathId(id) + '/approve', 'POST'), refresh), button('Rejeitar pedido', () => dialog('Rejeitar pedido', 'Informe o motivo para o solicitante.', reasonFields, data => api('/access-requests/' + pathId(id) + '/reject', 'POST', data), refresh), 'danger'));
  return [
    heading(r.requested_name, r.requested_email, link('Voltar', '#/solicitacoes', 'button secondary')),
    panel(badge(r.status), details([
      [
        'Papel solicitado (identificador)',
        r.requested_role_id
      ],
      [
        'Solicitada em',
        date(r.created_at)
      ],
      [
        'Decidida em',
        date(r.decided_at)
      ],
      [
        'Equipe solicitada',
        r.requested_team_id || 'Sem equipe'
      ]
    ]), r.rejection_reason ? info('Motivo da rejeição', r.rejection_reason) : null, actions)
  ];
}
export async function audit(params) {
  const filters = collectionFilters([
    {
      name: 'event',
      label: 'Evento'
    },
    {
      name: 'actor_id',
      label: 'Identificador da pessoa (UUID)'
    },
    {
      name: 'date_from',
      label: 'A partir de',
      type: 'datetime-local'
    },
    {
      name: 'date_to',
      label: 'Até',
      type: 'datetime-local'
    }
  ], params);
  const p = query(params, [
    'event',
    'actor_id'
  ]);
  for (const name of [
      'date_from',
      'date_to'
    ])
    if (params.get(name))
      p.set(name, new Date(params.get(name)).toISOString());
  const box = panel();
  try {
    const data = await api('/admin/audit-events?' + p);
    box.append(data.items.length ? table([
      'Quando',
      'Evento',
      'Pessoa',
      'Resultado',
      'Motivo autorizado'
    ], data.items.map(e => [
      date(e.created_at),
      e.event,
      e.actor_id || 'Sistema',
      e.success ? 'Concluído' : 'Negado ou falhou',
      e.reason || '—'
    ]), 'Auditoria administrativa') : info('Nenhum evento', 'Ajuste o período ou aguarde ações administrativas.'), pager(params, data.total));
  } catch (error) {
    box.replaceChildren(failure(error, refresh));
  }
  return [
    heading('Auditoria administrativa', 'Registros de ações administrativas, sem conteúdo científico, senhas ou motivos exclusivos do N3.'),
    filters,
    box
  ];
}
