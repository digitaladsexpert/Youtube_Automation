import os
import json
import asyncio

# FIXED: python-dotenv was in requirements.txt but load_dotenv() was never
# called anywhere, so on native `python run.py` (what the README tells you to
# run) ANTHROPIC_API_KEY was always None unless you exported it yourself.
# load_dotenv() won't override real env vars that are already set (e.g. from
# Docker), so this is safe in both native and containerized runs.
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from datetime import datetime
from app.agent import HermesAgent
from app.state_machine import State
from database.db import create_job, get_job, update_job_state

app = FastAPI(title="Hermes Production API")


class StartJobRequest(BaseModel):
    topic: str


@app.post("/start_job")
async def start_production(request: StartJobRequest, background_tasks: BackgroundTasks):
    job_id = f"JOB_{int(datetime.now().timestamp())}"
    await create_job(job_id, request.topic)
    background_tasks.add_task(run_hermes_async, job_id)
    return {"status": "accepted", "job_id": job_id}


async def run_hermes_async(job_id: str):
    agent = HermesAgent(job_id)
    await agent.run()


@app.get("/job/{job_id}/status")
async def get_status(job_id: str):
    job = await get_job(job_id)
    return job if job else {"error": "Not found"}


# NEW: these two endpoints are what actually make HUMAN_REVIEW a real gate.
# Previously the state existed in state_machine.py but nothing paused on it.
@app.post("/job/{job_id}/approve")
async def approve_job(job_id: str, background_tasks: BackgroundTasks):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    if job["state"] != State.HUMAN_REVIEW.value:
        raise HTTPException(
            status_code=400,
            detail=f"Job is in state '{job['state']}', not awaiting review.",
        )
    await update_job_state(job_id, State.APPROVED.value)
    background_tasks.add_task(run_hermes_async, job_id)
    return {"status": "approved", "job_id": job_id}


@app.post("/job/{job_id}/reject")
async def reject_job(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Not found")
    if job["state"] != State.HUMAN_REVIEW.value:
        raise HTTPException(
            status_code=400,
            detail=f"Job is in state '{job['state']}', not awaiting review.",
        )
    await update_job_state(job_id, State.BLOCKED.value)
    return {"status": "rejected", "job_id": job_id}
