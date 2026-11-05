# João - Revisão, cofre e notícias

> Referência de responsabilidade: revisão, cofre e publicações. As rotas estão implementadas; as etapas abaixo organizam manutenção e revisão, sem indicar novas funcionalidades pendentes. Evidências e limites estão em [AUTH_LAB.md](AUTH_LAB.md#escopo-implementado-e-limites).

**Código de referência:** `routers/vault.py`, `routers/publications.py` e ações de revisão em `routers/validations.py`.

Esta área mantém revisão N2, decisão N3 e consultas de notícias. As leituras públicas demonstram a projeção sanitizada; os fluxos privados exigem autenticação e autorização institucional.

Use fixtures e dados fictícios para revisão. Reutilize a autenticação e as regras compartilhadas existentes; preserve o selamento, a ordem dos locks e o caráter terminal das decisões.

Leia primeiro [Como funciona o sistema](BUSINESS_RULES.md). Consulte o contrato de cada rota em [ENDPOINTS.md](ENDPOINTS.md), as tabelas em [DATABASE.md](DATABASE.md) e o [exemplo completo](USE_CASES.md). As tabelas abaixo vinculam cada operação ao contrato e aos schemas correspondentes.

Todos os endereços abaixo começam com `/api/v1`. `{id}` e `{user_id}` representam identificadores do registro. `GET` consulta, `POST` cria ou executa uma ação, `PATCH` altera campos e `DELETE` remove o vínculo indicado.

## Área 1 - Consultar notícias públicas

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /public/publications](ENDPOINTS.md#get-publicpublications) | Listar apenas notícias publicadas, sem exigir login. | [PublicPublicationQuery](../facial_recognition/schemas/publications.py#L105) → [ListResponse](../facial_recognition/schemas/base_model.py#L91) de [PublicPublicationResponse](../facial_recognition/schemas/publications.py#L13) |
| [GET /public/publications/{id}](ENDPOINTS.md#get-publicpublicationsid) | Consultar uma notícia vigente com título, subtítulo, categoria, texto e data. | Sem corpo JSON → [PublicPublicationResponse](../facial_recognition/schemas/publications.py#L13) |

**Critérios de revisão:** Notícia retirada não aparece e seu detalhe retorna 404; nenhuma resposta mostra equipe, percentual interno, relatório ou motivo privado.

## Área 2 - Consultar envios e cofre

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /reports/sent](ENDPOINTS.md#get-reportssent) · [Complemento](ENDPOINTS.md#complemento-de-get-reportssent) | Permitir ao N2 acompanhar envios de sua equipe e pedidos de nova investigação. | [SentReportQuery](../facial_recognition/schemas/vault.py#L212) → [ListResponse](../facial_recognition/schemas/base_model.py#L91) de [SentReportResponse](../facial_recognition/schemas/vault.py#L82) |
| [GET /vault/dossiers](ENDPOINTS.md#get-vaultdossiers) | Listar os relatórios selados para o N3. | [VaultQuery](../facial_recognition/schemas/vault.py#L197) → [ListResponse](../facial_recognition/schemas/base_model.py#L91) de [VaultSummary](../facial_recognition/schemas/vault.py#L105) |
| [GET /vault/dossiers/{id}](ENDPOINTS.md#get-vaultdossiersid) | Mostrar ao N3 o relatório e a notícia preparada para decisão. | Sem corpo JSON → [VaultResponse](../facial_recognition/schemas/vault.py#L127) |
| [GET /publications](ENDPOINTS.md#get-publications-e-get-publicationsid) | Permitir ao N3 listar notícias e suas situações. | [PublicationQuery](../facial_recognition/schemas/publications.py#L118) → [ListResponse](../facial_recognition/schemas/base_model.py#L91) de [PublicationResponse](../facial_recognition/schemas/publications.py#L36) |
| [GET /publications/{id}](ENDPOINTS.md#get-publications-e-get-publicationsid) | Permitir ao N3 consultar uma publicação e seus metadados autorizados. | Sem corpo JSON → [PublicationResponse](../facial_recognition/schemas/publications.py#L36) |

**Critérios de revisão:** N2 recebe apenas os campos de acompanhamento e o pedido autorizado; não recebe o relatório selado ou motivo de sigilo. N1/N2/administrador não acessam o cofre.

## Área 3 - Revisar e enviar ao N3

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [POST /validations/{id}/return](ENDPOINTS.md#post-validationsidreturn) | Permitir ao N2 devolver uma análise com o motivo da correção. | [ValidationReturn](../facial_recognition/schemas/validations.py#L87) → [ValidationReturnResponse](../facial_recognition/schemas/validations.py#L198) |
| [POST /validations/{id}/close](ENDPOINTS.md#post-validationsidclose) | Permitir ao N2 encerrar durante a revisão, informando motivo à equipe. | [ValidationClose](../facial_recognition/schemas/validations.py#L100) → [ValidationCloseResponse](../facial_recognition/schemas/validations.py#L216) |
| [POST /validations/{id}/report/send](ENDPOINTS.md#post-validationsidreportsend) | Enviar conclusão, risco e notícia preparada ao N3, preservando o conteúdo no cofre. | [VaultSend](../facial_recognition/schemas/vault.py#L19) → [VaultSendResponse](../facial_recognition/schemas/vault.py#L46) |

**Critérios de revisão:** Somente N2 da equipe revisa; ações exigem investigação em revisão; análise do N1 não é sobrescrita; envio não libera outra tarefa e não retorna conteúdo selado ao N2.

## Área 4 - Decidir e retirar notícias

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [POST /vault/dossiers/{id}/publish](ENDPOINTS.md#post-vaultdossiersidpublish) | Publicar a notícia preparada e finalizar a investigação. | Sem corpo JSON → [PublicationPublishResponse](../facial_recognition/schemas/publications.py#L71) |
| [POST /vault/dossiers/{id}/keep-restricted](ENDPOINTS.md#post-vaultdossiersidkeep-restricted) | Manter em sigilo, registrar motivo exclusivo do N3 e encerrar a investigação. | [VaultDecisionReason](../facial_recognition/schemas/vault.py#L164) → [VaultDecisionResponse](../facial_recognition/schemas/vault.py#L178) |
| [POST /vault/dossiers/{id}/request-validation](ENDPOINTS.md#post-vaultdossiersidrequest-validation) | Registrar pedido de nova investigação e encerrar a atual preservando o relatório. | [VaultDecisionReason](../facial_recognition/schemas/vault.py#L164) → [VaultDecisionResponse](../facial_recognition/schemas/vault.py#L178) |
| [POST /publications/{id}/withdraw](ENDPOINTS.md#post-publicationsidwithdraw) | Retirar notícia do público, preservando conteúdo e motivo exclusivo do N3. | [PublicationWithdraw](../facial_recognition/schemas/publications.py#L58) → [PublicationWithdrawResponse](../facial_recognition/schemas/publications.py#L88) |

**Critérios de revisão:** Somente N3 decide; decisão não altera o original nem duplica notícia; pedido chega ao N2 correto; retirada não reabre investigação; motivos privados não vazam.

## Área 5 - Integrar com Amanda

Usar uma análise enviada por Amanda para testar devolução, encerramento e envio ao N3. Testar publicação e consulta pública. Em outro relatório, pedir nova investigação e conferir se Amanda consegue abrir a tarefa vinculada ao pedido.

No acompanhamento de envios, `new_validation_request` pertence ao próprio dossiê: projetar motivo, data e atendimento já consultados em `vault`. Uma investigação que atendeu o pedido anterior pode gerar outro pedido; seu card deve mostrar o novo pedido pendente. Nas consultas da investigação, preservar o motivo que originou a tarefa. A regressão cobre duas gerações, seus motivos e vínculos de atendimento.

A lista de revisões do N2 usa as consultas de investigações de Amanda com filtro de situação; não criar uma rota nova só para isso. Você implementa as ações de revisão da etapa 3.

As operações compartilhadas de decisão e preservação do histórico sustentam estas rotas. Alterações devem manter as projeções de resposta e os testes de acesso permitido e negado.

## Como revisar uma alteração

- Seguir os campos, respostas, limites e complementos da rota em ENDPOINTS.md. Os exemplos deste plano não substituem o contrato.
- Executar testes de sucesso, dados inválidos, acesso negado e situação incompatível quando aplicável.
- Conferir gravações e consultas no PostgreSQL real; simulações não comprovam as garantias do banco.
- Revisar com Luiz antes de avançar para operações que dependem dessa etapa. Registrar evidências executadas e limitações restantes.
