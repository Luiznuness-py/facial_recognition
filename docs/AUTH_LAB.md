# Autenticação, biometria e validação técnica

> A interface de `/lab` evoluiu para o frontend institucional. Consulte [FRONTEND.md](FRONTEND.md) para a navegação atual, as telas preparadas e o roteiro manual. Este guia continua descrevendo a autenticação existente; as rotas científicas e administrativas estão implementadas.

A autenticação em `/lab` permite testar o cadastro pelo ADMIN, a primeira entrada e o login posterior. Usa as tabelas da migration existente; não cria banco paralelo para o produto nem rotas que pulam a autenticação. A regra atual é a de BUSINESS_RULES.md e ENDPOINTS.md; [SYSTEM.md](SYSTEM.md) descreve a arquitetura atual e registra a substituição do desenho histórico de atores.

## Preparar e executar

Na raiz do projeto, com o Python 3.13 do ambiente Poetry:

```bash
poetry install --extras test
# Copie .env.example para .env se ainda não existir e configure os valores locais.
docker compose up -d --wait postgres
poetry run uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

Se o ambiente não estiver ativado, use `poetry run` antes de `python` e `uvicorn`. O lifespan aplica migrations e executa os seeds no PostgreSQL configurado no `.env` a cada início; suba o banco antes com `docker compose up -d`. O Poetry está configurado para buscar apenas torch no índice CPU oficial. Se usar pip, a instalação CPU do PyTorch pode ser feita no ambiente com `python -m pip install torch --index-url https://download.pytorch.org/whl/cpu`, evitando pacotes CUDA desnecessários. Use as dependências da raiz do projeto; arquivos de instalação de fornecedores não definem o ambiente desta aplicação.

Abra **http://127.0.0.1:8000/lab**. ADMIN usa `ADMIN_EMAIL` e `ADMIN_SECRET`, já existentes em Settings. A primeira entrada exige uma senha definitiva. Senhas novas e temporárias devem ter entre 8 e 128 caracteres e não podem estar na lista local de senhas comuns; login aceita de 1 a 128 caracteres. O seed valida a senha inicial somente se precisar criar o ADMIN. O bootstrap é idempotente: não redefine senha, não restaura excluídos e não cria outro ADMIN quando já existe um, mesmo com email diferente. ADMIN_SECRET é apenas a senha temporária inicial, nunca é o segredo de um JWT.

