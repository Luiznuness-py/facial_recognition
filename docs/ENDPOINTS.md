# Endpoints — chamadas do sistema e suas finalidades

Este arquivo é a referência para desenvolver a comunicação entre as telas e o servidor. Um endpoint é o endereço usado para executar uma ação ou consultar informações. `GET` consulta, `POST` executa uma ação ou cria um registro, `PATCH` altera campos e `DELETE` remove um vínculo quando permitido.

Para entender o funcionamento sem detalhes técnicos, leia [Como funciona o sistema](BUSINESS_RULES.md). O [banco alvo](DATABASE_TARGET.md) descreve as tabelas e o [exemplo completo](USE_CASES.md) mostra uma investigação preenchida.

**Estado:** estes endpoints são contratos planejados. Este documento não comprova que as rotas estejam implementadas ou testadas. As escolhas técnicas continuam sujeitas à revisão e aos testes indicados abaixo.

## Onde encontrar cada ação

| Grupo de endpoints | Para que serve |
| --- | --- |
| `/auth/*` | Entrar, cadastrar ou reconhecer a face, definir ou alterar senha, renovar e encerrar sessão. |
| `/access-requests*`, `/users*`, `/teams` | Solicitar e aprovar acesso, administrar contas e consultar equipes. |
| `/biological-agents*` | Cadastrar e consultar amostras, corrigir cadastro, ativar/inativar e abrir investigações. |
| `/validations*` | Salvar e enviar análises, gerir colaboradores e responsável, revisar e encaminhar ao N3. |
| `/reports/sent` | Acompanhar envios e pedidos do N3 sem acessar o conteúdo selado. |
| `/vault/dossiers*` | Consultar o cofre e decidir publicação, sigilo ou nova investigação. |
| `/publications*` | Consultar e retirar notícias pelo N3. |
| `/public/publications*` | Consultar notícias autorizadas sem login. |
| `/admin/*` | Consultar auditoria administrativa, papéis e permissões. |
| `/health` | Conferir se o processo responde. |

Todos os endereços têm o prefixo `/api/v1`. Os contratos abaixo detalham quem pode chamar, os dados recebidos, as verificações e a resposta. Os complementos de contrato também fazem parte da definição da rota.

## 1. Como chamamos a API

Todos os caminhos abaixo começam com `/api/v1`. Listas recebem `limit` (padrão 20, máximo 100), `offset` (padrão 0) e filtros descritos; respondem `{items,total,limit,offset}`. Total respeita os mesmos acessos. IDs são UUIDs; datas UTC com fuso; campo desconhecido é rejeitado. Campos vazios de motivo/texto obrigatório são inválidos.

Toda rota privada usa Access e conta/sessão habilitada, salvo as etapas de autenticação explicitadas. Toda alteração usa CSRF. A seção abaixo diz por que existe, quem usa, entrada, conferência e resposta de cada rota.

### Erros

401: precisa autenticar; 403: ação não permitida; 404: não existe ou não está no seu escopo; 409: duplicidade ou estado incompatível; 413: upload grande; 422: campo inválido; 429: limite; 503: indisponível. Corpo de erro `{error:{code,message,request_id}}`; erro de campo pode acrescentar lista `fields`, sem valores secretos. Respostas selecionam campos explicitamente. Nenhuma resposta contém senha, hash, vetor ou token de autenticação completo.


### `POST /auth/login`

| Método | Path | Descrição | Parm. Obrigatórios | Exemplo de Resposta |
|--------|------|-----------|------------------|----------------------|
| `POST` | `/auth/login` | Inicia o processo de login | `email, password` | `{next_step: "ENROLL_FACE", expires_in: 300}` |

Confere email e senha e escolhe a próxima etapa. Existe para iniciar o acesso sem liberar o laboratório antes da biometria e da troca obrigatória de senha.

- Quem/credencial: Conforme a credencial e a etapa descritas abaixo.
- Recebe: JSON `email,password`.
- Confere e faz: Rate limit; hash; aprovação; conta habilitada; validade temporária. ADMIN sem biometria. Demais recebem etapa determinada pelo servidor.
- Responde: 200: `next_step,expires_in`; JWT restrito em cookie HttpOnly ou sessão completa para ADMIN.

### `POST /auth/biometric/enroll`

| Método | Path | Descrição | Parm. Obrigatórios | Exemplo de Resposta |
|--------|------|-----------|------------------|----------------------|
| `POST` | `/auth/biometric/enroll` | Cadastra a face quando existe autorização de primeiro acesso ou recuperação | Cookie HTTPOnly + `frames` (imagens) | `{next_step: "CHANGE_PASSWORD", expires_in: 300}` |

Cadastra a face quando existe autorização de primeiro acesso ou recuperação. Não é uma rota para trocar a identidade por conta própria.

- Quem/credencial: Conforme a credencial e a etapa descritas abaixo.
- Recebe: Cookie restrito HttpOnly; multipart `frames` repetidos.
- Confere e faz: Etapa ENROLL_FACE, 5 min, autorização explícita, até 3 falhas; limites HTTP/imagem e pipeline; criptografa embeddings. Não cadastra novamente só por faltar vetor.
- Responde: 200: próximo JWT CHANGE_PASSWORD de 5 min, ou sessão se senha definitiva já válida e recuperação apenas facial.

### `POST /auth/biometric`

| Método | Path | Descrição | Parm. Obrigatórios | Exemplo de Resposta |
|--------|------|-----------|------------------|----------------------|
| `POST` | `/auth/biometric` | Confirma a identidade e a presença real da pessoa esperada | Cookie HTTPOnly + `frames` | `{next_step: "LOGIN", expires_in: 300}` |

Confirma a identidade e a presença real da pessoa esperada. É a segunda etapa de acesso ou a prova exigida para mudar senha.

- Quem/credencial: Conforme a credencial e a etapa descritas abaixo.
- Recebe: Cookie restrito HttpOnly; multipart `frames`.
- Confere e faz: Etapa VERIFY_FACE, prazo, falhas; compara somente templates do usuário esperado e versão compatível; reconhecimento AND anti-spoofing. Consome etapa atomicamente.
- Responde: 200: JWT CHANGE_PASSWORD ou sessão completa; reprovação controlada sem scores internos.

