# Guia detalhado de instalação e operação

Aplicação acadêmica para autenticação, controle de acesso e acompanhamento de investigações em um laboratório fictício de biossegurança ambiental. O sistema reúne cadastro de amostras, análises, revisão técnica, decisão de divulgação e consulta pública de notícias autorizadas.

O projeto é independente e não representa um serviço oficial do Ministério do Meio Ambiente ou do ICMBio. O reconhecimento facial e a detecção de apresentação fraudulenta (PAD) fazem parte de um experimento; os testes de software não comprovam sua eficácia em uso real.

## Visão geral

| Participante | Responsabilidade |
| --- | --- |
| N1 responsável | Cadastrar amostras, preparar análises e entregar ao supervisor. |
| N1 colaborador | Consultar somente as investigações compartilhadas com ele. |
| N2 supervisor | Distribuir trabalho na sua equipe, revisar entregas e enviar relatórios ao N3. |
| N3 autoridade | Consultar o cofre e decidir publicação, sigilo ou nova investigação. |
| Administrador | Administrar contas e pedidos de acesso, sem acesso científico pelo cargo. |
| Visitante | Consultar exclusivamente notícias publicadas. |

**Fluxo principal:** cadastro da amostra → análise do N1 → revisão do N2 → decisão do N3 → divulgação, quando autorizada.

Uma amostra pode ter várias investigações ao longo do tempo, com apenas uma em andamento. Entregas e dossiês preservam cópias históricas; decisões terminais não reabrem a investigação. Pedidos N3 sucessivos mantêm motivos e vínculos próprios. As regras completas estão em [BUSINESS_RULES.md](../docs/BUSINESS_RULES.md).

## Funcionalidades

- Pedidos institucionais de acesso, aprovação/rejeição e ciclo administrativo de contas.
- Ativação com temporária, biometria e senha definitiva; recuperação de senha/face e troca voluntária.
- Sessões com cookies HttpOnly, proteção CSRF, refresh com rotação e revogação no servidor.
- Cadastro de amostras, rascunhos, entregas numeradas, colaboradores e troca de responsável.
- Revisão com devolução, encerramento e envio de relatório/notícia ao cofre.
- Publicação, sigilo, solicitação de nova investigação e retirada de notícias pelo N3.
- Auditoria administrativa, autorização por ação/recurso e isolamento entre equipes.

Os fluxos usam exclusão lógica (`soft_delete`). A desativação de uma conta revoga o acesso e preserva sua identidade e a primeira data de ativação.

## Tecnologias e organização

| Área | Implementação |
| --- | --- |
| API | Python 3.13, FastAPI e schemas Pydantic. |
| Persistência | PostgreSQL 16, asyncpg, SQL parametrizado e migrations SQL. |
| Interface | HTML, CSS e módulos JavaScript, servidos pela própria API. |
| Credenciais | Argon2id, JWT por finalidade e refresh opaco persistido como hash. |
| Biometria | OpenCV YuNet/SFace, dois modelos MiniFASNet e templates criptografados com AES-GCM. |
| Testes | pytest, TestClient, PostgreSQL transacional e cenários concorrentes isolados. |

```text
facial_recognition/
├── app.py          # Aplicação, lifespan e contexto HTTP
├── core/           # Conexão, autenticação, autorização e regras compartilhadas
├── routers/        # Endpoints e transações de cada operação
├── schemas/        # Entradas validadas e projeções de saída
├── seed/           # Catálogos, primeiro ADMIN e carga local explícita
├── migrations/     # Estrutura e garantias SQL
├── exceptions/     # Erros do domínio biométrico e handlers HTTP
├── utils/          # Respostas, datas, auditoria e lista local de senhas
└── frontend/       # Interface e assets locais
docs/               # Regras, arquitetura, contratos e evidências
models/             # Quatro pesos usados no modo biométrico real
tests/              # Testes de contratos, fluxos, modelos e concorrência
main.py             # Comando manual de migrations, sem servidor ou reset
```

Não há build do frontend: Node e npm não são necessários para executar a aplicação. A arquitetura e os limites de cada módulo estão em [SYSTEM.md](../docs/SYSTEM.md).

## Requisitos

- Python 3.13 com pip e suporte a ambientes virtuais.
- PostgreSQL acessível ou Docker com Compose v2 para usar [compose.yaml](../compose.yaml).
- Navegador com JavaScript. O modo `real` também exige webcam e permissão de câmera.
- Os quatro pesos locais em `models/` para o modo `real`; origem, integridade e licenças em [models/README.md](../models/README.md).

