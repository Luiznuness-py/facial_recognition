# Amanda - Amostras e investigações

Você desenvolve os endpoints do cadastro e do trabalho do N1, começando pelas consultas. Use a conexão, autenticação, permissões e padrão de resposta preparados por Luiz.

Antes das consultas privadas, aguarde a base de autenticação/permissões. Antes das alterações delicadas, aguarde as funções de regra entregues por Luiz. Cada endpoint inclui entrada validada, consulta ou chamada da regra, resposta e testes.

Leia primeiro [Como funciona o sistema](BUSINESS_RULES.md). Consulte o contrato de cada rota em [ENDPOINTS.md](ENDPOINTS.md), as tabelas em [DATABASE.md](DATABASE.md) e o [exemplo completo](USE_CASES.md). Estes arquivos distribuem trabalho planejado; não afirmam que os endpoints já existem.

Todos os endereços abaixo começam com `/api/v1`. `{id}` e `{user_id}` representam identificadores do registro. `GET` consulta, `POST` cria ou executa uma ação, `PATCH` altera campos e `DELETE` remove o vínculo indicado.

## Etapa 1 - Consultar amostras e investigações

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /biological-agents](ENDPOINTS.md#get-biological-agents) | Listar amostras autorizadas, com pesquisa e filtro de ativas/inativas. | [BiologicalAgentQuery](../schemas/sc_biological_agents.py#L199) → [ListResponse](../schemas/sc_base_model.py#L90) de [BiologicalAgentResponse](../schemas/sc_biological_agents.py#L123) |
| [GET /biological-agents/{id}](ENDPOINTS.md#get-biological-agentsid) | Abrir o cadastro de uma amostra autorizada. | Sem corpo JSON → [BiologicalAgentResponse](../schemas/sc_biological_agents.py#L123) |
| [GET /biological-agents/{id}/validations](ENDPOINTS.md#get-biological-agentsidvalidations) · [Complemento](ENDPOINTS.md#complemento-das-consultas-de-validação) | Listar apenas as investigações que a pessoa pode consultar. | [ValidationQuery](../schemas/sc_validations.py#L227) → [ListResponse](../schemas/sc_base_model.py#L90) de [ValidationCardResponse](../schemas/sc_validations.py#L103) |
| [GET /validations/{id}](ENDPOINTS.md#get-validationsid) · [Complemento](ENDPOINTS.md#complemento-das-consultas-de-validação) | Consultar análise, entregas e motivos autorizados de uma investigação. | Sem corpo JSON → [ValidationResponse](../schemas/sc_validations.py#L131) |
| [GET /validations/{id}/participants](ENDPOINTS.md#get-validationsidparticipants) | Consultar responsável e colaboradores atuais. | Sem corpo JSON → `list` de [ValidationParticipantResponse](../schemas/sc_validation_participants.py#L24) (catálogo sem paginação). |

**Concluir quando:** N1 vê apenas tarefas vinculadas; N2 vê sua equipe; uma consulta não revela tarefas de outra equipe nem conteúdo do cofre. Total e filtros respeitam esses limites.

## Etapa 2 - Cadastrar e preparar a análise

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [POST /biological-agents](ENDPOINTS.md#post-biological-agents) | Cadastrar a amostra e criar junto a primeira investigação do N1. | [BiologicalAgentCreate](../schemas/sc_biological_agents.py#L14) → [BiologicalAgentCreateResponse](../schemas/sc_biological_agents.py#L184) |
| [PATCH /biological-agents/{id}](ENDPOINTS.md#patch-biological-agentsid) | Corrigir os dados cadastrais antes da primeira entrega. | [BiologicalAgentUpdate](../schemas/sc_biological_agents.py#L49) → [BiologicalAgentResponse](../schemas/sc_biological_agents.py#L123) |
| [PATCH /validations/{id}/analysis](ENDPOINTS.md#patch-validationsidanalysis) | Salvar campos do rascunho ou da correção sem enviar para revisão. | [ValidationAnalysisUpdate](../schemas/sc_validations.py#L36) → [ValidationResponse](../schemas/sc_validations.py#L131) |

**Concluir quando:** Cadastro cria amostra e primeira tarefa juntos; campos inválidos são rejeitados; colaborador não edita; cadastro deixa de ser editável após a primeira entrega.

## Etapa 3 - Selecionar e gerir a equipe

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /validations/{id}/participant-candidates](ENDPOINTS.md#get-validationsidparticipant-candidates) | Listar N1 ativos da equipe que podem entrar como colaboradores. | [UserCandidateQuery](../schemas/sc_users.py#L223) → [ListResponse](../schemas/sc_base_model.py#L90) de [UserSummary](../schemas/sc_users.py#L31) |
| [GET /biological-agents/{id}/responsible-candidates](ENDPOINTS.md#get-biological-agentsidresponsible-candidates) | Fornecer ao N2 os N1 ativos disponíveis para assumir uma investigação. | [UserCandidateQuery](../schemas/sc_users.py#L223) → [ListResponse](../schemas/sc_base_model.py#L90) de [UserSummary](../schemas/sc_users.py#L31) |
| [POST /validations/{id}/participants](ENDPOINTS.md#post-validationsidparticipants) | Incluir um colaborador com acesso somente de leitura. | [ValidationParticipantAdd](../schemas/sc_validation_participants.py#L10) → [ValidationParticipantResponse](../schemas/sc_validation_participants.py#L24) |
| [DELETE /validations/{id}/participants/{user_id}](ENDPOINTS.md#delete-validationsidparticipantsuser_id) | Permitir ao N2 remover um colaborador sem apagar histórico. | Sem corpo JSON → 204, sem corpo e sem schema de resposta. |
| [PATCH /validations/{id}/responsible](ENDPOINTS.md#patch-validationsidresponsible) | Permitir ao N2 trocar responsável, mantendo o anterior como colaborador. | [ValidationResponsibleUpdate](../schemas/sc_validations.py#L64) → [ValidationResponsibleResponse](../schemas/sc_validations.py#L255) |

**Concluir quando:** Somente integrantes ativos da mesma equipe podem ser escolhidos; colaborador não compartilha; só N2 remove/troca; mudanças exigem preparação ou devolução e preservam entregas antigas.

## Etapa 4 - Enviar e abrir novo trabalho

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [POST /validations/{id}/submit](ENDPOINTS.md#post-validationsidsubmit) | Enviar a análise completa ao N2, preservar uma cópia e bloquear edição. | Sem corpo JSON → [ValidationSubmitResponse](../schemas/sc_validations.py#L171) |
| [POST /biological-agents/{id}/validations](ENDPOINTS.md#post-biological-agentsidvalidations) · [Complemento](ENDPOINTS.md#complemento-de-post-biological-agentsidvalidations) | Permitir ao N2 abrir outra investigação e escolher o responsável; vincular pedido N3 quando houver. | [ValidationCreate](../schemas/sc_validations.py#L21) → [ValidationCreatedResponse](../schemas/sc_validations.py#L240) |
| [PATCH /biological-agents/{id}/status](ENDPOINTS.md#patch-biological-agentsidstatus) | Permitir ao N2 ativar ou inativar a amostra conforme as regras. | [BiologicalAgentStatusUpdate](../schemas/sc_biological_agents.py#L93) → [BiologicalAgentStatusResponse](../schemas/sc_biological_agents.py#L214) |

**Concluir quando:** Envio exige os quatro textos; repetição não cria entrega duplicada; não existem duas tarefas em andamento; amostra com tarefa em andamento não pode ser inativada.

## Etapa 5 - Integrar com João

Enviar uma análise para que João faça a revisão. Testar devolução e reenvio preservando a primeira entrega. Quando o N3 pedir outra investigação, criar a tarefa seguinte vinculada ao pedido e mostrar o motivo à nova equipe.

Luiz prepara as operações delicadas; você conecta suas rotas a elas e testa os resultados. Não implemente outra autenticação nem replique as regras em cada rota.

## Como entregar cada etapa

- Seguir os campos, respostas, limites e complementos da rota em ENDPOINTS.md. Os exemplos deste plano não substituem o contrato.
- Executar testes de sucesso, dados inválidos, acesso negado e situação incompatível quando aplicável.
- Conferir gravações e consultas no PostgreSQL real; simulações não comprovam as garantias do banco.
- Revisar com Luiz antes de avançar para operações que dependem dessa etapa. Registrar o que foi testado e o que ainda falta.
