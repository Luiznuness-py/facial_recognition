-- Schema inicial para bancos novos. Não converte bancos com a 001 já aplicada.
-- O serviço verifica permissões, reserva de N2/N3 e transições entre tabelas em transações.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador do papel — identifica de forma única o nível de acesso.
    code TEXT NOT NULL UNIQUE CHECK (code IN ('ADMIN', 'N1', 'N2', 'N3')), -- Código do papel — distingue ADMIN, N1, N2 e N3 nas regras de acesso.
    name TEXT NOT NULL CHECK (btrim(name) <> ''), -- Nome do papel — apresenta o nível de acesso por extenso.
    description TEXT, -- Descrição do papel — explica a finalidade deste nível de acesso.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    created_by UUID, -- Criado por — identifica o usuário que criou o registro.
    updated_at TIMESTAMPTZ, -- Data da última alteração — registra quando o registro foi alterado pela última vez.
    updated_by UUID, -- Alterado por — identifica o usuário que fez a última alteração.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
);

CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador da permissão — identifica de forma única uma permissão do sistema.
    code TEXT NOT NULL UNIQUE CHECK (btrim(code) <> ''), -- Código da permissão — identifica a ação verificada pela autorização do backend.
    description TEXT, -- Descrição da permissão — explica qual ação pode ser autorizada.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    created_by UUID, -- Criado por — identifica o usuário que criou o registro.
    updated_at TIMESTAMPTZ, -- Data da última alteração — registra quando o registro foi alterado pela última vez.
    updated_by UUID, -- Alterado por — identifica o usuário que fez a última alteração.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
);

CREATE TABLE role_permissions (
    role_id UUID NOT NULL REFERENCES roles(id), -- Papel vinculado — identifica o nível de acesso que recebe a permissão.
    permission_id UUID NOT NULL REFERENCES permissions(id), -- Permissão vinculada — identifica a ação concedida ao papel.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    created_by UUID, -- Criado por — identifica o usuário que criou o registro.
    updated_at TIMESTAMPTZ, -- Data da última alteração — registra quando o registro foi alterado pela última vez.
    updated_by UUID, -- Alterado por — identifica o usuário que fez a última alteração.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador da equipe — identifica de forma única o grupo administrativo.
    code TEXT NOT NULL UNIQUE CHECK (btrim(code) <> ''), -- Código da equipe — diferencia a equipe por um código único.
    name TEXT NOT NULL CHECK (btrim(name) <> ''), -- Nome da equipe — apresenta o nome do grupo administrativo.
    description TEXT, -- Descrição da equipe — explica a finalidade ou a composição do grupo.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    created_by UUID, -- Criado por — identifica o usuário que criou o registro.
    updated_at TIMESTAMPTZ, -- Data da última alteração — registra quando o registro foi alterado pela última vez.
    updated_by UUID, -- Alterado por — identifica o usuário que fez a última alteração.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador do usuário — identifica a conta e mantém seus vínculos no sistema.
    name TEXT NOT NULL CHECK (btrim(name) <> ''), -- Nome do usuário — identifica a pessoa nas telas e nos registros de autoria.
    email TEXT NOT NULL UNIQUE CHECK (email = lower(btrim(email)) AND email <> ''), -- Email do usuário — identifica a conta no login, sem permitir duplicidade.
    role_id UUID NOT NULL REFERENCES roles(id), -- Papel do usuário — define o nível ADMIN, N1, N2 ou N3 da conta.
    team_id UUID REFERENCES teams(id), -- Equipe do usuário — vincula a pessoa ao grupo usado no controle de acesso.
    status TEXT NOT NULL DEFAULT 'PENDING_ACTIVATION' -- Situação da ativação — informa se a conta aguarda concluir a ativação ou está ativa.
        CHECK (status IN ('PENDING_ACTIVATION', 'ACTIVE')),
    biometric_enrollment_required BOOLEAN NOT NULL DEFAULT TRUE, -- Cadastro facial obrigatório — indica se o usuário precisa cadastrar novamente o rosto.
    password_change_required BOOLEAN NOT NULL DEFAULT TRUE, -- Troca de senha obrigatória — indica se é necessário definir uma nova senha antes do acesso normal.
    activated_at TIMESTAMPTZ, -- Data da primeira ativação — registra a primeira conclusão da ativação e deve ser preservada nas reativações.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    created_by UUID REFERENCES users(id), -- Criado por — identifica o usuário que criou o registro.
    updated_at TIMESTAMPTZ, -- Data da última alteração — registra quando o registro foi alterado pela última vez.
    updated_by UUID REFERENCES users(id), -- Alterado por — identifica o usuário que fez a última alteração.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    biometric_failure_count INTEGER NOT NULL DEFAULT 0 CHECK (biometric_failure_count >= 0), -- Contagem de falhas biométricas — acumula reprovações do usuário na janela de controle.
    biometric_failure_window_started_at TIMESTAMPTZ, -- Início da janela biométrica — marca quando começou o período de contagem das falhas.
    biometric_blocked_until TIMESTAMPTZ, -- Bloqueio biométrico até — determina quando termina o bloqueio temporário do usuário.
    CHECK (status <> 'ACTIVE' OR activated_at IS NOT NULL)
);

