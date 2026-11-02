# Frontend do laboratório

Interface institucional em HTML, CSS e JavaScript, sem framework, dependências novas ou build. A identidade usa os dois PNGs aprovados, em `facial_recognition/frontend/static/assets/`. O rodapé cita ICMBio e MMA com links, sem reproduzir marcas oficiais e sem alegar parceria.

## Abrir

Com o PostgreSQL já disponível e o ambiente local preparado conforme `AUTH_LAB.md`:

```bash
poetry run uvicorn facial_recognition.app:app --reload
```

Abra `/lab` na mesma origem da API. A página inicial apresenta as publicações; `/lab#/login` abre o acesso institucional. O endereço `/` da API foi preservado. Não houve alteração de rede, certificado, banco, seed ou implantação.

As rotas das telas usam fragmentos de URL (`#/amostras`, por exemplo), sem precisar de novas rotas HTML no servidor. Busca, filtros e paginação ficam na URL. Não há dados científicos, senhas ou tokens persistidos no navegador.

## Organização

| Arquivo em `frontend/` | Responsabilidade |
| --- | --- |
| `index.html` | Estrutura semântica, logos, rodapé, conteúdo e janela de confirmação/formulário. |
| `static/lab.css` | Identidade visual, componentes, foco e apresentação responsiva. |
| `static/lab.js` | Navegação, menus por permissões, restauração e expiração de sessão. |
| `static/api.js` | Chamadas relativas, envelope, CSRF, refresh único em andamento e descoberta de rotas. |
| `static/ui.js` | Elementos DOM seguros, campos nativos, mensagens, paginação e ações compartilhadas. |
| `static/auth.js` | Login, cadastro/reconhecimento facial, senha e controle da câmera. |
| `static/admin.js` | Contas, solicitações e auditoria. |
| `static/science.js` | Amostras, investigações, revisão, envios e cofre. |
| `static/public.js` | Lista/detalhe de notícias e gestão das publicações pelo N3. |

Os conteúdos recebidos são criados como texto, sem interpolação em HTML. Os menus orientam a navegação por `auth/me.permissions`; a API continua responsável por autorizar cada ação e filtrar recursos/campos. ADMIN não ganha conteúdo científico; N3 não ganha a área de edição do N1/N2.

## Telas e chamadas preparadas

Todos os caminhos abaixo têm prefixo `/api/v1`. A presença de uma chamada no frontend **não significa que o backend a implementa**.

| Fluxo | Chamadas |
| --- | --- |
| Entrada e sessão | `GET /auth/me`, `GET /auth/flow`, `GET /auth/csrf`, `POST /auth/login`, `/auth/refresh`, `/auth/logout` |
| Biometria | Modo real: `POST /auth/biometric/enroll`, `POST /auth/biometric` com cinco campos `frames`; modo simulado: `POST /auth/biometric/simulate` sem corpo, após etapa autenticada |
| Definição e troca de senha | `POST /auth/password/complete`, `/auth/password-change/start`, `/auth/password-change/complete` |
| Contas | `GET /users`, `GET/PATCH /users/{id}`, `POST /users/{id}/deactivate`, `/reactivate`, `/recovery`, `/activation/revalidate` |
| Solicitações | `GET/POST /access-requests`, `GET /access-requests/{id}`, `POST /access-requests/{id}/approve`, `/reject` |
| Equipes e auditoria | `GET /teams`, `GET /admin/audit-events` |
| Amostras | `GET/POST /biological-agents`, `GET/PATCH /biological-agents/{id}`, `PATCH /biological-agents/{id}/status` |
| Investigações da amostra | `GET/POST /biological-agents/{id}/validations`, `GET /biological-agents/{id}/responsible-candidates` |
| Análise | `GET /validations/{id}`, `PATCH /validations/{id}/analysis`, `POST /validations/{id}/submit` |
| Colaboração | Participantes vêm em `GET /validations/{id}`; candidatos em `GET /validations/{id}/participant-candidates`; inclusão em `POST /validations/{id}/participants`; remoção em `DELETE /validations/{id}/participants/{user_id}`; atribuição em `PATCH /validations/{id}/responsible` |
| Revisão N2 | Consultas de amostras e investigações com `status=IN_REVIEW`; `POST /validations/{id}/return`, `/close`, `/report/send` |
| Acompanhamento N2 | `GET /reports/sent`; usa o identificador do pedido para abrir outra investigação, sem ler o dossiê |
| Cofre N3 | `GET /vault/dossiers`, `GET /vault/dossiers/{id}`, `POST /vault/dossiers/{id}/publish`, `/keep-restricted`, `/request-validation` |
| Publicações N3 | `GET /publications`, `GET /publications/{id}`, `POST /publications/{id}/withdraw` |
| Público | `GET /public/publications`, `GET /public/publications/{id}` |

