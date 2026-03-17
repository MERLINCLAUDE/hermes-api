import os
import json
import uuid
import anthropic
from collections import deque
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from agents.daily_plan import run_daily_plan
from agents.notion_context import fetch_notion_context
from agents.social_stats import fetch_social_stats
from agents.content_strategy import run_content_strategy
from agents.life_coach import run_life_coach
from agents.security_monitor import run_security_monitor

app = FastAPI(title="Hermès — 344 Agent Orchestrator", version="2.2.0")

HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
STATE_FILE = os.environ.get("STATE_FILE", "/data/hermes_state.json")
client = anthropic.Anthropic()


# ─── State persistence ────────────────────────────────────────────────────────
def _load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state():
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({
                "euclide": _euclide,
                "task_results": _task_results,
                "conversation_history": _conversation_history[-100:],
            }, f)
    except Exception as e:
        print(f"[hermes] state save error: {e}")


_persisted = _load_state()

# ─── Euclide Bridge state ─────────────────────────────────────────────────────
_euclide: dict = _persisted.get("euclide", {"online": False, "registered_at": None, "callback_url": None})
_task_queue: deque = deque()
_task_results: dict = _persisted.get("task_results", {})
_conversation_history: list = _persisted.get("conversation_history", [])  # max 100 entrées

# ─── Messages Euclide → Archimède (push asynchrone) ──────────────────────────
_euclide_push_queue: deque = deque(maxlen=50)  # messages non lus par Archimède

# ─── Shared context (mémoire partagée inter-agents) ───────────────────────────
_shared_context: dict = {}  # {"key": {"value": ..., "updated_at": ..., "source": ...}}


class ContextSetRequest(BaseModel):
    key: str
    value: str
    source: Optional[str] = "unknown"


class DispatchRequest(BaseModel):
    intent: str
    context: Optional[str] = ""
    task: Optional[str] = ""
    source: Optional[str] = "unknown"


class DispatchResponse(BaseModel):
    result: str
    intent: str
    source: str


# ─── Euclide Bridge models ─────────────────────────────────────────────────────
class EuclideRegisterRequest(BaseModel):
    callback_url: Optional[str] = "http://localhost:8766"


class EuclideAskRequest(BaseModel):
    task: str
    context: Optional[str] = ""
    source: Optional[str] = "unknown"


class EuclideRespondRequest(BaseModel):
    task_id: str
    result: str


class EuclidePushRequest(BaseModel):
    message: str
    category: Optional[str] = "info"  # info | alerte | deploy | question


def verify_key(x_api_key: str = Header(...)):
    if HERMES_API_KEY and x_api_key != HERMES_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _route(req: DispatchRequest) -> str:
    intent = req.intent
    ctx = req.context or ""
    task = req.task or ""

    if intent == "daily_plan":
        return run_daily_plan(client, ctx)
    elif intent == "notion_context":
        return fetch_notion_context()
    elif intent == "social_stats":
        return fetch_social_stats()
    elif intent == "content_strategy":
        return run_content_strategy(task or "strategy", ctx)
    elif intent == "life_coach":
        return run_life_coach(task or "checkin", ctx)
    elif intent == "security_monitor":
        return run_security_monitor(task or "full")
    elif intent == "thales_query":
        # thales_query est désormais géré directement par Archimède → Thalès API
        # Hermès répond gracieusement pour éviter le 400
        return "⚠️ thales_query déprécié — Archimède doit appeler Thalès directement via THALES_API_URL"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown intent: {intent}")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes", "version": "2.0.0"}