ALTER TABLE roles
    ADD FOREIGN KEY (created_by) REFERENCES users(id),
    ADD FOREIGN KEY (updated_by) REFERENCES users(id);
ALTER TABLE teams
    ADD FOREIGN KEY (created_by) REFERENCES users(id),
    ADD FOREIGN KEY (updated_by) REFERENCES users(id);
ALTER TABLE permissions
    ADD FOREIGN KEY (created_by) REFERENCES users(id),
    ADD FOREIGN KEY (updated_by) REFERENCES users(id);
ALTER TABLE role_permissions
    ADD FOREIGN KEY (created_by) REFERENCES users(id),
    ADD FOREIGN KEY (updated_by) REFERENCES users(id);

CREATE TABLE access_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador da solicitação — identifica de forma única o pedido de acesso.
    user_id UUID REFERENCES users(id), -- Conta aprovada — vincula a solicitação ao usuário criado após a aprovação.
    requested_name TEXT NOT NULL CHECK (btrim(requested_name) <> ''), -- Nome solicitado — guarda o nome da pessoa para quem a conta foi pedida.
    requested_email TEXT NOT NULL -- Email solicitado — guarda o endereço que será usado na conta aprovada.
        CHECK (requested_email = lower(btrim(requested_email)) AND requested_email <> ''),
    temporary_password_hash TEXT, -- Hash da senha temporária — permite verificar a senha do pedido enquanto ele estiver pendente.
    requested_by UUID NOT NULL REFERENCES users(id), -- Solicitado por — identifica o usuário que abriu o pedido de acesso.
    requested_role_id UUID NOT NULL REFERENCES roles(id), -- Papel solicitado — informa qual nível de acesso foi pedido para a nova conta.
    requested_team_id UUID REFERENCES teams(id), -- Equipe solicitada — informa o grupo previsto para a nova conta, quando aplicável.
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')), -- Situação da solicitação — indica se o pedido está pendente, aprovado ou rejeitado.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    updated_at TIMESTAMPTZ, -- Data da última alteração — registra quando o registro foi alterado pela última vez.
    updated_by UUID REFERENCES users(id), -- Alterado por — identifica o usuário que fez a última alteração.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    decided_by UUID REFERENCES users(id), -- Decidido por — identifica o administrador que aprovou ou rejeitou o pedido.
    decided_at TIMESTAMPTZ, -- Data da decisão — registra quando o pedido foi aprovado ou rejeitado.
    rejection_reason TEXT CHECK (char_length(rejection_reason) BETWEEN 1 AND 1500 AND btrim(rejection_reason) <> ''), -- Motivo da rejeição — explica por que o pedido de acesso foi recusado.
    CHECK ((status = 'PENDING' AND temporary_password_hash IS NOT NULL
            AND btrim(temporary_password_hash) <> '' AND decided_by IS NULL AND decided_at IS NULL)
        OR (status <> 'PENDING' AND temporary_password_hash IS NULL
            AND decided_by IS NOT NULL AND decided_at IS NOT NULL)),
    CHECK ((status = 'APPROVED') = (user_id IS NOT NULL)),
    CHECK ((status = 'REJECTED') = (rejection_reason IS NOT NULL))
);
-- Impede pedidos pendentes duplicados para o mesmo email, desconsiderando os excluídos logicamente.
CREATE UNIQUE INDEX access_requests_pending_email_unique
    ON access_requests(requested_email) WHERE status = 'PENDING' AND NOT soft_delete;

CREATE TABLE password_hashes (
    user_id UUID PRIMARY KEY REFERENCES users(id), -- Usuário da senha — vincula a única credencial atual à conta correspondente.
    password_hash TEXT NOT NULL CHECK (btrim(password_hash) <> ''), -- Hash da senha — permite conferir a senha sem armazenar seu texto original.
    is_temporary BOOLEAN NOT NULL, -- Senha temporária — indica se a senha atual é provisória e precisa ser substituída.
    temporary_expires_at TIMESTAMPTZ, -- Validade da senha temporária — determina até quando a senha provisória pode ser usada.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    created_by UUID REFERENCES users(id), -- Criado por — identifica o usuário que criou o registro.
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data da última alteração — registra quando o registro foi alterado pela última vez.
    updated_by UUID REFERENCES users(id), -- Alterado por — identifica o usuário que fez a última alteração.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    CHECK (is_temporary = (temporary_expires_at IS NOT NULL))
);