A lista de revisões começa pela seleção da amostra e consulta as investigações filtradas, pois não existe contrato de listagem global de revisões. Não foi inventado `GET /validations`.

Os participantes são lidos da projeção da investigação, que já os inclui; não é necessário chamar o catálogo de participantes novamente. Catálogos de papéis/permissões administrativos não receberam páginas de edição, pois não há esse fluxo no MVP.

### O que existe no backend inspecionado

- Login, CSRF, consulta de etapa, cadastro/reconhecimento facial, definição de senha, `auth/me`, refresh e logout.
- `GET /teams/` e `GET /users/`, incluindo filtros e paginação das contas.
- `POST /access-requests`, atualmente **somente criação direta pelo ADMIN**. A existência desse endereço não comprova solicitações pendentes por N2/N3; a tela informa a dependência e mantém o erro real da API.

As outras chamadas da tabela estão preparadas conforme os contratos, mas não têm implementação no checkout inspecionado. A troca voluntária de senha também depende de backend.

### Como a interface identifica pendências

Na abertura, consulta `/openapi.json` e confere o método e o caminho da operação. Uma operação ausente mostra “Funcionalidade pendente”; não chama uma alternativa nem inventa registros. O botão de tentar novamente atualiza a descoberta. Também é possível recarregar a página após implementar uma rota.

Se o OpenAPI estiver indisponível, a interface tenta a chamada normal e exibe o erro real; não presume que um 404 de um registro significa rota não implementada. Uma rota registrada pode continuar incompleta: o resultado do servidor é preservado, sem converter erro em sucesso.

## Comportamentos importantes

- Cookies permanecem HttpOnly; JavaScript não lê tokens de sessão. Não há uso de localStorage ou sessionStorage.
- Toda alteração solicita CSRF atualizado. Um 401 privado tenta refresh uma vez e repete a chamada uma vez; falha de renovação por credencial encerra a apresentação da área privada.
- Primeira entrada segue a etapa do servidor. ADMIN não passa pela câmera; usuários ativados não recebem uma etapa de senha indevida.
- Com `BIOMETRICS_MODE=real`, cadastro e reconhecimento usam câmera real. A captura para ao ocultar/sair da página, trocar de tela, cancelar ou concluir. A imagem apresentada é espelhada, mas a enviada mantém a orientação e proporção originais.
- Com `BIOMETRICS_MODE=simulated` em development/test, a etapa mostra “Biometria simulada” e permite continuar sem câmera. O backend informa o modo em auth/flow e autoriza o POST protegido `/auth/biometric/simulate`; a UI não escolhe o modo nem envia imagens fictícias. Senha definitiva e autorização continuam obrigatórias. Produção recusa simulação.
- O rascunho permite textos incompletos. “Salvar e enviar ao N2” exige os quatro textos, salva primeiro e só então envia. Se o envio falhar após salvar, a mensagem distingue as duas operações.
- A edição cadastral só aparece se `BiologicalAgentResponse.can_edit` for true para o ator. O backend deve considerar todas as entregas, sem depender de página/filtro, e revalidar a regra ao salvar.
- A troca de responsável preserva o anterior como colaborador conforme o backend. Colaboradores recebem leitura; o frontend não oferece edição ou envio para eles.
- O envio N2 mostra relatório interno e ficha pública em seções distintas, com prévia. A confirmação avisa sobre o selamento; após sucesso os campos são limpos e a tela muda para acompanhamento.
- Categoria pública é escolhida pelo N2, sem conversão automática do percentual de risco.
- N3 lê o conteúdo e decide sem editor do original. Publicação, sigilo, nova investigação e retirada têm confirmação ou formulário explicativo com motivo.
- Falhas comuns preservam os campos. Navegar com alterações não salvas pede confirmação; expiração de sessão limpa a área privada em vez de conservar conteúdo de outra identidade.
- Mensagens de erro de formulário recebem foco; labels são associados aos campos. Há link de salto, navegação nativa, indicadores textuais e foco visível.
- No celular, tabelas passam a registros com os rótulos dos campos. Textos longos quebram sem estourar a página.