@app.post("/dispatch", response_model=DispatchResponse)
async def dispatch(req: DispatchRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    try:
        result = _route(req)
        return DispatchResponse(result=result, intent=req.intent, source=req.source)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/intents")
async def list_intents(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return {
        "intents": [
            "daily_plan", "notion_context", "social_stats",
            "content_strategy", "life_coach", "security_monitor"
        ]
    }


# ─── Euclide Bridge endpoints ─────────────────────────────────────────────────
@app.post("/euclide/register")
async def euclide_register(req: EuclideRegisterRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    _euclide["online"] = True
    _euclide["registered_at"] = datetime.utcnow().isoformat()
    _euclide["callback_url"] = req.callback_url
    _save_state()
    return {"status": "registered", "registered_at": _euclide["registered_at"]}


@app.post("/euclide/unregister")
async def euclide_unregister(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    _euclide["online"] = False
    _euclide["registered_at"] = None
    _euclide["callback_url"] = None
    _save_state()
    return {"status": "unregistered"}


@app.get("/euclide/status")
async def euclide_status(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return {
        "online": _euclide["online"],
        "registered_at": _euclide["registered_at"],
        "pending_tasks": len(_task_queue),
    }


@app.post("/euclide/ask")
async def euclide_ask(req: EuclideAskRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    if not _euclide["online"]:
        raise HTTPException(status_code=503, detail="Euclide offline")
    task_id = str(uuid.uuid4())[:8]
    entry = {"task_id": task_id, "task": req.task, "context": req.context, "source": req.source}
    _task_queue.append(entry)
    _task_results[task_id] = {"status": "pending", "result": None}
    _conversation_history.append({
        "task_id": task_id,
        "from": req.source,
        "to": "euclide",
        "task": req.task,
        "context": req.context,
        "submitted_at": datetime.utcnow().isoformat(),
        "response": None,
        "responded_at": None,
    })
    _save_state()
    return {"status": "queued", "task_id": task_id}


@app.get("/euclide/tasks")
async def euclide_get_tasks(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    if _task_queue:
        task = _task_queue.popleft()
        _task_results[task["task_id"]] = {"status": "in_progress", "result": None}
        return {"task": task}
    return {"task": None}


@app.post("/euclide/respond")
async def euclide_respond(req: EuclideRespondRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    if req.task_id not in _task_results:
        raise HTTPException(status_code=404, detail="Task not found")
    _task_results[req.task_id] = {"status": "done", "result": req.result}
    for entry in reversed(_conversation_history):
        if entry["task_id"] == req.task_id:
            entry["response"] = req.result
            entry["responded_at"] = datetime.utcnow().isoformat()
            break
    _save_state()
    return {"status": "ok"}


@app.get("/euclide/history")
async def euclide_history(x_api_key: str = Header(...), limit: int = 20):
    verify_key(x_api_key)
    return {"history": list(reversed(_conversation_history))[:limit], "total": len(_conversation_history)}


@app.get("/euclide/result/{task_id}")
async def euclide_result(task_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    result = _task_results.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


# ─── Euclide → Archimède push ─────────────────────────────────────────────────
@app.post("/euclide/push")
async def euclide_push(req: EuclidePushRequest, x_api_key: str = Header(...)):
    """Euclide pousse un message vers Archimède (sera lu au prochain message de Lucas)."""
    verify_key(x_api_key)
    _euclide_push_queue.append({
        "message": req.message,
        "category": req.category,
        "pushed_at": datetime.utcnow().isoformat(),
        "read": False,
    })
    return {"status": "queued", "pending": len(_euclide_push_queue)}


@app.get("/euclide/messages")
async def euclide_messages(x_api_key: str = Header(...)):
    """Archimède récupère et vide les messages en attente d'Euclide."""
    verify_key(x_api_key)
    unread = [m for m in _euclide_push_queue if not m["read"]]
    for m in _euclide_push_queue:
        m["read"] = True
    return {"messages": unread, "count": len(unread)}


# ─── Shared context endpoints ─────────────────────────────────────────────────
@app.post("/context/set")
async def context_set(req: ContextSetRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    _shared_context[req.key] = {
        "value": req.value,
        "updated_at": datetime.utcnow().isoformat(),
        "source": req.source,
    }
    return {"status": "ok", "key": req.key}


@app.get("/context/get")
async def context_get(x_api_key: str = Header(...), key: Optional[str] = None):
    verify_key(x_api_key)
    if key:
        entry = _shared_context.get(key)
        return {key: entry} if entry else {}
    return _shared_context


@app.delete("/context/clear")
async def context_clear(x_api_key: str = Header(...), key: Optional[str] = None):
    verify_key(x_api_key)
    if key:
        _shared_context.pop(key, None)
    else:
        _shared_context.clear()
    return {"status": "cleared"}