CREATE TABLE vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador do vetor — identifica de forma única um registro biométrico.
    user_id UUID NOT NULL REFERENCES users(id), -- Usuário do vetor — identifica a pessoa representada pelo cadastro facial.
    ciphertext BYTEA NOT NULL CHECK (octet_length(ciphertext) > 0), -- Vetor criptografado — armazena a representação facial protegida por criptografia.
    nonce BYTEA NOT NULL CHECK (octet_length(nonce) = 12), -- Valor único da criptografia — guarda o valor de 12 bytes necessário para descriptografar com AES-GCM.
    key_version TEXT NOT NULL CHECK (btrim(key_version) <> ''), -- Versão da chave — identifica qual chave externa ao banco protege este vetor.
    model_version TEXT NOT NULL CHECK (btrim(model_version) <> ''), -- Versão do modelo — identifica o modelo biométrico que gerou a representação facial.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
);

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador da sessão — identifica o acesso autenticado em um navegador ou dispositivo.
    user_id UUID NOT NULL REFERENCES users(id), -- Usuário da sessão — vincula a sessão à conta autenticada.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    expires_at TIMESTAMPTZ NOT NULL, -- Data de expiração — determina até quando esta credencial pode ser utilizada.
    revoked_at TIMESTAMPTZ, -- Data de revogação — registra quando esta credencial foi invalidada antes de expirar.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    CHECK (expires_at > created_at AND expires_at <= created_at + INTERVAL '24 hours')
);

CREATE TABLE authentication_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador da tentativa — identifica o fluxo de autenticação ou recuperação em andamento.
    user_id UUID NOT NULL REFERENCES users(id), -- Usuário da tentativa — identifica a conta que precisa concluir as etapas de autenticação.
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'BLOCKED', 'COMPLETED', 'CANCELLED')), -- Situação da tentativa — indica se está pendente, bloqueada, concluída ou cancelada.
    stage TEXT NOT NULL CHECK (stage IN ('ENROLL_FACE', 'VERIFY_FACE', 'CHANGE_PASSWORD')), -- Etapa autorizada — define se o usuário deve cadastrar o rosto, reconhecê-lo ou trocar a senha.
    token_jti UUID NOT NULL UNIQUE, -- Identificador do token — vincula a tentativa ao JWT de etapa autorizado, sem guardar o token completo.
    biometric_failures INTEGER NOT NULL DEFAULT 0 CHECK (biometric_failures BETWEEN 0 AND 3), -- Falhas desta tentativa — conta reprovações biométricas dentro deste fluxo de autenticação.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > created_at), -- Data de expiração — determina até quando esta credencial pode ser utilizada.
    completed_at TIMESTAMPTZ, -- Data de conclusão — registra quando a tentativa foi concluída com sucesso.
    operation TEXT NOT NULL CHECK (operation IN ('LOGIN', 'ACTIVATION', 'RECOVERY', 'PASSWORD_CHANGE')), -- Operação de autenticação — distingue entrada, ativação, recuperação e troca de senha.
    initiating_session_id UUID REFERENCES sessions(id), -- Sessão de origem — vincula a troca voluntária de senha à sessão que iniciou a operação.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    CHECK ((status = 'COMPLETED') = (completed_at IS NOT NULL)),
    CHECK ((operation = 'PASSWORD_CHANGE') = (initiating_session_id IS NOT NULL))
);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador do token de renovação — identifica um item da cadeia de renovação da sessão.
    session_id UUID NOT NULL REFERENCES sessions(id), -- Sessão vinculada — identifica a sessão que este token pode renovar.
    token_hash TEXT NOT NULL UNIQUE CHECK (btrim(token_hash) <> ''), -- Hash do token — permite conferir o token de renovação sem guardar seu valor original.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > created_at), -- Data de expiração — determina até quando esta credencial pode ser utilizada.
    used_at TIMESTAMPTZ, -- Data de uso — registra quando o token foi consumido para impedir reutilização.
    revoked_at TIMESTAMPTZ, -- Data de revogação — registra quando esta credencial foi invalidada antes de expirar.
    replaced_by_id UUID REFERENCES refresh_tokens(id), -- Token sucessor — aponta para o novo token emitido na rotação.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    CHECK (replaced_by_id IS NULL OR (used_at IS NOT NULL AND replaced_by_id <> id))
);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador do evento — identifica de forma única uma entrada do log de ações.
    actor_id UUID REFERENCES users(id), -- Autor da ação — identifica quem executou a ação, quando houver usuário identificado.
    event TEXT NOT NULL CHECK (btrim(event) <> ''), -- Ação registrada — guarda o código da operação, como desativar ou reativar uma conta.
    resource_type TEXT NOT NULL CHECK (btrim(resource_type) <> ''), -- Tipo do recurso — informa qual entidade do sistema foi alvo da ação.
    resource_id UUID, -- Identificador do recurso — aponta para o registro afetado, quando houver um alvo específico.
    success BOOLEAN NOT NULL, -- Resultado da ação — informa se a operação foi bem-sucedida.
    reason TEXT, -- Motivo da ação — registra a justificativa ou causa permitida, sem copiar segredos ou conteúdo reservado.
    request_id UUID NOT NULL, -- Identificador da requisição — relaciona o evento aos demais registros da mesma chamada à API.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
);

