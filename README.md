# Arquitetura da APS — Sistema de Autenticação Biométrica Facial

## Contexto do projeto

O projeto da APS tem como tema o desenvolvimento de um sistema de identificação e autenticação biométrica. A proposta consiste em criar uma solução de reconhecimento facial capaz de identificar usuários e permitir ou negar acesso conforme um esquema de permissões.

No cenário proposto, o sistema controla o acesso a um cofre fictício de segurança máxima do Ministério do Meio Ambiente. Apenas usuários autorizados podem acessar o sistema, e cada usuário possui um nível de permissão diferente.

Os níveis definidos são:

- **Nível 1:** acesso concedido a indivíduos com permissão geral.
- **Nível 2:** acesso restrito aos diretores de divisões específicas.
- **Nível 3:** acesso exclusivo ao ministro do Meio Ambiente.

A solução precisa demonstrar o funcionamento da autenticação facial, desde a captura da imagem até a decisão final de acesso permitido ou negado.

---

# Laboratório de Biossegurança Ambiental

Sistema de identificação e autenticação biométrica facial para controle de acesso às informações de um laboratório fictício do Ministério do Meio Ambiente.

O sistema acompanha a investigação de agentes biológicos potencialmente perigosos, desde o registro técnico inicial até a decisão ministerial de manter a informação sigilosa ou divulgá-la ao público.

## Objetivo

Demonstrar autenticação facial em tempo real, controle de acesso por nível, colaboração técnica, rastreabilidade e tratamento de informações sigilosas.

O projeto atende ao tema da APS: desenvolvimento de um sistema de identificação e autenticação biométrica, utilizando as cinco fases do processamento digital de imagens.

## Contexto

O laboratório recebe amostras de agentes biológicos desconhecidos ou potencialmente perigosos encontrados no meio ambiente.

Cada agente é associado a uma especialidade técnica, como Bactérias Ambientais ou Toxinas. A equipe técnica registra e valida os casos; um diretor ou supervisor da mesma especialidade revisa o resultado.

Quando necessário, o diretor encaminha um relatório ao ministro do Meio Ambiente. O sistema então cria um dossiê sigiloso no cofre.

O cofre não guarda todos os dados técnicos do caso. Ele guarda exclusivamente o dossiê ministerial selado. Somente o ministro pode abrir seu conteúdo.

## Níveis de acesso

### Nível 1 — Equipe técnica

- Realiza login, senha e autenticação facial.
- Cadastra agentes em sua própria especialidade.
- Inicia validações técnicas.
- Inclui técnicos colaboradores da mesma especialidade.
- Registra sua própria análise técnica.
- Vê somente validações que criou ou das quais participa.
- Não acessa relatórios ministeriais, cofre ou publicações em rascunho.

### Nível 2 — Diretor ou supervisor

- Realiza login, senha e autenticação facial.
- Lidera uma especialidade técnica.
- Vê e revisa todas as validações de sua especialidade.
- Devolve uma validação para correção.
- Encerra um caso que não exige encaminhamento ministerial.
- Cria relatórios técnicos.
- Encaminha relatórios relevantes ao ministro.
- Após o envio, vê somente protocolo e status do dossiê.
- Não acessa o conteúdo selado no cofre.

### Nível 3 — Ministro do Meio Ambiente

- Realiza login, senha e autenticação facial.
- Acessa todos os dossiês selados no cofre.
- Mantém o conteúdo sigiloso ou cria uma publicação pública.
- Recebe retificações de relatórios enviados.
- Decide qual versão de um relatório deve ser considerada.

### Público

- Não realiza autenticação.
- Acessa somente informações publicadas pelo ministro.
- Nunca acessa validações técnicas, relatórios internos ou conteúdo do cofre.

## Especialidades e colaboração

Todo agente biológico deve ser cadastrado com uma especialidade obrigatória.

Para o MVP, a especialidade do agente não pode ser alterada pela interface após o cadastro.

Uma validação pode ter vários técnicos colaboradores. Um técnico só pode ser incluído como colaborador se pertencer à mesma especialidade da validação.

Cada colaborador registra sua própria contribuição com autor e data. Um colaborador não pode alterar silenciosamente a análise de outro técnico.

## Autenticação

O acesso às áreas autenticadas exige dois fatores:

1. Login e senha.
2. Biometria facial.

O sistema só libera a área correspondente ao nível do usuário após validar os dois fatores.

A biometria facial utiliza embeddings. As imagens capturadas são processadas e descartadas; o banco armazena somente os templates biométricos necessários para comparação.

