# Frontend do laboratório

Interface institucional em HTML, CSS e JavaScript, sem framework, dependências novas ou build. A identidade usa os dois PNGs aprovados, em `facial_recognition/frontend/static/assets/`. O rodapé aparece somente no portal público (`#/noticias` e seus detalhes) e cita ICMBio e MMA com links, sem reproduzir marcas oficiais e sem alegar parceria. Login, etapas de acesso e telas internas não exibem esse rodapé; as fotografias do login mantêm seus próprios créditos.

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
| `static/photos.js` | Fotografias locais responsivas, textos alternativos e legendas com autoria/licença. |
| `static/auth.js` | Login, cadastro/reconhecimento facial, senha e controle da câmera. |
| `static/admin.js` | Contas, solicitações e auditoria. |
| `static/science.js` | Amostras, investigações, revisão, envios e cofre. |
| `static/public.js` | Lista/detalhe de notícias e gestão das publicações pelo N3. |

Os conteúdos recebidos são criados como texto, sem interpolação em HTML. Os menus orientam a navegação por `auth/me.permissions`; a API continua responsável por autorizar cada ação e filtrar recursos/campos. ADMIN não ganha conteúdo científico; N3 não ganha a área de edição do N1/N2.

## Telas e contratos HTTP

Todos os caminhos abaixo têm prefixo `/api/v1` e estão registrados no backend atual. A presença de uma chamada e de sua rota não comprova a integração visual; o roteiro manual e as limitações de validação estão ao final deste documento.

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

### Backend disponível

As chamadas da tabela acima estão implementadas: autenticação e troca voluntária de senha, equipes, administração completa de contas/pedidos, auditoria administrativa, amostras e investigações, participantes, revisão, envios, cofre e publicações. `GET /validations/{id}/participants` também está disponível para clientes que precisem do catálogo separado.

Os contratos HTTP são exercitados com PostgreSQL real e a lista de operações documentadas é conferida contra `/openapi.json`. O roteiro visual completo com esse backend continua pendente. O layout foi revisado com respostas fictícias isoladas; depois, a demonstração em banco separado confirmou login N1, etapa simulada, amostras e publicações reais na interface. Isso é integração parcial, sem validar todos os percursos autenticados no navegador.

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
- A edição cadastral só aparece se `BiologicalAgentResponse.can_edit` for true para o ator. O backend considera todas as entregas, inclusive histórico excluído, sem depender de página/filtro, e revalida a regra sob lock ao salvar.
- A troca de responsável preserva o anterior como colaborador conforme o backend. Colaboradores recebem leitura; o frontend não oferece edição ou envio para eles.
- O envio N2 mostra relatório interno e ficha pública em seções distintas, com prévia. A confirmação avisa sobre o selamento; após sucesso os campos são limpos e a tela muda para acompanhamento.
- Categoria pública é escolhida pelo N2, sem conversão automática do percentual de risco.
- N3 lê o conteúdo e decide sem editor do original. Publicação, sigilo, nova investigação e retirada têm confirmação ou formulário explicativo com motivo.
- Falhas comuns preservam os campos. Navegar com alterações não salvas pede confirmação; expiração de sessão limpa a área privada em vez de conservar conteúdo de outra identidade.
- Mensagens de erro de formulário recebem foco; labels são associados aos campos. Há link de salto, navegação nativa, indicadores textuais e foco visível.
- No celular, tabelas passam a registros com os rótulos dos campos. Textos longos quebram sem estourar a página.

## Roteiro manual por fluxo

Usar somente contas e registros de teste autorizados. As rotas estão implementadas; executar o roteiro abaixo para verificar a integração visual. Uma mensagem de pendência só é esperada quando a API em execução usa uma versão sem a rota.

### Público

1. Abrir `/lab#/noticias` sem sessão. Conferir lista real, inclusive vazia, sem relatório, equipe, percentual interno ou local exato.
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
6. Atender pedido N3 usando o botão em Enviadas ao N3; conferir envio de `request_vault_id`, motivo e vínculo com a nova tarefa. Repetir com um segundo pedido: o card mostra o novo pedido pendente, enquanto a investigação mantém o motivo que a originou.
7. Solicitar conta N1: enviar somente nome, email e temporária; papel/equipe são determinados pelo servidor. Acompanhar a aprovação ou rejeição pelo ADMIN.

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

## Histórico da implementação visual anterior

