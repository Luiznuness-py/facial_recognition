# Explicacao das tabelas do banco de dados - Projeto APS

Este documento explica a proposta de organizacao das tabelas do banco de dados do projeto APS.

A ideia principal e separar bem as responsabilidades de cada tabela. Assim, o sistema consegue responder com clareza:

- quem é o usuario;
- quais permissoes existem;
- qual papel ou cargo ele possui;
- quais acessos foram realizados;
- quais recursos ou modulos do sistema podem ser acessados;

Essa estrutura deixa o banco mais organizado, facilita a manutencao e permite controlar melhor o acesso aos dados sensiveis.

## DBUsers - Usuarios do sistema

A tabela `DBUsers` representa as pessoas cadastradas no sistema.

No contexto da APS, esses usuarios sao as pessoas que vao passar pelo reconhecimento facial para tentar acessar o cofre ou consultar alguma parte protegida do sistema.

Ela deve guardar informacoes basicas do usuario, como nome, e-mail, idade, cargo ou role e o vinculo com o vetor biometrico.

A funcao dessa tabela e responder:

```text
Quem esta tentando acessar o sistema?
```

Exemplo:

```text
Nome: Joao Silva
E-mail: joao@email.com
Role: Diretor de Florestas
Vetor biometrico: ID 10
```

Essa tabela nao deve concentrar todas as regras de permissao. Ela apenas identifica o usuario e aponta para outras tabelas que explicam seu papel e seu dado biometrico.

## DBRoles - Papeis ou cargos de acesso

A tabela `DBRoles` representa o papel que o usuario tem dentro do sistema.

No projeto APS, os papeis servem para diferenciar os niveis de acesso. Por exemplo, um usuario comum pode ter acesso limitado, um diretor pode acessar apenas a area da sua divisao, e o ministro pode ter um acesso mais amplo.

Exemplos de roles:

```text
GENERAL_USER
DIRECTOR_FLORESTAS
DIRECTOR_BIODIVERSIDADE
DIRECTOR_AREAS_PROTECAO
DIRECTOR_DIREITOS_ANIMAIS
DIRECTOR_TOXINAS
MINISTER
ADMIN
```

A funcao dessa tabela e responder:

```text
Qual e o papel desse usuario no sistema?
```

Exemplo:

```text
Usuario: Maria Souza
Role: DIRECTOR_BIODIVERSIDADE
Nivel: 2
```

O ponto importante e que a role sozinha nao deve dizer tudo que o usuario pode fazer. Ela representa o cargo ou perfil. As permissoes detalhadas ficam em outras tabelas.

## DBPermissions - Permissoes do sistema

A tabela `DBPermissions` representa as acoes que podem ser realizadas dentro do sistema.

Ela responde o que alguem pode fazer, independentemente de onde essa acao sera feita.

Exemplos de permissoes:

```text
READ
CREATE
UPDATE
DELETE
GENERATE_REPORT
MANAGE_USERS
```

A funcao dessa tabela e responder:

```text
O que pode fazer?
```

Exemplo:

```text
READ   -> pode consultar informacoes
UPDATE -> pode alterar informacoes
DELETE -> pode remover informacoes
```

Separar permissoes em uma tabela propria evita repetir textos e regras em varias partes do banco. Tambem facilita adicionar novas permissoes no futuro.

## DBResources - Recursos ou modulos protegidos

A tabela `DBResources` representa qual parte do sistema esta sendo protegida.

Ela e importante porque uma permissao so faz sentido quando sabemos onde ela pode ser usada.

Por exemplo, dizer que um diretor pode `READ` ainda e incompleto. O sistema precisa saber se ele pode ler dados de florestas, biodiversidade, areas de protecao, toxinas ou outro modulo.

Exemplos de resources:

```text
FLORESTAS
BIODIVERSIDADE
DIREITOS_ANIMAIS
AREAS_PROTECAO
TOXINAS
RELATORIOS
USUARIOS
COFRE
```

A funcao dessa tabela e responder:

```text
Em qual area, tela, tabela ou modulo essa permissao pode ser usada?
```

Exemplo:

```text
Resource: FLORESTAS
Descricao: Dados relacionados a florestas protegidas
```

Sem `DBResources`, o sistema so conseguiria dizer:

```text
Diretor pode READ
Diretor pode UPDATE
```