Os comandos abaixo são executados na raiz do repositório. Linux/Bash é o ambiente usado nas validações registradas; as instruções Windows/PowerShell estão documentadas, sem alegação de validação nativa no Windows.

## Configuração

Crie `.env` somente se ainda não existir:

**Linux — Bash**

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
```

**Windows — PowerShell**

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Substitua os valores de exemplo antes de executar:

| Variável | Uso |
| --- | --- |
| `ENVIRONMENT` | `development` para uso local persistente; veja os efeitos de `test` abaixo. |
| `BIOMETRICS_MODE` | Obrigatório: `simulated` para trabalhar sem webcam ou `real` para executar os modelos. |
| `DB_HOST`, `DB_PORT` | Endereço do PostgreSQL; para o Compose local, `127.0.0.1` e a porta publicada. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Banco e credenciais; o Compose usa esses valores ao inicializar um volume novo. |
| `ADMIN_EMAIL`, `ADMIN_SECRET` | Email e senha temporária do primeiro administrador; não redefinem uma conta existente. |
| `SECRET_KEY` | Raiz criptográfica de pelo menos 32 bytes aleatórios para tokens, CSRF e templates faciais. |

Gere `SECRET_KEY` com `python3.13 -c "import secrets; print(secrets.token_urlsafe(48))"` no Linux ou `py -3.13 -c "import secrets; print(secrets.token_urlsafe(48))"` no Windows. Copie a saída somente para o `.env`. Não versione esse arquivo. Trocar a chave invalida tokens e impede ler templates criptografados com a chave anterior.

`ADMIN_SECRET` deve ter 8–128 caracteres e não constar na lista local de senhas comuns. É uma senha temporária, não a chave dos tokens.

## Executar localmente

### 1. Iniciar o banco

Se não usar um PostgreSQL já existente, execute no Bash ou PowerShell com o Docker ativo:

```text
docker compose up -d --wait postgres
docker compose ps postgres
```

O serviço usa PostgreSQL 16 e preserva dados no volume `pgdata`. O Compose publica a porta configurada nas interfaces do computador; mantenha seu acesso restrito ao ambiente autorizado. Alterar as credenciais do `.env` não altera as de um volume já inicializado.

### 2. Instalar dependências e iniciar a API

**Linux — Bash**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

**Windows — PowerShell**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

Os comandos Windows usam o executável diretamente e dispensam ativação da venv ou mudança da política do PowerShell. Se preferir ativar, use `.\.venv\Scripts\Activate.ps1` e depois `python`.

O PyTorch integra as dependências mesmo no modo simulado. Para instalar sua distribuição CPU antes do requirements, use `python -m pip install torch --index-url https://download.pytorch.org/whl/cpu`; no Windows sem ativação, substitua `python` por `.\.venv\Scripts\python.exe`.

### 3. Abrir a interface

- Interface: [http://127.0.0.1:8000/lab](http://127.0.0.1:8000/lab).
- Referência interativa da API: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
- Verificação do processo: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health).

O lifespan aplica migrations pendentes e executa os seeds de catálogos/ADMIN. Entre com `ADMIN_EMAIL` e `ADMIN_SECRET` e defina a senha definitiva. O bootstrap preserva contas existentes; alterar `ADMIN_SECRET` depois não troca a senha cadastrada.

Use Ctrl+C para parar a API. Para iniciar novamente, execute o comando Uvicorn no mesmo ambiente. `main.py` é opcional: aplica apenas migrations e preserva dados, sem servidor ou seeds.

### Alternativa com Poetry

Escolha venv/pip ou Poetry para manter um único ambiente de trabalho. Com Poetry instalado:

**Linux — Bash**

```bash
poetry env use python3.13
poetry install --extras test
poetry run uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

**Windows — PowerShell**

```powershell
$projectPython = py -3.13 -c "import sys; print(sys.executable)"
poetry env use "$projectPython"
poetry install --extras test
poetry run uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

O índice CPU do PyTorch está declarado no `pyproject.toml`. Não é necessário instalar o requirements novamente no ambiente Poetry.

## Ambientes, biometria e persistência

