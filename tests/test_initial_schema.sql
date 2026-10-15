-- Execute apenas em um banco isolado com a migration 001 aplicada.
-- Dados fictícios ficam dentro de uma transação revertida ao final.
\set ON_ERROR_STOP on
BEGIN;

CREATE FUNCTION pg_temp.expect_failure(statement TEXT, expected_state TEXT)
RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE actual_state TEXT;
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS actual_state = RETURNED_SQLSTATE;
        IF actual_state = expected_state THEN RETURN; END IF;
        RAISE EXCEPTION 'SQLSTATE esperado %, recebido %: %', expected_state, actual_state, SQLERRM;
    END;
    RAISE EXCEPTION 'Comando deveria falhar: %', statement;
END;
$$;

DO $$
BEGIN
    IF (SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'
        AND table_type = 'BASE TABLE' AND table_name <> 'schema_migrations') <> 18 THEN
        RAISE EXCEPTION 'Esperadas 18 tabelas do domínio';
    END IF;
    IF EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public'
        AND table_name = 'vectors' AND column_name = 'vector') THEN
        RAISE EXCEPTION 'Embedding numérico antigo ainda existe';
    END IF;
END;
$$;

INSERT INTO roles(id, code, name) VALUES
    ('00000000-0000-0000-0000-000000000001', 'ADMIN', 'Administrador'),
    ('00000000-0000-0000-0000-000000000002', 'N1', 'Pesquisador');
INSERT INTO teams(id, code, name) VALUES
    ('00000000-0000-0000-0000-000000000010', 'A', 'Equipe A');
INSERT INTO users(id, name, email, role_id) VALUES
    ('00000000-0000-0000-0000-000000000020', 'Admin teste', 'admin@teste.exemplo', '00000000-0000-0000-0000-000000000001');
INSERT INTO users(id, name, email, role_id, team_id) VALUES
    ('00000000-0000-0000-0000-000000000021', 'N1 teste', 'n1@teste.exemplo',
     '00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000010');

SELECT pg_temp.expect_failure($q$INSERT INTO users(name,email,role_id)
    SELECT name,email,role_id FROM users LIMIT 1$q$, '23505');
SELECT pg_temp.expect_failure($q$INSERT INTO users(name,email,role_id)
    SELECT name,'UPPER@teste.exemplo',role_id FROM users LIMIT 1$q$, '23514');

INSERT INTO access_requests(requested_name, requested_email, temporary_password_hash,
    requested_by, requested_role_id, requested_team_id)
VALUES ('Pedido', 'pedido@teste.exemplo', 'hash-ficticio',
    '00000000-0000-0000-0000-000000000020', '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000010');
SELECT pg_temp.expect_failure($q$INSERT INTO access_requests(requested_name,requested_email,
    temporary_password_hash,requested_by,requested_role_id)
    SELECT requested_name,requested_email,temporary_password_hash,requested_by,requested_role_id
    FROM access_requests$q$, '23505');
SELECT pg_temp.expect_failure($q$UPDATE access_requests SET status='APPROVED'$q$, '23514');
UPDATE access_requests SET status='REJECTED', temporary_password_hash=NULL,
    decided_by='00000000-0000-0000-0000-000000000020', decided_at=NOW(), rejection_reason='Teste';

INSERT INTO password_hashes(user_id, password_hash, is_temporary)
VALUES ('00000000-0000-0000-0000-000000000021', 'hash-ficticio', FALSE);
SELECT pg_temp.expect_failure($q$UPDATE password_hashes SET is_temporary=TRUE$q$, '23514');
INSERT INTO vectors(user_id, ciphertext, nonce, key_version, model_version)
VALUES ('00000000-0000-0000-0000-000000000021', decode('01','hex'),
    decode(repeat('00',12),'hex'), 'teste-1', 'teste-1');
SELECT pg_temp.expect_failure($q$UPDATE vectors SET nonce=decode('00','hex')$q$, '23514');

INSERT INTO sessions(id,user_id,expires_at) VALUES
    ('00000000-0000-0000-0000-000000000030','00000000-0000-0000-0000-000000000021',NOW()+INTERVAL '24 hours');
SELECT pg_temp.expect_failure($q$UPDATE sessions SET expires_at=created_at+INTERVAL '25 hours'$q$, '23514');
SELECT pg_temp.expect_failure($q$INSERT INTO authentication_attempts(user_id,stage,token_jti,expires_at,operation)
    VALUES ('00000000-0000-0000-0000-000000000021','VERIFY_FACE',gen_random_uuid(),NOW()+INTERVAL '5 minutes','PASSWORD_CHANGE')$q$, '23514');
INSERT INTO authentication_attempts(user_id,stage,token_jti,expires_at,operation,initiating_session_id)
VALUES ('00000000-0000-0000-0000-000000000021','VERIFY_FACE',gen_random_uuid(),NOW()+INTERVAL '5 minutes',
    'PASSWORD_CHANGE','00000000-0000-0000-0000-000000000030');
INSERT INTO refresh_tokens(session_id,token_hash,expires_at)
VALUES ('00000000-0000-0000-0000-000000000030','hash-ficticio',NOW()+INTERVAL '24 hours');
SELECT pg_temp.expect_failure($q$INSERT INTO refresh_tokens(session_id,token_hash,expires_at)
    SELECT session_id,token_hash,expires_at FROM refresh_tokens$q$, '23505');