### `POST /auth/password/complete`

| Método | Path | Descrição | Parm. Obrigatórios | Exemplo de Resposta |
|--------|------|-----------|------------------|----------------------|
| `POST` | `/auth/password/complete` | Finaliza a ativação ou recuperação com uma senha definitiva | Cookie HTTPOnly + `new_password,password_confirmation` | `{next_step: "LOGIN", expires_in: 300}` |

Finaliza a ativação ou recuperação com uma senha definitiva. Só então libera a sessão normal.

- Quem/credencial: Conforme a credencial e a etapa descritas abaixo.
- Recebe: Cookie restrito HttpOnly; JSON `new_password,password_confirmation`.
- Confere e faz: Etapa CHANGE_PASSWORD, prazo, biometria concluída quando exigida; política de senha e confirmação; hash; limpa flag e invalida temporária/tentativa.
- Responde: 200: sessão completa.

### `POST /auth/refresh`

| Método | Path | Descrição | Parm. Obrigatórios | Exemplo de Resposta |
|--------|------|-----------|------------------|----------------------|
| `POST` | `/auth/refresh` | Renova os cookies quando o access vence, evitando pedir biometria a cada quinze minutos, sem aumentar as 24 horas da sessão. | Cookie HttpOnly + CSRF | `{validade: "2026-01-01T00:00:00Z"}` |

Renova os cookies quando o access vence, evitando pedir biometria a cada quinze minutos, sem aumentar as 24 horas da sessão.

- Quem/credencial: Conforme a credencial e a etapa descritas abaixo.
- Recebe: Refresh Token opaco em cookie HttpOnly e CSRF.
- Confere e faz: Hash, rotação, replay, sessão/conta; mantém limite absoluto de 24h.
- Responde: 200: validade/metadados, sem tokens no JSON; cookies access e refresh substituídos.

### `POST /auth/logout`

| Método | Path | Descrição | Parm. Obrigatórios | Exemplo de Resposta |
|--------|------|-----------|------------------|----------------------|
| `POST` | `/auth/logout` | Encerra o contexto de acesso e limpa os cookies para que Sair tenha efeito no servidor, não apenas na tela. | Sessão, refresh válido ou JWT restrito, CSRF | `{"status":"success"}` |

Encerra o contexto de acesso e limpa os cookies para que Sair tenha efeito no servidor, não apenas na tela.

- Quem/credencial: Conforme a credencial e a etapa descritas abaixo.
- Recebe: Sessão, refresh ainda válido ou JWT restrito, conforme fluxo; CSRF.
- Confere e faz: Revoga sessão/token ou cancela tentativa; limpa cookie; não expõe credenciais.
- Responde: 204.

### `GET /auth/me`

Diz à tela quem está autenticado e quais menus mostrar. Não é uma autorização para confiar apenas no frontend.

- Quem/credencial: Conforme a credencial e a etapa descritas abaixo.
- Recebe: Sessão.
- Confere e faz: Conta/sessão atual.
- Responde: 200: `id,name,email,role,team,permissions` para orientar UI; UI não substitui autorização.

### `POST /access-requests`

| Método | Path | Descrição | Parm. Obrigatórios | Exemplo de Resposta |
|--------|------|-----------|------------------|----------------------|
| `POST` | `/access-requests` | Permite que N2/N3 solicitem acesso e que ADMIN cadastre diretamente, sem abrir cadastro ao público. | `name,email,temporary_password`; `role_code,team_id` somente quando permitidos | `{"id":"123e4567-e89b-12d3-a456-426614174000","status":"PENDING"}` |

Permite que N2/N3 solicitem acesso e que ADMIN cadastre diretamente, sem abrir cadastro ao público.

- Quem/credencial: `accounts.request`: N2/N3/ADMIN
- Recebe: `name,email,temporary_password`; `role_code,team_id` somente quando permitidos.
- Confere e faz: N2 força N1 e sua equipe; N3 somente N2; ADMIN N1/N2/N3. Email único, política de senha e equipe válida. Guarda dados/hash no pedido, sem criar usuário pendente de aprovação. ADMIN aprova e cria conta na mesma transação.
- Responde: 201: solicitação e estado; cadastro ADMIN inclui vínculo da conta criada, nunca senha/hash.

### `GET /access-requests`

| Método | Path | Descrição | Parm. Obrigatórios | Exemplo de Resposta |
|--------|------|-----------|------------------|----------------------|
| `GET` | `/access-requests` | Alimenta a lista de solicitações que o solicitante acompanha ou ADMIN decide. | Paginação/status | `{"items":[{"id":"123e4567-e89b-12d3-a456-426614174000","status":"PENDING"}],"total":1,"limit":20,"offset":0}` |

Alimenta a lista de solicitações que o solicitante acompanha ou ADMIN decide.

- Quem/credencial: `accounts.request.read`
- Recebe: Paginação/status.
- Confere e faz: N2/N3 próprias; ADMIN todas.
- Responde: 200: lista sanitizada.

### `GET /access-requests/{id}`

Mostra os dados e a decisão de um pedido autorizado, inclusive o motivo de rejeição.

- Quem/credencial: `accounts.request.read`
- Recebe: UUID.
- Confere e faz: Solicitante ou ADMIN.
- Responde: 200: pedido, decisão e motivo.

### `POST /access-requests/{id}/approve`

Cria a conta aprovada e reserva a posição N2/N3, iniciando a validade da temporária.

- Quem/credencial: `accounts.approve`: ADMIN
- Recebe: Sem corpo.
- Confere e faz: Pendente; email disponível e vaga N2/N3 não ocupada por conta ativa ou pendente de ativação; cria usuário, reserva posição, associa pedido, estabelece hash na conta e início das 24h e remove hash do pedido atomicamente; não altera dados solicitados.
- Responde: 200: solicitação aprovada e identificador/estado da conta; 409 se vaga ocupada.

### `POST /access-requests/{id}/reject`

Encerra o pedido com explicação, sem criar conta nem manter seu hash temporário.

