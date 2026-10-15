-- Schema inicial para bancos novos. Não converte bancos com a 001 já aplicada.
-- O serviço verifica permissões, reserva de N2/N3 e transições entre tabelas em transações.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE CHECK (code IN ('ADMIN', 'N1', 'N2', 'N3')),
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID,
    updated_at TIMESTAMPTZ,
    updated_by UUID
);

CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE CHECK (btrim(code) <> ''),
    description TEXT
);

CREATE TABLE role_permissions (
    role_id UUID NOT NULL REFERENCES roles(id),
    permission_id UUID NOT NULL REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE CHECK (btrim(code) <> ''),
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID,
    updated_at TIMESTAMPTZ,
    updated_by UUID
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    email TEXT NOT NULL UNIQUE CHECK (email = lower(btrim(email)) AND email <> ''),
    role_id UUID NOT NULL REFERENCES roles(id),
    team_id UUID REFERENCES teams(id),
    status TEXT NOT NULL DEFAULT 'PENDING_ACTIVATION'
        CHECK (status IN ('PENDING_ACTIVATION', 'ACTIVE', 'DISABLED')),
    biometric_enrollment_required BOOLEAN NOT NULL DEFAULT TRUE,
    password_change_required BOOLEAN NOT NULL DEFAULT TRUE,
    activated_at TIMESTAMPTZ,
    disabled_at TIMESTAMPTZ,
    disabled_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    biometric_failure_count INTEGER NOT NULL DEFAULT 0 CHECK (biometric_failure_count >= 0),
    biometric_failure_window_started_at TIMESTAMPTZ,
    biometric_blocked_until TIMESTAMPTZ,
    CHECK (status <> 'ACTIVE' OR activated_at IS NOT NULL),
    CHECK ((status = 'DISABLED' AND disabled_at IS NOT NULL AND disabled_by IS NOT NULL)
        OR (status <> 'DISABLED' AND disabled_at IS NULL AND disabled_by IS NULL))
);

ALTER TABLE roles
    ADD FOREIGN KEY (created_by) REFERENCES users(id),
    ADD FOREIGN KEY (updated_by) REFERENCES users(id);
ALTER TABLE teams
    ADD FOREIGN KEY (created_by) REFERENCES users(id),
    ADD FOREIGN KEY (updated_by) REFERENCES users(id);

CREATE TABLE access_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    requested_name TEXT NOT NULL CHECK (btrim(requested_name) <> ''),
    requested_email TEXT NOT NULL
        CHECK (requested_email = lower(btrim(requested_email)) AND requested_email <> ''),
    temporary_password_hash TEXT,
    requested_by UUID NOT NULL REFERENCES users(id),
    requested_role_id UUID NOT NULL REFERENCES roles(id),
    requested_team_id UUID REFERENCES teams(id),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_by UUID REFERENCES users(id),
    decided_at TIMESTAMPTZ,
    rejection_reason TEXT CHECK (char_length(rejection_reason) BETWEEN 1 AND 1500 AND btrim(rejection_reason) <> ''),
    CHECK ((status = 'PENDING' AND temporary_password_hash IS NOT NULL
            AND btrim(temporary_password_hash) <> '' AND decided_by IS NULL AND decided_at IS NULL)
        OR (status <> 'PENDING' AND temporary_password_hash IS NULL
            AND decided_by IS NOT NULL AND decided_at IS NOT NULL)),
    CHECK ((status = 'APPROVED') = (user_id IS NOT NULL)),
    CHECK ((status = 'REJECTED') = (rejection_reason IS NOT NULL))
);
CREATE UNIQUE INDEX access_requests_pending_email_unique
    ON access_requests(requested_email) WHERE status = 'PENDING';

CREATE TABLE password_hashes (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    password_hash TEXT NOT NULL CHECK (btrim(password_hash) <> ''),
    is_temporary BOOLEAN NOT NULL,
    temporary_expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by UUID REFERENCES users(id),
    CHECK (is_temporary = (temporary_expires_at IS NOT NULL))
);

CREATE TABLE vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    ciphertext BYTEA NOT NULL CHECK (octet_length(ciphertext) > 0),
    nonce BYTEA NOT NULL CHECK (octet_length(nonce) = 12),
    key_version TEXT NOT NULL CHECK (btrim(key_version) <> ''),
    model_version TEXT NOT NULL CHECK (btrim(model_version) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CHECK (expires_at > created_at AND expires_at <= created_at + INTERVAL '24 hours')
);

