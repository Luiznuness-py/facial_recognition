# APS — Laboratório de Biossegurança Ambiental

Projeto acadêmico local de autenticação facial e controle de acesso para um laboratório fictício do Ministério do Meio Ambiente. MVP reduzido aprovado em 05/10/2026: N1 registra uma investigação de agente desconhecido, N2 revisa e conclui, N3 decide a divulgação. Autenticação permanece como definida.

## Estado do projeto

O frontend institucional está em `/lab`, com notícias públicas, login e telas por papel. Autenticação, equipes, listagem de contas e cadastro direto pelo ADMIN têm chamadas para as rotas existentes. As telas científicas e os demais fluxos administrativos estão preparados conforme os contratos e informam quando dependem de backend ainda não implementado. Veja [telas, integração e roteiro manual](docs/FRONTEND.md) e [preparação da autenticação, testes e limites](docs/AUTH_LAB.md).

`main.py` aplica as migrations pendentes e encerra a conexão, preservando as tabelas e os dados. Para iniciar a API e a interface, use o comando Uvicorn abaixo.

## Documentação para revisar

Leia nesta ordem:

1. [Como funciona o sistema](docs/BUSINESS_RULES.md): objetivo, participantes, acesso, fluxo e regras essenciais em linguagem simples.
2. [Exemplo completo](docs/USE_CASES.md): uma investigação preenchida para visualizar o fluxo; inclui exemplos técnicos.
3. [Endpoints e suas finalidades](docs/ENDPOINTS.md): chamadas das telas, dados, verificações, respostas e escolhas de implementação.
4. [Tabelas e campos](docs/DATABASE.md): estrutura e garantias do banco alvo.

Esses arquivos são a referência atual do planejamento, ainda para revisão. A documentação descreve o desenho do sistema e não representa código já implementado.

## Fluxo e responsabilidades

- N1 cadastra agente e assume a primeira validação. Como responsável, edita/envia e compartilha com N1 do grupo; como colaborador, somente consulta a tarefa compartilhada.
- N2 do grupo abre as validações seguintes e escolhe responsável; revisa, devolve, encerra ou envia conclusão/ficha ao N3. Cards Enviadas ao N3 mostram título, agente vinculado e situação da decisão, sem relatório selado. Um N2 habilitado por equipe.
- N3 consulta o cofre e publica a ficha preparada ou mantém restrito; pode retirar notícia. Um N3 ativo.
- ADMIN gerencia contas/acesso, sem conteúdo técnico/cofre pelo cargo; público consulta somente notícias aprovadas.

Cadastro em `biological_agents`, análise em `validations`. Várias validações por agente, uma em andamento. Encerramento ou publicação libera outra; envio ao N3 mantém a vaga ocupada. Sigilo decidido pelo N3, sem pedido de ajuste ou nova validação, encerra a tarefa automaticamente e libera outra. Um responsável edita; colaboradores apenas leem. Compartilhamento pelo N1 responsável ou N2 supervisor do grupo, somente com N1 ativos do mesmo grupo; colaboradores apenas leem.

Seis tabelas do laboratório: `biological_agents`, `validations`, `validation_participants`, `investigation_submissions`, `vault` e `publications`. Entregas/dossiês pertencem à validação; publicação ao dossiê. Relatório e ficha juntos no cofre, sem acesso selado pelos colaboradores. Contas/autenticação usam as tabelas já definidas.

Todas as 18 tabelas da aplicação usam `soft_delete`, sem exclusão física pelos fluxos do produto. Contas usam PENDING_ACTIVATION/ACTIVE, desativação por `soft_delete` e `activated_at` preservando a primeira ativação. `audit_events` concentra o log genérico de ações, sem novas tabelas de histórico. As rotas ainda precisam implementar filtros e restauração conforme esses contratos.

Sem transferência entre grupos, rascunho ministerial separado, retificação, devolução pública ou substituição de notícia. Original/histórico preservados; retirada de publicação não reabre a tarefa anterior.

## Acesso e autenticação

Sem cadastro público. N2 solicita N1 da própria equipe; N3 solicita N2; ADMIN aprova ou cadastra diretamente. Temporária entregue manualmente, ativação com face e senha definitiva. ADMIN dispensa biometria. Reativação sempre exige reset de senha/face.

Papéis/permissões no banco, autorização central por ação e recurso. Credenciais restritas de etapa, access JWT e refresh opaco em cookies HttpOnly. Detalhes completos, incluindo CSRF, expiração, recuperação e limites, ficam no plano geral e contratos.

## Tecnologias e divisão

Frontend HTML/CSS/JavaScript; FastAPI; PostgreSQL, SQL parametrizado e asyncpg. PostgreSQL pode executar em container local. Pipeline inicial YuNet/SFace e MiniFASNet/Silent-Face, com parâmetros a avaliar. Dupla do sistema usa simulador de desenvolvimento enquanto dupla dos modelos testa; simulador não comprova eficácia biométrica.