- Quem/credencial: `accounts.approve`: ADMIN
- Recebe: `reason`.
- Confere e faz: Pendente, motivo obrigatório; encerra sem criar usuário e remove hash do pedido na mesma transação; preserva histórico.
- Responde: 200: solicitação rejeitada.

### `GET /users` e `GET /users/{id}`

Permite ao administrador localizar e consultar contas sem ler faces ou conteúdo do laboratório.

- Quem/credencial: `accounts.manage`: ADMIN
- Recebe: Filtros/paginação ou UUID.
- Confere e faz: Escopo administrativo.
- Responde: 200: dados/status/flags, sem templates ou segredos.

### `PATCH /users/{id}`

Permite ao administrador corrigir dados institucionais e papel/grupo mantendo a identidade e a história.

- Quem/credencial: `accounts.manage`: ADMIN
- Recebe: Campos permitidos `name,email,role_code,team_id`.
- Confere e faz: Somente ADMIN; email válido/sem duplicidade; coerência papel/equipe e disponibilidade N2/N3 contando ativas/pendentes. Mudança de email ou permissões revoga sessões/tentativas e gera auditoria em transação.
- Responde: 200: conta atualizada; 409 se email/vaga ocupados.

### `POST /users/{id}/deactivate`

Bloqueia uma pessoa e suas credenciais sem apagar registros anteriores.

- Quem/credencial: `accounts.manage`: ADMIN
- Recebe: `reason`.
- Confere e faz: Bloqueia conta ativa ou pendente de ativação, cancela tentativas e revoga sessões; libera posição N2/N3, preserva identidade/email/histórico.
- Responde: 200: conta desativada.

### `POST /users/{id}/reactivate`

Permite voltar ao sistema com nova senha e biometria, sem criar outra identidade ou perder história.

- Quem/credencial: `accounts.manage`: ADMIN
- Recebe: `temporary_password,reason`.
- Confere e faz: DISABLED; cargo/equipe e vaga disponíveis; reserva posição N2/N3, redefine senha e face obrigatoriamente, revoga sessões/tentativas e autoriza ativação em transação.
- Responde: 200: PENDING_ACTIVATION, validade e etapas, sem senha/hash; 409 se vaga ocupada.

### `POST /users/{id}/activation/revalidate`

Renova a mesma senha temporária quando a pessoa não terminou a ativação dentro de 24 horas.

- Quem/credencial: `accounts.manage`: ADMIN
- Recebe: Sem corpo.
- Confere e faz: Conta aprovada com ativação incompleta e senha temporária; mantém hash e face, renova 24h e cancela tentativas anteriores.
- Responde: 200: nova validade e etapa exigida.

### `POST /users/{id}/recovery`

Autoriza a recuperação de senha, rosto ou ambos. Separa recuperação administrada de um cadastro facial livre.

- Quem/credencial: `accounts.manage`: ADMIN
- Recebe: `mode`: PASSWORD/BIOMETRIC/BOTH; `reason`; `temporary_password` para senha.
- Confere e faz: Conta habilitada; hash temporário quando necessário; para face remove vetores e autoriza cadastro na mesma transação; revoga sessões/tentativas.
- Responde: 200: requisitos e validade, sem senha.

### `GET /teams`

Fornece os grupos para seleção autorizada em formulários de conta; não transfere agentes entre grupos.

- Quem/credencial: `teams.read`: usuários autenticados
- Recebe: Paginação.
- Confere e faz: Catálogo de equipes habilitadas.
- Responde: 200: `id,code,name,description`.

### `POST /biological-agents`

Registra a amostra e cria a primeira tarefa do N1, sem misturar o cadastro com a conclusão científica.

- Quem/credencial: `agents.create`: N1
- Recebe: `provisional_label,material_type,collection_location,collected_on,initial_observations,investigation_reason` obrigatórios e `known_information` opcional.
- Confere e faz: N1 ativo; grupo derivado; agente ACTIVE; cria agente e primeira validação OPEN com criador responsável em transação.
- Responde: 201: agente e primeira validação.

### `GET /biological-agents`

Monta a lista de agentes ativos/inativos que a pessoa pode consultar.

- Quem/credencial: `agents.read`: N1/N2
- Recebe: Paginação/pesquisa; filtro ativo/inativo.
- Confere e faz: N1 com responsabilidade/participação autorizada; N2 equipe; inclui inativos para consulta do histórico e filtra totais.
- Responde: 200: cadastro permitido, sem análises invisíveis.

### `GET /biological-agents/{id}`

Abre o cadastro de um agente, mantendo separados os cards das validações.

- Quem/credencial: `agents.read`: N1/N2
- Recebe: ID.
- Confere e faz: Vínculo autorizado ou N2 do grupo.
- Responde: 200: cadastro e situação geral; não inclui todas as validações por existir vínculo com uma.

### `GET /biological-agents/{id}/validations`

Monta os cards da página do agente, incluindo apenas tarefas que o usuário pode ler.

- Quem/credencial: `validations.read`: N1/N2
- Recebe: Paginação/status.
- Confere e faz: N1 somente responsável/participante de cada tarefa; N2 grupo.
- Responde: 200: cards autorizados, total filtrado.

### `POST /biological-agents/{id}/validations`

Permite ao supervisor atribuir outra investigação do mesmo agente quando a anterior terminou.

- Quem/credencial: `validations.create`: N2
- Recebe: `responsible_user_id`.
- Confere e faz: Mesmo grupo, agente ativo, N1 ativo; nenhuma validação OPEN/IN_REVIEW/RETURNED/REPORTED; cria nova OPEN e responsável em transação.
- Responde: 201: nova tarefa.

### `GET /validations/{id}`

Mostra o formulário científico, equipe e história autorizada de uma tarefa.

- Quem/credencial: `validations.read`: responsável/participante N1 ou N2 do grupo
- Recebe: ID.
- Confere e faz: Vínculo atual e grupo; conteúdo permitido por estado; sem relatório/ficha selados.
- Responde: 200: análise, participantes, estado e metadados permitidos.

### `PATCH /validations/{id}/analysis`

Salva o trabalho parcial ou corrigido do único responsável; não envia automaticamente para revisão.