CREATE TABLE biological_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador da amostra — identifica de forma única o agente biológico investigado.
    code TEXT NOT NULL UNIQUE CHECK (btrim(code) <> ''), -- Código da amostra — permite localizar o cadastro por um código único.
    provisional_label TEXT NOT NULL CHECK (char_length(provisional_label) BETWEEN 1 AND 120 AND btrim(provisional_label) <> ''), -- Identificação provisória — nomeia a amostra antes da identificação definitiva do agente.
    material_type TEXT NOT NULL CHECK (char_length(material_type) BETWEEN 1 AND 100 AND btrim(material_type) <> ''), -- Tipo de material — descreve o material coletado para investigação.
    collection_location TEXT NOT NULL CHECK (char_length(collection_location) BETWEEN 1 AND 255 AND btrim(collection_location) <> ''), -- Local da coleta — registra onde a amostra foi obtida.
    collected_on DATE NOT NULL CHECK (collected_on <= CURRENT_DATE), -- Data da coleta — registra o dia em que a amostra foi coletada.
    initial_observations TEXT NOT NULL CHECK (char_length(initial_observations) BETWEEN 1 AND 1500 AND btrim(initial_observations) <> ''), -- Observações iniciais — descreve o que foi observado no cadastro da amostra.
    investigation_reason TEXT NOT NULL CHECK (char_length(investigation_reason) BETWEEN 1 AND 1500 AND btrim(investigation_reason) <> ''), -- Motivo da investigação — explica por que a amostra precisa ser analisada.
    known_information TEXT CHECK (char_length(known_information) <= 1500), -- Informações conhecidas — reúne os dados já disponíveis sobre a amostra, quando houver.
    team_id UUID NOT NULL REFERENCES teams(id), -- Equipe da amostra — define o grupo responsável pelo cadastro e pelas investigações.
    created_by UUID NOT NULL REFERENCES users(id), -- Criado por — identifica o usuário que criou o registro.
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE')), -- Situação da amostra — indica se está ativa para novas investigações ou inativa.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    updated_at TIMESTAMPTZ, -- Data da última alteração — registra quando o registro foi alterado pela última vez.
    updated_by UUID REFERENCES users(id), -- Alterado por — identifica o usuário que fez a última alteração.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    UNIQUE (id, team_id)
);

