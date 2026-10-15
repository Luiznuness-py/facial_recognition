# João - Revisão, cofre e notícias

Você desenvolve os endpoints de revisão pelo N2, decisão pelo N3 e consulta de notícias. Comece pelas notícias públicas, que permitem aprender o padrão de consultas sem depender do login.

Use dados fictícios preparados por Luiz enquanto Amanda desenvolve as investigações. Nas consultas privadas, use a autenticação/permissões dele. Nas decisões, use as funções de regra que ele entregar. Cada endpoint inclui entrada validada, consulta ou chamada da regra, resposta e testes.

Leia primeiro [Como funciona o sistema](BUSINESS_RULES.md). Consulte o contrato de cada rota em [ENDPOINTS.md](ENDPOINTS.md), as tabelas em [DATABASE.md](DATABASE.md) e o [exemplo completo](USE_CASES.md). Estes arquivos distribuem trabalho planejado; não afirmam que os endpoints já existem.

Todos os endereços abaixo começam com `/api/v1`. `{id}` e `{user_id}` representam identificadores do registro. `GET` consulta, `POST` cria ou executa uma ação, `PATCH` altera campos e `DELETE` remove o vínculo indicado.

## Etapa 1 - Consultar notícias públicas

| Endpoint | Para que serve |
| --- | --- |
| [GET /public/publications](ENDPOINTS.md#get-publicpublications) | Listar apenas notícias publicadas, sem exigir login. |
| [GET /public/publications/{id}](ENDPOINTS.md#get-publicpublicationsid) | Consultar uma notícia vigente com título, subtítulo, categoria, texto e data. |

**Concluir quando:** Notícia retirada não aparece e seu detalhe retorna 404; nenhuma resposta mostra equipe, percentual interno, relatório ou motivo privado.

## Etapa 2 - Consultar envios e cofre

| Endpoint | Para que serve |
| --- | --- |
| [GET /reports/sent](ENDPOINTS.md#get-reportssent) · [Complemento](ENDPOINTS.md#complemento-de-get-reportssent) | Permitir ao N2 acompanhar envios de sua equipe e pedidos de nova investigação. |
| [GET /vault/dossiers](ENDPOINTS.md#get-vaultdossiers) | Listar os relatórios selados para o N3. |
| [GET /vault/dossiers/{id}](ENDPOINTS.md#get-vaultdossiersid) | Mostrar ao N3 o relatório e a notícia preparada para decisão. |
| [GET /publications](ENDPOINTS.md#get-publications-e-get-publicationsid) | Permitir ao N3 listar notícias e suas situações. |
| [GET /publications/{id}](ENDPOINTS.md#get-publications-e-get-publicationsid) | Permitir ao N3 consultar uma publicação e seus metadados autorizados. |

**Concluir quando:** N2 recebe apenas os campos de acompanhamento e o pedido autorizado; não recebe o relatório selado ou motivo de sigilo. N1/N2/administrador não acessam o cofre.

## Etapa 3 - Revisar e enviar ao N3

| Endpoint | Para que serve |
| --- | --- |
| [POST /validations/{id}/return](ENDPOINTS.md#post-validationsidreturn) | Permitir ao N2 devolver uma análise com o motivo da correção. |
| [POST /validations/{id}/close](ENDPOINTS.md#post-validationsidclose) | Permitir ao N2 encerrar durante a revisão, informando motivo à equipe. |
| [POST /validations/{id}/report/send](ENDPOINTS.md#post-validationsidreportsend) | Enviar conclusão, risco e notícia preparada ao N3, preservando o conteúdo no cofre. |

**Concluir quando:** Somente N2 da equipe revisa; ações exigem investigação em revisão; análise do N1 não é sobrescrita; envio não libera outra tarefa e não retorna conteúdo selado ao N2.

## Etapa 4 - Decidir e retirar notícias

| Endpoint | Para que serve |
| --- | --- |
| [POST /vault/dossiers/{id}/publish](ENDPOINTS.md#post-vaultdossiersidpublish) | Publicar a notícia preparada e finalizar a investigação. |
| [POST /vault/dossiers/{id}/keep-restricted](ENDPOINTS.md#post-vaultdossiersidkeep-restricted) | Manter em sigilo, registrar motivo exclusivo do N3 e encerrar a investigação. |
| [POST /vault/dossiers/{id}/request-validation](ENDPOINTS.md#post-vaultdossiersidrequest-validation) | Registrar pedido de nova investigação e encerrar a atual preservando o relatório. |
| [POST /publications/{id}/withdraw](ENDPOINTS.md#post-publicationsidwithdraw) | Retirar notícia do público, preservando conteúdo e motivo exclusivo do N3. |

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
