# APS — Laboratório de Biossegurança Ambiental

Projeto acadêmico local de autenticação facial e controle de acesso para um laboratório fictício do Ministério do Meio Ambiente. MVP reduzido aprovado em 05/10/2026: N1 registra uma investigação de agente desconhecido, N2 revisa e conclui, N3 decide a divulgação. Autenticação permanece como definida.

## Estado do projeto

Regras e contratos estão em planejamento. A base existente contém configuração/conexão PostgreSQL e migrations; a documentação não significa que a API, páginas ou integração biométrica já funcionam. A migration inicial e os testes SQL acompanham os contratos documentados; as rotas ainda serão implementadas.

`main.py` aplica as migrations pendentes e encerra a conexão, preservando as tabelas e os dados. Ele ainda não inicia a API; sua entrada normal será definida na implementação.

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

> Nesta fase inicial, os ajustes de estrutura ficam na migration 001. Um banco
> que já registrou essa versão não é atualizado ao editar o arquivo. Nenhum reset
> é executado automaticamente; recriar o banco local exige uma decisão explícita.