CREATE TABLE validations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador da investigação — identifica a tarefa e seu formulário científico atual.
    agent_id UUID NOT NULL, -- Amostra investigada — vincula a investigação ao cadastro do agente biológico.
    team_id UUID NOT NULL REFERENCES teams(id), -- Equipe da investigação — delimita o grupo autorizado a trabalhar nesta tarefa.
    responsible_user_id UUID NOT NULL REFERENCES users(id), -- Responsável pela investigação — identifica o único N1 que pode editar e enviar a análise.
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'IN_REVIEW', 'RETURNED', 'REPORTED', 'PUBLISHED', 'CLOSED')), -- Situação da investigação — acompanha o fluxo da abertura até publicação ou encerramento.
    assessments_performed TEXT CHECK (char_length(assessments_performed) <= 1500), -- Avaliações realizadas — descreve os procedimentos aplicados na investigação.
    observed_results TEXT CHECK (char_length(observed_results) <= 5000), -- Resultados observados — registra os resultados obtidos na análise da amostra.
    technical_opinion TEXT CHECK (char_length(technical_opinion) <= 5000), -- Parecer técnico — reúne a interpretação técnica dos resultados pelo responsável.
    recommendation TEXT CHECK (char_length(recommendation) <= 5000), -- Recomendação — informa as ações propostas a partir da investigação.
    estimated_risk_percentage NUMERIC(5, 2) CHECK (estimated_risk_percentage BETWEEN 0 AND 100), -- Percentual de risco estimado — registra a estimativa do N1; nulo significa risco não determinado.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data de criação — registra quando o registro foi criado.
    created_by UUID NOT NULL REFERENCES users(id), -- Criado por — identifica o usuário que criou o registro.
    updated_at TIMESTAMPTZ, -- Data da última alteração — registra quando o registro foi alterado pela última vez.
    updated_by UUID REFERENCES users(id), -- Alterado por — identifica o usuário que fez a última alteração.
    closed_at TIMESTAMPTZ, -- Data de encerramento — registra quando a investigação foi encerrada.
    closed_by UUID REFERENCES users(id), -- Encerrado por — identifica o usuário que executou o encerramento.
    closure_reason TEXT CHECK (char_length(closure_reason) BETWEEN 1 AND 1500 AND btrim(closure_reason) <> ''), -- Motivo do encerramento — guarda a justificativa do encerramento manual pelo N2.
    closure_cause TEXT CHECK (closure_cause IN ('N2_CLOSED', 'N3_RESTRICTED', 'N3_NEW_VALIDATION')), -- Causa do encerramento — distingue encerramento do N2, sigilo ou pedido de nova investigação pelo N3.
    previous_validation_id UUID UNIQUE REFERENCES validations(id), -- Investigação anterior — liga a nova tarefa à investigação que originou o pedido do N3.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    FOREIGN KEY (agent_id, team_id) REFERENCES biological_agents(id, team_id),
    CHECK (previous_validation_id IS NULL OR previous_validation_id <> id),
    CHECK (status IN ('OPEN', 'RETURNED') OR
        (assessments_performed IS NOT NULL AND btrim(assessments_performed) <> ''
         AND observed_results IS NOT NULL AND btrim(observed_results) <> ''
         AND technical_opinion IS NOT NULL AND btrim(technical_opinion) <> ''
         AND recommendation IS NOT NULL AND btrim(recommendation) <> '')),
    CHECK ((status = 'CLOSED' AND closed_at IS NOT NULL AND closed_by IS NOT NULL AND closure_cause IS NOT NULL)
        OR (status <> 'CLOSED' AND closed_at IS NULL AND closed_by IS NULL AND closure_cause IS NULL)),
    CHECK ((closure_cause = 'N2_CLOSED' AND closure_reason IS NOT NULL)
        OR (closure_cause IS DISTINCT FROM 'N2_CLOSED' AND closure_reason IS NULL))
);
-- Garante uma única investigação em andamento por amostra, desconsiderando as excluídas logicamente.
CREATE UNIQUE INDEX validations_one_active_per_agent
    ON validations(agent_id) WHERE status IN ('OPEN', 'IN_REVIEW', 'RETURNED', 'REPORTED') AND NOT soft_delete;

CREATE TABLE validation_participants (
    validation_id UUID NOT NULL REFERENCES validations(id), -- Investigação compartilhada — identifica a tarefa que o colaborador pode consultar.
    user_id UUID NOT NULL REFERENCES users(id), -- Colaborador — identifica o N1 que recebe acesso de leitura à investigação.
    added_by UUID NOT NULL REFERENCES users(id), -- Adicionado por — identifica quem incluiu originalmente o colaborador na investigação.
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data da inclusão — registra quando o vínculo de colaboração foi criado.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    PRIMARY KEY (validation_id, user_id)
);