Os resultados desta seção se referem à etapa visual anterior à implementação atual do backend.

- Sintaxe dos sete módulos JavaScript conferida com Node.
- Smoke estático de `/lab`, sete módulos, CSS, dois PNGs e cabeçalhos; 41 testes passaram no conjunto `tests/test_frontend.py` + `tests/test_cookie_transport.py`.
- Tentativa dos testes existentes de autenticação/regressões/cookies/request-id: 52 passaram e 26 tiveram erro de preparação por PostgreSQL indisponível (`ConnectionRefusedError`). Não são 26 falhas funcionais do frontend, mas também não comprovam autenticação real integrada.
- Navegador Chromium/Brave headless real em desktop e celular; revisão com respostas de API fictícias interceptadas no processo de teste, fora do produto. Percorridos N1, N2, N3 e ADMIN, campos JSON, preservação após erro, CSRF, leitura de colaborador, decisões N3 e captura de cinco imagens com câmera artificial do navegador. Não comprova eficácia biométrica ou transações reais.
- Artefatos de revisão ficam em `work/frontend-review/`; capturas com dados fictícios são identificadas como prévia de teste. Não são dados científicos reais e não há modo demonstrativo embutido na aplicação.
- Nenhum commit, push ou deploy. Banco, modelos, autorização e regras científicas do backend não foram implementados ou alterados nesta etapa.

## Pendências atuais de validação

- Repetir o roteiro visual com o backend real; a revisão atual de layout usa respostas fictícias isoladas. PostgreSQL e testes HTTP estão disponíveis.
- Validar no navegador o percurso completo do modo simulado com as contas fictícias; os fluxos HTTP já têm testes com PostgreSQL.
- Webcam física, calibração biométrica, leitor de tela, dispositivos móveis físicos e HTTPS remoto ainda não validados.
- Sem painel de métricas inventadas, mapa epidemiológico, prontuário animal ou cadastro público: não fazem parte dos contratos atuais.

## Refinamento dos controles e das fotografias

O commit `36bf438` preserva a base funcional e documental anterior a este refinamento. As mudanças visuais seguintes não alteram os contratos HTTP, autenticação, permissões ou regras do laboratório.

O construtor de formulários mantém o `select` original em `controls`, com nome, valor, eventos e validação. `enhanceSelect` apresenta um botão combobox e uma listbox no top layer da Popover API. Isso permite o mesmo estilo no formulário e no menu aberto, sem recorte pelo diálogo ou pelo contêiner. Navegadores sem a API usam o campo nativo; não perdem a seleção ou a validação.

- Setas, Home e End exploram opções; Enter, Espaço e Tab confirmam. Escape cancela a exploração sem fechar também o diálogo. Digitação procura por prefixo, sem distinção de acentos; letras repetidas percorrem opções equivalentes.
- `aria-expanded`, `aria-controls`, `aria-activedescendant`, `aria-selected`, label, ajuda e erro acompanham o estado. O foco permanece no combobox durante a exploração.
- O popup limita largura/altura ao viewport e pode abrir acima do campo. Alterações de tamanho ou scroll externo o fecham; scroll da própria lista permanece disponível.
- `required`, `disabled`, bloqueio do fieldset, reset e o vínculo de equipe condicionado ao papel são preservados. Confirmar o mesmo valor não marca rascunho como alterado.
- Campos de senha oferecem Mostrar/Ocultar com estado acessível, sem aparar ou substituir a senha. Filtros oferecem limpeza e opção abrangente; paginação usa singular/plural.

O portal mantém a direção editorial, a marca, Manrope e a paleta aprovadas. Quatro fotografias ilustrativas apresentam fauna e ecossistemas; Anavilhanas também aparece no login. As imagens usam WebP local em 640/1280 pixels, dimensões declaradas e `srcset`; apenas a principal é priorizada, e as demais usam carregamento tardio. Após o ajuste de alinhamento solicitado, as fotos do portal preenchem quadros iguais 3:2, sem deformação, usando recorte visual nas bordas; o tucano tem foco à direita para preservar o bico. A imagem do login conserva sua proporção natural. No portal estreito, o texto e a ação principal antecedem as fotos. Créditos e transformações estão em [CREDITS.md](../facial_recognition/frontend/static/assets/CREDITS.md).

