# Como funciona o sistema

O projeto é um sistema acadêmico para um laboratório fictício de biossegurança ambiental. Ele controla o acesso das pessoas e acompanha a investigação de amostras com agentes biológicos ainda não identificados, até a decisão sobre divulgar os resultados.

**Este documento descreve o funcionamento planejado.** As funcionalidades ainda precisam ser implementadas e testadas. Os [endpoints](ENDPOINTS.md), o [banco de dados](DATABASE_TARGET.md) e o [exemplo completo](USE_CASES.md) são referências para quem precisar de mais detalhes.

## 1. Quem participa

| Participante | Responsabilidade | Limite de acesso |
| --- | --- | --- |
| N1 responsável | Cadastra a amostra, prepara a análise e envia ao N2. Pode incluir colegas da equipe para leitura. | Edita somente investigações sob sua responsabilidade. Não acessa o cofre. |
| N1 colaborador | Lê a investigação compartilhada e o cadastro da amostra correspondente. | Não edita, envia ou compartilha. Não recebe acesso às outras investigações da amostra. |
| N2 - supervisor | Supervisiona sua equipe, distribui investigações, revisa análises e envia a conclusão ao N3. | Não atua em outras equipes nem consulta o conteúdo selado após o envio. |
| N3 - autoridade responsável | Consulta o cofre e decide publicar, manter em sigilo ou solicitar outra investigação. Pode retirar notícias. | Não altera o relatório recebido nem a notícia preparada pelo N2. |
| Administrador | Aprova acesso, administra contas e auxilia na recuperação de senha ou reconhecimento facial. | Seu cargo não permite ler análises, o cofre ou motivos reservados ao N3. |
| Visitante | Consulta notícias autorizadas. | Não acessa informações internas. |

As equipes são divisões administrativas. N1 e N2 pertencem a uma equipe; N3 e administrador não precisam pertencer. Cada equipe tem apenas um N2 habilitado, e o sistema tem apenas um N3 habilitado. Uma conta aprovada já ocupa essa posição, mesmo antes da primeira entrada.

## 2. Como as pessoas recebem acesso e entram

Não existe cadastro aberto ao público. O N2 solicita contas N1 para sua equipe; o N3 solicita contas N2. O administrador aprova ou rejeita os pedidos e também pode cadastrar diretamente N1, N2 e N3. A conta só é criada após a aprovação.

A senha temporária é entregue pessoalmente, fora do sistema, e vale por 24 horas após a aprovação. Na primeira entrada, a pessoa usa essa senha, cadastra o rosto e define sua senha definitiva. Se não concluir a tempo, o administrador pode renovar a validade da mesma senha; o rosto já cadastrado não precisa ser cadastrado novamente.

Nas entradas seguintes, N1, N2 e N3 usam senha e reconhecimento facial, com uma verificação para tentar identificar o uso de fotos ou outras imitações. O administrador usa apenas senha. O acesso só é liberado depois de concluir todas as etapas exigidas.

Há uma conta por vez no mesmo perfil do navegador. Se Ana estiver conectada e Bruno iniciar a entrada com email e senha corretos, Ana será desconectada naquele perfil, incluindo suas abas. Bruno ainda precisa concluir as etapas para receber acesso. Outros navegadores ou dispositivos não são desconectados por essa troca. A sessão dura no máximo 24 horas.

Todos podem alterar a própria senha, confirmando a senha atual e, quando exigido, o rosto. A alteração encerra todas as sessões e exige nova entrada. Senha esquecida ou problema com o cadastro facial são resolvidos pelo administrador. Desativar uma conta bloqueia seu acesso imediatamente, preservando o histórico; reativá-la exige nova senha temporária, novo cadastro facial quando aplicável e senha definitiva.

## 3. Como uma investigação acontece

**N1 cadastra → N1 analisa → N2 revisa → N3 decide → visitante consulta a notícia, se publicada.**

### Cadastro e análise pelo N1

O N1 registra a identificação provisória da amostra, material, local e data da coleta, observações e motivo da investigação. Pode acrescentar informações já conhecidas. Não precisa saber o nome científico do agente.

O cadastro da amostra e a investigação são coisas diferentes: uma amostra pode ter várias investigações ao longo do tempo. A primeira nasce junto com o cadastro e fica sob responsabilidade do N1 que o criou. As seguintes são abertas pelo N2, que escolhe um N1 ativo da mesma equipe. Só pode existir uma investigação em andamento por amostra.

O responsável registra avaliações realizadas, resultados observados, parecer e recomendação. Pode informar uma estimativa de risco ou deixá-la como não determinada. Salvar permite continuar depois; enviar entrega a análise ao N2 e bloqueia sua edição. Não há prazo obrigatório para concluir a investigação.