CREATE TABLE authentication_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'BLOCKED', 'COMPLETED', 'CANCELLED')),
    stage TEXT NOT NULL CHECK (stage IN ('ENROLL_FACE', 'VERIFY_FACE', 'CHANGE_PASSWORD')),
    token_jti UUID NOT NULL UNIQUE,
    biometric_failures INTEGER NOT NULL DEFAULT 0 CHECK (biometric_failures BETWEEN 0 AND 3),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > created_at),
    completed_at TIMESTAMPTZ,
    operation TEXT NOT NULL CHECK (operation IN ('LOGIN', 'ACTIVATION', 'RECOVERY', 'PASSWORD_CHANGE')),
    initiating_session_id UUID REFERENCES sessions(id),
    CHECK ((status = 'COMPLETED') = (completed_at IS NOT NULL)),
    CHECK ((operation = 'PASSWORD_CHANGE') = (initiating_session_id IS NOT NULL))
);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES sessions(id),
    token_hash TEXT NOT NULL UNIQUE CHECK (btrim(token_hash) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > created_at),
    used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    replaced_by_id UUID REFERENCES refresh_tokens(id),
    CHECK (replaced_by_id IS NULL OR (used_at IS NOT NULL AND replaced_by_id <> id))
);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID REFERENCES users(id),
    event TEXT NOT NULL CHECK (btrim(event) <> ''),
    resource_type TEXT NOT NULL CHECK (btrim(resource_type) <> ''),
    resource_id UUID,
    success BOOLEAN NOT NULL,
    reason TEXT,
    request_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE biological_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE CHECK (btrim(code) <> ''),
    provisional_label TEXT NOT NULL CHECK (char_length(provisional_label) BETWEEN 1 AND 120 AND btrim(provisional_label) <> ''),
    material_type TEXT NOT NULL CHECK (char_length(material_type) BETWEEN 1 AND 100 AND btrim(material_type) <> ''),
    collection_location TEXT NOT NULL CHECK (char_length(collection_location) BETWEEN 1 AND 255 AND btrim(collection_location) <> ''),
    collected_on DATE NOT NULL CHECK (collected_on <= CURRENT_DATE),
    initial_observations TEXT NOT NULL CHECK (char_length(initial_observations) BETWEEN 1 AND 1500 AND btrim(initial_observations) <> ''),
    investigation_reason TEXT NOT NULL CHECK (char_length(investigation_reason) BETWEEN 1 AND 1500 AND btrim(investigation_reason) <> ''),
    known_information TEXT CHECK (char_length(known_information) <= 1500),
    team_id UUID NOT NULL REFERENCES teams(id),
    created_by UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    UNIQUE (id, team_id)
);