- Quem/credencial: `analyses.write`: somente N1 responsável
- Recebe: `assessments_performed,observed_results,technical_opinion,recommendation,estimated_risk_percentage`; no PATCH só enviar os campos que deseja alterar.
- Confere e faz: OPEN/RETURNED; confirma responsável no servidor, não basta participar; salva parcial.
- Responde: 200: análise atual.

### `POST /validations/{id}/submit`

Entrega a análise completa ao supervisor e preserva uma cópia com a equipe daquele momento.

- Quem/credencial: `analyses.write`: somente N1 responsável
- Recebe: Sem corpo.
- Confere e faz: Responsável; análise completa; snapshot da entrega e participantes; IN_REVIEW atômico.
- Responde: 200: estado/data.

### `GET /validations/{id}/participants`

Mostra quem integra a tarefa atual sem expor o diretório inteiro de usuários.

- Quem/credencial: `validations.read`
- Recebe: ID.
- Confere e faz: Leitura autorizada e grupo.
- Responde: 200: participantes mínimos, sem diretório global.

### `GET /validations/{id}/participant-candidates`

Fornece os N1 do grupo que podem ser convidados, sem mostrar pessoas de outro grupo.

- Quem/credencial: `validations.share`: N1 responsável ou N2 supervisor do grupo
- Recebe: Pesquisa/paginação.
- Confere e faz: Ator autorizado na validação; candidatos N1 ativos do mesmo grupo; N2 somente grupo supervisionado; sem expor outro grupo.
- Responde: 200: candidatos mínimos.

### `POST /validations/{id}/participants`

Compartilha a investigação com um N1 apenas em leitura.

- Quem/credencial: `validations.share`: N1 responsável ou N2 supervisor do grupo
- Recebe: `user_id`.
- Confere e faz: Ator N1 responsável ou N2 supervisor habilitado do grupo da validação; alvo N1 ativo desse grupo, sem duplicata; vínculo exclusivamente de leitura; estado OPEN/RETURNED, preservando participantes das entregas anteriores.
- Responde: 201: compartilhamento em leitura.

### `POST /validations/{id}/return`

Devolve a entrega ao responsável com o que precisa ser corrigido.

- Quem/credencial: `validations.review`: N2 do grupo
- Recebe: `reason`.
- Confere e faz: IN_REVIEW; motivo obrigatório até 1.500 caracteres; preserva entrega e devolve para o responsável; motivo visível ao responsável e colaboradores autorizados.
- Responde: 200: RETURNED e motivo.

### `POST /validations/{id}/close`

Permite ao supervisor encerrar uma entrega durante a revisão, explicando o motivo à equipe.

- Quem/credencial: `validations.review`: N2 do grupo
- Recebe: `reason` obrigatório, até 1.500 caracteres.
- Confere e faz: N2 ativo do grupo; somente IN_REVIEW; grava CLOSED/motivo/autor/data, preserva conteúdo e libera vaga em transação; motivo consultável pelo responsável e colaboradores autorizados.
- Responde: 200: estado, motivo e autoria/data do encerramento.

### `POST /validations/{id}/report/send`

Sela a conclusão do supervisor e a ficha pronta para divulgação, entregando-as ao ministro.

- Quem/credencial: `reports.send`: N2 do grupo
- Recebe: `title,final_conclusion,final_risk_percentage,public_title,public_subtitle?,public_risk_category,public_body`.
- Confere e faz: IN_REVIEW; campos completos e grupo; sela cópia recebida/participantes, relatório e ficha; protocolo e REPORTED em transação, sem liberar outra validação.
- Responde: 200: protocolo/situação, sem conteúdo selado.

### `GET /reports/sent`

Permite ao supervisor acompanhar o destino do envio e receber pedidos de nova investigação sem ler o cofre.

- Quem/credencial: `reports.read`: N2 supervisor
- Recebe: Paginação, busca e situação.
- Confere e faz: Somente validações enviadas do grupo supervisionado; totais filtrados; seleciona campos permitidos, sem leitura completa do cofre.
- Responde: 200: cards com `validation_id,title,agent:{id,code,provisional_label},decision_status,protocol` — campos escolhidos para a resposta.

### `GET /vault/dossiers`

Monta a lista do cofre exclusivo do ministro.

- Quem/credencial: `vault.read`: N3
- Recebe: Paginação/protocolo/situação.
- Confere e faz: Consulta metadados dos originais selados.
- Responde: 200: lista filtrada.

### `GET /vault/dossiers/{id}`

Abre o relatório original e a prévia da notícia para decisão do ministro.

- Quem/credencial: `vault.read`: N3
- Recebe: ID.
- Confere e faz: Audita leitura do original e ficha preparada.
- Responde: 200: conteúdo autorizado e situação de divulgação.

### `POST /vault/dossiers/{id}/publish`

Publica a ficha preparada sem expor o relatório interno e libera outra tarefa.

- Quem/credencial: `publications.publish`: N3
- Recebe: Sem conteúdo editável.
- Confere e faz: Dossiê completo em WAITING_N3, validação REPORTED; copia somente ficha aprovada para publicação, com data/autor; muda sua validação REPORTED para PUBLISHED e libera vaga; unicidade/auditoria em transação.
- Responde: 200: ID público, PUBLISHED e data; aprovação já vigente não duplica.

### `POST /vault/dossiers/{id}/keep-restricted`

Registra a decisão de manter o conteúdo interno e encerra a tarefa correspondente.

- Quem/credencial: `vault.decide`: N3
- Recebe: `reason` obrigatório, até 1.500 caracteres; leitura somente N3.
- Confere e faz: Dossiê WAITING_N3 e validação REPORTED; registra sigilo, fecha a validação em CLOSED e libera vaga em transação, sem editar original.
- Responde: 200: decisão, validação encerrada e situação.

### `GET /publications` e `GET /publications/{id}`

Permite ao ministro acompanhar notícias e retiradas, sem confundir essa lista com o cofre.

- Quem/credencial: `publications.read`: N3
- Recebe: Paginação ou ID.
- Confere e faz: Consulta conteúdo público e metadados das decisões/retirada; não concede acesso a outro perfil.
- Responde: 200: publicação e situação.