Mas isso gera uma duvida:

```text
Diretor de que area?
```

Com `DBResources`, o controle fica mais preciso:

```text
DIRECTOR_FLORESTAS pode READ em FLORESTAS
DIRECTOR_BIODIVERSIDADE pode READ em BIODIVERSIDADE
MINISTER pode READ em todos os modulos
```

## DBRolePermissions - Ligacao entre role, permissao e recurso

A tabela `DBRolePermissions` e uma tabela de relacionamento.

Ela liga tres informacoes principais:

- quem tem acesso: `DBRoles`;
- o que pode fazer: `DBPermissions`;
- onde pode fazer: `DBResources`.

Essa tabela e o centro do controle de autorizacao, porque define exatamente quais acoes cada papel pode executar em cada recurso do sistema.

A funcao dessa tabela e responder:

```text
Qual perfil pode fazer qual acao em qual recurso?
```

Exemplo:

```text
Role: DIRECTOR_FLORESTAS
Permission: READ
Resource: FLORESTAS
```

Outro exemplo:

```text
Role: DIRECTOR_FLORESTAS
Permission: UPDATE
Resource: FLORESTAS
```

Nesse caso, o diretor de florestas pode consultar e alterar dados de florestas.

Mas ele nao deveria ter automaticamente acesso a biodiversidade, areas de protecao ou toxinas. Para isso acontecer, precisaria existir outro registro em `DBRolePermissions`.

Exemplo de tabela:

```text
ID_ROLE_PERMISSION | ID_ROLE | ID_PERMISSION | ID_RESOURCE
1                  | 2       | 1             | 1
2                  | 2       | 3             | 1
3                  | 3       | 1             | 2
4                  | 6       | 1             | 1
5                  | 6       | 1             | 2
```

Essa modelagem e melhor do que colocar varias colunas de permissao diretamente no usuario, porque permite crescer o sistema sem baguncar a estrutura.

## Exemplo geral do fluxo de acesso

Um fluxo simples de acesso poderia funcionar assim:

```text
1. O usuario tenta acessar o sistema.
2. O sistema verifica o vetor facial em DBVectors.
3. Se o reconhecimento for valido, o sistema identifica o usuario em DBUsers.
4. O sistema consulta a role do usuario em DBRoles.
5. O sistema verifica em DBRolePermissions se aquela role possui a permissao necessaria.
6. A permissao e validada junto com DBPermissions e DBResources.
7. O acesso e permitido ou negado.
8. A tentativa e registrada em DBAccessLogs ou DBRegistros.
```

Exemplo pratico:

```text
Usuario: Ana
Role: DIRECTOR_FLORESTAS
Permissao solicitada: READ
Recurso solicitado: FLORESTAS
Resultado: PERMITIDO
```

Outro exemplo:

```text
Usuario: Ana
Role: DIRECTOR_FLORESTAS
Permissao solicitada: READ
Recurso solicitado: TOXINAS
Resultado: NEGADO
```

Isso acontece porque Ana e diretora de florestas, nao de toxinas. Entao ela so pode acessar toxinas se existir uma permissao especifica liberando isso.

## Resumo da responsabilidade de cada tabela

```text
DBUsers            -> identifica quem e o usuario
DBRoles            -> define o papel ou cargo do usuario
DBPermissions      -> define quais acoes existem no sistema
DBResources        -> define quais modulos ou areas podem ser protegidos
DBRolePermissions  -> liga role + permissao + recurso
```

``` mermaid
erDiagram
    DB_USERS {
        int id_user PK
        int id_role FK
        varchar name
        varchar email
    }

    DB_ROLES {
        int id_role PK
        varchar name
        int access_level
    }

    DB_PERMISSIONS {
        int id_permission PK
        varchar action
    }

    DB_RESOURCES {
        int id_resource PK
        varchar name
        varchar description
    }

    DB_ROLE_PERMISSIONS {
        int id_role_permission PK
        int id_role FK
        int id_resource FK
        int id_permission FK
    }

    DB_ROLES ||--o{ DB_USERS : "possui"
    DB_ROLES ||--o{ DB_ROLE_PERMISSIONS : "recebe"
    DB_RESOURCES ||--o{ DB_ROLE_PERMISSIONS : "protege"
    DB_PERMISSIONS ||--o{ DB_ROLE_PERMISSIONS : "autoriza"
```