CREATE TABLE validations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL,
    team_id UUID NOT NULL REFERENCES teams(id),
    responsible_user_id UUID NOT NULL REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'IN_REVIEW', 'RETURNED', 'REPORTED', 'PUBLISHED', 'CLOSED')),
    assessments_performed TEXT CHECK (char_length(assessments_performed) <= 1500),
    observed_results TEXT CHECK (char_length(observed_results) <= 5000),
    technical_opinion TEXT CHECK (char_length(technical_opinion) <= 5000),
    recommendation TEXT CHECK (char_length(recommendation) <= 5000),
    estimated_risk_percentage NUMERIC(5, 2) CHECK (estimated_risk_percentage BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID NOT NULL REFERENCES users(id),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    closed_at TIMESTAMPTZ,
    closed_by UUID REFERENCES users(id),
    closure_reason TEXT CHECK (char_length(closure_reason) BETWEEN 1 AND 1500 AND btrim(closure_reason) <> ''),
    closure_cause TEXT CHECK (closure_cause IN ('N2_CLOSED', 'N3_RESTRICTED', 'N3_NEW_VALIDATION')),
    previous_validation_id UUID UNIQUE REFERENCES validations(id),
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
CREATE UNIQUE INDEX validations_one_active_per_agent
    ON validations(agent_id) WHERE status IN ('OPEN', 'IN_REVIEW', 'RETURNED', 'REPORTED');

CREATE TABLE validation_participants (
    validation_id UUID NOT NULL REFERENCES validations(id),
    user_id UUID NOT NULL REFERENCES users(id),
    added_by UUID NOT NULL REFERENCES users(id),
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (validation_id, user_id)
);

CREATE TABLE investigation_submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    validation_id UUID NOT NULL REFERENCES validations(id),
    submission_number INTEGER NOT NULL CHECK (submission_number > 0),
    responsible_user_id UUID NOT NULL REFERENCES users(id),
    submitted_by UUID NOT NULL REFERENCES users(id),
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assessments_performed TEXT NOT NULL CHECK (char_length(assessments_performed) BETWEEN 1 AND 1500 AND btrim(assessments_performed) <> ''),
    observed_results TEXT NOT NULL CHECK (char_length(observed_results) BETWEEN 1 AND 5000 AND btrim(observed_results) <> ''),
    technical_opinion TEXT NOT NULL CHECK (char_length(technical_opinion) BETWEEN 1 AND 5000 AND btrim(technical_opinion) <> ''),
    recommendation TEXT NOT NULL CHECK (char_length(recommendation) BETWEEN 1 AND 5000 AND btrim(recommendation) <> ''),
    estimated_risk_percentage NUMERIC(5, 2) CHECK (estimated_risk_percentage BETWEEN 0 AND 100),
    participants_snapshot JSONB NOT NULL CHECK (jsonb_typeof(participants_snapshot) = 'array'),
    returned_by UUID REFERENCES users(id),
    returned_at TIMESTAMPTZ,
    return_reason TEXT CHECK (char_length(return_reason) BETWEEN 1 AND 1500 AND btrim(return_reason) <> ''),
    UNIQUE (validation_id, submission_number),
    UNIQUE (id, validation_id),
    CHECK ((returned_by IS NULL AND returned_at IS NULL AND return_reason IS NULL)
        OR (returned_by IS NOT NULL AND returned_at IS NOT NULL AND return_reason IS NOT NULL))
);

CREATE TABLE dossiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    validation_id UUID NOT NULL UNIQUE REFERENCES validations(id),
    source_submission_id UUID NOT NULL UNIQUE,
    protocol TEXT NOT NULL UNIQUE CHECK (btrim(protocol) <> ''),
    sent_by UUID NOT NULL REFERENCES users(id),
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    received_snapshot JSONB NOT NULL CHECK (jsonb_typeof(received_snapshot) = 'object'),
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120 AND btrim(title) <> ''),
    final_conclusion TEXT NOT NULL CHECK (char_length(final_conclusion) BETWEEN 1 AND 5000 AND btrim(final_conclusion) <> ''),
    final_risk_percentage NUMERIC(5, 2) NOT NULL CHECK (final_risk_percentage BETWEEN 0 AND 100),
    public_title TEXT NOT NULL CHECK (char_length(public_title) BETWEEN 1 AND 120 AND btrim(public_title) <> ''),
    public_subtitle TEXT CHECK (char_length(public_subtitle) <= 200),
    public_risk_category TEXT NOT NULL CHECK (public_risk_category IN ('LOW', 'MODERATE', 'HIGH')),
    public_body TEXT NOT NULL CHECK (char_length(public_body) BETWEEN 1 AND 5000 AND btrim(public_body) <> ''),
    decision_status TEXT NOT NULL DEFAULT 'WAITING_N3' CHECK (decision_status IN ('WAITING_N3', 'PUBLISHED', 'RESTRICTED', 'NEW_VALIDATION_REQUESTED')),
    decided_by UUID REFERENCES users(id),
    decided_at TIMESTAMPTZ,
    restricted_reason TEXT CHECK (char_length(restricted_reason) BETWEEN 1 AND 1500 AND btrim(restricted_reason) <> ''),
    new_validation_requested_by UUID REFERENCES users(id),
    new_validation_requested_at TIMESTAMPTZ,
    new_validation_request_reason TEXT CHECK (char_length(new_validation_request_reason) BETWEEN 1 AND 1500 AND btrim(new_validation_request_reason) <> ''),
    request_fulfilled_by_validation_id UUID UNIQUE REFERENCES validations(id),
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
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id UUID NOT NULL UNIQUE REFERENCES dossiers(id),
    public_title TEXT NOT NULL CHECK (char_length(public_title) BETWEEN 1 AND 120 AND btrim(public_title) <> ''),
    public_subtitle TEXT CHECK (char_length(public_subtitle) <= 200),
    public_risk_category TEXT NOT NULL CHECK (public_risk_category IN ('LOW', 'MODERATE', 'HIGH')),
    public_body TEXT NOT NULL CHECK (char_length(public_body) BETWEEN 1 AND 5000 AND btrim(public_body) <> ''),
    status TEXT NOT NULL DEFAULT 'PUBLISHED' CHECK (status IN ('PUBLISHED', 'WITHDRAWN')),
    published_by UUID NOT NULL REFERENCES users(id),
    published_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    withdrawn_by UUID REFERENCES users(id),
    withdrawn_at TIMESTAMPTZ,
    withdrawal_reason TEXT CHECK (char_length(withdrawal_reason) BETWEEN 1 AND 1500 AND btrim(withdrawal_reason) <> ''),
    CHECK ((status = 'WITHDRAWN' AND withdrawn_by IS NOT NULL AND withdrawn_at IS NOT NULL AND withdrawal_reason IS NOT NULL)
        OR (status = 'PUBLISHED' AND withdrawn_by IS NULL AND withdrawn_at IS NULL AND withdrawal_reason IS NULL))
);