### `POST /publications/{id}/withdraw`

Tira a notícia da consulta pública, preservando conteúdo e motivo reservado no histórico.

- Quem/credencial: `publications.publish`: N3
- Recebe: `reason` obrigatório, até 1.500 caracteres; leitura somente N3.
- Confere e faz: Retira da consulta pública, preservando conteúdo/histórico; repetição não apaga registro.
- Responde: 200: WITHDRAWN.

### `GET /public/publications`

Fornece a lista de notícias vigentes para quem não está autenticado.

- Quem/credencial: Público
- Recebe: Paginação/pesquisa.
- Confere e faz: Somente PUBLISHED; usa cópia pública, nunca cofre.
- Responde: 200: notícias autorizadas.

### `GET /public/publications/{id}`

Mostra uma notícia autorizada em layout fixo, sem consulta ao cofre.

- Quem/credencial: Público
- Recebe: ID público.
- Confere e faz: Vigente; retirada/inexistente retorna 404.
- Responde: 200: `id,title,subtitle?,risk_category,body,published_at`.

### `GET /admin/audit-events`

Permite revisar eventos administrativos sem revelar conteúdo científico ou motivos exclusivos do ministro.

- Quem/credencial: `audit.read`: ADMIN
- Recebe: Paginação/evento/usuário/período.
- Confere e faz: Somente metadados administrativos e de acesso; sem conteúdo de análises/relatórios/cofre.
- Responde: 200: eventos sanitizados.

### `GET /admin/roles`

Mostra o catálogo de papéis e suas permissões; não cria um editor de permissões.

- Quem/credencial: `authorization.read`: ADMIN
- Recebe: Nenhuma.
- Confere e faz: Catálogo.
- Responde: 200: papéis e permissões associadas.

### `GET /admin/permissions`

Mostra as ações conhecidas pela autorização central.

- Quem/credencial: `authorization.read`: ADMIN
- Recebe: Nenhuma.
- Confere e faz: Catálogo.
- Responde: 200: ações conhecidas.

### `GET /health`

Indica que o processo responde, sem revelar banco, segredos ou diagnóstico interno.

- Quem/credencial: Pública
- Recebe: Nenhuma.
- Confere e faz: Liveness simples, sem detalhes de infraestrutura.
- Responde: 200: estado básico.

### `GET /auth/csrf`

Prepara a proteção contra chamadas forjadas antes de login ou operações privadas. Rota pública de preparação, sem acesso a dados.

Recebe os cookies atuais. Emite contexto aleatório HttpOnly quando anônimo e devolve `{csrf_token}` assinado, vinculado ao contexto anônimo, tentativa ou sessão válida. JavaScript guarda esse token de proteção só em memória e envia `X-CSRF-Token` nas alterações. Não é token de autenticação. Se contexto inválido, não tratá-lo como prova autenticada; criar contexto anônimo. Não aceita chamada cross-site nem habilita CORS de terceiros. Retorna 200; não renova a sessão.

### `GET /auth/flow`

Ao recarregar a página de face/senha, informa a etapa ainda permitida, sem prolongá-la. Usa cookie restrito, valida a tentativa e retorna `{operation,next_step,expires_in}`; expirado retorna 401.

### `POST /auth/password-change/start` e `POST /auth/password-change/complete`

Start: sessão válida, CSRF e `current_password`. Confere hash e cria tentativa PASSWORD_CHANGE ligada à sessão: VERIFY_FACE para N1/N2/N3; CHANGE_PASSWORD para ADMIN. Retorna 200 e próximo passo em cookie restrito. Não revoga a sessão apenas por iniciar.

Complete: sessão iniciadora ainda válida, cookie CHANGE_PASSWORD da mesma operação, CSRF e `new_password,password_confirmation`. Confere face quando exigida, atualiza hash e revoga todas as sessões/tentativas atomicamente. Retorna 200 `{next_step:"LOGIN"}` e limpa cookies. A rota biométrica reconhece a operação e, neste caso, não cria nova sessão ao aprovar face.

### `PATCH /biological-agents/{id}`

Permite corrigir cadastro antes do primeiro envio. Criador N1 com vínculo autorizado ou N2 do grupo; Access e CSRF. Recebe qualquer subconjunto dos sete campos cadastrais; campos enviados devem cumprir limites. Confere que não existe entrega anterior do agente e grava alteração/auditoria. Retorna 200 com cadastro; após primeira entrega retorna 409.

### `PATCH /biological-agents/{id}/status`

N2 do grupo ativa/inativa o agente. Recebe `{status:"ACTIVE"}` ou `{status:"INACTIVE"}` com Access e CSRF. Desativar confere ausência de tarefa em andamento, em transação. Retorna 200 `{id,status}`; se tarefa aberta, 409. Não modifica publicação/histórico.

### `GET /biological-agents/{id}/responsible-candidates`

N2 precisa escolher responsável para próxima tarefa sem consultar diretório de outro grupo. Access, permissão de criar validação e grupo do agente. Recebe busca/paginação, devolve 200 com N1 ativos do grupo, apenas ID/nome; não exige existir validação nova para consultar candidatos.

### `DELETE /validations/{id}/participants/{user_id}`

N2 do grupo remove um colaborador em OPEN/RETURNED. Access e CSRF, sem corpo. Não remove o responsável; elimina vínculo atual, guarda auditoria e não apaga entregas anteriores. Retorna 204; vínculo ausente retorna 404.

### `PATCH /validations/{id}/responsible`

N2 do grupo troca responsável em OPEN/RETURNED. Recebe `{responsible_user_id}`. Confere N1 ativo do grupo, mantém anterior como colaborador e torna novo o único editor, sem duplicar vínculos. Retorna 200 com responsável e participantes; entregas antigas não mudam.

### `POST /vault/dossiers/{id}/request-validation`

N3 pede outra investigação, não edição do original. Access, CSRF, `vault.decide` e `{reason}` obrigatório até 1.500. Só dossiê aguardando decisão e validação REPORTED. Registra pedido e fecha a anterior numa transação. Retorna 200 com situação NEW_VALIDATION_REQUESTED e validação CLOSED. N2 do grupo vê motivo no card; outro perfil não ganha o cofre.