Os controles usam HTML/CSS/JavaScript sem dependência nova da aplicação. Os testes DOM isolados em `tests/frontend_ui.test.mjs` podem executar com `node tests/frontend_ui.test.mjs` (Node 18+). O pytest também os executa quando Node está disponível; sem essa ferramenta, registra skip desse teste específico. Node não é necessário para executar a aplicação.

Os cenários DOM isolados não validam motores reais, leitor de tela, teclado móvel ou composição visual. Chrome/Chromium, Edge, Firefox, Safari e Brave são os alvos de compatibilidade. O navegador integrado foi liberado depois dessa rodada; sua revisão está registrada na seção seguinte. Os outros navegadores e dispositivos físicos continuam pendentes. Não foi utilizado outro controlador para contornar a configuração Work.

### Validação deste refinamento — 04/11/2026

- `node tests/frontend_ui.test.mjs`: oito cenários aprovados, sem dependências DOM externas.
- `python -m pytest -q --disable-warnings --tb=short tests/test_frontend.py tests/test_cookie_transport.py tests/test_request_id.py`: 52 testes aprovados, seis avisos, em 1,83 s.
- Suíte completa no estado final: **154 testes e oito subtestes aprovados**, seis avisos, em **134,58 s**, sem skips. O teste Python dos controles inclui os oito cenários JavaScript; eles não são oito testes Python adicionais.
- As oito variantes WebP retornaram HTTP 200 e `image/webp`, com dimensões e proporções conferidas. Somam 692.440 bytes em disco; nenhuma ultrapassa 250.000 bytes. Isso é tamanho de arquivos locais, não medição de tráfego ou desempenho em produção.
- Passaram sintaxe dos oito módulos JavaScript e do módulo de testes, análise dos 71 arquivos Python, conferência das docstrings de 333 funções/métodos, imports dos 55 módulos da aplicação, contratos documentados no OpenAPI e `git diff --check`. O lint de fontes da revisão visual terminou com zero falhas e zero avisos.

As primeiras execuções HTTP ficaram bloqueadas no sandbox e foram encerradas antes da repetição com acesso local. A suíte bem-sucedida rodou sequencialmente, com os fixtures de rollback e schemas isolados existentes. Nessa rodada anterior à revisão visual abaixo, não houve validação visual nova, alteração de dependências da aplicação, migrations ou reset manual de `public`/volume. Os refinamentos permanecem separados do commit funcional `36bf438`, sem novo commit ou push.

### Revisão visual no navegador integrado — 04/11/2026

Após o usuário habilitar o navegador no Work, a interface atual foi aberta pelo controle oficial `cua_repl` em uma prévia local isolada. O servidor de revisão serviu os HTML/CSS/JavaScript reais e respostas fictícias de API; seu lifespan não inicializou banco, migrations, seeds ou inferência. As mutações de revisão retornaram erro explícito, sem alterar registros reais. Nenhum modo de demonstração foi adicionado ao produto.

Foram percorridos portal e detalhe público, login, cadastro/verificação facial com câmera desligada, etapa de senha e biometria simulada; amostras, cadastro, detalhes e análise N1; revisões, relatório, envios e pedidos N2; cofre, dossiê, publicações e pedidos N3; contas, cadastro, detalhes, pedidos, auditoria e senha ADMIN. A inspeção combinou screenshots, árvore acessível e geometria DOM. Foram registradas **151 medições de largura** em 320, 390, 768, 1.024 e 1.440 pixels, incluindo repetições e cenários dirigidos. As alturas principais foram 740, 844, 1.024, 768 e 1.000 pixels, respectivamente; uma janela de 1.440 × 600 também foi conferida.

Problemas confirmados e corrigidos nesta revisão:

- Nomes/equipes sem espaços e textos de responsável podiam aumentar a largura total da página. No caso estreito reproduzido, a largura passou de 1.076 para 305 pixels úteis, com viewport de 320 pixels. Parágrafos, identidade lateral, situação e erro agora permitem quebra de texto; o rodapé lateral pode reorganizar seus grupos.
- A validação nativa podia focar um input posterior ao primeiro menu obrigatório. O foco desse menu é encaminhado após a validação nativa. `showModal()` também focava o `select` oculto: foco automático/programático nesse campo agora segue para o combobox visível. Duas regressões permanentes ampliaram os contratos JavaScript de oito para dez cenários; ambas falharam antes da correção.
- `.field small` sobrepunha a cor do erro; o seletor de erro passou a ter prioridade. Placeholder e cabeçalhos de tabela passaram de contrastes calculados de 3,67:1 e 4,16:1 para 4,96:1 sobre branco, usando a cor secundária existente. Essa medição não equivale a uma certificação integral de acessibilidade.
- O link de ação “Gerenciar” quebrava no meio da palavra em tablet. Ações diretas da tabela permanecem em uma linha; eventual largura excedente usa o contêiner rolável existente.
- A imagem do login ficava alinhada ao fundo, com espaço desequilibrado no celular estreito. Ela foi centralizada verticalmente, preservando proporção e enquadramento completo.
- A altura mínima da lateral excedia janelas baixas: media 620 pixels em 504 pixels disponíveis. Agora respeita os 504 pixels e permite scroll interno quando necessário.
- O contêiner das fotos cortava o indicador de foco dos créditos à direita. O recorte e sua animação antiga sem alvo foram removidos; controles focáveis programaticamente também usam o indicador de foco da interface.
- A troca de rota podia conservar o scroll da tela anterior. Navegações retornam ao início; atualização dos dados na mesma rota preserva a posição. O link de salto também escondia o título sob o cabeçalho fixo: a margem de rolagem mantém o título abaixo dele, conferida de 40 para 136 pixels com cabeçalho de 96 pixels.

As medições finais de largura não encontraram estouro horizontal nos casos registrados. Foram conferidos menus em formulário e diálogo, abertura acima/abaixo, Escape sem fechar o diálogo, seleção por teclado, equipe desabilitada para N3, erro que preserva os campos e foco, imagens carregadas sem distorção perceptível por arredondamento e os estados público vazio/indisponível. As capturas e `layout-checks.json` ficam em `work/frontend-review/validation-20261104/`, ignorados pelo Git e identificados como revisão com dados fictícios.

A suíte completa sobre o estado final passou com **154 testes e oito subtestes**, seis avisos, em **456,48 s**, sem skips. O teste Python dos controles inclui os dez cenários JavaScript; eles não são dez testes Python adicionais. A tentativa anterior foi encerrada pelo ambiente antes de concluir e não é contabilizada como execução aprovada. A repetição em sessão persistente terminou sem falhas, sem testes comuns simultâneos. O tempo total desta rodada local não é benchmark de produção. Passaram também sintaxe dos oito módulos JavaScript e dos testes, análise Python/docstrings, links locais e `git diff --check`; o lint de fontes terminou com zero falhas e zero avisos.

O navegador integrado não substitui testes nativos em Chrome, Edge, Firefox, Safari e Brave, nem teclado móvel físico, leitor de tela ou webcam. As capturas e medições demonstram os estados percorridos; não demonstram ausência de todo defeito visual possível, autenticação real ponta a ponta ou eficácia facial/PAD. Não houve commit, push ou deploy nesta revisão.

### Ajuste das duplas de fotografias — 04/11/2026

O usuário identificou uma diferença que a revisão de largura não detectava: as fotografias de cada dupla tinham alturas distintas, pois eram exibidas nas proporções naturais. As quatro imagens do portal agora usam quadros 3:2 com `object-fit: cover`; o tucano usa `object-position: right center` para preservar o bico. O login mantém o enquadramento natural. Arquivos WebP e licenças foram preservados; créditos, rodapé e texto alternativo foram atualizados.

As duas duplas foram verificadas no navegador em larguras CSS efetivas de 320, 390, 768, 1.024 e 1.440 pixels: imagens de cada dupla com dimensões iguais e, nas duas colunas, legendas iniciando na mesma altura, com tolerância de meio pixel para arredondamento. Nenhum desses casos apresentou estouro horizontal. `photo-layout-checks.json` e `photos-aligned.jpg`, em `work/frontend-review/validation-20261104/`, registram a medição e a captura. A diferença de alturas das imagens era um problema confirmado; a contagem anterior de verificações horizontais não era prova desse alinhamento vertical.

Após esse ajuste, os quatro testes de `tests/test_frontend.py` passaram, com seis avisos, em 2,83 s; incluem os dez contratos DOM JavaScript. Sintaxe de `photos.js`, lint de fontes e `git diff --check` também passaram. A suíte completa não foi repetida nessa alteração de apresentação; o último resultado completo permanece identificado na seção anterior.

### Demonstração com backend real e configuração própria