| Ambiente | Schema | Comportamento |
| --- | --- | --- |
| `development` | `public` | Preserva dados ao encerrar; aceita `real` ou `simulated`. |
| `test` | `test`, no mesmo `DB_NAME` | O encerramento normal da API reseta esse schema; os fixtures pytest fazem rollback externo. |
| `production` | `public` | Exige modo `real` e HTTPS para emissão de cookies; preparação de produção não foi validada. |

**Não use `ENVIRONMENT=test` para dados que deseja preservar.** O reinício por `--reload` também encerra o lifespan. Os testes comuns não devem executar em paralelo ou junto de uma API usando o schema `test`.

O modo `simulated` mantém senha, etapas, CSRF, permissões e sessões, mas não executa reconhecimento ou PAD e não cria vetores fictícios. Contas ativadas sem face precisam de recuperação BIOMETRIC autorizada pelo ADMIN antes de usar o modo real. Credenciais de simulação não valem no modo real.

No modo `real`, os quatro pesos são carregados localmente antes de liberar a API; não há download automático. Capturas exigem cinco imagens e os limites descritos em [AUTH_LAB.md](../docs/AUTH_LAB.md).

HTTP com cookies sem Secure só é aceito em loopback e development/test. Acesso por IP de rede, celular ou produção exige mesma origem HTTPS e certificado confiável. A configuração de HTTPS remoto e a captura em dispositivos físicos permanecem pendentes de validação.

Migrations aplicadas não são reaplicadas ao editar seu arquivo. Evoluções de instalações existentes exigem nova migration. Nunca use `docker compose down -v` como solução de conexão: ele remove o volume. `docker compose down` interrompe os serviços preservando o volume.

## Carga fictícia de desenvolvimento

Com `ENVIRONMENT=development` e `BIOMETRICS_MODE=simulated`, execute explicitamente:

```bash
python -m facial_recognition.seed.development
```

No Windows sem ativação, use `.\.venv\Scripts\python.exe`; com Poetry, use `poetry run python`. A carga cria seis contas fictícias, além do ADMIN, e uma amostra com primeira investigação:

| Conta | Papel |
| --- | --- |
| `n1.a@example.com` | N1 responsável da Equipe A |
| `colaborador.a@example.com` | Outro N1 da Equipe A |
| `n2.a@example.com` | N2 da Equipe A |
| `n1.b@example.com` | N1 da Equipe B |
| `n2.b@example.com` | N2 da Equipe B |
| `n3@example.com` | Autoridade N3 |

A temporária das contas novas é **`Temporary!Demo2026`**, válida por 24 horas; ADMIN usa a configuração local. As contas precisam concluir a ativação. A carga não roda automaticamente, não redefine senhas nem restaura contas existentes. Conflito de vaga N2/N3 reverte a transação inteira.

### Ambiente separado de demonstração

[.env.demo.example](../.env.demo.example) é o modelo público para a configuração local `.env.demo`. Use um `DB_NAME` próprio em um PostgreSQL já disponível, credenciais locais de conexão e uma `SECRET_KEY` nova. O banco escolhido precisa existir antes da carga; iniciar o servidor aplica migrations pendentes nele. O `.env.demo` real permanece ignorado pelo Git e não substitui o `.env` principal.

Para abrir a instância preparada nesta sessão:

```bash
python -m uvicorn facial_recognition.app:app --env-file .env.demo --host 127.0.0.1 --port 8020
```

Abra `http://127.0.0.1:8020/lab`. O ambiente usa `ENVIRONMENT=development` e `BIOMETRICS_MODE=simulated`, com dados persistentes no banco separado. Os mesmos argumentos funcionam no PowerShell; use o Python da venv conforme a seção de instalação.

Em um banco novo, a carga básica existente pode usar esse arquivo de configuração:

```bash
python -m dotenv -f .env.demo run -- python -m facial_recognition.seed.development
```

Essa carga básica cria as contas pendentes descritas acima. Na instância preparada para exploração visual, as sete contas fictícias já concluíram a ativação pelas rotas reais com biometria simulada. Foram criados exemplos de análise, revisão, cofre, sigilo, publicação e dois pedidos sucessivos do N3, além de uma solicitação de acesso pendente. Essa preparação adicional não faz parte da inicialização automática da aplicação.

As quatro contas principais são `n1.a@example.com`, `n2.a@example.com`, `n3@example.com` e `admin.demo@example.com`. A senha definida na preparação está no campo `DEMO_PASSWORD` do arquivo local, não é lida pela API e não altera credenciais ao ser editada. `ADMIN_SECRET` continua sendo apenas a temporária de bootstrap, sem redefinir o ADMIN já ativado. N1/N2/N3 usam “Continuar sem câmera” na etapa de simulação; ADMIN entra sem etapa facial.