## Roteiro manual por fluxo

Usar somente contas e registros de teste autorizados. As funções futuras devem ser verificadas conforme os respectivos endpoints forem implementados. Uma mensagem de pendência é o resultado esperado enquanto a rota não existir.

### Público

1. Abrir `/lab#/noticias` sem sessão. Conferir notícia pendente ou lista real, sem relatório, equipe, percentual interno ou local exato.
2. Pesquisar e paginar; recarregar e conferir os filtros na URL.
3. Abrir detalhe; verificar parágrafos longos e voltar à lista. Notícia retirada deve retornar 404 e sumir da lista.
4. Conferir logo, links ICMBio/MMA e identificação acadêmica no rodapé.

### Entrada, ativação e senha

1. Tentar senha inválida; conferir mensagem sem liberar área privada e sem apagar o email.
2. Entrar como ADMIN; confirmar ausência de etapa facial e definição de senha somente quando exigida.
3. Entrar com temporária de N1/N2/N3; em real cadastrar rosto; em simulated continuar sem câmera; definir senha e chegar ao menu autorizado. Repetir com senha definitiva: reconhecimento facial, sem novo cadastro ou troca obrigatória indevida.
4. Negar permissão de câmera, remover dispositivo e ocultar a aba durante a captura. Conferir recuperação e desligamento.
5. Conferir cinco `frames`, sem token no corpo, sem autenticação falsa e sem imagens persistidas pelo frontend.
6. Recarregar durante etapa válida e expirada. Conferir restauração ou pedido de nova entrada.
7. Iniciar Alterar senha, confirmar senha atual, cumprir a etapa facial quando exigida e completar com senha/confirmação iguais. Conferir retorno ao login e revogação real das sessões pelo backend.
8. Expirar access, conferir refresh/repetição únicos; revogar refresh e confirmar saída da área privada. Sair deve chamar o servidor.

### ADMIN

1. Filtrar contas vigentes, pendentes e desativadas; paginar e abrir uma conta.
2. Criar N1/N2 com equipe e N3 sem equipe. Conferir rejeição de email duplicado/vaga ocupada e preservação dos campos.
3. Corrigir nome/email/papel/equipe; verificar rejeição de combinações incompatíveis e encerramento de sessões quando aplicável.
4. Revalidar a mesma temporária. Recuperar senha, biometria e ambas: BIOMETRIC não deve enviar `temporary_password`; outros modos exigem senha de 8–128 caracteres.
5. Desativar com motivo e reativar com nova temporária/motivo. Conferir manutenção do histórico e exigência de recadastro.
6. Aprovar e rejeitar pedidos pendentes, consultando o motivo autorizado. Conferir auditoria, filtros de data e ausência de conteúdo científico.

### N1