SECRET_KEY, já existente, precisa ter pelo menos 32 bytes aleatórios. Exemplo para gerar um valor local: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Coloque-o no `.env`, não em arquivos versionados. Trocar essa raiz invalida JWTs e impede ler vetores criptografados com a raiz anterior: preserve-a enquanto precisar desses cadastros. BIOMETRICS_MODE também é obrigatório; escolha real ou simulated conforme a seção [Modo obrigatório de biometria](#modo-obrigatório-de-biometria). Os caminhos e limiares dos modelos ficam no código.

O acesso HTTP sem cookie Secure é restrito a loopback (`localhost`, `127.0.0.1` ou `::1`) em `development` ou `test`. Em `production`, a emissão de cookies exige HTTPS mesmo em loopback. Para acessar por outro computador é necessário servir na mesma origem HTTPS com certificado confiável; não há exceção de rede que desative a proteção. A câmera exige contexto seguro (HTTPS ou localhost) e permissão do navegador. O bootstrap e a câmera real não foram executados contra contas do banco pessoal durante os testes automatizados.

## Experimentar o fluxo

1. ADMIN entra e define a senha definitiva, se necessário.
2. No painel, cria N1/N2 escolhendo equipe, ou N3 sem equipe. A conta já nasce aprovada; a temporária vale 24 horas. Só há um N2 habilitado por equipe e um N3 habilitado.
3. ADMIN sai. O usuário entra com email e temporária.
4. No modo real, o usuário liga a câmera e envia cinco frames, separados por cerca de 450 ms. Todos precisam conter exatamente um rosto e passar no PAD.
5. O backend criptografa o template facial e muda a etapa para definir senha. Ainda não existe sessão normal.
6. O usuário define a senha definitiva. O backend preserva a primeira activated_at e emite access e refresh.
7. No modo real, depois de sair, a entrada normal exige senha definitiva e reconhecimento facial com PAD. O reconhecimento compara somente o rosto da conta informada, não procura outra pessoa no banco.

Ao recarregar, a interface tenta recuperar sessão ou etapa. A câmera é desligada ao sair da tela, ocultar a página ou concluir a captura. Existe tratamento de permissão negada, dispositivo desconectado, falha de rede, imagem sem rosto, múltiplos rostos, PAD/identidade reprovados e modelo indisponível. Dados das contas são renderizados com textContent.

## Como o código se divide

Os módulos compartilhados ficam em `core/`; os endpoints permanecem em `routers/`.

| Arquivo | Responsabilidade |
|---|---|
| [core/settings.py](../facial_recognition/core/settings.py) | Configurações do `.env`, normalização do ambiente e URL do banco. |
| [core/database.py](../facial_recognition/core/database.py) | Pool, schema por ambiente, migrations e `get_connection`. Declara o alias `Connection` com `Annotated` e `Depends`. Também contém o reset manual `drop_all_tables`. |
| [core/authentication.py](../facial_recognition/core/authentication.py) | Classe `Authentication`: `get_current_user`, `get_current_attempt`, `issue_stage`, `issue_session`, `lock_attempt`, `build_user_response` e `process_biometric`. Não guarda dados de uma requisição em atributos compartilhados. |
| [core/authorization.py](../facial_recognition/core/authorization.py) | Classe `Authorization`: recebe um código no construtor e verifica a permissão em `__call__`. Exemplo de dependência: `Depends(Authorization("accounts.manage"))`. Não presume hierarquia entre papéis. |
| [core/queries.py](../facial_recognition/core/queries.py) | `UserQueries.USER_SQL`, consulta base compartilhada da conta, papel e credencial. As demais consultas ainda estão nos módulos que as executam. |
| [core/__init__.py](../facial_recognition/core/__init__.py) | Disponibiliza `Connection`, `UserQueries`, `Authentication` e `Authorization`. Os módulos internos importam diretamente do arquivo responsável para evitar ciclos. |
| [core/token_jwt.py](../facial_recognition/core/token_jwt.py) | Classe `TokenJwt`, assinatura HS256, campos obrigatórios e finalidades ACCESS/RESTRICTED. Guarda configuração, não usuário. |
| [core/security.py](../facial_recognition/core/security.py) | Argon2id, política de senhas, cookies HttpOnly/SameSite, CSRF com HMAC e AES-GCM para vetores. Deriva chaves por finalidade a partir de `SECRET_KEY`. |
| [core/biometrics.py](../facial_recognition/core/biometrics.py) | `decode_frame` valida imagens; `FaceModels` carrega YuNet/SFace, coordena a antifraude e calcula/compara o vetor facial. |
| [core/minifasnet.py](../facial_recognition/core/minifasnet.py) | Arquiteturas, `CropImage` e adaptador `MiniFASNet`. Carrega os dois pesos locais e combina suas probabilidades. Não depende de `vendor/`. |
| [core/inference.py](../facial_recognition/core/inference.py) | Classe `Inference`: executa `FaceModels.evaluate` em uma thread, limita a uma captura por vez e controla a espera de 30 segundos. |
| [core/request_limit.py](../facial_recognition/core/request_limit.py) | Middleware `RequestLimits`: limites de corpo e frequência por IP dentro de cada processo. |
| [core/log.py](../facial_recognition/core/log.py) | Configura os logs usados pelo comando manual. |
| [utils/utils.py](../facial_recognition/utils/utils.py) | Funções compartilhadas `now`, `audit` e `failure`. Auditoria participa da transação do chamador; não abre conexão ou commit próprio. |
| [routers/__init__.py](../facial_recognition/routers/__init__.py) | Um agregador inclui auth, users, teams e access_requests com prefixo `/api/v1`; lab fica sem esse prefixo. |
| [routers/auth.py](../facial_recognition/routers/auth.py) | Endpoints de autenticação; usa uma instância de `Authentication` e delega o processamento biométrico. |
| [routers/users.py](../facial_recognition/routers/users.py), [teams.py](../facial_recognition/routers/teams.py) e [access_requests.py](../facial_recognition/routers/access_requests.py) | Listagem de contas, catálogo de equipes e cadastro direto de contas. Usam `Authorization` por permissão. |
| [routers/lab.py](../facial_recognition/routers/lab.py) | Entrega o HTML público em `/lab`; não autoriza acesso aos dados privados. |
| [app.py](../facial_recognition/app.py) | Monta FastAPI, agrega rotas e arquivos estáticos, registra middlewares e handlers. Mantém `/` e `/health` diretamente no arquivo. Carrega os modelos somente em real, prepara o banco e executa seeds no lifespan. Em test, o encerramento reseta o schema test. |
| [seed/seed_bootstrap.py](../facial_recognition/seed/seed_bootstrap.py) | Depois das migrations, executa [seed_catalogs.py](../facial_recognition/seed/seed_catalogs.py) e [seed_admin.py](../facial_recognition/seed/seed_admin.py) dentro de transação e lock. Não redefine contas existentes. |
| [frontend/index.html](../facial_recognition/frontend/index.html), [lab.js](../facial_recognition/frontend/static/lab.js) e [lab.css](../facial_recognition/frontend/static/lab.css) | Interface sem compilação ou dependências externas: formulários, câmera, requisições e apresentação. |
| [models/README.md](../models/README.md) | Relação dos quatro pesos versionados, origens, hashes e licenças. Não há pasta `scripts/` nem download automático. |

Cada requisição HTTP recebe um UUID gerado no servidor em `request.state.request_id`. Os eventos de `audit` da mesma chamada reutilizam esse UUID; a resposta o devolve em `X-Request-ID`. Erros também o incluem em `error.details.request_id`, inclusive 413/429 do limitador e falhas inesperadas, cujo log usa o mesmo identificador. O cabeçalho enviado pelo cliente não define esse valor.

### Comando manual e reset

O [main.py](../main.py) aplica migrations e fecha o pool, preservando dados; não inicia a API nem executa seeds. O comando normal para iniciar backend e frontend é Uvicorn. Consulte o [README](../README.md#executar-localmente) para venv, Poetry, configuração e Docker Compose.

`drop_all_tables` remove e recria o schema test em ambiente test ou public em development, recusando outros ambientes. O lifespan chama essa função no encerramento normal **somente em test**, inclusive em reinícios por reload; development preserva dados. Uma interrupção forçada pode impedir o cleanup. É exclusão física, diferente do soft_delete do produto. Não compartilhe o schema test entre instâncias durante uso ou testes.

### Autenticação, autorização e CSRF

`get_current_user` lê `lab_access` e exige JWT ACCESS, conta ativa e sessão não revogada no banco. `get_current_attempt` lê `lab_stage` e exige JWT RESTRICTED, tentativa pendente, etapa, operação, identificador e prazo compatíveis. Ambas usam `TokenJwt.validate_token`, com campos e chaves por finalidade; token intermediário não substitui access. `Authorization` recebe a conta autenticada e consulta os vínculos vigentes de permissão.

Antes de cada alteração, `lab.js` busca `GET /api/v1/auth/csrf`. O backend cria o cookie HttpOnly `lab_csrf_context` se necessário e devolve uma assinatura HMAC vinculada ao contexto e ao cookie de etapa/access, ou ao contexto anônimo. O frontend guarda a assinatura em memória e a envia em `X-CSRF-Token` **na própria requisição da ação**, junto dos cookies enviados pelo navegador. `require_csrf` verifica origem e assinatura; não identifica usuário nem concede permissão. As mutações protegidas recusam a requisição com 403 quando essa conferência falha. O envio JSON usa `Content-Type: application/json`; para `FormData`, o navegador define o multipart e seu boundary.

Access dura 15 minutos; etapa, 5 minutos; sessão e refresh, no máximo 24 horas. Esses limites do recorte são definidos no código conforme ENDPOINTS; os antigos campos ACCESS_TOKEN_EXPIRE/REFRESH_TOKEN_EXPIRE de Settings não controlam este fluxo. O refresh é opaco, fica como SHA-256 no banco e gira em cada uso. Reutilizá-lo revoga a sessão. Logout revoga no servidor, não apenas no navegador.

A criação e conclusão usam transações; a troca de jti impede reutilizar etapas. Três reprovações reais por usuário na janela de 15 minutos bloqueiam a biometria por cinco minutos, mesmo com novo login. Captura ruim ou indisponibilidade não contam como fraude. Há também limite de três reprovações por tentativa. Regras e gravações do contador são testadas no PostgreSQL.

A etapa exige uma senha não excluída logicamente. Antes de gravar o resultado biométrico ou concluir a senha, o backend bloqueia e confere novamente usuário, credencial e tentativa; uma exclusão durante o processamento impede a gravação. Upload sem multipart válido retorna 422 e não conta como reprovação biométrica.

Os eventos de auditoria identificam o recurso afetado: `users`, `sessions` ou `authentication_attempts`. A saída identificada registra `LOGOUT` na mesma transação da revogação da sessão ou do cancelamento da tentativa, inclusive quando só resta o refresh. Uma chamada anônima apenas limpa os cookies, sem inventar autoria.

## Modelos e limites do experimento

A implementação MiniFASNet está concentrada em [core/minifasnet.py](../facial_recognition/core/minifasnet.py), incluindo as duas arquiteturas e o recorte. Seus pesos ficam em models/2.7_80x80_MiniFASNetV2.pth e models/4_0_0_80x80_MiniFASNetV1SE.pth. O notebook OpenCV_Notebook.ipynb foi usado como referência e removido após a integração; a aplicação não o executa. O adaptador usa FaceDetectorYN com confiança 0,9, FaceRecognizerSF, média normalizada e limiar cosseno **0,2332** do notebook. O notebook fazia identificação entre várias pessoas; o backend faz verificação da identidade esperada. No PAD, usa os dois .pth, as arquiteturas e o CropImage enviados; soma as saídas softmax e exige classe real (índice 1), como o exemplo. Mantém BGR e escala 0..255 do ToTensor original; o crop usa a caixa única detectada pelo YuNet, substituindo o detector RetinaFace relativo ao diretório de execução do exemplo. Carrega os pesos PyTorch com weights_only=True, em CPU, sem recarregar por frame.

A captura acontece no navegador: `getUserMedia` alimenta o vídeo, `drawImage` copia cada frame para um canvas e `toBlob` gera JPEG com qualidade 0,9. São cinco imagens com proporção preservada, limitadas a 640 × 480, e cerca de 450 ms entre capturas. O `FormData` usa o campo `frames`; o servidor recebe fotos, não um stream contínuo.

`process_biometric` lê o multipart e entrega os bytes a `Inference`. `asyncio.to_thread` executa `FaceModels.evaluate(contents, reference)` fora do loop principal da API. Para cada foto, a sequência é: validação e decodificação → YuNet → MiniFASNetV2 → MiniFASNetV1SE → SFace. Os dois modelos PAD executam sequencialmente; `torch.set_num_threads(2)` configura paralelismo interno dos cálculos PyTorch, não uma thread por modelo. O limite de uma captura por vez vale por processo, sem fila de espera; não é um coordenador compartilhado entre vários workers.

Todas as cinco fotos precisam passar no PAD combinado. Cada uma aprovada gera um embedding SFace de 128 valores normalizados; o código calcula a média dos cinco e normaliza novamente. Cadastro guarda apenas o vetor final criptografado; login compara esse vetor com o cadastrado para a conta esperada. Uma falha interrompe a captura inteira. Não há teste de consistência de identidade entre os cinco embeddings nem seleção por qualidade de desfoque/pose antes da média; essas melhorias e seus limiares dependem de avaliação, não estão implementadas.

Cinco frames e intervalo de 450 ms são escolhas iniciais desta bancada, não calibração comprovada. Exigir todos os frames aprovados é conservador e pode aumentar rejeições. MiniFASNet é um classificador de imagens; esta integração não é uma prova de vida com desafio ativo nem comprovação contra replay de vídeo. O smoke com foto local comprova execução e formatos, não taxa de acerto, FAR/FRR ou antifraude real. Scores e embeddings não são retornados ao navegador. A câmera ao vivo e ataques com foto/tela precisam ser avaliados manualmente e registrados antes de alegar eficácia.

Transporte: corpo biométrico até 16 MiB, exatamente cinco arquivos de até 1 MiB, JPEG/PNG reais, integridade verificada com Pillow e dimensões mínimas de 80 × 80 e máximas de 1920 de largura × 1080 de altura antes da decodificação completa pelo OpenCV. O formato é identificado pelo conteúdo, sem confiar na extensão do arquivo. Uma inferência por vez; ocupação retorna 429, tempo acima de 30 segundos retorna 503 e o trabalho mantém a vaga até realmente terminar. Frames não são persistidos. Templates ficam em vectors com AES-GCM e dados associados ao UUID da conta. Não usamos a chave para inferir autorização.

Os quatro pesos (YuNet, SFace e os dois MiniFASNet) são versionados em models/ e acompanham o clone do projeto. Não há script de download. Origem, hashes e licenças estão em [models/README.md](../models/README.md). O lifespan carrega os modelos locais antes de abrir o banco e liberar a API; se falhar, orienta restaurar os arquivos do repositório. Não há download automático durante a inicialização ou o login. Arquivo local de senhas comuns em [utils/passwords.txt](../facial_recognition/utils/passwords.txt): SecLists 10k-most-common.txt, SHA-256 `68782d6a4a19a4768d5f15dd66bd534e7a33055cc755411e33f16d18c50fdcce`, consultado em memória; nenhuma senha é enviada a serviço externo.

## Testes reproduzíveis

Todos os ambientes usam o mesmo banco `DB_NAME`, configurado no Docker ou em um PostgreSQL acessível. Somente o schema muda: API em `ENVIRONMENT=test` e pytest usam `test`; os demais ambientes usam `public`. O banco precisa existir e o usuário precisa poder criar schemas; a aplicação cria o schema test automaticamente. Não há fallback de `test` para `public` nem um banco separado para testes.

```bash
ENVIRONMENT=test poetry run uvicorn facial_recognition.app:app --reload
poetry run pytest -q tests
```

O pytest força o ambiente test e usa os mesmos DB_HOST, DB_PORT, DB_USER, DB_PASSWORD e DB_NAME de Settings; TEST_DATABASE_URL não é utilizado. Migrations são aplicadas no schema test. Cada caso roda em uma transação externa: limpa temporariamente as tabelas para inserir seus fixtures e, no fim, executa rollback, restaurando os cadastros anteriores. Commits das rotas viram savepoints nessa conexão de teste. Durante o fixture, o reset do lifespan ocorre dentro da transação externa e é revertido pelo rollback; fora do fixture, a API test reseta o schema ao encerrar. Enquanto as tabelas estão bloqueadas pelo teste, requisições simultâneas da API test podem aguardar; evite experimentar a interface durante a bateria. Não use execução paralela de testes com esse fixture compartilhado.

A conta ADMIN fictícia dos testes não substitui permanentemente o ADMIN configurado; as alterações são desfeitas. O teste de pesos reais falha se faltar algum dos dois ONNX conferidos inicialmente; a ausência de pesos MiniFASNet também impede seu carregamento. Se não houver imagens locais em dataset/*/*/*.jpg, o smoke é marcado como skipped. Os testes de fluxo substituem o carregamento dos modelos e a inferência por um stub declarado, para isolar as transições de autenticação. O teste de modelos usa os pesos e as imagens reais, sem stub; uma foto reprovada por PAD é um resultado válido do modelo, não motivo para ignorar a reprovação no produto.

Os testes usam o lifespan real, com seed automático após migrations. Também verificam que mudar os valores iniciais não cria outro ADMIN nem redefine sua senha.

[test_model_setup.py](../tests/test_model_setup.py) verifica que a falha no carregamento dos pesos impede a inicialização antes de abrir o banco e orienta restaurar os arquivos locais. [test_minifasnet.py](../tests/test_minifasnet.py) cobre a combinação das redes e o recorte.

Os testes cobrem JWT por finalidade/expiração/claims, criptografia vinculada ao usuário, validação de imagem, primeiro ADMIN, criação/ativação/login, permissões, CSRF/origem, limite de corpo, exclusão lógica, rotação/replay de refresh, logout, rotação de etapa, contador de falhas e bootstrap idempotente.

[test_auth_regressions.py](../tests/test_auth_regressions.py) cobre senha excluída durante a ativação, exclusão de senha ou tentativa durante a inferência aprovada/reprovada, ausência de gravações parciais, recurso/autor/alvo da auditoria, logout por sessão/etapa/refresh e uploads malformados. Esses casos verificam o fluxo com inferência substituída explicitamente; os testes de pesos reais continuam separados.

## Escopo implementado e limites

Estão implementados pedidos por N2/N3 e decisão ADMIN, ciclo administrativo das contas, revalidação da temporária, recuperação PASSWORD/BIOMETRIC/BOTH e troca voluntária de senha com revogação das sessões. A troca exige a sessão iniciadora ainda vigente e reconhecimento facial para N1/N2/N3; biometria real e simulada conduzem à etapa de senha sem criar outra sessão.

O laboratório cobre cadastro e primeira investigação atômicos, consultas por vínculo/equipe, rascunho e entregas preservadas, participantes e responsável, revisão, cofre, decisões N3, atendimento de pedido de nova investigação e publicação/retirada. `core/accounts.py` e `core/laboratory.py` concentram regras compartilhadas; as transações ficam nos routers. Não há nova migration nem novas dependências.

A [carga fictícia manual](../README.md#carga-fictícia-de-desenvolvimento) só executa em development/simulated e não modifica senhas existentes. Os testes comuns usam rollback; os testes de concorrência usam conexões independentes e removem somente seus schemas aleatórios `race_<uuid>` e `auth_race_<uuid>` em finally.

A integração visual completa com este backend continua pendente. Depois da liberação do navegador integrado, o layout foi revisado com respostas fictícias isoladas, conforme [FRONTEND.md](FRONTEND.md#revisão-visual-no-navegador-integrado--04112026). Na demonstração posterior, com API e banco próprios, foram conferidos visualmente o login N1, a etapa simulada, amostras e publicações, sem percorrer todos os fluxos autenticados no navegador. A eficácia do reconhecimento e do PAD, a captura física e FAR/FRR exigem avaliação própria. Os testes HTTP que substituem inferência ou usam simulação verificam estados e autorização, sem comprovar biometria.

## Validação da implementação — 04/11/2026

A suíte completa final passou: **152 testes e 8 subtestes**, com 6 avisos, em **134,19 segundos**, usando Python 3.13 e PostgreSQL local. Comando: `python -m pytest -q --disable-warnings --tb=short`. Nenhum teste foi ignorado nessa execução.

- [test_administration.py](../tests/test_administration.py): catálogos, pedidos e isolamento por solicitante, aprovação/rejeição, ciclo das contas, vagas, recuperações, primeira ativação preservada, troca de senha com biometria real substituída/simulada, sessão iniciadora revogada, auditoria administrativa e carga fictícia (repetição, restrições de ambiente e rollback por conflito).
- [test_laboratory.py](../tests/test_laboratory.py): escopo por equipe e investigação, rascunho, entregas/devolução, candidatos e participantes, responsável, cadastro preservado inclusive com histórico excluído, estado da amostra, envio selado, três decisões N3, publicação/retirada e duas gerações consecutivas de pedidos N3. As duas listagens têm regressões de contagem de consultas para páginas de 1 e 100 registros. Cofre e decisões continuam exclusivos de N3 mesmo com permissões atribuídas por engano a N2. Auditoria do envio referencia o ID do dossiê.
- [test_auth_concurrency.py](../tests/test_auth_concurrency.py): refresh contra revogação nas duas ordens, replay simultâneo, troca de senha contra login/logout e troca de conta contra gravação de auditoria. Revalida o token após localizar sem lock; preserva revogação confirmada, vínculo do sucessor e expiração absoluta.
- [test_auth_regressions.py](../tests/test_auth_regressions.py): as conclusões de ativação/recuperação e troca voluntária comparam a senha fora do loop, inclusive ao recusar senha repetida; o teste verifica a ausência de loop na thread, sem limite de tempo.
- [test_laboratory_concurrency.py](../tests/test_laboratory_concurrency.py): conexões independentes disputam criação, envio de análise, decisões incompatíveis e troca de responsável contra escrita. Confere perda de edição do responsável anterior, preservação do snapshot após mudança de nome e compartilhamentos simultâneos entre dois N1.
- [test_frontend.py](../tests/test_frontend.py): assets e cabeçalhos, além de conferir as **59 operações documentadas** no OpenAPI. Os demais testes de autenticação, cookies, request-id e modelos também integraram a execução completa.

Passaram sintaxe de 71 arquivos Python e 7 JavaScript, conferência de docstrings das funções/classes de topo da implementação alterada, imports de todos os módulos da aplicação (incluindo schemas), 388 links locais e `git diff --check`. As 59 operações documentadas estão no OpenAPI. Não houve commit/push, alteração de migrations aplicadas ou reset manual do schema public/volume. A validação visual e a avaliação biométrica física continuam com os limites descritos acima.

Antes das correções, os testes permanentes reproduziram os quatro problemas: deadlock real entre refresh/revogação, comparação no loop, pedido N3 anterior no card do novo envio e consultas por amostra. Reproduziram também deadlocks de login/logout contra troca de senha e de compartilhamentos cruzados. O lock exclusivo das contas do navegador também foi testado contra a FK de autoria da auditoria: `FOR NO KEY UPDATE` evita esse bloqueio, mantendo a serialização. Candidatos usam `FOR SHARE`, que impede alteração da conta sem impedir referências de autoria. Os casos confirmados desta revisão foram corrigidos; não há outro bug confirmado pendente neste recorte. Isso não demonstra ausência de outras condições de corrida ou falhas fora dos cenários testados.

| Requisição HTTP local | Consultas antes, páginas 1/100 | Consultas após, páginas 1/100 |
| --- | --- | --- |
| Listagem de amostras | 5 / 104 | 4 / 4 |
| Cards de investigações | 8 / 305 | 5 / 5 |

A contagem inclui autenticação e autorização reais do fixture. Na rodada direcionada final, a listagem de amostras levou 10,21 ms para um item e 10,60 ms para 100 itens. São medições pontuais locais, sem aquecimento ou estudo de carga, não benchmarks de produção. As regressões exigem contagem constante e verificam a regra de edição histórica, sem impor limite de latência. A bateria ampliada de fluxos conectados passou com 46 testes em 95,51 s; a rodada final de laboratório, com 10 testes em 29,25 s; ambas tiveram 6 avisos.

## Revisão da documentação e docstrings — 04/11/2026

Os 13 arquivos Markdown do projeto foram revisados. O README organiza apresentação, funcionalidades, estrutura, configuração, execução Linux/Windows, testes e diagnóstico local. SYSTEM.md passou a descrever a arquitetura atual; os guias por responsabilidade, contratos, banco, exemplos, modelos e créditos foram alinhados à implementação. Resultados históricos continuam identificados como históricos.

A revisão conferiu 331 funções/métodos nos 71 arquivos Python da aplicação, testes e comando manual; 177 docstrings foram completadas. Foram documentados parâmetros, retornos ou yields, exceções e pré-condições/efeitos relevantes. Auxiliares assíncronos e adaptadores dos testes também estão incluídos. A comparação de AST com o estado anterior à revisão, removendo somente docstrings, confirmou que nenhuma lógica, assinatura ou valor executável foi alterado. Artefatos locais ignorados em dataset/ e work/ não integram esse inventário de fontes.

A suíte foi repetida depois das alterações: **152 testes e 8 subtestes passaram, com 6 avisos, em 132,56 s**. Passaram também os imports dos 55 módulos da aplicação, as 59 operações documentadas no OpenAPI, sintaxe dos sete módulos JavaScript, parsing dos 13 Markdown, 409 links locais com âncoras, sintaxe Bash dos exemplos e git diff --check. Os quatro hashes dos pesos locais correspondem aos registrados em models/README.md.

Não houve commit/push, alteração de dependências, migrations ou lógica de negócio. A instalação do zero, os comandos PowerShell em Windows nativo, links externos, renderização visual do README e a integração com câmera física não foram repetidos nessa revisão. As limitações de eficácia biométrica e de integração visual do backend permanecem as registradas acima.

## Validação após o refinamento da interface — 04/11/2026

A base funcional/documental foi registrada no commit local `36bf438` antes das alterações visuais, conforme solicitado. A nova rodada completa passou com **154 testes e oito subtestes**, seis avisos, em **134,58 s**, sem skips. Os 52 testes direcionados de frontend, cookies e request-id passaram em 1,83 s. Os oito cenários DOM de seleção, senha e filtros passam pelo teste Python correspondente e também podem rodar diretamente com Node 18+; não representam oito casos Python adicionais.

Os testes novos verificam teclado/estado dos controles e entrega dos oito WebP locais, dimensões, proporção, tamanho e créditos. Passaram sintaxe Python/JavaScript, docstrings de 333 funções/métodos, imports dos 55 módulos da aplicação, contratos documentados no OpenAPI, lint de fontes visuais e `git diff --check`. A lógica Python da aplicação permanece igual à do commit funcional; somente os testes Python receberam novos cenários. Detalhes estão em [FRONTEND.md](FRONTEND.md#validação-deste-refinamento--04112026).

As execuções presas no sandbox foram encerradas antes da rodada sequencial bem-sucedida com acesso ao PostgreSQL local. Nessa rodada anterior à liberação do navegador, a renderização ainda estava bloqueada no Work. A revisão visual subsequente está registrada em FRONTEND.md; motores Chrome/Edge/Firefox/Safari/Brave separados e leitor de tela continuam pendentes. Os testes não comprovam eficácia facial/PAD. Não houve novo commit/push, alteração de dependências da aplicação ou migrations, nem reset manual de `public`/volume.

## Revalidação após a revisão visual — 04/11/2026

Após o usuário habilitar o navegador integrado, o layout atual foi revisado com respostas fictícias isoladas e recebeu correções de responsividade, foco, scroll e apresentação de erros. As duas regressões de foco falharam antes da correção e ampliaram os contratos JavaScript para dez cenários. As 151 medições de largura e as capturas estão descritas em [FRONTEND.md](FRONTEND.md#revisão-visual-no-navegador-integrado--04112026).

A suíte completa final passou: **154 testes e oito subtestes**, seis avisos, em **456,48 s**, sem skips. O teste Python de interface inclui os dez cenários JavaScript; eles não aumentam a contagem de casos Python. A primeira tentativa foi encerrada antes de concluir e não conta como aprovação. A repetição em sessão persistente terminou sem falhas, com testes comuns sequenciais. A prévia visual não conectou ao PostgreSQL nem alterou dados reais. A duração total local não é benchmark de produção.

Sintaxe Python/JavaScript, docstrings, links locais, lint de fontes visuais e `git diff --check` passaram. A lógica Python da aplicação continua igual à do commit funcional. A revisão em navegador integrado com fixtures não demonstra integração visual autenticada com PostgreSQL real, comportamento em todos os motores/dispositivos ou eficácia facial/PAD. Não houve commit, push, alteração de dependências/migrations ou reset manual de `public`/volume.

## Histórico de validações — 26/10/2026

Os resultados abaixo são registros das rodadas anteriores, não uma nova execução da bateria completa sobre a estrutura atual.

Na validação inicial, 19 testes passaram em Python 3.13 com PostgreSQL 16 isolado, incluindo os dois testes que executam os pesos reais. A rodada completa levou aproximadamente 29 segundos. Também passaram compile/sintaxe Python, verificação sintática do JavaScript, conferência dos links locais da documentação e poetry check. O login ADMIN, recuperação da sessão após recarregar, equipes e listagem de contas foram conferidos no navegador; a interface estreita foi inspecionada visualmente, sem overflow horizontal. Foram observados avisos de depreciação do ambiente existente (Field(env=...) e TestClient/httpx), sem falhas funcionais nessa rodada.

Após a revisão, foram corrigidos os cinco problemas de exclusão lógica, upload malformado e auditoria. A bateria passou a ter **33 testes**, todos aprovados em **72,71 segundos**, com 14 casos adicionais de regressão e os dois testes de pesos reais mantidos. Também passaram compile/sintaxe Python e `git diff --check`. A interface no navegador não foi retestada nesta correção; as rotas foram verificadas pelos testes HTTP. O PostgreSQL usado foi descartável e separado do banco do projeto.

Após restaurar o reset manual e separar a integração MiniFASNet, **38 testes passaram em 72,33 segundos**, com PostgreSQL descartável e os pesos reais no novo diretório. Os dois casos de [test_minifasnet.py](../tests/test_minifasnet.py) verificam a combinação das redes e a preservação de BGR/0..255. Uma comparação adicional com três entradas sintéticas e os pesos reais preservou as probabilidades (tolerância absoluta de 1e-7) e as decisões anteriores à separação. Isso verifica a reorganização, sem substituir a avaliação antifraude com câmera.

Na correção do roteamento, todos os ambientes passaram a usar DB_NAME, mudando apenas o schema. **40 testes passaram em 70,90 segundos**, com public e test no mesmo banco PostgreSQL descartável. A inicialização real com ENVIRONMENT=test também foi conferida no DB_NAME configurado no Docker, criando apenas o schema test e seus dados iniciais.

Na consolidação do MiniFASNet, vendor foi removido e a configuração, as redes e o recorte ficaram reunidos em minifasnet.py. Os dois pesos foram preservados sem mudança de SHA-256 em models/ e a licença ficou em licenses/. **42 testes passaram em 53,51 segundos**, incluindo os pesos reais e os casos de recorte nos limites da imagem. A comparação anterior/posterior em três entradas sintéticas preservou as probabilidades (tolerância absoluta de 1e-7) e as decisões. A câmera física não foi reavaliada nesta alteração.

Na padronização das docstrings, foram revisadas 253 definições Python e completadas 172 documentações, incluindo parâmetros, atributos, retornos, erros e efeitos relevantes. A comparação da árvore sintática, desconsiderando apenas docstrings, confirmou a preservação da lógica. Os links das classes foram reposicionados e a geração do OpenAPI foi conferida. Passaram 15 testes locais, incluindo JWT, criptografia, imagens, reset simulado, timeout e pesos reais; a bateria com PostgreSQL e a interface não foram repetidas nesta alteração de documentação.

Captura física da webcam, rejeição de fotos/telas, comparação entre pessoas e calibração de FAR/FRR continuam pendentes. Nenhuma conta real foi criada e nenhum banco existente foi apagado para os testes.

A validação do schema compartilhado também preservou um cadastro sentinela inserido antes da bateria: após os 19 testes, a linha continuou intacta e nenhum usuário fictício dos testes permaneceu. O schema public não recebeu tabelas da aplicação nessa rodada.

## Revisão da estrutura — 02/11/2026

Os caminhos e a divisão entre `core/`, `routers/` e `utils/` foram conferidos no código atual. O guia passou a refletir a classe `Authentication`, a dependência `Authorization`, o fluxo CSRF, a captura e agregação das cinco imagens, os pesos versionados e o limite de 128 caracteres para senhas. A única definição sem docstring era a classe `Authentication`; sua documentação foi adicionada. A varredura final encontrou **259 definições Python, todas com docstring**, incluindo testes e o comando manual.

**16 testes locais passaram**, cobrindo JWT, criptografia, validação de imagem, inicialização sem pesos, roteamento/reset simulado, combinação MiniFASNet, timeout e o smoke com pesos reais. Também passaram a conferência dos links locais deste guia, a sintaxe JavaScript e `git diff --check`. Não foi repetida a bateria de integração com PostgreSQL nem a validação visual/câmera. Os resultados históricos acima não representam uma nova execução desses fluxos.

Registro histórico da revisão anterior: havia divergências no comando main.py e nos imports de audit/now. No código atual, main.py aplica migrations sem reset e access_requests importa diretamente de utils/utils.py. O reset de test pertence ao encerramento do lifespan, conforme a seção atual de execução.


## Modo obrigatório de biometria

Defina `BIOMETRICS_MODE=real` ou `BIOMETRICS_MODE=simulated` no `.env` antes de iniciar a aplicação. Não há valor padrão: ausência ou valor inválido impede a inicialização. `simulated` é permitido somente em `development` e `test`; produção exige `real`. O `.env.example` usa `simulated` para os colegas sem webcam.

Em `real`, o pipeline e seus limites permanecem ativos. Em `simulated`, o lifespan não carrega os pesos nem executa inferência. Após email/senha corretos, `GET /api/v1/auth/flow` informa `biometrics_mode`; a interface mostra “Biometria simulada” e oferece continuar sem câmera. O POST `/api/v1/auth/biometric/simulate`, sem corpo, exige CSRF e tentativa restrita vigente, revalida conta e temporária sob bloqueio e registra `BIOMETRIC_SIMULATED`. A ativação ainda exige senha definitiva. As rotas reais de upload recusam uso no modo simulado.

A simulação não grava vetores fictícios nem altera vetores reais existentes. Ela conclui a exigência facial da conta para permitir os testes de fluxo; isso não comprova cadastro facial. Ao voltar para `real`, uma conta ativada sem vetor real precisará do fluxo administrativo de recuperação facial pelo ADMIN ou de um novo cadastro fictício. Use somente contas de desenvolvimento. Não reutilize esses cadastros como cadastros biométricos de produção.

JWTs e hashes dos tokens opacos usam separação por modo: uma credencial emitida em simulação não autentica nem renova sessão no modo real. Reinicie o servidor ao trocar a configuração e faça novo login. A simulação não substitui senha, autorização, CSRF ou as regras do PostgreSQL. Os testes existentes fixam `BIOMETRICS_MODE=real` e substituem inferência somente nos casos de fluxo; testes específicos cobrem o modo simulado sem câmera.


## Validação de consolidação — 02/11/2026

A bateria completa passou com **107 testes em 88,86 s**, em PostgreSQL 16 descartável sem volume e separado do banco do projeto, incluindo os dois smokes com pesos reais e dataset local. A primeira tentativa revelou que o fixture mantinha FaceModels.load simulado no smoke HTTP real; esse teste foi corrigido para carregar explicitamente os pesos reais antes da inferência. Um teste de integração adicional passou em 4,08 s, cobrindo ativação e login simulados, auditoria explícita, ausência de vetores fictícios, autorização e rejeição de JWT/refresh simulados após mudar para real. Portanto, foram verificados 108 casos distintos nesta consolidação (107 na bateria e um adicional).

Também passaram pip check, conferência offline do requirements contra o ambiente instalado, poetry check, configuração do Compose, sintaxe Python/JavaScript, links locais e revisão de docstrings das definições Python. A instalação do zero com venv não foi concluída nesta máquina: Python 3.13 está instalado sem o pacote python3.13-venv/ensurepip. O README documenta esse pré-requisito; não foi instalado pacote de sistema nesta rodada.

Os percursos dos quatro papéis no navegador foram repetidos com API fictícia isolada. A edição cadastral respeitou can_edit false/true/ausente, independentemente da página/filtro. Esse registro histórico com API fictícia não comprova a integração visual com as rotas científicas hoje implementadas, nem a eficácia biométrica ou o uso em celular físico. O container descartável é removido ao finalizar a validação; o banco do projeto não é resetado.