CREATE TABLE investigation_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador da entrega — identifica de forma única uma análise enviada ao N2.
    validation_id UUID NOT NULL REFERENCES validations(id), -- Investigação de origem — vincula a entrega à tarefa em que a análise foi produzida.
    submission_number INTEGER NOT NULL CHECK (submission_number > 0), -- Número da entrega — ordena os envios da mesma investigação, sem repetir a numeração.
    responsible_user_id UUID NOT NULL REFERENCES users(id), -- Responsável na entrega — preserva quem respondia pela investigação no momento do envio.
    submitted_by UUID NOT NULL REFERENCES users(id), -- Enviado por — identifica o usuário que realizou o envio da análise.
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data do envio — registra quando esta entrega foi encaminhada ao N2.
    assessments_performed TEXT NOT NULL CHECK (char_length(assessments_performed) BETWEEN 1 AND 1500 AND btrim(assessments_performed) <> ''), -- Avaliações entregues — preserva os procedimentos informados no momento do envio.
    observed_results TEXT NOT NULL CHECK (char_length(observed_results) BETWEEN 1 AND 5000 AND btrim(observed_results) <> ''), -- Resultados entregues — preserva os resultados informados no momento do envio.
    technical_opinion TEXT NOT NULL CHECK (char_length(technical_opinion) BETWEEN 1 AND 5000 AND btrim(technical_opinion) <> ''), -- Parecer entregue — preserva a interpretação técnica enviada para revisão.
    recommendation TEXT NOT NULL CHECK (char_length(recommendation) BETWEEN 1 AND 5000 AND btrim(recommendation) <> ''), -- Recomendação entregue — preserva as ações propostas no momento do envio.
    estimated_risk_percentage NUMERIC(5, 2) CHECK (estimated_risk_percentage BETWEEN 0 AND 100), -- Risco estimado na entrega — preserva a estimativa do N1, quando informada.
    participants_snapshot JSONB NOT NULL CHECK (jsonb_typeof(participants_snapshot) = 'array'), -- Cópia dos participantes — preserva a identificação da equipe vinculada no momento da entrega.
    returned_by UUID REFERENCES users(id), -- Devolvido por — identifica o N2 que devolveu a entrega para correção.
    returned_at TIMESTAMPTZ, -- Data da devolução — registra quando a entrega foi devolvida ao responsável.
    return_reason TEXT CHECK (char_length(return_reason) BETWEEN 1 AND 1500 AND btrim(return_reason) <> ''), -- Motivo da devolução — descreve o que precisa ser corrigido ou complementado.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    UNIQUE (validation_id, submission_number),
    UNIQUE (id, validation_id),
    CHECK ((returned_by IS NULL AND returned_at IS NULL AND return_reason IS NULL)
        OR (returned_by IS NOT NULL AND returned_at IS NOT NULL AND return_reason IS NOT NULL))
);

CREATE TABLE vault (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador do registro no cofre — identifica o relatório selado enviado ao N3.
    validation_id UUID NOT NULL UNIQUE REFERENCES validations(id), -- Investigação concluída — vincula o dossiê à única investigação que o originou.
    source_submission_id UUID NOT NULL UNIQUE, -- Entrega de origem — identifica a análise preservada que fundamenta o relatório.
    protocol TEXT NOT NULL UNIQUE CHECK (btrim(protocol) <> ''), -- Protocolo do relatório — permite localizar o dossiê por um código único.
    sent_by UUID NOT NULL REFERENCES users(id), -- Enviado por — identifica o N2 que encaminhou o relatório e a ficha ao N3.
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data do envio ao cofre — registra quando o dossiê foi encaminhado ao N3.
    received_snapshot JSONB NOT NULL CHECK (jsonb_typeof(received_snapshot) = 'object'), -- Cópia recebida — preserva os dados da análise, da amostra e da equipe usados no relatório.
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120 AND btrim(title) <> ''), -- Título do relatório — identifica o assunto do documento reservado.
    final_conclusion TEXT NOT NULL CHECK (char_length(final_conclusion) BETWEEN 1 AND 5000 AND btrim(final_conclusion) <> ''), -- Conclusão final — registra a conclusão técnica consolidada pelo N2.
    final_risk_percentage NUMERIC(5, 2) NOT NULL CHECK (final_risk_percentage BETWEEN 0 AND 100), -- Percentual de risco final — registra a avaliação de risco consolidada pelo N2.
    public_title TEXT NOT NULL CHECK (char_length(public_title) BETWEEN 1 AND 120 AND btrim(public_title) <> ''), -- Título público — identifica a notícia sem expor o conteúdo reservado do relatório.
    public_subtitle TEXT CHECK (char_length(public_subtitle) <= 200), -- Subtítulo público — complementa opcionalmente o título da notícia.
    public_risk_category TEXT NOT NULL CHECK (public_risk_category IN ('LOW', 'MODERATE', 'HIGH')), -- Categoria pública de risco — classifica o risco divulgado como baixo, moderado ou alto.
    public_body TEXT NOT NULL CHECK (char_length(public_body) BETWEEN 1 AND 5000 AND btrim(public_body) <> ''), -- Texto público — contém as informações preparadas para divulgação na notícia.
    decision_status TEXT NOT NULL DEFAULT 'WAITING_N3' CHECK (decision_status IN ('WAITING_N3', 'PUBLISHED', 'RESTRICTED', 'NEW_VALIDATION_REQUESTED')), -- Situação da decisão — acompanha a espera e a decisão do N3 sobre o dossiê.
    decided_by UUID REFERENCES users(id), -- Decidido por — identifica o N3 que decidiu o destino do relatório.
    decided_at TIMESTAMPTZ, -- Data da decisão — registra quando o N3 decidiu o destino do relatório.
    restricted_reason TEXT CHECK (char_length(restricted_reason) BETWEEN 1 AND 1500 AND btrim(restricted_reason) <> ''), -- Motivo do sigilo — justifica a restrição do relatório e só pode ser consultado pelo N3.
    new_validation_requested_by UUID REFERENCES users(id), -- Nova investigação solicitada por — identifica o N3 que pediu outra investigação.
    new_validation_requested_at TIMESTAMPTZ, -- Data do pedido de nova investigação — registra quando o N3 solicitou uma nova tarefa.
    new_validation_request_reason TEXT CHECK (char_length(new_validation_request_reason) BETWEEN 1 AND 1500 AND btrim(new_validation_request_reason) <> ''), -- Motivo da nova investigação — explica à equipe autorizada o que motivou o pedido do N3.
    request_fulfilled_by_validation_id UUID UNIQUE REFERENCES validations(id), -- Investigação que atende ao pedido — vincula o pedido do N3 à nova tarefa criada pelo N2.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    FOREIGN KEY (source_submission_id, validation_id) REFERENCES investigation_submissions(id, validation_id),
    CHECK ((decision_status = 'WAITING_N3' AND decided_by IS NULL AND decided_at IS NULL)
        OR (decision_status <> 'WAITING_N3' AND decided_by IS NOT NULL AND decided_at IS NOT NULL)),
    CHECK ((decision_status = 'RESTRICTED') = (restricted_reason IS NOT NULL)),
    CHECK ((decision_status = 'NEW_VALIDATION_REQUESTED'
            AND new_validation_requested_by IS NOT NULL AND new_validation_requested_at IS NOT NULL
            AND new_validation_request_reason IS NOT NULL)
        OR (decision_status <> 'NEW_VALIDATION_REQUESTED'
            AND new_validation_requested_by IS NULL AND new_validation_requested_at IS NULL
            AND new_validation_request_reason IS NULL AND request_fulfilled_by_validation_id IS NULL))
);