## Fluxo de validação

```text
N1 cadastra o agente e inicia a validação
          ↓
N1 inclui colaboradores da mesma especialidade
          ↓
Os técnicos registram análises individuais
          ↓
N2 revisa a validação
 ├─ devolve para correção
 ├─ encerra o caso
 └─ cria relatório técnico
          ↓
N2 encaminha o relatório ao ministro
          ↓
O sistema cria um dossiê selado no cofre
          ↓
N3 analisa o dossiê
 ├─ mantém o conteúdo sigiloso
 └─ cria uma publicação pública
```

## Cofre e retificações

O encaminhamento de um relatório ao ministro cria uma versão selada no cofre.

O N2 não pode editar nem excluir um dossiê selado.

Caso o N2 identifique um erro após o envio, ele deve criar uma retificação ou uma nova versão do relatório. O ministro recebe o aviso e decide qual versão considerar.

O histórico de versões e retificações é preservado para auditoria.

## Publicação pública

Uma publicação é um registro separado do dossiê sigiloso.

O conteúdo do cofre nunca é copiado automaticamente para a página pública. O ministro redige e revisa uma versão segura e resumida para divulgação.

Somente o ministro pode criar, publicar ou retirar uma publicação pública.

Retirar uma publicação não apaga seu histórico; a decisão e a data devem permanecer registradas.

## Regras de negócio

1. O acesso autenticado exige login, senha e biometria facial válidos.
2. Cada usuário possui um nível de acesso: N1, N2 ou N3.
3. Todo agente biológico possui uma especialidade obrigatória.
4. A especialidade do agente não pode ser alterada pela interface no MVP.
5. N1 cadastra agentes somente em sua própria especialidade.
6. N1 vê somente validações que criou ou das quais participa.
7. Um colaborador deve pertencer à mesma especialidade da validação.
8. Cada análise técnica registra autor e data.
9. N2 revisa somente validações da especialidade que lidera.
10. N2 pode devolver, encerrar ou encaminhar um caso ao ministro.
11. Um relatório encaminhado cria um dossiê selado no cofre.
12. Apenas N3 pode ler o conteúdo de um dossiê no cofre.
13. N2 não pode editar ou excluir um dossiê selado.
14. Correções posteriores devem ser registradas como retificação ou nova versão.
15. Somente N3 pode criar, publicar ou retirar uma publicação pública.
16. O público vê somente publicações com status publicado.
17. Autenticações, tentativas de acesso, alterações relevantes, envios, retificações e decisões devem gerar registros de auditoria.

## Componentes previstos

```text
Frontend
├── Página pública
├── Login e biometria
├── Área N1: cadastro e validações
├── Área N2: revisão e relatórios
└── Área N3: cofre e publicações

Backend
├── Autenticação
├── Reconhecimento facial
├── Gestão de especialidades, agentes e validações
├── Gestão de relatórios, cofre e publicações
└── Auditoria

Banco de dados
├── Usuários, papéis e especialidades
├── Templates biométricos
├── Agentes biológicos e validações colaborativas
├── Relatórios e dossiês do cofre
├── Publicações
└── Logs de auditoria
```

## Tecnologias previstas

- Frontend: HTML, CSS e JavaScript.
- Backend: FastAPI.
- Banco de dados: PostgreSQL.
- Infraestrutura local: Docker.
- Biometria facial: TensorFlow/Keras.
- Persistência: SQL manual.

## Configuração local

Copie o arquivo de exemplo antes de iniciar o projeto:

```bash
cp .env.example .env
```

O arquivo `.env` contém dados locais de conexão e segredos de desenvolvimento.
Ele é ignorado pelo Git e nunca deve ser versionado. Versione apenas o
`.env.example`, com valores de exemplo sem segredos reais.

## Executar o PostgreSQL com Docker

O Docker é necessário apenas quando o PostgreSQL local for executado pelo
projeto. Se já houver um PostgreSQL acessível, preencha o `.env` com seus
dados de conexão e pule esta etapa.

```bash
docker compose up -d postgres
docker compose ps
```

O PostgreSQL ficará disponível no host, porta e banco definidos em `.env`.
Para encerrar o container sem apagar os dados persistidos:

```bash
docker compose down
```

## Executar com Poetry

```bash
poetry install
poetry run python main.py
```

## Executar com venv

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

> Atenção: no estado atual, `main.py` é usado para testar migrations e executa
> um reset do schema ao final. Não o use com dados que precisam ser preservados.
> A execução normal da API será documentada quando a aplicação FastAPI tiver sua
> entrada definida.
