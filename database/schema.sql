CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE jobs (
    id VARCHAR(50) PRIMARY KEY,
    topic TEXT,
    state VARCHAR(30) NOT NULL,
    script_path TEXT,
    scene_plan_path TEXT,
    asset_manifest_path TEXT,
    video_path TEXT,
    thumbnail_path TEXT,
    metadata_path TEXT,
    quality_score FLOAT,
    policy_status VARCHAR(20),
    gdrive_link TEXT,
    errors JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE assets (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(50) REFERENCES jobs(id),
    scene_id VARCHAR(20),
    file_path TEXT,
    license TEXT
);