CREATE TABLE publications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- Identificador da publicação — identifica de forma única uma notícia aprovada.
    vault_id UUID NOT NULL UNIQUE REFERENCES vault(id), -- Registro de origem no cofre — vincula a notícia ao relatório aprovado, sem expor esse vínculo ao público.
    public_title TEXT NOT NULL CHECK (char_length(public_title) BETWEEN 1 AND 120 AND btrim(public_title) <> ''), -- Título público — identifica a notícia sem expor o conteúdo reservado do relatório.
    public_subtitle TEXT CHECK (char_length(public_subtitle) <= 200), -- Subtítulo público — complementa opcionalmente o título da notícia.
    public_risk_category TEXT NOT NULL CHECK (public_risk_category IN ('LOW', 'MODERATE', 'HIGH')), -- Categoria pública de risco — classifica o risco divulgado como baixo, moderado ou alto.
    public_body TEXT NOT NULL CHECK (char_length(public_body) BETWEEN 1 AND 5000 AND btrim(public_body) <> ''), -- Texto público — contém as informações preparadas para divulgação na notícia.
    status TEXT NOT NULL DEFAULT 'PUBLISHED' CHECK (status IN ('PUBLISHED', 'WITHDRAWN')), -- Situação da publicação — indica se a notícia está publicada ou foi retirada.
    published_by UUID NOT NULL REFERENCES users(id), -- Publicado por — identifica o N3 que aprovou a divulgação da notícia.
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Data da publicação — registra quando a notícia foi divulgada.
    withdrawn_by UUID REFERENCES users(id), -- Retirado por — identifica o N3 que retirou a notícia da consulta pública.
    withdrawn_at TIMESTAMPTZ, -- Data da retirada — registra quando a notícia deixou de ser exibida ao público.
    withdrawal_reason TEXT CHECK (char_length(withdrawal_reason) BETWEEN 1 AND 1500 AND btrim(withdrawal_reason) <> ''), -- Motivo da retirada — justifica a retirada da notícia e só pode ser consultado pelo N3.
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE, -- Exclusão lógica — marca o registro como excluído sem remover seus dados do banco.
    CHECK ((status = 'WITHDRAWN' AND withdrawn_by IS NOT NULL AND withdrawn_at IS NOT NULL AND withdrawal_reason IS NOT NULL)
        OR (status = 'PUBLISHED' AND withdrawn_by IS NULL AND withdrawn_at IS NULL AND withdrawal_reason IS NULL))
);