### Complemento de `POST /biological-agents/{id}/validations`

Além de `responsible_user_id`, recebe `request_dossier_id` opcional quando atende pedido N3. Confere mesmo agente/grupo, pedido pendente e ausência de validação ativa. Cria tarefa e marca atendimento atomicamente. Se há pedido pendente para o agente, a próxima tarefa deve vinculá-lo; não deixar um pedido ativo e criar tarefas desvinculadas. Retorna 201 com tarefa e motivo autorizado. Novo responsável escolhe colaboradores depois.

### Complemento de `GET /reports/sent`

Além do título, agente, protocolo e situação, retorna `dossier_id` como identificador da ação (não autorização de leitura), e `new_validation_request:{reason,requested_at,fulfilled_validation_id}` somente quando há pedido. N2 nunca recebe o motivo de sigilo/retirada. Situação do card: WAITING_N3, PUBLISHED, RESTRICTED, NEW_VALIDATION_REQUESTED; se publicada e retirada, mostrar WITHDRAWN. Um pedido atendido continua registrado com o ID da nova tarefa.

### Complemento das consultas de validação

`GET /validations/{id}` e cards devolvem motivo de encerramento N2, motivos de devolução e pedido N3 autorizado à equipe desta tarefa. Não copiam motivo de sigilo de outro campo. N1 vê sua análise e entregas, mesmo depois do encerramento, enquanto possuir vínculo atual; isso não é leitura da cópia ministerial. N2 revisa essas entregas, mas não lê campos internos do dossiê após envio.

## 2. Escolhas para fechar a implementação — revisão final

Estas escolhas completam o plano; foram feitas agora dentro do pedido de consolidar, não são uma alegação de teste ou aprovação anterior.

### Cookies e validação

JWT HS256, chave aleatória de pelo menos 32 bytes para access, outra para restrito e outra para CSRF; fora do banco/repositório. Algoritmo fixo no servidor. `iss="aps-lab"`; `aud="aps-lab-api"`. Claims comuns `sub,type,jti,iat,exp,iss,aud`; restrito inclui `attempt_id,stage,operation`; access inclui `session_id`. `type` é RESTRICTED ou ACCESS. JWT assinado não é conteúdo secreto: não incluir senha, face, parecer ou permissões como única prova.

Cookies `lab_access` (Path `/api/v1`), `lab_refresh` (Path `/api/v1/auth`), `lab_stage` (Path `/api/v1/auth`) e `lab_csrf_context` (Path `/api/v1`): HttpOnly, SameSite=Strict, sem Domain. Emissão normal de sessão limpa cookie de etapa. Limpeza usa mesmo nome/Path. Max-Age corresponde ao prazo real restante. Respostas privadas/autenticação: `Cache-Control: no-store`.

Escolha local: servir front e API na MESMA origem HTTPS, com certificado local confiável, e cookies Secure=true. A preparação desse HTTPS ainda será implementada, sem exigir deploy ou Nginx. Para testes isolados HTTP de desenvolvedor, Secure=false só em configuração explícita de desenvolvimento e loopback; esse modo não é o padrão nem funciona como configuração para rede. HTTPS também permite a câmera com navegador; autorização de câmera continua necessária.

CSRF: token aleatório com assinatura HMAC ligada ao contexto, nunca double-submit sem assinatura. GET de preparação devolve token, e cada POST/PATCH/DELETE verifica header, assinatura e contexto. Confirmar Origin exata; quando Origin ausente, conferir origem do Referer; ausência de ambos em mutação browser é negada. Bloquear `Sec-Fetch-Site: cross-site`; não habilitar CORS para terceiros. Rotacionar contexto após login, mudança de etapa, renovação ou logout; frontend busca novo CSRF. Token CSRF pode ser lido pelo JavaScript; tokens de autenticação não.

Base da escolha: [OWASP sobre CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) e [OWASP sobre segurança REST](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html). SameSite complementa CSRF; algoritmo permitido não é escolhido pelo header recebido.

### Limites iniciais de desenvolvimento

Um processo backend. Rate limit em memória por IP e operação: login 10/minuto; refresh 30/minuto; chamadas de biometria 6/minuto; demais alterações 60/minuto; leituras 120/minuto. A janela é fixa de 60 segundos; excesso retorna 429 e Retry-After. Não confiar em X-Forwarded-For sem proxy conhecido. Reiniciar limpa rate limit, mas NÃO a contagem biométrica persistida por usuário.

JSON até 256 KiB. Multipart biométrico até 16 MiB no total, até 20 imagens, cada arquivo até 1 MiB, JPEG/PNG, largura até 1.920, altura até 1.080 e área até 2.073.600 pixels. São tetos de transporte, não a quantidade final de frames do modelo. Verificar bytes reais, formato, dimensões e decodificação limitada; nome/MIME informados não provam tipo. Frames apenas em memória, descartados ao terminar. Uma execução biométrica por vez; se ocupada, 429 com Retry-After=1, sem fila ilimitada; timeout de 30 segundos retorna 503 e não conta fraude. Não liberar a vaga do processamento enquanto o trabalho subjacente ainda estiver rodando.

Os modelos definirão quantidade/intervalo de frames, crops, limiares, resolução interna e agregação; estes parâmetros não podem ser fechados com honestidade antes dos testes. Interface do sistema: entrada validada e usuário esperado; saída aprovado/reprovado/qualidade insuficiente/indisponível, sem expor embeddings ou scores ao cliente.

### Concorrência, persistência e segurança da tela

Transações e bloqueio por agente para cadastro/envio/edição/estado/criação/decisão; índices únicos como segunda proteção. Bloqueio por email normalizado para pedido/criação/aprovação/correção, sempre na mesma ordem; reserva N2 com bloqueio do grupo e N3 com bloqueio global da posição. Bloquear usuário em contadores/recuperações/trocas de credenciais. Bloquear sessão e refresh na rotação. Nenhum “consultar e depois gravar” sem transação para esses fluxos.