-- Apenas os metadados listados podem mudar em registros históricos.
CREATE FUNCTION protect_historical_content() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    mutable_fields TEXT[];
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Conteúdo histórico não pode ser excluído' USING ERRCODE = '23514';
    END IF;
    IF TG_TABLE_NAME = 'investigation_submissions' THEN
        mutable_fields := ARRAY['returned_by', 'returned_at', 'return_reason'];
        IF OLD.returned_at IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'Devolução registrada não pode ser alterada' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'dossiers' THEN
        mutable_fields := ARRAY['decision_status', 'decided_by', 'decided_at', 'restricted_reason',
            'new_validation_requested_by', 'new_validation_requested_at',
            'new_validation_request_reason', 'request_fulfilled_by_validation_id'];
        IF OLD.decision_status <> 'WAITING_N3' AND
            (to_jsonb(NEW) - 'request_fulfilled_by_validation_id') IS DISTINCT FROM
            (to_jsonb(OLD) - 'request_fulfilled_by_validation_id') THEN
            RAISE EXCEPTION 'Decisão final não pode ser alterada' USING ERRCODE = '23514';
        END IF;
        IF OLD.request_fulfilled_by_validation_id IS NOT NULL AND
            NEW.request_fulfilled_by_validation_id IS DISTINCT FROM OLD.request_fulfilled_by_validation_id THEN
            RAISE EXCEPTION 'Atendimento registrado não pode ser alterado' USING ERRCODE = '23514';
        END IF;
    ELSE
        mutable_fields := ARRAY['status', 'withdrawn_by', 'withdrawn_at', 'withdrawal_reason'];
        IF OLD.status = 'WITHDRAWN' AND NEW IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'Notícia retirada não pode ser alterada' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF (to_jsonb(NEW) - mutable_fields) IS DISTINCT FROM (to_jsonb(OLD) - mutable_fields) THEN
        RAISE EXCEPTION 'Conteúdo histórico não pode ser alterado' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER investigation_submissions_preserve_content
    BEFORE UPDATE OR DELETE ON investigation_submissions
    FOR EACH ROW EXECUTE FUNCTION protect_historical_content();
CREATE TRIGGER dossiers_preserve_content
    BEFORE UPDATE OR DELETE ON dossiers
    FOR EACH ROW EXECUTE FUNCTION protect_historical_content();
CREATE TRIGGER publications_preserve_content
    BEFORE UPDATE OR DELETE ON publications
    FOR EACH ROW EXECUTE FUNCTION protect_historical_content();

CREATE INDEX users_team_status_idx ON users(team_id, status);
CREATE INDEX access_requests_requester_status_idx ON access_requests(requested_by, status);
CREATE INDEX biological_agents_team_status_idx ON biological_agents(team_id, status);
CREATE INDEX validations_agent_status_idx ON validations(agent_id, status);
CREATE INDEX validations_responsible_status_idx ON validations(responsible_user_id, status);
CREATE INDEX validation_participants_user_idx ON validation_participants(user_id);
CREATE INDEX dossiers_decision_sent_idx ON dossiers(decision_status, sent_at);
CREATE INDEX publications_status_published_idx ON publications(status, published_at);
CREATE INDEX vectors_user_idx ON vectors(user_id);
CREATE INDEX sessions_user_idx ON sessions(user_id);
CREATE INDEX refresh_tokens_session_idx ON refresh_tokens(session_id);
