BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_initial

CREATE TABLE var_jobs (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    task_id VARCHAR(64) NOT NULL, 
    user_id VARCHAR(128) NOT NULL, 
    status VARCHAR(16) DEFAULT 'pending' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    error_message TEXT, 
    portfolio_value FLOAT NOT NULL, 
    n_simulations INTEGER NOT NULL, 
    confidence_level FLOAT NOT NULL, 
    horizon_days INTEGER NOT NULL, 
    var_pct FLOAT, 
    var_abs FLOAT, 
    cvar_pct FLOAT, 
    cvar_abs FLOAT, 
    result_s3_key VARCHAR(512), 
    PRIMARY KEY (id), 
    CONSTRAINT uq_var_jobs_task_id UNIQUE (task_id)
);

CREATE INDEX ix_var_jobs_user_created ON var_jobs (user_id, created_at);

CREATE INDEX ix_var_jobs_task_id ON var_jobs (task_id);

CREATE INDEX ix_var_jobs_status ON var_jobs (status);

INSERT INTO alembic_version (version_num) VALUES ('0001_initial') RETURNING alembic_version.version_num;

-- Running upgrade 0001_initial -> 0002_users_and_tier

CREATE TABLE users (
    id UUID DEFAULT gen_random_uuid() NOT NULL, 
    external_id VARCHAR(128) NOT NULL, 
    tier VARCHAR(16) DEFAULT 'free' NOT NULL, 
    api_key_hash VARCHAR(64), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL, 
    last_active_at TIMESTAMP WITH TIME ZONE, 
    total_jobs INTEGER DEFAULT '0' NOT NULL, 
    total_simulations BIGINT DEFAULT '0' NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_users_external_id UNIQUE (external_id)
);

CREATE INDEX ix_users_external_id ON users (external_id);

CREATE INDEX ix_users_api_key_hash ON users (api_key_hash);

ALTER TABLE var_jobs ADD COLUMN tier VARCHAR(16) DEFAULT 'free' NOT NULL;

ALTER TABLE var_jobs ADD COLUMN duration_ms INTEGER;

UPDATE alembic_version SET version_num='0002_users_and_tier' WHERE alembic_version.version_num = '0001_initial';

COMMIT;

