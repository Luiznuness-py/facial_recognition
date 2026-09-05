# Arquitetura da APS — Sistema de Autenticação Biométrica Facial

## 1. Direção técnica adotada

A arquitetura escolhida busca equilibrar três pontos:

1. Atender ao enunciado da APS.
2. Evitar o uso de soluções prontas para a parte principal do reconhecimento facial.
3. Manter o projeto organizado e viável para desenvolvimento e apresentação.

A stack proposta é:

```text
Frontend: HTML, CSS e JavaScript puro
Backend: FastAPI
Banco de dados: PostgreSQL
Infraestrutura local: Docker para subir o PostgreSQL
Modelo de IA: TensorFlow/Keras
Persistência: SQL manual, sem ORM
Validação: manual nas regras principais
Modelo facial: próprio, sem modelo pré-treinado
```

A ideia central é que o grupo desenvolva a lógica principal do sistema: captura da imagem, pré-processamento, geração de embeddings, comparação biométrica, verificação de permissões e registro das tentativas de acesso.

---

## 2. Papel do Docker no projeto

O Docker será usado principalmente para evitar a necessidade de instalar e configurar o PostgreSQL diretamente na máquina de cada integrante do grupo. Em vez de cada pessoa instalar o banco manualmente, o projeto terá um arquivo `docker-compose.yml` responsável por subir um container do PostgreSQL com as mesmas configurações para todos.

A ideia é usar Docker para padronizar o ambiente de banco de dados, não para esconder a lógica do projeto. O grupo continuará criando as tabelas, escrevendo SQL manual, fazendo conexão pelo backend e controlando as regras de negócio.

Arquitetura com Docker:

```text
Computador local
   |
   | docker compose up -d
   v
Container PostgreSQL
   |
   | porta 5432 exposta localmente
   v
FastAPI conecta em localhost:5432
```

Exemplo de `docker-compose.yml` para o banco:

```yaml
services:
  postgres:
    image: postgres:16
    container_name: aps_postgres
    environment:
      POSTGRES_DB: aps_biometria
      POSTGRES_USER: aps_user
      POSTGRES_PASSWORD: aps_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./sql/schema.sql:/docker-entrypoint-initdb.d/schema.sql

volumes:
  postgres_data:
```

Com essa configuração, quando o container for iniciado pela primeira vez, o PostgreSQL cria o banco `aps_biometria`.

A conexão do backend pode usar variáveis de ambiente:

```text
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aps_biometria
DB_USER=aps_user
DB_PASSWORD=aps_password
```

No início do projeto, a recomendação é containerizar apenas o PostgreSQL. Dessa forma, o banco de dados pode ser executado de maneira padronizada por meio do Docker, sem a necessidade de instalação manual em cada máquina.

O backend com FastAPI pode rodar localmente em um ambiente virtual Python durante a fase inicial de desenvolvimento. Posteriormente, caso o grupo queira padronizar ainda mais a execução da aplicação, também será possível criar um container para o backend, mantendo frontend, backend e banco de dados em serviços isolados, porém conectados por meio do `docker-compose`.

---

## 3. Papel do FastAPI

O FastAPI será usado como camada de API HTTP. Ele será responsável por receber as requisições do frontend e encaminhar os dados para os serviços internos do sistema.

O FastAPI não será usado como forma de esconder a lógica principal do projeto. Ele apenas organiza:

- rotas HTTP;
- recebimento de arquivos/imagens;
- respostas em JSON;
- comunicação entre frontend e backend.

A lógica principal continuará sendo implementada pelo grupo.

---

## 4. Solução escolhida: CNN siamesa e embeddings faciais

A solução mais adequada encontrada para a entrega desse proejeto é treinar um modelo para gerar embeddings faciais.

Nesse caso, o modelo não responde diretamente:

```text
"Esse rosto é o usuário X."
```

Em vez disso, ele transforma o rosto em um vetor numérico de características:

```text
[0.12, 0.87, 0.44, 0.03, ...]
```

Esse vetor é chamado de **embedding biométrico**.

A lógica passa a ser:

```text
1. O modelo é treinado previamente para extrair características faciais.
2. No cadastro, o sistema captura imagens do novo usuário.
3. O modelo gera embeddings dessas imagens.
4. Os embeddings são salvos no PostgreSQL.
5. Na autenticação, uma nova imagem é capturada.
6. O modelo gera um novo embedding.
7. O sistema compara esse embedding com os embeddings salvos.
8. Se a distância for pequena o suficiente, o usuário é reconhecido.
9. Depois disso, o sistema verifica o nível de permissão.
```