A demonstração solicitada roda em `http://127.0.0.1:8020/lab`, com `.env.demo`, `ENVIRONMENT=development`, `BIOMETRICS_MODE=simulated` e um banco PostgreSQL novo, separado do banco principal. A chave criptográfica também é própria desse ambiente. O `.env` principal e os dados existentes foram preservados; `.env.demo` é privado e ignorado pelo Git. Modelo e comandos estão no [guia de instalação](SETUP.md#ambiente-separado-de-demonstração).

As sete contas fictícias foram ativadas pelas rotas normais, com simulação explícita e senha definitiva. A carga adicional passou pelas regras e transações da API: sete amostras visíveis ao N1 A e uma da Equipe B, seis envios/dossiês, duas publicações e um pedido de acesso pendente. Há um pedido N3 atendido e outro pendente na segunda geração da mesma investigação. As sessões usadas na preparação foram encerradas; os quatro logins principais foram conferidos por HTTP. No navegador, foram conferidos portal com as duas publicações, login N1, “Continuar sem câmera” e lista com sete amostras.

A API real permanece disponível para exploração local dos dados fictícios. Isso não é inferência facial, implantação de produção ou comprovação de todos os fluxos reais no navegador. A carga básica `seed.development` permanece idempotente e não ganhou ativação automática; os exemplos adicionais foram preparados explicitamente nesta instância.

### Rodapé exclusivo do portal público — 06/11/2026

O rodapé institucional e suas referências aparecem apenas sob `.public-page`, incluindo detalhes de notícias. Fica oculto por padrão, no login, nas etapas de autenticação e na área interna. A regra usa as classes de navegação existentes, sem alterar autenticação ou autorização.

A conferência no navegador da demonstração real confirmou `display: grid` no portal e no acesso ao detalhe público, e `display: none` no login e na lista N1 após a etapa biométrica simulada. A captura `work/frontend-review/validation-20261106/area-interna-sem-rodape.png` registra a área interna. Os quatro testes de `tests/test_frontend.py` passaram com seis avisos em 2,66 s; `git diff --check` passou. A primeira execução restrita dos testes foi interrompida por bloqueio do TestClient; o resultado citado é da repetição concluída fora do sandbox. A suíte completa e outros motores de navegador não foram repetidos nesta alteração de CSS.

A análise da densidade ficou como proposta: na janela de 1.280 × 720, o cabeçalho mediu 96 px, os filtros aproximadamente 122 px e a maioria das linhas da tabela aproximadamente 94 px. Redução de espaçamentos, visão de pendências por perfil e atalhos de trabalho ainda não foram implementados nesta etapa.

### Identidade visual

O portal usa composição editorial com fotografia ilustrativa de fauna. O acesso tem apresentação e formulário separados; a área institucional usa navegação lateral, tabelas e formulários. A tipografia Manrope é servida localmente, com suporte a movimento reduzido e foco visível.

As logos são próprias do projeto. Fotografia, fonte e licenças constam em [CREDITS.md](../facial_recognition/frontend/static/assets/CREDITS.md); a imagem não representa uma coleta ou instalação real. Os materiais e referências institucionais não indicam vínculo oficial.

A revisão visual anterior usou respostas fictícias de API e câmera artificial do navegador. Seus registros locais, não versionados, não comprovam comportamento do backend final, transações, dispositivos físicos ou eficácia biométrica. O roteiro manual acima continua pendente com o backend atual.

### Consolidação de contratos — 02/11/2026

O botão “Corrigir cadastro” deixou de inferir autorização pelos cards da página atual. Agora depende de can_edit === true na resposta da amostra, além de papel/permissão compatíveis. BiologicalAgentResponse exige esse campo; o backend calcula esse valor com base no histórico completo e revalidar no PATCH. Campo ausente mantém a ação oculta, sem liberar edição por falta de dados.

A revisão no navegador confirmou can_edit false/true/ausente em páginas e filtros diferentes e repetiu os percursos N1/N2/N3/ADMIN com respostas fictícias, sem erros JavaScript. A etapa simulada sem câmera também foi conferida com POST vazio protegido por CSRF e avanço para senha. As capturas permanecem em artefatos locais de revisão, não versionados; não são evidência de backend científico implementado.

A validação real de autenticação e o isolamento do modo simulado em PostgreSQL estão registrados em AUTH_LAB.md. HTTPS remoto, celular físico, leitor de tela e calibração facial permanecem pendentes.
