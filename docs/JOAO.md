# João - Revisão, cofre e notícias

Você desenvolve os endpoints de revisão pelo N2, decisão pelo N3 e consulta de notícias. Comece pelas notícias públicas, que permitem aprender o padrão de consultas sem depender do login.

Use dados fictícios preparados por Luiz enquanto Amanda desenvolve as investigações. Nas consultas privadas, use a autenticação/permissões dele. Nas decisões, use as funções de regra que ele entregar. Cada endpoint inclui entrada validada, consulta ou chamada da regra, resposta e testes.

Leia primeiro [Como funciona o sistema](BUSINESS_RULES.md). Consulte o contrato de cada rota em [ENDPOINTS.md](ENDPOINTS.md), as tabelas em [DATABASE.md](DATABASE.md) e o [exemplo completo](USE_CASES.md). Estes arquivos distribuem trabalho planejado; não afirmam que os endpoints já existem.

Todos os endereços abaixo começam com `/api/v1`. `{id}` e `{user_id}` representam identificadores do registro. `GET` consulta, `POST` cria ou executa uma ação, `PATCH` altera campos e `DELETE` remove o vínculo indicado.

## Etapa 1 - Consultar notícias públicas

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /public/publications](ENDPOINTS.md#get-publicpublications) | Listar apenas notícias publicadas, sem exigir login. | [PublicPublicationQuery](../schemas/sc_publications.py#L105) → [ListResponse](../schemas/sc_base_model.py#L90) de [PublicPublicationResponse](../schemas/sc_publications.py#L13) |
| [GET /public/publications/{id}](ENDPOINTS.md#get-publicpublicationsid) | Consultar uma notícia vigente com título, subtítulo, categoria, texto e data. | Sem corpo JSON → [PublicPublicationResponse](../schemas/sc_publications.py#L13) |

**Concluir quando:** Notícia retirada não aparece e seu detalhe retorna 404; nenhuma resposta mostra equipe, percentual interno, relatório ou motivo privado.

## Etapa 2 - Consultar envios e cofre

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [GET /reports/sent](ENDPOINTS.md#get-reportssent) · [Complemento](ENDPOINTS.md#complemento-de-get-reportssent) | Permitir ao N2 acompanhar envios de sua equipe e pedidos de nova investigação. | [SentReportQuery](../schemas/sc_vault.py#L212) → [ListResponse](../schemas/sc_base_model.py#L90) de [SentReportResponse](../schemas/sc_vault.py#L82) |
| [GET /vault/dossiers](ENDPOINTS.md#get-vaultdossiers) | Listar os relatórios selados para o N3. | [VaultQuery](../schemas/sc_vault.py#L197) → [ListResponse](../schemas/sc_base_model.py#L90) de [VaultSummary](../schemas/sc_vault.py#L105) |
| [GET /vault/dossiers/{id}](ENDPOINTS.md#get-vaultdossiersid) | Mostrar ao N3 o relatório e a notícia preparada para decisão. | Sem corpo JSON → [VaultResponse](../schemas/sc_vault.py#L127) |
| [GET /publications](ENDPOINTS.md#get-publications-e-get-publicationsid) | Permitir ao N3 listar notícias e suas situações. | [PublicationQuery](../schemas/sc_publications.py#L118) → [ListResponse](../schemas/sc_base_model.py#L90) de [PublicationResponse](../schemas/sc_publications.py#L36) |
| [GET /publications/{id}](ENDPOINTS.md#get-publications-e-get-publicationsid) | Permitir ao N3 consultar uma publicação e seus metadados autorizados. | Sem corpo JSON → [PublicationResponse](../schemas/sc_publications.py#L36) |

**Concluir quando:** N2 recebe apenas os campos de acompanhamento e o pedido autorizado; não recebe o relatório selado ou motivo de sigilo. N1/N2/administrador não acessam o cofre.

## Etapa 3 - Revisar e enviar ao N3

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [POST /validations/{id}/return](ENDPOINTS.md#post-validationsidreturn) | Permitir ao N2 devolver uma análise com o motivo da correção. | [ValidationReturn](../schemas/sc_validations.py#L77) → [ValidationReturnResponse](../schemas/sc_validations.py#L188) |
| [POST /validations/{id}/close](ENDPOINTS.md#post-validationsidclose) | Permitir ao N2 encerrar durante a revisão, informando motivo à equipe. | [ValidationClose](../schemas/sc_validations.py#L90) → [ValidationCloseResponse](../schemas/sc_validations.py#L206) |
| [POST /validations/{id}/report/send](ENDPOINTS.md#post-validationsidreportsend) | Enviar conclusão, risco e notícia preparada ao N3, preservando o conteúdo no cofre. | [VaultSend](../schemas/sc_vault.py#L19) → [VaultSendResponse](../schemas/sc_vault.py#L46) |

**Concluir quando:** Somente N2 da equipe revisa; ações exigem investigação em revisão; análise do N1 não é sobrescrita; envio não libera outra tarefa e não retorna conteúdo selado ao N2.

## Etapa 4 - Decidir e retirar notícias

| Endpoint | Para que serve | Schemas de entrada → saída |
| --- | --- | --- |
| [POST /vault/dossiers/{id}/publish](ENDPOINTS.md#post-vaultdossiersidpublish) | Publicar a notícia preparada e finalizar a investigação. | Sem corpo JSON → [PublicationPublishResponse](../schemas/sc_publications.py#L71) |
| [POST /vault/dossiers/{id}/keep-restricted](ENDPOINTS.md#post-vaultdossiersidkeep-restricted) | Manter em sigilo, registrar motivo exclusivo do N3 e encerrar a investigação. | [VaultDecisionReason](../schemas/sc_vault.py#L164) → [VaultDecisionResponse](../schemas/sc_vault.py#L178) |
| [POST /vault/dossiers/{id}/request-validation](ENDPOINTS.md#post-vaultdossiersidrequest-validation) | Registrar pedido de nova investigação e encerrar a atual preservando o relatório. | [VaultDecisionReason](../schemas/sc_vault.py#L164) → [VaultDecisionResponse](../schemas/sc_vault.py#L178) |
| [POST /publications/{id}/withdraw](ENDPOINTS.md#post-publicationsidwithdraw) | Retirar notícia do público, preservando conteúdo e motivo exclusivo do N3. | [PublicationWithdraw](../schemas/sc_publications.py#L58) → [PublicationWithdrawResponse](../schemas/sc_publications.py#L88) |

**Concluir quando:** Somente N3 decide; decisão não altera o original nem duplica notícia; pedido chega ao N2 correto; retirada não reabre investigação; motivos privados não vazam.

## Etapa 5 - Integrar com Amanda

Usar uma análise enviada por Amanda para testar devolução, encerramento e envio ao N3. Testar publicação e consulta pública. Em outro relatório, pedir nova investigação e conferir se Amanda consegue abrir a tarefa vinculada ao pedido.

A lista de revisões do N2 usa as consultas de investigações de Amanda com filtro de situação; não criar uma rota nova só para isso. Você implementa as ações de revisão da etapa 3.

Luiz prepara as operações de decisão e preservação do histórico. Você conecta suas rotas a elas, seleciona os campos corretos das respostas e testa acesso permitido e negado.

## Como entregar cada etapa

- Seguir os campos, respostas, limites e complementos da rota em ENDPOINTS.md. Os exemplos deste plano não substituem o contrato.
- Executar testes de sucesso, dados inválidos, acesso negado e situação incompatível quando aplicável.
- Conferir gravações e consultas no PostgreSQL real; simulações não comprovam as garantias do banco.
- Revisar com Luiz antes de avançar para operações que dependem dessa etapa. Registrar o que foi testado e o que ainda falta.