INSERT INTO biological_agents(id,code,provisional_label,material_type,collection_location,
    collected_on,initial_observations,investigation_reason,team_id,created_by)
VALUES ('00000000-0000-0000-0000-000000000040','TESTE-01','Amostra teste','Material teste','Local fictício',
    CURRENT_DATE,'Observação','Investigar','00000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000021');
SELECT pg_temp.expect_failure($q$UPDATE biological_agents SET collected_on=CURRENT_DATE+1$q$, '23514');
INSERT INTO validations(id,agent_id,team_id,responsible_user_id,created_by)
VALUES ('00000000-0000-0000-0000-000000000050','00000000-0000-0000-0000-000000000040',
    '00000000-0000-0000-0000-000000000010','00000000-0000-0000-0000-000000000021','00000000-0000-0000-0000-000000000021');
SELECT pg_temp.expect_failure($q$INSERT INTO validations(agent_id,team_id,responsible_user_id,created_by)
    SELECT agent_id,team_id,responsible_user_id,created_by FROM validations$q$, '23505');
SELECT pg_temp.expect_failure($q$UPDATE validations SET status='IN_REVIEW'$q$, '23514');
SELECT pg_temp.expect_failure($q$UPDATE validations SET estimated_risk_percentage=100.01$q$, '23514');
UPDATE validations SET status='IN_REVIEW', assessments_performed='Avaliação', observed_results='Resultado',
    technical_opinion='Parecer', recommendation='Recomendação';
INSERT INTO investigation_submissions(id,validation_id,submission_number,responsible_user_id,submitted_by,
    assessments_performed,observed_results,technical_opinion,recommendation,participants_snapshot)
SELECT '00000000-0000-0000-0000-000000000060',id,1,responsible_user_id,responsible_user_id,
    assessments_performed,observed_results,technical_opinion,recommendation,'[]'::jsonb FROM validations;
SELECT pg_temp.expect_failure($q$INSERT INTO investigation_submissions(validation_id,submission_number,
    responsible_user_id,submitted_by,assessments_performed,observed_results,technical_opinion,recommendation,participants_snapshot)
    SELECT validation_id,submission_number,responsible_user_id,submitted_by,assessments_performed,
    observed_results,technical_opinion,recommendation,participants_snapshot FROM investigation_submissions$q$, '23505');
SELECT pg_temp.expect_failure($q$UPDATE investigation_submissions SET technical_opinion='Alteração'$q$, '23514');
SELECT pg_temp.expect_failure($q$DELETE FROM investigation_submissions$q$, '23514');
UPDATE investigation_submissions SET returned_by='00000000-0000-0000-0000-000000000020',
    returned_at=NOW(),return_reason='Complementar';
SELECT pg_temp.expect_failure($q$UPDATE investigation_submissions SET return_reason='Outro'$q$, '23514');

INSERT INTO dossiers(id,validation_id,source_submission_id,protocol,sent_by,received_snapshot,title,
    final_conclusion,final_risk_percentage,public_title,public_risk_category,public_body)
VALUES ('00000000-0000-0000-0000-000000000070','00000000-0000-0000-0000-000000000050',
    '00000000-0000-0000-0000-000000000060','PROTOCOLO-TESTE','00000000-0000-0000-0000-000000000020',
    '{}','Relatório','Conclusão',35,'Notícia','MODERATE','Texto público fictício');
SELECT pg_temp.expect_failure($q$UPDATE dossiers SET final_conclusion='Alterada'$q$, '23514');
SELECT pg_temp.expect_failure($q$DELETE FROM dossiers$q$, '23514');
SELECT pg_temp.expect_failure($q$UPDATE dossiers SET decision_status='RESTRICTED',
    decided_by='00000000-0000-0000-0000-000000000020',decided_at=NOW()$q$, '23514');
UPDATE dossiers SET decision_status='PUBLISHED',decided_by='00000000-0000-0000-0000-000000000020',decided_at=NOW();
SELECT pg_temp.expect_failure($q$UPDATE dossiers SET decision_status='RESTRICTED',restricted_reason='Sigilo'$q$, '23514');
INSERT INTO publications(dossier_id,public_title,public_risk_category,public_body,published_by)
SELECT id,public_title,public_risk_category,public_body,sent_by FROM dossiers;
SELECT pg_temp.expect_failure($q$UPDATE publications SET public_body='Alterado'$q$, '23514');
SELECT pg_temp.expect_failure($q$UPDATE publications SET status='WITHDRAWN'$q$, '23514');
UPDATE publications SET status='WITHDRAWN',withdrawn_by='00000000-0000-0000-0000-000000000020',
    withdrawn_at=NOW(),withdrawal_reason='Teste de retirada';
SELECT pg_temp.expect_failure($q$UPDATE publications SET status='PUBLISHED',withdrawn_by=NULL,
    withdrawn_at=NULL,withdrawal_reason=NULL$q$, '23514');
SELECT pg_temp.expect_failure($q$DELETE FROM publications$q$, '23514');

UPDATE validations SET status='PUBLISHED';
INSERT INTO validations(agent_id,team_id,responsible_user_id,created_by)
SELECT agent_id,team_id,responsible_user_id,created_by FROM validations;
SELECT pg_temp.expect_failure($q$DELETE FROM users WHERE id='00000000-0000-0000-0000-000000000021'$q$, '23503');

ROLLBACK;
\echo 'Schema, constraints e preservação do histórico: verificações passaram.'