O responsável e o N2 podem incluir N1 ativos da mesma equipe como colaboradores de leitura. Somente o N2 pode remover colaboradores ou trocar o responsável. Essas mudanças são permitidas enquanto a análise está em preparação ou foi devolvida para correção. Ao trocar o responsável, o anterior passa a colaborador.

### Revisão pelo N2

O N2 lê a análise enviada, sem alterar o texto do N1, e escolhe uma das opções:

- **Devolver:** explica o que precisa ser corrigido. O responsável ajusta e envia novamente; as entregas anteriores permanecem preservadas.
- **Encerrar:** informa o motivo à equipe e termina a investigação sem encaminhar ao N3.
- **Enviar ao N3:** prepara a conclusão final, o percentual de risco e uma notícia pronta para divulgação. A categoria pública de risco é escolhida pelo N2, sem conversão automática do percentual.

Ao enviar ao N3, a análise, o relatório e a notícia ficam preservados no cofre. O N2 acompanha título, amostra, protocolo e situação da decisão, mas não pode reabrir o conteúdo enviado. Enquanto o N3 não decidir, essa investigação continua em andamento.

### Decisão pelo N3

| Decisão | Resultado |
| --- | --- |
| Publicar | A notícia preparada pelo N2 fica disponível ao público. A investigação termina. |
| Manter em sigilo | Não há notícia pública. A investigação termina, e somente o N3 consulta o motivo do sigilo. |
| Solicitar outra investigação | A investigação atual termina, preservando o relatório. O N2 recebe o motivo e abre outra investigação da mesma amostra, escolhendo um responsável. A nova equipe também recebe esse motivo, sem acesso ao cofre anterior. |

O N3 não corrige nem devolve o relatório ou a notícia para edição nesta versão. Cada relatório recebe uma decisão final. Um pedido de nova investigação aguarda o N2 da equipe, inclusive se for necessário substituir esse supervisor; a próxima investigação deve atender ao pedido. Não há opção de rejeitar ou cancelar esse pedido nesta versão.

### Divulgação ao público

A notícia mostra título, subtítulo opcional, categoria de risco, texto e data de publicação. Não mostra percentual interno, nomes da equipe, local exato, relatório ou motivos privados.

O N3 pode retirar uma notícia, informando um motivo consultável somente por ele. Ela deixa de aparecer ao público, mas permanece no histórico interno. Não há edição, substituição ou republicação da mesma notícia. Uma nova investigação pode resultar em outra notícia.

## 4. Situações da investigação

| Situação | O que acontece | Permite abrir outra investigação da amostra? |
| --- | --- | --- |
| Em preparação | O responsável preenche a análise. | Não |
| Em revisão | O N2 avalia a entrega; o responsável não edita. | Não |
| Devolvida para correção | O responsável corrige e pode reenviar. | Não |
| Aguardando N3 | O conteúdo está no cofre, aguardando decisão. | Não |
| Publicada | O N3 autorizou a notícia. | Sim |
| Encerrada | O N2 encerrou, ou o N3 manteve sigilo ou solicitou outra investigação. | Sim |

Uma investigação terminada não é reaberta. O N2 pode criar outra, desde que a amostra esteja ativa.

## 5. Regras que sempre precisam ser respeitadas

- **Acesso limitado:** N1 consulta investigações às quais está vinculado; N2 atua apenas na sua equipe; o cofre é exclusivo do N3. Compartilhar uma investigação não libera as demais.
- **Um responsável por investigação:** somente ele edita e envia a análise. Colaboradores apenas leem. Remover um colaborador retira seu acesso atual, sem apagar sua participação nas entregas anteriores.
- **Cadastro preservado:** o N1 criador, enquanto autorizado, ou o N2 da equipe pode corrigir o cadastro da amostra somente antes da primeira entrega de análise.
- **Amostras ativas e inativas:** somente o N2 altera essa situação. Não pode inativar uma amostra com investigação em andamento. Inativas continuam disponíveis para consulta autorizada do histórico; precisam ser reativadas para receber novo trabalho.
- **Histórico mantido:** contas, amostras, entregas, relatórios e notícias não são apagados para eliminar o histórico. Inativar uma amostra ou retirar uma notícia não reabre uma investigação terminada.
- **Continuidade da equipe:** se um responsável perder acesso, o N2 precisa atribuir outro para o trabalho continuar. Um novo N2 assume os registros de sua equipe; um novo N3 assume o cofre, preservando a autoria anterior.
- **Limites desta versão:** não há transferência de amostras entre equipes, edição de conteúdo selado, rascunho separado para o N3 ou alteração de notícias já aprovadas.
