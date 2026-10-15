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

| Endpoint | Para que serve |
| --- | --- |
| [GET /health](ENDPOINTS.md#get-health) | Informar que a API responde, sem mostrar informações internas. |
| [GET /teams](ENDPOINTS.md#get-teams) | Fornecer as equipes para seleções autorizadas. |
| [GET /admin/roles](ENDPOINTS.md#get-adminroles) | Consultar os níveis de acesso e suas permissões. |
| [GET /admin/permissions](ENDPOINTS.md#get-adminpermissions) | Consultar as ações conhecidas pelo sistema. |
| [GET /admin/audit-events](ENDPOINTS.md#get-adminaudit-events) | Consultar eventos administrativos sem expor análises ou dados secretos. |

**Concluir quando:** Consultas retornam apenas os campos permitidos; catálogos administrativos não podem ser lidos por N1/N2/N3.

## Etapa 3 - Contas e solicitações

| Endpoint | Para que serve |
| --- | --- |
| [POST /access-requests](ENDPOINTS.md#post-access-requests) | Solicitar conta ou cadastrar diretamente pelo administrador. |
| [GET /access-requests](ENDPOINTS.md#get-access-requests) | Listar pedidos: próprios para solicitantes, todos para administrador. |
| [GET /access-requests/{id}](ENDPOINTS.md#get-access-requestsid) | Consultar um pedido autorizado e sua decisão. |
| [POST /access-requests/{id}/approve](ENDPOINTS.md#post-access-requestsidapprove) | Aprovar o pedido e criar a conta. |
| [POST /access-requests/{id}/reject](ENDPOINTS.md#post-access-requestsidreject) | Rejeitar com motivo, sem criar conta. |
| [GET /users](ENDPOINTS.md#get-users-e-get-usersid) | Listar contas para o administrador. |
| [GET /users/{id}](ENDPOINTS.md#get-users-e-get-usersid) | Consultar dados administrativos de uma conta. |
| [PATCH /users/{id}](ENDPOINTS.md#patch-usersid) | Corrigir nome, email, nível ou equipe, respeitando as restrições. |
| [POST /users/{id}/deactivate](ENDPOINTS.md#post-usersiddeactivate) | Bloquear acesso preservando histórico. |
| [POST /users/{id}/reactivate](ENDPOINTS.md#post-usersidreactivate) | Reativar com nova senha temporária e recadastro facial quando exigido. |
| [POST /users/{id}/activation/revalidate](ENDPOINTS.md#post-usersidactivationrevalidate) | Renovar a validade da mesma senha temporária. |
| [POST /users/{id}/recovery](ENDPOINTS.md#post-usersidrecovery) | Autorizar recuperação de senha, cadastro facial ou ambos. |

**Concluir quando:** Pedidos seguem o nível/equipe permitido; email não duplica; aprovação reserva as vagas N2/N3; desativação revoga acesso.

## Etapa 4 - Entrada e segurança compartilhada

| Endpoint | Para que serve |
| --- | --- |
| [GET /auth/csrf](ENDPOINTS.md#get-authcsrf) | Preparar a proteção das chamadas que alteram dados. |
| [POST /auth/login](ENDPOINTS.md#post-authlogin) | Verificar email/senha e iniciar a etapa correta de autenticação. |
| [GET /auth/flow](ENDPOINTS.md#get-authflow) | Consultar a etapa pendente após recarregar a página. |
| [POST /auth/biometric/enroll](ENDPOINTS.md#post-authbiometricenroll) | Cadastrar a face somente com autorização. |
| [POST /auth/biometric](ENDPOINTS.md#post-authbiometric) | Reconhecer a pessoa e verificar tentativa de imitação. |
| [POST /auth/password/complete](ENDPOINTS.md#post-authpasswordcomplete) | Definir a senha definitiva e concluir ativação ou recuperação. |
| [POST /auth/refresh](ENDPOINTS.md#post-authrefresh) | Renovar credenciais sem prolongar o limite da sessão. |
| [POST /auth/logout](ENDPOINTS.md#post-authlogout) | Encerrar acesso no servidor e limpar os cookies. |
| [GET /auth/me](ENDPOINTS.md#get-authme) | Informar quem está autenticado e suas permissões. |
| [POST /auth/password-change/start](ENDPOINTS.md#post-authpassword-changestart-e-post-authpassword-changecomplete) | Iniciar troca de senha confirmando a senha atual. |
| [POST /auth/password-change/complete](ENDPOINTS.md#post-authpassword-changestart-e-post-authpassword-changecomplete) | Concluir troca de senha e encerrar todas as sessões. |

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