## Testes e qualidade

Com PostgreSQL acessível e o ambiente Python preparado:

```bash
python -m pip install "pytest>=8" "httpx>=0.28"
python -m pytest -q --disable-warnings --tb=short
```

Em Poetry, o extra `test` instala as dependências: execute `poetry run pytest -q --disable-warnings --tb=short`. No Windows sem ativação, use o Python da venv.

Os contratos JavaScript dos controles também podem ser executados com `node tests/frontend_ui.test.mjs` (Node 18+). O pytest os inclui quando Node está disponível e registra skip desse teste quando não está. Essa ferramenta é opcional para testes; a aplicação continua sem build ou dependência de Node. Esses cenários DOM isolados não substituem a revisão visual e de acessibilidade nos navegadores.

Os testes comuns usam o schema `test` com rollback. Os cenários concorrentes usam conexões independentes e schemas aleatórios removidos em `finally`. Testes de fluxo substituem explicitamente a inferência; smokes com pesos reais não medem acurácia ou resistência a fraude. Sem dataset local, o smoke correspondente pode ser ignorado.

Resultados executados, regressões de concorrência e contagens de consultas estão em [AUTH_LAB.md](../docs/AUTH_LAB.md#validação-da-implementação--04112026). A integração visual com o backend final, a calibração e a eficácia facial/PAD não estão comprovadas por essa suíte.

O layout foi revisado no navegador integrado em cinco larguras, com dados fictícios isolados. Cobertura, correções e limites estão na [validação visual](../docs/FRONTEND.md#revisão-visual-no-navegador-integrado--04112026); os demais motores de navegador e a integração visual com o backend real continuam pendentes.

## Documentação

| Documento | Conteúdo |
| --- | --- |
| [Regras de negócio](../docs/BUSINESS_RULES.md) | Participantes, acesso, estados e invariantes do laboratório. |
| [Arquitetura](../docs/SYSTEM.md) | Componentes, limites, transações e fluxo entre interface, API e banco. |
| [Caso de uso completo](../docs/USE_CASES.md) | Exemplo fictício da aprovação da conta à decisão sobre a notícia. |
| [Contratos HTTP](../docs/ENDPOINTS.md) | Rotas, permissões, schemas, respostas, erros e complementos. |
| [Banco de dados](../docs/DATABASE.md) | Tabelas, relacionamentos, constraints, exclusão lógica e locks. |
| [Autenticação e validação](../docs/AUTH_LAB.md) | Implementação biométrica, testes executados e limites de evidência. |
| [Frontend](../docs/FRONTEND.md) | Módulos, contratos de interface e roteiro de validação manual. |
| [Amanda](../docs/AMANDA.md), [João](../docs/JOAO.md), [Luiz](../docs/LUIZ.md) | Responsabilidades por área e critérios de revisão. |
| [Modelos](../models/README.md) e [créditos visuais](../facial_recognition/frontend/static/assets/CREDITS.md) | Origem, integridade e licenças dos materiais de terceiros. |

## Diagnóstico local

| Sintoma | Conferência |
| --- | --- |
| PostgreSQL indisponível | `docker compose ps postgres`, `docker compose logs --tail=100 postgres` e parâmetros `DB_*`. |
| Porta ocupada | Ajustar `DB_PORT` para o banco ou `--port` no Uvicorn e manter interface/API na mesma origem. |
| Senha temporária vencida | Revalidação autorizada pelo ADMIN; alterar `.env` não recupera conta existente. |
| Falta de pesos no modo real | Conferir os quatro arquivos e hashes em `models/README.md`. |
| Ativação sem webcam | Usar simulação somente em development/test, preservando as etapas obrigatórias. |
| Cookies recusados fora de loopback | Preparar HTTPS confiável; publicar apenas em `0.0.0.0` não resolve o transporte. |
| Venv sem pip no Ubuntu | Conferir o pacote `python3.13-venv` da distribuição antes de recriar o ambiente. |

## Licenças e atribuições

As licenças dos modelos e demais materiais de terceiros estão preservadas em `licenses/` e nos créditos vinculados acima. A fotografia ilustra a fauna e não representa uma instalação ou coleta do laboratório fictício. Referências institucionais não indicam vínculo oficial.