-- Bloqueia exclusão física e mudanças no conteúdo histórico; permite apenas os metadados autorizados e soft_delete.
CREATE FUNCTION protect_historical_content() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    mutable_fields TEXT[];
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Conteúdo histórico não pode ser excluído' USING ERRCODE = '23514';
    END IF;
    IF TG_TABLE_NAME = 'investigation_submissions' THEN
        mutable_fields := ARRAY['returned_by', 'returned_at', 'return_reason', 'soft_delete'];
        IF OLD.returned_at IS NOT NULL AND
            (to_jsonb(NEW) - 'soft_delete') IS DISTINCT FROM (to_jsonb(OLD) - 'soft_delete') THEN
            RAISE EXCEPTION 'Devolução registrada não pode ser alterada' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'vault' THEN
        mutable_fields := ARRAY['decision_status', 'decided_by', 'decided_at', 'restricted_reason',
            'new_validation_requested_by', 'new_validation_requested_at',
            'new_validation_request_reason', 'request_fulfilled_by_validation_id', 'soft_delete'];
        IF OLD.decision_status <> 'WAITING_N3' AND
            (to_jsonb(NEW) - ARRAY['request_fulfilled_by_validation_id', 'soft_delete']) IS DISTINCT FROM
            (to_jsonb(OLD) - ARRAY['request_fulfilled_by_validation_id', 'soft_delete']) THEN
            RAISE EXCEPTION 'Decisão final não pode ser alterada' USING ERRCODE = '23514';
        END IF;
        IF OLD.request_fulfilled_by_validation_id IS NOT NULL AND
            NEW.request_fulfilled_by_validation_id IS DISTINCT FROM OLD.request_fulfilled_by_validation_id THEN
            RAISE EXCEPTION 'Atendimento registrado não pode ser alterado' USING ERRCODE = '23514';
        END IF;
    ELSE
        mutable_fields := ARRAY['status', 'withdrawn_by', 'withdrawn_at', 'withdrawal_reason', 'soft_delete'];
        IF OLD.status = 'WITHDRAWN' AND
            (to_jsonb(NEW) - 'soft_delete') IS DISTINCT FROM (to_jsonb(OLD) - 'soft_delete') THEN
            RAISE EXCEPTION 'Notícia retirada não pode ser alterada' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF (to_jsonb(NEW) - mutable_fields) IS DISTINCT FROM (to_jsonb(OLD) - mutable_fields) THEN
        RAISE EXCEPTION 'Conteúdo histórico não pode ser alterado' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

-- Protege as entregas antes de alterações ou exclusões, preservando a análise enviada e as devoluções já registradas.
CREATE TRIGGER investigation_submissions_preserve_content
    BEFORE UPDATE OR DELETE ON investigation_submissions
    FOR EACH ROW EXECUTE FUNCTION protect_historical_content();
-- Protege os dossiês antes de alterações ou exclusões, preservando o conteúdo selado e as decisões já tomadas.
CREATE TRIGGER vault_preserve_content
    BEFORE UPDATE OR DELETE ON vault
    FOR EACH ROW EXECUTE FUNCTION protect_historical_content();
-- Protege as notícias antes de alterações ou exclusões, preservando o conteúdo aprovado e as retiradas já registradas.
CREATE TRIGGER publications_preserve_content
    BEFORE UPDATE OR DELETE ON publications
    FOR EACH ROW EXECUTE FUNCTION protect_historical_content();

-- Acelera a busca de usuários por equipe e situação da ativação.
CREATE INDEX users_team_status_idx ON users(team_id, status);
-- Acelera a busca de pedidos por solicitante e situação da decisão.
CREATE INDEX access_requests_requester_status_idx ON access_requests(requested_by, status);
-- Acelera a busca de amostras por equipe e situação ativa ou inativa.
CREATE INDEX biological_agents_team_status_idx ON biological_agents(team_id, status);
-- Acelera a busca das investigações de uma amostra por situação.
CREATE INDEX validations_agent_status_idx ON validations(agent_id, status);
-- Acelera a busca das investigações de um responsável por situação.
CREATE INDEX validations_responsible_status_idx ON validations(responsible_user_id, status);
-- Acelera a busca dos vínculos de colaboração de um usuário.
CREATE INDEX validation_participants_user_idx ON validation_participants(user_id);
-- Acelera a consulta do cofre por situação da decisão e data do envio.
CREATE INDEX vault_decision_sent_idx ON vault(decision_status, sent_at);
-- Acelera a busca das notícias por situação e data de publicação.
CREATE INDEX publications_status_published_idx ON publications(status, published_at);
-- Acelera a localização dos registros biométricos de um usuário.
CREATE INDEX vectors_user_idx ON vectors(user_id);
-- Acelera a localização das sessões de um usuário.
CREATE INDEX sessions_user_idx ON sessions(user_id);
-- Acelera a localização dos tokens de renovação vinculados a uma sessão.
CREATE INDEX refresh_tokens_session_idx ON refresh_tokens(session_id);