## Preparar o ambiente local

Execute os comandos na raiz deste repositório. Use **Python 3.13** e Docker Compose v2 se o PostgreSQL for executado em container. Não é necessário Node, npm ou build do frontend.

#### Linux — Bash

Instale Python 3.13 com suporte a venv/pip e Docker Engine com o plugin Compose (ou Docker Desktop para Linux). Confira:

```bash
python3.13 --version
docker compose version
docker info
```

No Ubuntu com Python 3.13 já instalado, se criar a venv falhar por ausência de `ensurepip`/pip:

```bash
sudo apt install python3.13-venv
```

Esse pacote depende de a distribuição/repositório fornecer Python 3.13. Não substitua por Python 3.12 para este projeto.

#### Windows — PowerShell

Instale Python 3.13 com pip e o launcher `py`. Instale e abra o Docker Desktop, usando o backend WSL 2 e containers Linux; conclua os requisitos de virtualização/WSL solicitados pelo instalador. O projeto pode ser executado pelo PowerShell, sem instalar Python dentro do WSL. Confira:

```powershell
py -3.13 --version
docker compose version
docker info
```

Referências de instalação: [venv do Python](https://docs.python.org/3.13/library/venv.html) e [Docker Desktop no Windows](https://docs.docker.com/desktop/setup/install/windows-install/). Os comandos Windows abaixo são para PowerShell, não para o Prompt de Comando (cmd).

### 1. Configurar o .env

Crie a cópia somente se ainda não houver `.env`; os comandos preservam uma configuração existente.

**Linux — Bash:**

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
```

**Windows — PowerShell:**

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edite os valores antes de subir o banco:

| Campo | Como preencher |
|---|---|
| `ENVIRONMENT` | `development` para trabalhar preservando dados; `test` apaga o schema test no encerramento normal da API; `production` exige biometria real e HTTPS para emitir cookies. |
| `BIOMETRICS_MODE` | Obrigatório: `simulated` para colegas sem webcam ou `real` para modelos reais. Simulação só é aceita em development/test. |
| `DB_HOST` | `127.0.0.1` para a API no computador acessando o Compose. |
| `DB_PORT` | Porta publicada no computador; padrão do exemplo: `5432`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | Nome do banco, usuário e senha; o Compose usa esses mesmos valores para inicializar um volume novo. |
| `ADMIN_EMAIL` | Email usado para criar o primeiro administrador. |
| `ADMIN_SECRET` | Senha temporária inicial: 8–128 caracteres, fora da lista de senhas comuns; não é a chave dos tokens. |
| `SECRET_KEY` | Raiz secreta com pelo menos 32 bytes aleatórios. Gere com o comando abaixo. |

**Linux — Bash:**

```bash
python3.13 -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Windows — PowerShell:**

```powershell
py -3.13 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copie a saída somente para `SECRET_KEY` no `.env`. Preserve essa chave enquanto precisar dos templates faciais criptografados: trocá-la impede a leitura dos vetores anteriores. `.env` é ignorado pelo Git; não compartilhe credenciais reais. Os valores `troque_...` do exemplo devem ser substituídos.

### 2. Iniciar o PostgreSQL com Docker Compose

Se já tiver PostgreSQL acessível, use seus dados no `.env` e pule a criação do container. Caso contrário, execute os mesmos comandos no **Bash/Linux ou PowerShell/Windows**, com o Docker em execução:

```bash
docker compose up -d --wait postgres
docker compose ps postgres
```

O serviço usa PostgreSQL 16, publica `DB_PORT` e mantém os dados no volume `pgdata`. Aguarde o health check ficar saudável antes de iniciar a API. `DB_HOST` configura a conexão da API, não o endereço de publicação do Docker. O Compose atual publica a porta do banco nas interfaces do computador; não a exponha à internet.

Para investigar uma falha de inicialização, em ambos os sistemas:

```bash
docker compose logs --tail=100 postgres
```

Se a porta já estiver ocupada, escolha outra em `DB_PORT`. Se o Docker reportar permissão negada, confira o acesso do seu usuário ao daemon conforme a instalação da sua máquina; não mude permissões do socket para acesso público.

Em um volume existente, mudar `DB_USER`, `DB_PASSWORD` ou `DB_NAME` no `.env` não recria o banco nem altera suas credenciais. Preserve a configuração original ou faça uma migração administrativa planejada. **Não use `docker compose down -v` para resolver conexão: isso remove o volume e apaga seus dados.**

Para parar preservando o volume, em ambos os sistemas:

```bash
docker compose down
```

### 3. Instalar e executar com venv

**Linux — Bash:**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

**Windows — PowerShell:**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

Se o PowerShell bloquear `Activate.ps1`, não é necessário alterar a política de execução: use diretamente o Python da venv, sem ativá-la:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

O PyTorch faz parte das dependências mesmo em modo simulado. Para evitar pacotes CUDA desnecessários no Linux/Windows, é possível instalar a versão CPU **antes** do requirements. Com a venv ativa, os comandos são iguais em Bash e PowerShell (sem ativação no Windows, substitua `python` por `.\.venv\Scripts\python.exe`):

```bash
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
```

Abra **http://127.0.0.1:8000/lab**. O portal público e a tela de login estão disponíveis; endpoints ainda não implementados mostram pendência. A API aplica migrations e seeds automaticamente. Entre com `ADMIN_EMAIL`/`ADMIN_SECRET` e defina uma senha definitiva. O bootstrap não redefine contas existentes; alterar ADMIN_SECRET depois não troca a senha cadastrada.

Interrompa o Uvicorn com Ctrl+C. Ao voltar em outro terminal, na raiz do projeto:

**Linux — Bash:**

```bash
source .venv/bin/activate
python -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

**Windows — PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

Se não puder ativar, execute `.\.venv\Scripts\python.exe -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1`.

Use `deactivate` para sair da venv. Não é necessário rodar `main.py` antes da API: esse comando aplica apenas migrations, sem servidor ou seeds, e preserva dados.

### Alternativa: Poetry

Escolha venv ou Poetry, sem instalar em dois ambientes por engano. Instale o Poetry antes de usar esta alternativa.

**Linux — Bash:**

```bash
poetry env use python3.13
poetry install
poetry run uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

**Windows — PowerShell:**

```powershell
$projectPython = py -3.13 -c "import sys; print(sys.executable)"
poetry env use "$projectPython"
poetry install
poetry run uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

Para instalar também os testes: `poetry install --extras test`. O Poetry usa o índice CPU para torch.

## Ambientes, biometria e dados

- `development`: usa o schema `public`, preservando dados ao encerrar.
- `test`: usa o mesmo `DB_NAME`, mas no schema `test`; o lifespan remove e recria esse schema ao encerrar normalmente, antes de fechar o pool. Não use esse ambiente para dados que deseja preservar. Reinício automático por `--reload` também encerra o lifespan e executa o reset.
- `production`: usa `public`; simulação não é permitida e HTTP não emite cookies, mesmo em loopback.

`BIOMETRICS_MODE=simulated` permite avançar a etapa facial sem webcam, mantendo senha, CSRF, permissões e sessões. Não cria vetores falsos. Credenciais de simulação não valem no modo real. Contas ativadas sem face precisam de recadastro/recuperação facial para uso real; o fluxo administrativo correspondente continua pendente. Confira [autenticação e modos](docs/AUTH_LAB.md#modo-obrigatório-de-biometria).

Em `real`, o lifespan carrega YuNet, SFace e os dois MiniFASNet locais. Os quatro pesos acompanham o repositório em `models/`; não há download na inicialização. Arquivos ausentes/incompatíveis impedem iniciar em modo real. Consulte [origem, hashes e licenças](models/README.md). Em `simulated`, esses pesos não são carregados.

HTTP sem cookie Secure é permitido somente em loopback e development/test. Celular pelo IP de rede precisa de HTTPS confiável para autenticação e câmera. Túnel/HTTPS remoto será configurado depois; não basta trocar o host para `0.0.0.0`.

A migration 001 define o schema para bancos novos. Editá-la não atualiza bancos que já a registraram; uma evolução de banco existente exige migration adicional ou decisão explícita de recriação. O reset de test no encerramento é separado desse mecanismo.

## Testes

Com a venv ativa e PostgreSQL acessível, os comandos são iguais no Bash/Linux e PowerShell/Windows:

```bash
python -m pip install "pytest>=8" "httpx>=0.28"
python -m pytest -q tests
```

No Windows sem ativação da venv, use `.\.venv\Scripts\python.exe` no lugar de `python` nos comandos de teste.

O pytest força `ENVIRONMENT=test` e `BIOMETRICS_MODE=real`; os testes de fluxo substituem a inferência, e os testes do simulador configuram o modo explicitamente. Testes com banco usam transação e rollback sobre o schema test; não execute em paralelo nem junto da API test. Não use seu banco com dados importantes para validações. Os smokes com modelos reais podem ser ignorados se não houver dataset local; isso não comprova eficácia biométrica. Veja [isolamento e limites](docs/AUTH_LAB.md#testes-reproduzíveis).

Os contratos em [ENDPOINTS.md](docs/ENDPOINTS.md) incluem links para os schemas de entrada e saída de cada rota. As distribuições em [AMANDA.md](docs/AMANDA.md), [JOAO.md](docs/JOAO.md) e [LUIZ.md](docs/LUIZ.md) repetem esses atalhos para facilitar a implementação.

## Bancada biométrica

O guia de execução e a explicação da implementação estão em [AUTH_LAB.md](docs/AUTH_LAB.md). Nenhum banco existente é apagado na inicialização.
