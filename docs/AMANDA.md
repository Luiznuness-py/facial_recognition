# Amanda - Amostras e investigações

Você desenvolve os endpoints do cadastro e do trabalho do N1, começando pelas consultas. Use a conexão, autenticação, permissões e padrão de resposta preparados por Luiz.

Antes das consultas privadas, aguarde a base de autenticação/permissões. Antes das alterações delicadas, aguarde as funções de regra entregues por Luiz. Cada endpoint inclui entrada validada, consulta ou chamada da regra, resposta e testes.

Leia primeiro [Como funciona o sistema](BUSINESS_RULES.md). Consulte o contrato de cada rota em [ENDPOINTS.md](ENDPOINTS.md), as tabelas em [DATABASE.md](DATABASE.md) e o [exemplo completo](USE_CASES.md). Estes arquivos distribuem trabalho planejado; não afirmam que os endpoints já existem.

Todos os endereços abaixo começam com `/api/v1`. `{id}` e `{user_id}` representam identificadores do registro. `GET` consulta, `POST` cria ou executa uma ação, `PATCH` altera campos e `DELETE` remove o vínculo indicado.

## Etapa 1 - Consultar amostras e investigações

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /biological-agents](ENDPOINTS.md#get-biological-agents) | Listar amostras autorizadas, com pesquisa e filtro de ativas/inativas. | [BiologicalAgentQuery](../facial_recognition/schemas/biological_agents.py#L236) → [ListResponse](../facial_recognition/schemas/base_model.py#L91) de [BiologicalAgentResponse](../facial_recognition/schemas/biological_agents.py#L158) |
| [GET /biological-agents/{id}](ENDPOINTS.md#get-biological-agentsid) | Abrir o cadastro de uma amostra autorizada. | Sem corpo JSON → [BiologicalAgentResponse](../facial_recognition/schemas/biological_agents.py#L158) |
| [GET /biological-agents/{id}/validations](ENDPOINTS.md#get-biological-agentsidvalidations) · [Complemento](ENDPOINTS.md#complemento-das-consultas-de-validação) | Listar apenas as investigações que a pessoa pode consultar. | [ValidationQuery](../facial_recognition/schemas/validations.py#L237) → [ListResponse](../facial_recognition/schemas/base_model.py#L91) de [ValidationCardResponse](../facial_recognition/schemas/validations.py#L113) |
| [GET /validations/{id}](ENDPOINTS.md#get-validationsid) · [Complemento](ENDPOINTS.md#complemento-das-consultas-de-validação) | Consultar análise, entregas e motivos autorizados de uma investigação. | Sem corpo JSON → [ValidationResponse](../facial_recognition/schemas/validations.py#L141) |
| [GET /validations/{id}/participants](ENDPOINTS.md#get-validationsidparticipants) | Consultar responsável e colaboradores atuais. | Sem corpo JSON → `list` de [ValidationParticipantResponse](../facial_recognition/schemas/validation_participants.py#L24) (catálogo sem paginação). |

**Concluir quando:** N1 vê apenas tarefas vinculadas; N2 vê sua equipe; uma consulta não revela tarefas de outra equipe nem conteúdo do cofre. Total e filtros respeitam esses limites.

## Etapa 2 - Cadastrar e preparar a análise

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [POST /biological-agents](ENDPOINTS.md#post-biological-agents) | Cadastrar a amostra e criar junto a primeira investigação do N1. | [BiologicalAgentCreate](../facial_recognition/schemas/biological_agents.py#L14) → [BiologicalAgentCreateResponse](../facial_recognition/schemas/biological_agents.py#L221) |
| [PATCH /biological-agents/{id}](ENDPOINTS.md#patch-biological-agentsid) | Corrigir os dados cadastrais antes da primeira entrega. | [BiologicalAgentUpdate](../facial_recognition/schemas/biological_agents.py#L61) → [BiologicalAgentResponse](../facial_recognition/schemas/biological_agents.py#L158) |
| [PATCH /validations/{id}/analysis](ENDPOINTS.md#patch-validationsidanalysis) | Salvar campos do rascunho ou da correção sem enviar para revisão. | [ValidationAnalysisUpdate](../facial_recognition/schemas/validations.py#L36) → [ValidationResponse](../facial_recognition/schemas/validations.py#L141) |

**Concluir quando:** Cadastro cria amostra e primeira tarefa juntos; campos inválidos são rejeitados; colaborador não edita; cadastro deixa de ser editável após a primeira entrega.

## Etapa 3 - Selecionar e gerir a equipe

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /validations/{id}/participant-candidates](ENDPOINTS.md#get-validationsidparticipant-candidates) | Listar N1 ativos da equipe que podem entrar como colaboradores. | [UserCandidateQuery](../facial_recognition/schemas/users.py#L244) → [ListResponse](../facial_recognition/schemas/base_model.py#L91) de [UserSummary](../facial_recognition/schemas/users.py#L31) |
| [GET /biological-agents/{id}/responsible-candidates](ENDPOINTS.md#get-biological-agentsidresponsible-candidates) | Fornecer ao N2 os N1 ativos disponíveis para assumir uma investigação. | [UserCandidateQuery](../facial_recognition/schemas/users.py#L244) → [ListResponse](../facial_recognition/schemas/base_model.py#L91) de [UserSummary](../facial_recognition/schemas/users.py#L31) |
| [POST /validations/{id}/participants](ENDPOINTS.md#post-validationsidparticipants) | Incluir um colaborador com acesso somente de leitura. | [ValidationParticipantAdd](../facial_recognition/schemas/validation_participants.py#L10) → [ValidationParticipantResponse](../facial_recognition/schemas/validation_participants.py#L24) |
| [DELETE /validations/{id}/participants/{user_id}](ENDPOINTS.md#delete-validationsidparticipantsuser_id) | Permitir ao N2 remover um colaborador sem apagar histórico. | Sem corpo JSON → 204, sem corpo e sem schema de resposta. |
| [PATCH /validations/{id}/responsible](ENDPOINTS.md#patch-validationsidresponsible) | Permitir ao N2 trocar responsável, mantendo o anterior como colaborador. | [ValidationResponsibleUpdate](../facial_recognition/schemas/validations.py#L74) → [ValidationResponsibleResponse](../facial_recognition/schemas/validations.py#L265) |

**Concluir quando:** Somente integrantes ativos da mesma equipe podem ser escolhidos; colaborador não compartilha; só N2 remove/troca; mudanças exigem preparação ou devolução e preservam entregas antigas.

## Etapa 4 - Enviar e abrir novo trabalho

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [POST /validations/{id}/submit](ENDPOINTS.md#post-validationsidsubmit) | Enviar a análise completa ao N2, preservar uma cópia e bloquear edição. | Sem corpo JSON → [ValidationSubmitResponse](../facial_recognition/schemas/validations.py#L181) |
| [POST /biological-agents/{id}/validations](ENDPOINTS.md#post-biological-agentsidvalidations) · [Complemento](ENDPOINTS.md#complemento-de-post-biological-agentsidvalidations) | Permitir ao N2 abrir outra investigação e escolher o responsável; vincular pedido N3 quando houver. | [ValidationCreate](../facial_recognition/schemas/validations.py#L21) → [ValidationCreatedResponse](../facial_recognition/schemas/validations.py#L250) |
| [PATCH /biological-agents/{id}/status](ENDPOINTS.md#patch-biological-agentsidstatus) | Permitir ao N2 ativar ou inativar a amostra conforme as regras. | [BiologicalAgentStatusUpdate](../facial_recognition/schemas/biological_agents.py#L128) → [BiologicalAgentStatusResponse](../facial_recognition/schemas/biological_agents.py#L251) |

**Concluir quando:** Envio exige os quatro textos; repetição não cria entrega duplicada; não existem duas tarefas em andamento; amostra com tarefa em andamento não pode ser inativada.

## Etapa 5 - Integrar com João

Enviar uma análise para que João faça a revisão. Testar devolução e reenvio preservando a primeira entrega. Quando o N3 pedir outra investigação, criar a tarefa seguinte vinculada ao pedido e mostrar o motivo à nova equipe.

Luiz prepara as operações delicadas; você conecta suas rotas a elas e testa os resultados. Não implemente outra autenticação nem replique as regras em cada rota.

## Como entregar cada etapa

- Seguir os campos, respostas, limites e complementos da rota em ENDPOINTS.md. Os exemplos deste plano não substituem o contrato.
- Executar testes de sucesso, dados inválidos, acesso negado e situação incompatível quando aplicável.
- Conferir gravações e consultas no PostgreSQL real; simulações não comprovam as garantias do banco.
- Revisar com Luiz antes de avançar para operações que dependem dessa etapa. Registrar o que foi testado e o que ainda falta.

## Contrato de edição cadastral

`BiologicalAgentResponse.can_edit` é obrigatório nas respostas completas de amostras. O serviço deve calcular o valor para o usuário atual verificando vínculo/permissão e a ausência de qualquer entrega anterior da amostra, sem depender da página ou filtro das investigações. Não use apenas entregas visíveis nem ignore histórico por soft_delete. O frontend só oferece “Corrigir cadastro” se o campo for true; PATCH revalida a condição na transação. Esta operação científica permanece pendente de implementação.
