import asyncio
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config.settings import settings, RepoConfig, load_repos_config, save_repos_config
from core.orchestrator import AgentOrchestrator
from core.scheduler import TimeWindowScheduler

app = FastAPI(title="OS-Agent Autonomous Contribution Dashboard", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

# Shared orchestrator instance
orchestrator = AgentOrchestrator()

# Background loop task reference
background_task = None
is_loop_running = False

class TimeWindowRequest(BaseModel):
    start_time: str
    end_time: str

class AddRepoRequest(BaseModel):
    repo: str
    labels: Optional[List[str]] = ["good first issue", "help wanted"]
    notes: Optional[str] = ""

@app.get("/")
async def root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "OS-Agent API running. Static index.html not yet initialized."}

@app.get("/api/status")
async def get_status():
    scheduler = TimeWindowScheduler(settings.WORK_WINDOW_START, settings.WORK_WINDOW_END, settings.TIMEZONE)
    is_active, status_msg = scheduler.is_active_now()
    seconds_to_wait = scheduler.seconds_until_next_window()
    current_time_str = scheduler.get_current_time().strftime("%Y-%m-%d %H:%M:%S")

    state = orchestrator.get_state()
    repos = load_repos_config()

    return {
        "current_time": current_time_str,
        "timezone": settings.TIMEZONE,
        "window_start": settings.WORK_WINDOW_START,
        "window_end": settings.WORK_WINDOW_END,
        "is_active": is_active,
        "status_message": status_msg,
        "seconds_to_next_window": seconds_to_wait,
        "dry_run": settings.DRY_RUN,
        "require_approval": settings.REQUIRE_APPROVAL,
        "is_loop_running": is_loop_running,
        "agent_status": state.get("current_status", "Idle"),
        "last_run": state.get("last_run"),
        "tracked_repos_count": len([r for r in repos if r.enabled]),
        "pending_approvals": state.get("pending_approvals", []),
        "completed_contributions": state.get("completed_contributions", []),
        "activity_log": state.get("activity_log", [])[:20]
    }

@app.post("/api/time-window")
async def update_time_window(req: TimeWindowRequest):
    settings.WORK_WINDOW_START = req.start_time.strip()
    settings.WORK_WINDOW_END = req.end_time.strip()
    orchestrator.scheduler.start_str = settings.WORK_WINDOW_START
    orchestrator.scheduler.end_str = settings.WORK_WINDOW_END
    orchestrator.log_event(f"Updated contribution window to: {settings.WORK_WINDOW_START} - {settings.WORK_WINDOW_END}")
    return {"success": True, "start": settings.WORK_WINDOW_START, "end": settings.WORK_WINDOW_END}

@app.get("/api/repos")
async def get_repos():
    return load_repos_config()

@app.post("/api/repos")
async def add_repo(req: AddRepoRequest):
    repos = load_repos_config()
    cleaned = req.repo.strip()
    if any(r.repo.lower() == cleaned.lower() for r in repos):
        raise HTTPException(status_code=400, detail="Repository already exists in registry.")

    new_repo = RepoConfig(
        repo=cleaned,
        enabled=True,
        labels=req.labels or ["good first issue", "help wanted"],
        notes=req.notes or ""
    )
    repos.append(new_repo)
    save_repos_config(repos)
    orchestrator.log_event(f"Added new target repository: {cleaned}")
    return {"success": True, "repo": new_repo}

@app.delete("/api/repos/{owner}/{repo_name}")
async def delete_repo(owner: str, repo_name: str):
    target = f"{owner}/{repo_name}".lower()
    repos = load_repos_config()
    filtered = [r for r in repos if r.repo.lower() != target]
    save_repos_config(filtered)
    orchestrator.log_event(f"Removed repository: {owner}/{repo_name}")
    return {"success": True}

@app.patch("/api/repos/{owner}/{repo_name}/toggle")
async def toggle_repo(owner: str, repo_name: str):
    target = f"{owner}/{repo_name}".lower()
    repos = load_repos_config()
    updated = False
    new_state = False
    for r in repos:
        if r.repo.lower() == target:
            r.enabled = not r.enabled
            new_state = r.enabled
            updated = True
            break
    if not updated:
        raise HTTPException(status_code=404, detail="Repo not found")
    save_repos_config(repos)
    orchestrator.log_event(f"Toggled repository {owner}/{repo_name}: {'Enabled' if new_state else 'Disabled'}")
    return {"success": True, "enabled": new_state}

@app.post("/api/run-cycle")
async def trigger_cycle(force: bool = True):
    orchestrator.log_event(f"Manual contribution cycle triggered (force={force})")
    # Run in background thread to avoid blocking FastAPI
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, orchestrator.run_contribution_cycle, force)
    return {"success": True, "result": result}

@app.post("/api/approve/{action_id:path}")
async def approve_action(action_id: str):
    loop = asyncio.get_event_loop()
    approved = await loop.run_in_executor(None, orchestrator.approve_action, action_id)
    if not approved:
        raise HTTPException(status_code=404, detail="Pending action not found or approval failed")
    return {"success": True, "action_id": action_id}

@app.post("/api/reject/{action_id:path}")
async def reject_action(action_id: str):
    state = orchestrator.get_state()
    pending = state.get("pending_approvals", [])
    state["pending_approvals"] = [p for p in pending if p["id"] != action_id]
    orchestrator._save_state(state)
    orchestrator.log_event(f"Rejected pending action {action_id}")
    return {"success": True}

@app.post("/api/toggle-dry-run")
async def toggle_dry_run():
    settings.DRY_RUN = not settings.DRY_RUN
    orchestrator.log_event(f"Toggled DRY_RUN mode: {settings.DRY_RUN}")
    return {"success": True, "dry_run": settings.DRY_RUN}

# Mount static files directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