Essa abordagem permite cadastrar novos usuários sem treinar o modelo novamente.

---

## 5. Relação com as cinco fases do processamento de imagens

O projeto deve ser explicado com base nas cinco fases do processamento digital de imagens.

### 1. Aquisição

A imagem é obtida pela webcam do navegador usando JavaScript.

Também podem ser capturadas imagens de referência durante o cadastro do usuário.

### 2. Pré-processamento

A imagem é tratada antes de ser enviada ao modelo.

Exemplos:

- redimensionamento;
- normalização dos pixels;
- conversão de cor;
- centralização do rosto;
- padronização do tamanho da entrada.

### 3. Segmentação

A segmentação corresponde à separação da região de interesse, ou seja, a região do rosto.

Dependendo da autorização do professor, pode ser usado OpenCV para auxiliar na detecção da face. Caso o professor não permita detectores prontos, o sistema pode trabalhar com captura controlada, orientando o usuário a posicionar o rosto em uma área central da tela.

### 4. Extração de características

A extração de características é feita pela CNN. As camadas convolucionais aprendem padrões visuais do rosto e transformam a imagem em um vetor numérico.

Esse vetor é o embedding facial.

### 5. Classificação/interpretação

A interpretação ocorre quando o sistema compara o embedding capturado com os embeddings armazenados no banco.

Se a distância estiver dentro do limite aceito, o usuário é reconhecido. Depois disso, o backend verifica o nível de permissão e decide se o acesso será permitido ou negado.

---

## 6. Cálculo de distância entre embeddings

Depois que o modelo gera o embedding da imagem capturada, o sistema compara esse vetor com os embeddings armazenados no banco.

Uma forma simples é usar distância euclidiana.

```python
import math


def calcular_distancia(embedding_a, embedding_b):
    soma = 0

    for valor_a, valor_b in zip(embedding_a, embedding_b):
        soma += (valor_a - valor_b) ** 2

    return math.sqrt(soma)
```

A lógica de autenticação seria:

```text
Se a menor distância encontrada for menor que o limite definido, o usuário é reconhecido.
Se a distância for maior que o limite, o usuário não é reconhecido.
```

Exemplo:

```text
Distância encontrada: 0.38
Limite configurado: 0.50
Resultado: usuário reconhecido
```

Outro exemplo:

```text
Distância encontrada: 0.82
Limite configurado: 0.50
Resultado: usuário não reconhecido
```

O limite ideal deve ser definido com testes durante o desenvolvimento.

## 7. Como funciona uma rede siamesa

A rede siamesa trabalha comparando pares de imagens.

Durante o treinamento, ela recebe dois tipos de pares:

### Par positivo

Duas imagens da mesma pessoa.

```text
foto_01_luiz.jpg + foto_02_luiz.jpg
Resultado esperado: parecido
```

### Par negativo

Duas imagens de pessoas diferentes.

```text
foto_01_luiz.jpg + foto_01_joao.jpg
Resultado esperado: diferente
```

A rede aprende a gerar vetores próximos para imagens da mesma pessoa e vetores distantes para imagens de pessoas diferentes.

O objetivo do modelo não é memorizar nomes. O objetivo é aprender uma representação numérica do rosto.

---

## 8. Regra de permissão

O reconhecimento facial identifica quem é a pessoa. A autorização decide se ela pode acessar ou não.

Essas duas etapas devem ficar separadas.

```text
Reconhecimento facial:
Quem é essa pessoa?

Autorização:
Essa pessoa tem permissão para acessar esta área?
```

Exemplo de regra:

```text
Nível 1: acesso geral.
Nível 2: acesso à divisão específica.
Nível 3: acesso total.
```

---

## 9. Dataset do projeto

O dataset pode ser criado pelo próprio grupo.

Estrutura sugerida:

```text
dataset/
├── raw/
│   ├── pessoa_1/
│   │   ├── img_001.jpg
│   │   ├── img_002.jpg
│   │   └── img_003.jpg
│   ├── pessoa_2/
│   │   ├── img_001.jpg
│   │   ├── img_002.jpg
│   │   └── img_003.jpg
│   └── pessoa_3/
│       ├── img_001.jpg
│       ├── img_002.jpg
│       └── img_003.jpg
│
└── processed/
    ├── pessoa_1/
    ├── pessoa_2/
    └── pessoa_3/
```

