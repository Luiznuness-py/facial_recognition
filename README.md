# APS | Laboratório de Biossegurança Ambiental

Aplicação acadêmica para acompanhar amostras, investigações, revisão técnica e publicação de notícias em um laboratório fictício. API em Python/FastAPI, banco PostgreSQL e interface HTML/CSS/JavaScript, sem build do frontend.

**Fluxo:** amostra → análise N1 → revisão N2 → decisão N3 → notícia pública autorizada. O administrador gerencia acessos; o visitante consulta notícias.

## Comece por aqui

1. Instale Python 3.13 e disponibilize PostgreSQL 16 ou Docker Compose.
2. Copie [.env.example](.env.example) para `.env`, se ele ainda não existir.
3. Escolha o modo abaixo e preencha banco, senha temporária do ADMIN e chave secreta.
4. Instale as dependências e inicie a aplicação.

[Configurar o .env](#configurar-o-env) · [Executar](#executar) · [Documentação](#documentação)

## Configurar o .env

### Escolha como usar

| Quero… | `ENVIRONMENT` | `BIOMETRICS_MODE` |
| --- | --- | --- |
| Explorar a interface sem câmera, preservando dados | `development` | `simulated` |
| Usar webcam e os modelos faciais localmente | `development` | `real` |
| Executar em ambiente de teste descartável | `test` | `simulated` ou `real` |
| Preparar uma instalação de produção | `production` | `real` |

**Para começar, use `development` + `simulated`.** A senha e as permissões continuam obrigatórias; na etapa biométrica, use “Continuar sem câmera”. Simulação não verifica identidade facial.

`test` usa o schema `test` e o limpa no encerramento normal da API. Não o use para guardar trabalho. O modo `real` exige os [quatro modelos locais](models/README.md) e câmera. Produção exige HTTPS e preparação adicional, ainda sem validação de implantação.

### Preencha estas variáveis

Os nomes são sensíveis a maiúsculas. Variáveis do processo têm prioridade sobre `.env`.

| Variável | Valor ou formato | O que controla |
| --- | --- | --- |
| `ENVIRONMENT` | `development`, `test`, `production` | Ambiente e seleção do schema. |
| `BIOMETRICS_MODE` | `simulated`, `real` | Simulação sem câmera ou execução dos modelos. Obrigatória. |
| `DB_HOST` | `127.0.0.1` no Compose local | Endereço do PostgreSQL. |
| `DB_PORT` | `5432` normalmente | Porta do PostgreSQL. |
| `DB_NAME` | Ex.: `app_db` | Banco usado pela aplicação. |
| `DB_USER` | Ex.: `app_user` | Usuário do banco. |
| `DB_PASSWORD` | Sua senha do banco | Credencial de conexão. |
| `ADMIN_EMAIL` | Seu email administrativo | Identificação do primeiro ADMIN. |
| `ADMIN_SECRET` | Senha temporária de 8–128 caracteres, fora da lista de senhas comuns | Criação do primeiro ADMIN; não redefine conta existente. |
| `SECRET_KEY` | Chave aleatória com pelo menos 32 bytes | Protege tokens, CSRF e templates faciais. |

Gere `SECRET_KEY` e copie a saída para `.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use o Python 3.13 instalado (`python3.13` no Linux ou `py -3.13` no Windows, se necessário). Não versione `.env`. Trocar `SECRET_KEY` invalida tokens e impede ler templates criptografados com a chave anterior.

Alterar `ADMIN_SECRET` não troca a senha de um ADMIN já ativado. Alterar `DB_PASSWORD` não muda a senha de um volume PostgreSQL existente.

**Outras opções:** `APP_NAME` e `APP_VERSION` identificam a API. `DEBUG`, `ASYNC_MODE` e `DATABASE_ECHO` são opções declaradas/legadas; não são seletores dos fluxos acima. `ALGORITHM`, `ACCESS_TOKEN_EXPIRE` e `REFRESH_TOKEN_EXPIRE` não alteram o algoritmo e os prazos fixos atuais. Não use `DATABASE_URL`: a conexão usa os campos `DB_*`.

## Executar

Com o `.env` preenchido, inicie o banco, caso use Docker:

```text
docker compose up -d --wait postgres
```

**Linux — Bash**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

**Windows — PowerShell**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn facial_recognition.app:app --reload --host 127.0.0.1
```

Abra a [interface](http://127.0.0.1:8000/lab) ou a [referência da API](http://127.0.0.1:8000/docs). Na primeira execução, a aplicação aplica migrations pendentes e cria o ADMIN. Entre com `ADMIN_EMAIL` e `ADMIN_SECRET` para definir a senha definitiva. Dados existentes são preservados em `development`.

Poetry, instalação CPU do PyTorch, diagnóstico e persistência estão no [guia detalhado](docs/SETUP.md). Não remova volumes nem edite migrations aplicadas para resolver problemas de configuração.

## Dados fictícios e demonstração

Em `development` + `simulated`, a carga opcional cria contas N1/N2/N3 e uma amostra:

```bash
python -m facial_recognition.seed.development
```

As contas novas precisam de ativação. Consulte [contas e senha temporária](docs/SETUP.md#carga-fictícia-de-desenvolvimento).

Para uma demonstração em banco separado, use [.env.demo.example](.env.demo.example) e siga o [guia da demonstração](docs/SETUP.md#ambiente-separado-de-demonstração). O exemplo não inclui a carga adicional preparada em uma instância local nem contas previamente ativadas.

## Testes

Com PostgreSQL disponível e dependências de teste instaladas:

```bash
python -m pytest -q --disable-warnings --tb=short
```

Não execute os testes comuns em paralelo. Instalação das ferramentas e limites dos testes estão no [guia detalhado](docs/SETUP.md#testes-e-qualidade); resultados reais estão em [AUTH_LAB.md](docs/AUTH_LAB.md).

## Documentação

| Preciso entender… | Documento |
| --- | --- |
| Instalação, Poetry, demonstração e diagnóstico | [SETUP.md](docs/SETUP.md) |
| Papéis, permissões e regras científicas | [BUSINESS_RULES.md](docs/BUSINESS_RULES.md) |
| Organização do código e arquitetura | [SYSTEM.md](docs/SYSTEM.md) |
| Um exemplo completo de uso | [USE_CASES.md](docs/USE_CASES.md) |
| Endpoints, entradas e respostas | [ENDPOINTS.md](docs/ENDPOINTS.md) |
| Tabelas, histórico e concorrência | [DATABASE.md](docs/DATABASE.md) |
| Autenticação, biometria e validações | [AUTH_LAB.md](docs/AUTH_LAB.md) |
| Interface e revisão visual | [FRONTEND.md](docs/FRONTEND.md) |
| Responsabilidades por área | [Amanda](docs/AMANDA.md), [João](docs/JOAO.md), [Luiz](docs/LUIZ.md) |

Projeto independente, sem vínculo oficial com ICMBio ou MMA. Testes com biometria simulada não comprovam eficácia facial ou PAD. Consulte as origens e licenças dos [modelos](models/README.md) e dos [recursos visuais](facial_recognition/frontend/static/assets/CREDITS.md).