Sem exclusão física de história pelo usuário e sem expurgo automático neste MVP. Não persistir frames nem temporárias em texto. Logs não copiam corpo de requisição/resposta sensível. Nome e motivo científico exibidos por textContent/escape; CSP restringe scripts/conexões à origem, sem HTML de usuário. A política permite imagens próprias/data para prévia local, estilos/scripts externos da própria aplicação e proíbe objetos/frames; avaliar blob somente se preview realmente usar. Erro não mostra stack trace.

## 3. Páginas e organização para desenvolver

Páginas públicas: Login e Notícias/lista/detalhe. Etapas: Cadastro facial, Reconhecimento facial e Definir senha. Todos têm menu Alterar senha e Sair. N1: Agentes, cadastro, detalhe com cards e validação editável/leitura. N2: Agentes, Revisões, Enviadas ao N3 e Solicitações. N3: Cofre/dossiê, Publicações e Solicitações. ADMIN: Solicitações, Contas e Auditoria administrativa. Não criar perfil nem página para cada transição.

Pastas alvo: `backend/app/{core,security,routers,schemas,services,repositories,biometrics}`, `backend/seed/admin.py`, `backend/migrations`, `frontend/{pages,js,css,assets}`, `docs`. Core gerencia config/pool/lifespan; security concentra tokens, dependências/CSRF/autorização; router traduz HTTP; service muda estados; repository SQL. Biometrics tem simulador e adaptação real. Sem ORM, microserviços ou framework frontend novo. Reorganização das pastas será uma etapa explícita na implementação; nenhum arquivo de execução foi movido.

Ordem: base/config/migrations → contas/permissões → login/simulador → agentes/validações → revisão/cofre/publicação → páginas → integração real e testes do conjunto. Testes precisam cobrir acessos negativos e concorrência em PostgreSQL real; mocks não comprovam constraints. Testar cookies/CSRF/câmera também no navegador. Não executar o `main.py` atual em banco persistente: ele remove tabelas.

## 4. Respostas que as telas usam

| Chamada | Campos da resposta |
| --- | --- |
| Login/etapa aprovada | `next_step,expires_in`; se sessão completa, `user:{id,name,email,role,team}`. Cookies chegam pelo servidor, não no JSON. |
| Cadastro de agente | `agent:{id,code,provisional_label,status,team_id,created_at},validation:{id,status,responsible_user_id}`. |
| Cadastro completo autorizado | Campos cadastrais mais código/estado/datas; nunca todas as análises junto por padrão. |
| Card de validação | `id,status,responsible:{id,name},created_at,latest_submitted_at,can_edit,can_submit`; flags só ajudam a UI, não autorizam chamadas. |
| Leitura da validação | Cadastro mínimo do agente, quatro textos/risco da tarefa, responsável, participantes atuais, entregas autorizadas e motivos compartilhados. Nenhum campo ministerial. |
| Enviar ao N3 | `validation_id,status:"REPORTED",protocol,sent_at`; limpar formulário sem persistir cópia no navegador. |
| N3 lê dossiê | Identificação do agente, entrega selada, relatório interno, ficha, decisão e metadados/motivos N3. |
| Notícia pública | `id,title,subtitle,risk_category,body,published_at`. Campos public_* do banco são projetados nestes nomes. |

Limites de motivos de rejeição, desativação, recuperação, reativação, devolução, encerramento, sigilo, pedido N3 e retirada: 1.500. Obrigatórios nas ações que pedem motivo; reativação usa esse padrão nesta consolidação. Campos não utilizados numa operação são rejeitados, não ignorados silenciosamente.

Grupos não atravessam permissões: consulta do criador N1 ao cadastro continua exigindo vínculo com validação autorizado, conforme a regra geral. Contas desativadas não leem nada privado. N3 novo assume o cofre; N2 novo vê o grupo e pedidos da área; autores anteriores permanecem registrados.

## 5. Permissões iniciais e quem as recebe

O seed registra estas associações. Rotas sem permissão listada abaixo continuam protegidas pela credencial de etapa quando aplicável; rotas públicas são explicitamente públicas. Nenhum papel ganha permissão por ser numericamente maior.

| Ação no banco | Papéis iniciais | Restrição adicional |
| --- | --- | --- |
| accounts.request | N2, N3, ADMIN | N2 solicita N1 próprio grupo; N3 solicita N2; ADMIN níveis institucionais. |
| accounts.request.read | N2, N3, ADMIN | Próprios pedidos; ADMIN todos. |
| accounts.approve, accounts.manage | ADMIN | Sem conteúdo técnico; gestão de ADMIN fora do MVP. |
| authorization.read, audit.read | ADMIN | Catálogos e auditoria sanitizada. |
| teams.read | N1, N2, N3, ADMIN | Catálogo mínimo de grupos. |
| agents.create | N1 | Grupo do usuário; primeira tarefa automática. |
| agents.read, validations.read | N1, N2 | N1 vínculo por tarefa; N2 grupo. |
| agents.update | N1, N2 | Criador N1 autorizado ou N2 do grupo, antes de primeira entrega. |
| agents.manage | N2 | Estado do agente no próprio grupo. |
| validations.create | N2 | Grupo, agente ativo e vaga disponível. |
| analyses.write | N1 | Responsável único, OPEN/RETURNED. |
| validations.share | N1, N2 | Responsável N1 ou N2 do grupo, OPEN/RETURNED. |
| validations.participants.manage | N2 | Remover/trocar responsável do grupo, OPEN/RETURNED. |
| validations.review | N2 | Devolver/encerrar em IN_REVIEW do grupo. |
| reports.send, reports.read | N2 | Grupo; send em IN_REVIEW, read só metadados ministeriais. |
| vault.read, vault.decide | N3 | Cofre, sigilo e pedido de outra investigação. |
| publications.publish, publications.read | N3 | Publicar original aguardando decisão; consultar/retirar cópias públicas. |

Todos os autenticados podem consultar auth/me, iniciar troca da própria senha e sair, sem uma permissão institucional extra. Leitura pública usa somente rotas public/publications; ela não concede a rota privada publications ao N1 ou ADMIN.

## 6. Repetir uma chamada e não duplicar trabalho