Recomendação inicial:

```text
3 a 5 pessoas
50 a 100 imagens por pessoa para treino e teste
variação leve de iluminação, posição e expressão
```

---

## 10. Fluxo de autenticação facial

O fluxo de autenticação é o principal fluxo da apresentação.

```text
1. Usuário acessa a tela de autenticação.
2. O navegador solicita acesso à webcam.
3. O usuário posiciona o rosto na câmera.
4. O JavaScript captura uma imagem.
5. A imagem é enviada para a API FastAPI.
6. O backend valida a imagem recebida.
7. A imagem passa pelo pré-processamento.
8. O modelo gera o embedding facial.
9. O sistema busca os templates ativos no PostgreSQL.
10. O sistema compara o embedding atual com os embeddings cadastrados.
11. Se a menor distância estiver abaixo do limite definido, o usuário é reconhecido.
12. O backend verifica o nível de acesso do usuário.
13. O sistema registra a tentativa no banco.
14. A API retorna o resultado para o frontend.
15. O frontend exibe acesso permitido ou negado.
```

Exemplo de resposta da API:

```json
{
  "recognized": true,
  "authorized": true,
  "user": {
    "id": 1,  
    "name": "João",
    "role": "Diretor de Fiscalização",
    "access_level": 2
  },
  "distance": 0.3821,
  "message": "Acesso permitido."
}
```

Exemplo de resposta negada:

```json
{
  "recognized": false,  
  "authorized": false,
  "user": null,
  "distance": null,
  "message": "Usuário não reconhecido."
}
```

---

## 11. Fluxo de cadastro de usuário

O cadastro de usuário deve permitir inserir uma nova pessoa no sistema sem retreinar o modelo.

Fluxo proposto:

```text
1. Administrador acessa a tela de cadastro.
2. Informa nome, cargo, divisão e nível de acesso.
3. O sistema abre a webcam.
4. São capturadas várias imagens do rosto do usuário.
5. Cada imagem passa pelo pré-processamento.
6. O modelo gera um embedding para cada imagem.
7. O sistema salva os embeddings no PostgreSQL.
8. O usuário passa a estar disponível para autenticação.
```

---

## 12. Arquitetura geral do sistema

```text
Frontend HTML/CSS/JavaScript
   |
   | captura imagem da webcam
   | envia imagem via fetch()
   v
Backend FastAPI
   |
   | recebe imagem
   | valida arquivo
   | pré-processa imagem
   v
Modelo CNN siamesa TensorFlow/Keras
   |
   | gera embedding facial
   v
Comparador biométrico
   |
   | calcula distância/similaridade
   v
PostgreSQL
   |
   | usuários
   | permissões
   | templates biométricos
   | logs de tentativas
```

A separação principal é:

- o frontend captura e exibe informações;
- o backend processa e decide;
- o modelo gera embeddings;
- o banco armazena usuários, permissões e templates;
- o comparador biométrico calcula a similaridade;
- a regra de permissão determina se o acesso será permitido ou negado.

---

## 13. Estrutura de pastas proposta

```text
aps-biometria/
├── frontend/
│   ├── index.html
│   ├── cadastro.html
│   ├── dashboard.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── camera.js
│       ├── api.js
│       ├── auth.js
│       └── cadastro.js
│
├── backend/
│   ├── main.py
│   ├── core/
│   │   ├── database.py
│   │   ├── settings.py
│   ├── routes/
│   │   ├── innit.py
│   │   ├── auth_routes.py
│   │   ├── user_routes.py
│   │   └── report_routes.py
│   ├── seeds/
│   │   ├── seeds.py
│   ├── services/
│   │   ├── image_service.py
│   │   ├── recognition_service.py
│   │   ├── permission_service.py
│   │   └── access_log_service.py
│   ├── repository/
│   │   ├── user_repository.py
│   │   ├── template_repository.py
│   │   └── access_log_repository.py
│
├── model/
│   ├── train.py
│   ├── evaluate.py
│   ├── predict.py
│   └── face_embedding_model.keras
│
├── dataset/
│   ├── raw/
│   └── processed/
│
├── docs/
│   ├── ARCHITECTURE.md.md
│   └── ETAPAS.excalidraw
│
├── README.md
├── requirements.txt
├── docker-compose.yml
└── .env.example
```

