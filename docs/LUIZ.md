# Luiz - Base, segurança e apoio à integração

Você prepara a estrutura que Amanda e João vão usar, implementa contas e autenticação e assume as regras que exigem mais cuidado. Eles implementam os endpoints das funcionalidades, incluindo validação dos dados, consultas e testes, usando o padrão que você entregar.

## Etapa 1 - Preparar a base

- Conferir o código e as migrations existentes antes de reorganizar ou adicionar tabelas. O desenho em DATABASE.md ainda precisa ser comparado com o banco real.
- Preparar a entrada da API, configuração, conexão com PostgreSQL e aplicação das migrations sem apagar dados.
- Definir o padrão de rota, validação de entrada, regra de negócio, consulta ao banco, resposta e erro. Manter SQL parametrizado.
- Preparar dados fictícios de desenvolvimento: administrador, N1/N2 de duas equipes e N3.
- Entregar uma consulta pequena de ponta a ponta como exemplo, com um teste de acesso permitido e outro negado.

**Concluir quando:** a API inicia, o banco mantém os dados após reinício e Amanda/João conseguem reproduzir o exemplo.

Leia primeiro [Como funciona o sistema](BUSINESS_RULES.md). Consulte o contrato de cada rota em [ENDPOINTS.md](ENDPOINTS.md), as tabelas em [DATABASE.md](DATABASE.md) e o [exemplo completo](USE_CASES.md). Estes arquivos distribuem trabalho planejado; não afirmam que os endpoints já existem.

Todos os endereços abaixo começam com `/api/v1`. `{id}` e `{user_id}` representam identificadores do registro. `GET` consulta, `POST` cria ou executa uma ação, `PATCH` altera campos e `DELETE` remove o vínculo indicado.