1. Cadastrar os sete campos da amostra. Conferir código e primeira investigação gerados pelo servidor.
2. Salvar rascunho com textos parciais/risco vazio; simular falha de rede e conferir preservação dos campos.
3. Enviar análise completa; conferir bloqueio e entrega preservada. Após devolução, corrigir e reenviar, sem apagar a primeira entrega.
4. Incluir colaborador; entrar como ele e conferir leitura, sem salvar, enviar ou compartilhar. Remoção deve retirar o acesso atual sem alterar entregas antigas.
5. Conferir acesso negado ao cofre, contas, investigações não vinculadas e registros de outra equipe, inclusive por endereço direto.

### N2

1. Selecionar amostra em Revisões e abrir tarefas em revisão. Conferir ausência de edição no texto do N1.
2. Devolver e encerrar com motivo; conferir retorno do estado real e histórico.
3. Em preparação/devolução, incluir/remover colaborador e trocar responsável. Conferir que o anterior passa a leitor.
4. Abrir nova investigação com responsável elegível, amostra ativa e sem outra investigação em andamento. Conferir conflitos reais do backend.
5. Preparar relatório e ficha, conferir prévia e enviar. Conferir confirmação de selamento e que o acompanhamento não recebe/reabre conteúdo selado.
6. Atender pedido N3 usando o botão em Enviadas ao N3; conferir envio de `request_vault_id`, motivo e vínculo com a nova tarefa.
7. Solicitar conta N1: enviar somente nome, email e temporária; papel/equipe são determinados pelo servidor. No backend atual, esse fluxo ainda não está disponível.

### N3

1. Filtrar cofre e abrir dossiê. Conferir entrega, relatório, percentual interno e ficha pública separados.
2. Em dossiês distintos, publicar, manter em sigilo e solicitar outra investigação. Conferir decisão final e bloqueio de nova decisão incompatível.
3. Conferir motivo de sigilo exclusivo do N3; pedido de nova investigação segue para N2, sem liberar o cofre.
4. Retirar publicação com motivo, conferir desaparecimento público, preservação do histórico e ausência de botão de republicação/edição.
5. Solicitar N2 escolhendo equipe, sem escolher N1/N3.

### Usabilidade transversal

1. Conferir em 1440, 768 e 390 pixels: navegação, tabela, formulários, câmera, dossiê e notícias.
2. Navegar só com Tab/Shift+Tab/Enter/Espaço e usar Escape nas janelas. Conferir foco, labels e confirmação de descarte.
3. Usar textos muito longos e marcação HTML literal. Nenhum conteúdo deve executar como HTML ou ampliar a largura da página.
4. Simular 403, 404, 409, 422, 429, 503 e desconexão; conferir mensagem, campos preservados e ausência de sucesso fictício.
5. Clicar duas vezes ao enviar uma ação; conferir uma única mutação. Não trocar de tela enquanto a ação estiver em andamento.

## Evidências desta implementação

- Sintaxe dos sete módulos JavaScript conferida com Node.
- Smoke estático de `/lab`, sete módulos, CSS, dois PNGs e cabeçalhos; 41 testes passaram no conjunto `tests/test_frontend.py` + `tests/test_cookie_transport.py`.
- Tentativa dos testes existentes de autenticação/regressões/cookies/request-id: 52 passaram e 26 tiveram erro de preparação por PostgreSQL indisponível (`ConnectionRefusedError`). Não são 26 falhas funcionais do frontend, mas também não comprovam autenticação real integrada.
- Navegador Chromium/Brave headless real em desktop e celular; revisão com respostas de API fictícias interceptadas no processo de teste, fora do produto. Percorridos N1, N2, N3 e ADMIN, campos JSON, preservação após erro, CSRF, leitura de colaborador, decisões N3 e captura de cinco imagens com câmera artificial do navegador. Não comprova eficácia biométrica ou transações reais.
- Artefatos de revisão ficam em `work/frontend-review/`; capturas com dados fictícios são identificadas como prévia de teste. Não são dados científicos reais e não há modo demonstrativo embutido na aplicação.
- Nenhum commit, push ou deploy. Banco, modelos, autorização e regras científicas do backend não foram implementados ou alterados nesta etapa.