Salvar rascunho altera somente campos enviados. Repetir envio de uma entrega já em revisão não cria outra entrega: retorna conflito. Cadastro repetido é outra ação e não tem deduplicação automática por nome de amostra. Criação de tarefa, atendimento de pedido e decisões conflitantes são protegidos por transação e unicidade.

Se a mesma publicação já está vigente, repetir Publicar retorna a publicação existente, sem duplicar. Se retirada, Publicar não restaura: 409. Repetir Retirar devolve a situação já retirada, sem trocar motivo/autoria/data. Para sigilo ou pedido N3 já decididos, repetição com conteúdo diferente retorna 409; não sobrescrever motivo. Decisão terminal não muda para outra ação.

Implementação deve padronizar tipos/datas e aplicar as garantias descritas em DATABASE_TARGET.md. Estes documentos fecham o desenho para revisão; SQL executável, testes e preparação local continuam trabalho de implementação, não novas regras a inventar.

## Referência detalhada de acesso e autenticação

### Solicitação e ativação de contas

N2 solicita conta N1 do próprio grupo; N3 solicita conta N2 escolhendo grupo; ADMIN pode cadastrar qualquer nível institucional diretamente, com aprovação automática. N2 não escolhe grupo ou papel livremente: o backend os deriva.

O solicitante entrega a a senha temporária pessoalmente, fora do sistema; o site pode sugerir uma senha aleatória. Não enviamos email. Enquanto o pedido está pendente, não existe conta: só os dados do pedido e o hash da senha. ADMIN aprova ou rejeita com motivo, sem editar o pedido. Aprovação cria a conta e inicia 24 horas de validade; remove o hash do pedido na mesma operação. Rejeição também remove esse hash, guarda histórico e não cria conta. Outra tentativa usa novo formulário.

A senha temporária permite retomar a ativação até vencer: primeiro login não a consome. Só é invalidada quando a senha definitiva é criada. Se vencer, ADMIN revalida a MESMA senha por mais 24 horas. Se a face já foi cadastrada, não é cadastrada outra vez: a pessoa reconhece sua face e vai à troca de senha.

Primeira conta ADMIN vem do seed e dispensa biometria. Outros administradores e recuperação da própria conta ADMIN ficam fora do MVP. O ADMIN inicial também troca sua senha temporária antes de receber acesso normal.

### Login, biometria e senha

Primeira entrada: email/senha temporária → cadastrar face com anti-spoofing → criar senha definitiva → sessão. Entrada normal: email/senha → reconhecer face com anti-spoofing → sessão. ADMIN usa senha e dispensa face.

Há três credenciais: JWT restrito de etapa (5 minutos), Access JWT (até 15 minutos) e Refresh Token (até o fim da sessão de 24 horas). Depois de aprovar a face, se ainda precisa trocar a senha, emitimos OUTRO JWT restrito, exclusivo para senha, por mais cinco minutos; o anterior deixa de valer. Ter um token restrito nunca libera as funcionalidades do laboratório.

O sistema permite uma conta por vez no mesmo perfil do navegador. Se Ana estiver logada e Bruno iniciar um novo login com email e senha corretos, a sessão da Ana naquele navegador será encerrada. Bruno só receberá acesso após concluir a autenticação. Todas as abas desse perfil compartilham a troca de conta; sessões em outros navegadores, perfis ou dispositivos permanecem válidas. JWT completo não fica no banco: a tentativa guarda etapa, identificador autorizado a expiração. Sessão normal só nasce ao terminar todas as etapas. Refresh é guardado apenas como hash e gira a cada renovação; uso de um refresh consumido revoga a sessão. Renovar não prolonga as 24 horas.

Até três reprovações biométricas por tentativa; também três reprovações reais por usuário numa janela de 15 minutos causam bloqueio de cinco minutos. Novo login não zera contador. Falha de processamento e captura ruim não contam como fraude; PAD reprovado ou rosto válido que não contam. Sucesso completo limpa os controles; ao terminar o bloqueio inicia outro ciclo de contagem sem restaurar tokens. Bloqueio encerrado não restaura tokens expirados.

Senhas temporárias e definitivas: 8 a 30 caracteres e consulta a TXT local de senhas previsíveis. Não obrigar combinações arbitrárias de maiúscula/símbolo. Comparação escolhida para revisão: senha inteira, com distinção de maiúsculas, sem remover espaços da senha; nunca consultar senha pela rede. Arquivo carregado uma vez no servidor; ausência da lista impede criar novas senhas, mas não impede verificar login existente. Referência: [SecLists — 10k-most-common.txt](https://github.com/danielmiessler/SecLists/blob/master/Passwords/Common-Credentials/10k-most-common.txt). Fixar revisão e checksum na implementação. A mensagem é “A senha é muito fraca. Escolha outra senha.”

### Recuperação e alteração de contas

Não há página “Editar dados”. Há “Alterar senha”: sessão válida, senha atual, face nova para N1/N2/N3, nova senha e confirmação. ADMIN dispensa face. Ao completar, revogar todas as sessões e pedir novo login. A prova é ligada à sessão e à operação de troca; não reutilizar um token de ativação como prova dessa operação.

Somente ADMIN recupera senha esquecida (nova temporária, face mantida), biometria (remove embeddings e autoriza recadastro, senha mantida) ou ambas. Recuperação facial com senha definitiva válida termina em sessão sem exigir outra troca de senha. Apenas faltar um embedding não autoriza cadastrar face.

Desativar conta revoga sessões/tentativas e libera posição, preservando email e história. Reativar sempre exige nova temporária e novo cadastro facial, com troca de senha. ADMIN também corrige nome/email/papel/grupo; mudança de email ou permissões revoga sessão. Não altera dados históricos. Mudança de grupo/papel de responsável em tarefa ainda em preparação exige substituição pelo N2 antes, para não deixar editor fora do grupo. Desativação da conta nunca é impedida por esse motivo: bloqueia acesso imediatamente, mantém tarefa/história e N2 deve atribuir outro responsável antes de continuar. Se a tarefa está em revisão, N2 pode concluir a revisão ou devolver antes de trocar. Essas são escolhas desta consolidação para revisão.

