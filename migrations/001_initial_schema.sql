CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID,
    updated_at TIMESTAMPTZ,
    updated_by UUID,
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID,
    code VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(80) NOT NULL,
    level SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 3),
    description VARCHAR(255)
);

CREATE TABLE specialties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID,
    updated_at TIMESTAMPTZ,
    updated_by UUID,
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    description VARCHAR(255)
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID REFERENCES users(id),
    role_id UUID NOT NULL REFERENCES roles(id),
    specialty_id UUID REFERENCES specialties(id),
    name VARCHAR(150) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE
);

ALTER TABLE roles
    ADD CONSTRAINT roles_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES users(id),
    ADD CONSTRAINT roles_updated_by_fkey
        FOREIGN KEY (updated_by) REFERENCES users(id),
    ADD CONSTRAINT roles_deleted_by_fkey
        FOREIGN KEY (deleted_by) REFERENCES users(id);

ALTER TABLE specialties
    ADD CONSTRAINT specialties_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES users(id),
    ADD CONSTRAINT specialties_updated_by_fkey
        FOREIGN KEY (updated_by) REFERENCES users(id),
    ADD CONSTRAINT specialties_deleted_by_fkey
        FOREIGN KEY (deleted_by) REFERENCES users(id);

CREATE TABLE password_hashes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID REFERENCES users(id),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id),
    password_hash TEXT NOT NULL
);

CREATE TABLE vectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID REFERENCES users(id),
    user_id UUID NOT NULL REFERENCES users(id),
    vector DOUBLE PRECISION[] NOT NULL CHECK (cardinality(vector) > 0),
    model_version VARCHAR(50) NOT NULL
);

CREATE TABLE biological_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID REFERENCES users(id),
    specialty_id UUID NOT NULL REFERENCES specialties(id),
    name VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    found_location VARCHAR(255) NOT NULL,
    found_biome VARCHAR(50) NOT NULL,
    found_at TIMESTAMPTZ
);

CREATE TABLE validations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID REFERENCES users(id),
    biological_agent_id UUID NOT NULL REFERENCES biological_agents(id),
    status VARCHAR(30) NOT NULL
        CHECK (status IN ('OPEN', 'IN_REVIEW', 'RETURNED', 'CLOSED', 'REPORTED')),
    final_risk_percentage NUMERIC(5, 2)
        CHECK (final_risk_percentage BETWEEN 0 AND 100),
    final_conclusion TEXT,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    return_reason TEXT,
    CHECK (status <> 'RETURNED' OR return_reason IS NOT NULL)
);

CREATE TABLE validation_collaborators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID REFERENCES users(id),
    validation_id UUID NOT NULL REFERENCES validations(id),
    user_id UUID NOT NULL REFERENCES users(id),
    UNIQUE (validation_id, user_id)
);

CREATE TABLE technical_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ,
    updated_by UUID REFERENCES users(id),
    soft_delete BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    deleted_by UUID REFERENCES users(id),
    validation_id UUID NOT NULL REFERENCES validations(id),
    author_id UUID NOT NULL REFERENCES users(id),
    risk_percentage NUMERIC(5, 2) NOT NULL
        CHECK (risk_percentage BETWEEN 0 AND 100),
    technical_opinion TEXT NOT NULL,
    recommendation TEXT,
    submitted_at TIMESTAMPTZ,
    UNIQUE (validation_id, author_id),
    FOREIGN KEY (validation_id, author_id)
        REFERENCES validation_collaborators (validation_id, user_id)
);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (expires_at > created_at)
);

CREATE TABLE logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    event VARCHAR(100) NOT NULL,
    success BOOLEAN NOT NULL,
    reason VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