## Pendências

- PostgreSQL disponível para repetir integração real e testar com contas autorizadas.
- Implementação das rotas futuras pelos responsáveis, conforme BUSINESS_RULES.md e ENDPOINTS.md.
- Validar o percurso completo do modo simulado com PostgreSQL e contas fictícias; o recurso já está implementado no backend e frontend.
- Webcam física, calibração biométrica, leitor de tela, dispositivos móveis físicos e HTTPS remoto ainda não validados.
- Sem painel de métricas inventadas, mapa epidemiológico, prontuário animal ou cadastro público: não fazem parte dos contratos atuais.

### Reformulação visual

A primeira versão foi rejeitada na avaliação visual: tipografia genérica, pouca separação entre navegação e conteúdo, predominância de fundos esverdeados e ausência de uma composição própria para o portal e para o acesso. A segunda versão refaz essa direção, preservando os formulários, contratos e autenticação presentes no checkout, inclusive o modo de biometria já existente.

- **Portal:** direção `editorial-report` da skill design-taste-frontend, com fotografia de fauna em destaque, título editorial, pesquisa de publicações e apresentação do projeto.
- **Acesso:** composição dividida, com imagem e texto sobre verde profundo à esquerda e formulário claro à direita. No celular, a apresentação fica compacta acima do formulário.
- **Área institucional:** navegação lateral escura, ícones funcionais próprios, identificação da pessoa na base do menu, tabelas e filtros em superfícies claras.
- **Tipografia:** Manrope variável servida localmente; a logo fornecida permanece intacta.
- **Interação:** entradas breves de imagem/conteúdo, retorno visual dos controles e suporte a movimento reduzido. Não há animação contínua.
- **Imagens e licenças:** fotografia ilustrativa de AntanO, CC BY-SA 4.0; fonte sob OFL. Fontes, licença e uso constam em `frontend/static/assets/CREDITS.md`, com crédito e link também na interface. A fotografia não representa o laboratório fictício.

As skills clean e minimal orientaram as telas internas; design-taste-frontend orientou o portal. A revisão usa também as [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md). Inspeção de screenshots em computador, tablet e celular não substitui validação em dispositivos físicos ou com leitor de tela.

A checagem automática da skill é registrada em `work/redesign/`. O portal tem uma fotografia principal, em vez de preencher a página com quatro imagens e vídeo para cumprir uma meta de página promocional. Legendas e links de navegação também podem ser classificados pelo detector como rótulos acima de títulos; devem ser avaliados no contexto das capturas. Não se declara aprovação integral pelo inspetor.

Foram repetidos os 41 testes estáticos/de cookies e os percursos de interface com respostas de API isoladas. A revisão estética não representa validação das rotas científicas ou da biometria contra dados reais. Nenhuma dependência de execução, framework, build ou integração externa foi adicionada.


### Consolidação de contratos — 02/11/2026

O botão “Corrigir cadastro” deixou de inferir autorização pelos cards da página atual. Agora depende de can_edit === true na resposta da amostra, além de papel/permissão compatíveis. BiologicalAgentResponse exige esse campo; Amanda deve calculá-lo no backend com base no histórico completo e revalidar no PATCH. Campo ausente mantém a ação oculta, sem liberar edição por falta de dados.

A revisão no navegador confirmou can_edit false/true/ausente em páginas e filtros diferentes e repetiu os percursos N1/N2/N3/ADMIN com respostas fictícias, sem erros JavaScript. A etapa simulada sem câmera também foi conferida com POST vazio protegido por CSRF e avanço para senha. As capturas permanecem em artefatos locais de revisão, não versionados; não são evidência de backend científico implementado.

A validação real de autenticação e o isolamento do modo simulado em PostgreSQL estão registrados em AUTH_LAB.md. HTTPS remoto, celular físico, leitor de tela e calibração facial permanecem pendentes.