## Etapa 2 - Consultas de apoio

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /health](ENDPOINTS.md#get-health) | Informar que a API responde, sem mostrar informações internas. | Sem corpo JSON → `dict[str, str]`, com `{"status":"ok"}`. |
| [GET /teams](ENDPOINTS.md#get-teams) | Fornecer as equipes para seleções autorizadas. | [PaginationParams](../schemas/sc_base_model.py#L73) → [ListResponse](../schemas/sc_base_model.py#L90) de [TeamResponse](../schemas/sc_teams.py#L8) |
| [GET /admin/roles](ENDPOINTS.md#get-adminroles) | Consultar os níveis de acesso e suas permissões. | Sem corpo JSON → `list` de [RoleResponse](../schemas/sc_roles.py#L12) (catálogo sem paginação). |
| [GET /admin/permissions](ENDPOINTS.md#get-adminpermissions) | Consultar as ações conhecidas pelo sistema. | Sem corpo JSON → `list` de [PermissionResponse](../schemas/sc_permissions.py#L8) (catálogo sem paginação). |
| [GET /admin/audit-events](ENDPOINTS.md#get-adminaudit-events) | Consultar eventos administrativos sem expor análises ou dados secretos. | [AuditEventQuery](../schemas/sc_audit_events.py#L37) → [ListResponse](../schemas/sc_base_model.py#L90) de [AuditEventResponse](../schemas/sc_audit_events.py#L12) |

**Concluir quando:** Consultas retornam apenas os campos permitidos; catálogos administrativos não podem ser lidos por N1/N2/N3.

## Etapa 3 - Contas e solicitações

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [POST /access-requests](ENDPOINTS.md#post-access-requests) | Solicitar conta ou cadastrar diretamente pelo administrador. | [AccessRequestCreate](../schemas/sc_access_requests.py#L18) → [AccessRequestResponse](../schemas/sc_access_requests.py#L38) |
| [GET /access-requests](ENDPOINTS.md#get-access-requests) | Listar pedidos: próprios para solicitantes, todos para administrador. | [AccessRequestQuery](../schemas/sc_access_requests.py#L79) → [ListResponse](../schemas/sc_base_model.py#L90) de [AccessRequestResponse](../schemas/sc_access_requests.py#L38) |
| [GET /access-requests/{id}](ENDPOINTS.md#get-access-requestsid) | Consultar um pedido autorizado e sua decisão. | Sem corpo JSON → [AccessRequestResponse](../schemas/sc_access_requests.py#L38) |
| [POST /access-requests/{id}/approve](ENDPOINTS.md#post-access-requestsidapprove) | Aprovar o pedido e criar a conta. | Sem corpo JSON → [AccessRequestResponse](../schemas/sc_access_requests.py#L38) |
| [POST /access-requests/{id}/reject](ENDPOINTS.md#post-access-requestsidreject) | Rejeitar com motivo, sem criar conta. | [AccessRequestReject](../schemas/sc_access_requests.py#L66) → [AccessRequestResponse](../schemas/sc_access_requests.py#L38) |
| [GET /users](ENDPOINTS.md#get-users-e-get-usersid) | Listar contas para o administrador. | [UserQuery](../schemas/sc_users.py#L175) → [ListResponse](../schemas/sc_base_model.py#L90) de [UserResponse](../schemas/sc_users.py#L46) |
| [GET /users/{id}](ENDPOINTS.md#get-users-e-get-usersid) | Consultar dados administrativos de uma conta. | Sem corpo JSON → [UserResponse](../schemas/sc_users.py#L46) |
| [PATCH /users/{id}](ENDPOINTS.md#patch-usersid) | Corrigir nome, email, nível ou equipe, respeitando as restrições. | [UserUpdate](../schemas/sc_users.py#L88) → [UserResponse](../schemas/sc_users.py#L46) |
| [POST /users/{id}/deactivate](ENDPOINTS.md#post-usersiddeactivate) | Bloquear acesso preservando histórico. | [UserDeactivate](../schemas/sc_users.py#L118) → [UserResponse](../schemas/sc_users.py#L46) |
| [POST /users/{id}/reactivate](ENDPOINTS.md#post-usersidreactivate) | Reativar com nova senha temporária e recadastro facial quando exigido. | [UserReactivate](../schemas/sc_users.py#L131) → [UserActivationResponse](../schemas/sc_users.py#L73) |
| [POST /users/{id}/activation/revalidate](ENDPOINTS.md#post-usersidactivationrevalidate) | Renovar a validade da mesma senha temporária. | Sem corpo JSON → [UserActivationResponse](../schemas/sc_users.py#L73) |
| [POST /users/{id}/recovery](ENDPOINTS.md#post-usersidrecovery) | Autorizar recuperação de senha, cadastro facial ou ambos. | [UserRecovery](../schemas/sc_users.py#L147) → [UserActivationResponse](../schemas/sc_users.py#L73) |

**Concluir quando:** Pedidos seguem o nível/equipe permitido; email não duplica; aprovação reserva as vagas N2/N3; desativação usa soft_delete e revoga acesso; reativação preserva activated_at da primeira ativação e exige nova senha/face. Consultas e autorização ignoram registros e vínculos excluídos; ações geram log sanitizado em audit_events.

## Etapa 4 - Entrada e segurança compartilhada

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /auth/csrf](ENDPOINTS.md#get-authcsrf) | Preparar a proteção das chamadas que alteram dados. | Sem corpo JSON → [CsrfResponse](../schemas/sc_sessions.py#L58) |
| [POST /auth/login](ENDPOINTS.md#post-authlogin) | Verificar email/senha e iniciar a etapa correta de autenticação. | [LoginRequest](../schemas/sc_sessions.py#L12) → [AuthenticationStepResponse](../schemas/sc_authentication_attempts.py#L13) ou [SessionResponse](../schemas/sc_sessions.py#L28) |
| [GET /auth/flow](ENDPOINTS.md#get-authflow) | Consultar a etapa pendente após recarregar a página. | Sem corpo JSON → [AuthenticationFlowResponse](../schemas/sc_authentication_attempts.py#L29) |
| [POST /auth/biometric/enroll](ENDPOINTS.md#post-authbiometricenroll) | Cadastrar a face somente com autorização. | `multipart/form-data`: `frames: list[UploadFile]`; limites de upload aplicados na rota. → [AuthenticationStepResponse](../schemas/sc_authentication_attempts.py#L13) ou [SessionResponse](../schemas/sc_sessions.py#L28) |
| [POST /auth/biometric](ENDPOINTS.md#post-authbiometric) | Reconhecer a pessoa e verificar tentativa de imitação. | `multipart/form-data`: `frames: list[UploadFile]`; limites de upload aplicados na rota. → [AuthenticationStepResponse](../schemas/sc_authentication_attempts.py#L13) ou [SessionResponse](../schemas/sc_sessions.py#L28) |
| [POST /auth/password/complete](ENDPOINTS.md#post-authpasswordcomplete) | Definir a senha definitiva e concluir ativação ou recuperação. | [PasswordCompleteRequest](../schemas/sc_password_hashes.py#L11) → [SessionResponse](../schemas/sc_sessions.py#L28) |
| [POST /auth/refresh](ENDPOINTS.md#post-authrefresh) | Renovar credenciais sem prolongar o limite da sessão. | Sem corpo JSON → [RefreshTokenResponse](../schemas/sc_refresh_tokens.py#L8) |
| [POST /auth/logout](ENDPOINTS.md#post-authlogout) | Encerrar acesso no servidor e limpar os cookies. | Sem corpo JSON → 204, sem corpo e sem schema de resposta. |
| [GET /auth/me](ENDPOINTS.md#get-authme) | Informar quem está autenticado e suas permissões. | Sem corpo JSON → [CurrentUserResponse](../schemas/sc_users.py#L209) |
| [POST /auth/password-change/start](ENDPOINTS.md#post-authpassword-changestart-e-post-authpassword-changecomplete) | Iniciar troca de senha confirmando a senha atual. | [PasswordChangeStartRequest](../schemas/sc_password_hashes.py#L34) → [AuthenticationStepResponse](../schemas/sc_authentication_attempts.py#L13) |
| [POST /auth/password-change/complete](ENDPOINTS.md#post-authpassword-changestart-e-post-authpassword-changecomplete) | Concluir troca de senha e encerrar todas as sessões. | [PasswordCompleteRequest](../schemas/sc_password_hashes.py#L11) → [LoginRequiredResponse](../schemas/sc_sessions.py#L45) |

**Concluir quando:** Etapa incompleta não acessa o laboratório; sessão revogada não funciona; permissões, cookies e proteção das alterações são verificados no servidor.

## Etapa 5 - Preparar as operações delicadas para os colegas

Entregar funções de regra de negócio que as rotas de Amanda e João possam chamar. Essas funções verificam acesso e situação atual e gravam todas as mudanças necessárias juntas, sem deixar metade da operação salva.

- **Para Amanda:** cadastro com primeira investigação, nova investigação com atendimento de pedido N3, envio com cópia preservada da entrega, alteração de participantes/responsável e ativação/inativação da amostra.
- **Para João:** devolução/encerramento, envio selado ao N3, publicação, sigilo, pedido de nova investigação e retirada de notícia.
- **Para ambos:** consulta com acesso limitado por pessoa/equipe, paginação, erros e registro de eventos sem dados secretos.

**Concluir quando:** testes em PostgreSQL real comprovam uma investigação em andamento por amostra, entregas preservadas e decisões incompatíveis impedidas, inclusive com duas chamadas simultâneas. Amanda e João sabem quais funções chamar e quais dados passar.

## Etapa 6 - Revisar a integração

Revisar os endpoints dos colegas, integrar o caminho completo do cadastro à divulgação e testar acessos indevidos entre equipes. Testar autenticação com o simulador e depois com a integração biométrica real; registrar esses resultados separadamente. O simulador não comprova reconhecimento facial.

Você apoia e revisa; Amanda e João continuam responsáveis pelos endpoints atribuídos a eles.

## Como entregar cada etapa

- Seguir os campos, respostas, limites e complementos da rota em ENDPOINTS.md. Os exemplos deste plano não substituem o contrato.
- Executar testes de sucesso, dados inválidos, acesso negado e situação incompatível quando aplicável.
- Conferir gravações e consultas no PostgreSQL real; simulações não comprovam as garantias do banco.
- Revisar com Luiz antes de avançar para operações que dependem dessa etapa. Registrar o que foi testado e o que ainda falta.