---

## 14. Plano de execução em etapas

### Etapa 1 — Estrutura inicial

- Criar repositório.
- Criar estrutura de pastas.
- Criar README inicial.
- Criar ambiente virtual Python.
- Criar `requirements.txt`.

### Etapa 2 — Banco de dados com Docker

- Criar `docker-compose.yml` para subir o PostgreSQL.
- Criar volume persistente para não perder os dados do banco.
- Criar arquivo `.env.example` com as variáveis de conexão.
- Criar banco da APS no container.
- Criar tabelas iniciais pelo arquivo `sql/schema.sql`.
- Criar conexão manual do backend com o PostgreSQL.
- Testar inserts e selects simples.

### Etapa 3 — Frontend básico

- Criar `index.html`.
- Criar tela de autenticação.
- Criar CSS inicial.
- Criar JavaScript para abrir webcam.
- Capturar imagem da câmera.

### Etapa 4 — Backend básico

- Criar API FastAPI.
- Criar rota de status.
- Criar rota para receber imagem.
- Validar se a imagem chegou corretamente.
- Retornar resposta JSON simples.

### Etapa 5 — Dataset

- Criar tela ou script para capturar imagens.
- Organizar imagens por pessoa.
- Separar imagens brutas e processadas.
- Padronizar tamanho das imagens.

### Etapa 6 — Modelo

- Criar CNN siamesa com TensorFlow/Keras.
- Criar pares positivos e negativos.
- Treinar o modelo.
- Salvar o modelo treinado.
- Criar script para gerar embeddings.

### Etapa 7 — Cadastro biométrico

- Criar tela de cadastro de usuário.
- Salvar dados do usuário no PostgreSQL.
- Capturar imagens do usuário.
- Gerar embeddings.
- Salvar embeddings na tabela `templates_biometricos`.

### Etapa 8 — Autenticação

- Receber imagem pela API.
- Gerar embedding.
- Buscar templates no PostgreSQL.
- Calcular menor distância.
- Identificar usuário mais provável.
- Verificar permissão.
- Retornar resultado para o frontend.

### Etapa 9 — Logs e relatórios

- Registrar todas as tentativas.
- Criar tela simples de histórico.
- Mostrar usuário, data/hora, resultado e motivo.

### Etapa 10 — Documentação e apresentação

- Documentar arquitetura.
- Documentar banco.
- Explicar modelo.
- Explicar as cinco fases do processamento de imagem.
- Preparar demonstração.
- Preparar possíveis perguntas do professor.

---

## 23. Resumo final da proposta

A proposta final é desenvolver um sistema local de autenticação biométrica facial com frontend em HTML/CSS/JavaScript, backend em FastAPI, PostgreSQL executando em Docker e modelo próprio em TensorFlow/Keras.

O modelo será treinado previamente como uma CNN siamesa para gerar embeddings faciais. No cadastro, o sistema salva os embeddings do usuário no banco. Na autenticação, o sistema gera um novo embedding e compara com os templates cadastrados.

Essa abordagem permite cadastrar novos usuários sem retreinar o modelo inteiro, tornando o projeto mais robusto e mais coerente com um sistema biométrico real.

Stack final:

```text
HTML
CSS
JavaScript
FastAPI
Docker
PostgreSQL
SQL manual
TensorFlow/Keras
CNN siamesa
Embeddings faciais
```

Frase principal para defender o projeto:

```text
O modelo não memoriza usuários fixos. Ele aprende a extrair características faciais. O cadastro de novos usuários gera templates biométricos armazenados no banco, e a autenticação compara a imagem capturada em tempo real com os templates cadastrados para permitir ou negar acesso conforme o nível de permissão.
```

---

## 20. MVP do sistema

O MVP deve conter apenas o necessário para demonstrar o projeto funcionando.

Funcionalidades mínimas:

```text
1. Cadastro de usuários.
2. Captura de imagens pela webcam.
3. Geração de embeddings no cadastro.
4. Armazenamento dos templates biométricos no PostgreSQL.
5. Autenticação facial em tempo real.
6. Comparação do rosto capturado com os templates cadastrados.
7. Verificação do nível de permissão.
8. Exibição de acesso permitido ou negado.
9. Registro das tentativas de acesso.
10. Tela simples de relatório de tentativas.
```

---
