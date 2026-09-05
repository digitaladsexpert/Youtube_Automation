import uvicorn
import os
from database.db import init_db
import asyncio

if __name__ == "__main__":
    asyncio.run(init_db())
    print("✅ Database Ready (SQLite)")
    print("🚀 Server Starting on http://0.0.0.0:8000")
    print("📄 Docs: http://localhost:8000/docs")

    # FIXED: reload=True was hardcoded. That's fine for local dev (auto-restarts
    # on file edits) but wrong for a deployed rented-GPU box — the file watcher
    # is pure overhead there and reload can interact badly with the in-memory
    # background job tasks (a reload mid-job would drop it). Defaults to off;
    # set UVICORN_RELOAD=true only when actively editing code locally.
    reload_enabled = os.getenv("UVICORN_RELOAD", "false").lower() == "true"
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=reload_enabled)
