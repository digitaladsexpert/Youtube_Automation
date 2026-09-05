import os
import json
import aiosqlite
from datetime import datetime

DB_PATH = "youtube_prod.db"

async def get_db_connection():
    return await aiosqlite.connect(DB_PATH)

async def init_db():
    conn = await get_db_connection()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            topic TEXT,
            state TEXT NOT NULL,
            script_path TEXT,
            scene_plan_path TEXT,
            asset_manifest_path TEXT,
            video_path TEXT,
            thumbnail_path TEXT,
            metadata_path TEXT,
            quality_score REAL,
            policy_status TEXT,
            gdrive_link TEXT,
            errors TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await conn.commit()
    await conn.close()

async def create_job(job_id, topic):
    conn = await get_db_connection()
    await conn.execute("INSERT INTO jobs (id, topic, state) VALUES (?, ?, ?)", (job_id, topic, "IDEA"))
    await conn.commit()
    await conn.close()

async def update_job_state(job_id, state):
    conn = await get_db_connection()
    await conn.execute("UPDATE jobs SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (state, job_id))
    await conn.commit()
    await conn.close()

async def get_job(job_id):
    conn = await get_db_connection()
    async with conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)) as cursor:
        row = await cursor.fetchone()
    await conn.close()
    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    return None

async def log_error(job_id, error_msg):
    conn = await get_db_connection()
    async with conn.execute("SELECT errors FROM jobs WHERE id = ?", (job_id,)) as cursor:
        row = await cursor.fetchone()
        old_errors = json.loads(row[0]) if row and row[0] else []
    old_errors.append(error_msg)
    await conn.execute("UPDATE jobs SET errors = ? WHERE id = ?", (json.dumps(old_errors), job_id))
    await conn.commit()
    await conn.close()

async def update_gdrive_link(job_id, link):
    conn = await get_db_connection()
    await conn.execute("UPDATE jobs SET gdrive_link = ? WHERE id = ?", (link, job_id))
    await conn.commit()
    await conn.close()