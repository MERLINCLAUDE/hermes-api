import os
import json
import uuid
import anthropic
from collections import deque
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List

from agents.daily_plan import run_daily_plan
from agents.notion_context import fetch_notion_context
from agents.social_stats import fetch_social_stats
from agents.content_strategy import run_content_strategy
from agents.life_coach import run_life_coach
from agents.security_monitor import run_security_monitor

app = FastAPI(title="Hermès — 344 Agent Orchestrator", version="3.0.0")

HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
STATE_FILE = os.environ.get("STATE_FILE", "/data/hermes_state.json")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

client = anthropic.Anthropic()

# ─── Supabase client (optionnel — fallback in-memory si absent) ──────────────
_sb = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        from supabase import create_client
        _sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print(f"[hermes] Supabase connecté : {SUPABASE_URL}")
    except Exception as e:
        print(f"[hermes] Supabase indisponible (fallback in-memory) : {e}")


# ─── Helpers Supabase ─────────────────────────────────────────────────────────

def sb_register_agent(name: str, agent_type: str, capabilities: list, metadata: dict = {}) -> bool:
    if not _sb:
        return False
    try:
        _sb.table("agents").upsert({
            "name": name,
            "agent_type": agent_type,
            "status": "online",
            "capabilities": capabilities,
            "last_seen": datetime.utcnow().isoformat(),
            "metadata": metadata,
        }).execute()
        return True
    except Exception as e:
        print(f"[sb] register_agent error: {e}")
        return False


def sb_unregister_agent(name: str) -> bool:
    if not _sb:
        return False
    try:
        _sb.table("agents").update({
            "status": "offline",
            "last_seen": datetime.utcnow().isoformat(),
        }).eq("name", name).execute()
        return True
    except Exception as e:
        print(f"[sb] unregister_agent error: {e}")
        return False


def sb_get_agents() -> list:
    if not _sb:
        return []
    try:
        return _sb.table("agents").select("*").order("name").execute().data or []
    except Exception as e:
        print(f"[sb] get_agents error: {e}")
        return []


def sb_get_agent(name: str) -> dict | None:
    if not _sb:
        return None
    try:
        rows = _sb.table("agents").select("*").eq("name", name).execute().data
        return rows[0] if rows else None
    except Exception as e:
        print(f"[sb] get_agent error: {e}")
        return None


def sb_enqueue_task(from_agent: str, to_agent: str, task: str, context: str = "", priority: str = "normal") -> str:
    task_id = str(uuid.uuid4())[:12]
    if _sb:
        try:
            _sb.table("agent_tasks").insert({
                "task_id": task_id,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "task": task,
                "context": context,
                "status": "pending",
                "priority": priority,
            }).execute()
            return task_id
        except Exception as e:
            print(f"[sb] enqueue_task error: {e}")
    # Fallback in-memory
    entry = {"task_id": task_id, "task": task, "context": context, "source": from_agent}
    if to_agent == "euclide":
        _task_queue.append(entry)
    _task_results[task_id] = {"status": "pending", "result": None}
    return task_id


def sb_get_next_task(agent_name: str) -> dict | None:
    if _sb:
        try:
            rows = (
                _sb.table("agent_tasks")
                .select("*")
                .eq("to_agent", agent_name)
                .eq("status", "pending")
                .order("created_at")
                .limit(1)
                .execute()
                .data
            )
            if rows:
                task = rows[0]
                _sb.table("agent_tasks").update({
                    "status": "processing",
                    "updated_at": datetime.utcnow().isoformat(),
                }).eq("task_id", task["task_id"]).execute()
                return task
            return None
        except Exception as e:
            print(f"[sb] get_next_task error: {e}")
    # Fallback in-memory (euclide only)
    if agent_name == "euclide" and _task_queue:
        task = _task_queue.popleft()
        _task_results[task["task_id"]] = {"status": "in_progress", "result": None}
        return task
    return None


def sb_complete_task(task_id: str, result: str) -> bool:
    if _sb:
        try:
            _sb.table("agent_tasks").update({
                "status": "done",
                "result": result,
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("task_id", task_id).execute()
            return True
        except Exception as e:
            print(f"[sb] complete_task error: {e}")
    # Fallback in-memory
    if task_id in _task_results:
        _task_results[task_id] = {"status": "done", "result": result}
    return True


def sb_set_context(key: str, value: str, source: str = "system") -> bool:
    if _sb:
        try:
            _sb.table("shared_context").upsert({
                "key": key,
                "value": value,
                "source": source,
                "updated_at": datetime.utcnow().isoformat(),
            }).execute()
            return True
        except Exception as e:
            print(f"[sb] set_context error: {e}")
    # Fallback in-memory
    _shared_context[key] = {"value": value, "updated_at": datetime.utcnow().isoformat(), "source": source}
    return True


def sb_get_context(key: str | None = None) -> dict:
    if _sb:
        try:
            if key:
                rows = _sb.table("shared_context").select("*").eq("key", key).execute().data
                return {r["key"]: r for r in rows} if rows else {}
            else:
                rows = _sb.table("shared_context").select("*").execute().data or []
                return {r["key"]: r for r in rows}
        except Exception as e:
            print(f"[sb] get_context error: {e}")
    # Fallback in-memory
    if key:
        entry = _shared_context.get(key)
        return {key: entry} if entry else {}
    return _shared_context


def sb_delete_context(key: str | None = None) -> bool:
    if _sb:
        try:
            if key:
                _sb.table("shared_context").delete().eq("key", key).execute()
            else:
                _sb.table("shared_context").delete().neq("key", "").execute()
            return True
        except Exception as e:
            print(f"[sb] delete_context error: {e}")
    # Fallback in-memory
    if key:
        _shared_context.pop(key, None)
    else:
        _shared_context.clear()
    return True


# ─── State persistence (fallback in-memory) ──────────────────────────────────
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

_euclide: dict = _persisted.get("euclide", {"online": False, "registered_at": None, "callback_url": None})
_task_queue: deque = deque()
_task_results: dict = _persisted.get("task_results", {})
_conversation_history: list = _persisted.get("conversation_history", [])
_euclide_push_queue: deque = deque(maxlen=50)
_shared_context: dict = {}


# ─── Pydantic models ──────────────────────────────────────────────────────────
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
    category: Optional[str] = "info"


# ─── New inter-agent models ───────────────────────────────────────────────────
class AgentRegisterRequest(BaseModel):
    name: str
    agent_type: str = "cloud"   # "cloud" | "local"
    capabilities: List[str] = []
    metadata: dict = {}


class AgentToAgentRequest(BaseModel):
    from_agent: str
    to_agent: str
    task: str
    context: Optional[str] = ""
    priority: Optional[str] = "normal"   # "low" | "normal" | "high"


class AgentRespondRequest(BaseModel):
    task_id: str
    result: str
    agent_name: str


# ─── Auth ─────────────────────────────────────────────────────────────────────
def verify_key(x_api_key: str):
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
        return "⚠️ thales_query déprécié — utiliser /agent-to-agent avec to_agent='thales'"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown intent: {intent}")


# ─── Core endpoints ───────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "hermes",
        "version": "3.0.0",
        "supabase": _sb is not None,
    }


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
    return {"intents": ["daily_plan", "notion_context", "social_stats", "content_strategy", "life_coach", "security_monitor"]}


# ─── Agent Registry ───────────────────────────────────────────────────────────
@app.post("/agents/register")
async def agent_register(req: AgentRegisterRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    sb_register_agent(req.name, req.agent_type, req.capabilities, req.metadata)
    if req.name == "euclide":
        _euclide["online"] = True
        _euclide["registered_at"] = datetime.utcnow().isoformat()
        _save_state()
    return {"status": "registered", "agent": req.name, "registered_at": datetime.utcnow().isoformat()}


@app.post("/agents/unregister")
async def agent_unregister(name: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    sb_unregister_agent(name)
    if name == "euclide":
        _euclide["online"] = False
        _save_state()
    return {"status": "offline", "agent": name}


@app.get("/agents")
async def list_agents(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    agents = sb_get_agents()
    if not agents:
        # Fallback: retourner l'état Euclide connu
        agents = [{"name": "euclide", "status": "online" if _euclide["online"] else "offline"}]
    return {"agents": agents, "count": len(agents)}


@app.get("/agents/{name}")
async def get_agent(name: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    agent = sb_get_agent(name)
    if not agent:
        if name == "euclide":
            return {"name": "euclide", "status": "online" if _euclide["online"] else "offline"}
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return agent


# ─── Agent-to-Agent routing ───────────────────────────────────────────────────
@app.post("/agent-to-agent")
async def agent_to_agent(req: AgentToAgentRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    task_id = sb_enqueue_task(req.from_agent, req.to_agent, req.task, req.context or "", req.priority or "normal")

    # Log dans l'historique
    _conversation_history.append({
        "task_id": task_id,
        "from": req.from_agent,
        "to": req.to_agent,
        "task": req.task,
        "context": req.context,
        "submitted_at": datetime.utcnow().isoformat(),
        "response": None,
        "responded_at": None,
    })
    _save_state()

    return {
        "status": "queued",
        "task_id": task_id,
        "from_agent": req.from_agent,
        "to_agent": req.to_agent,
        "priority": req.priority,
    }


@app.get("/agent/{name}/tasks")
async def agent_get_tasks(name: str, x_api_key: str = Header(...)):
    """Agent polls sa propre queue — générique pour tous les agents."""
    verify_key(x_api_key)
    task = sb_get_next_task(name)
    return {"task": task}


@app.post("/agent/respond")
async def agent_respond(req: AgentRespondRequest, x_api_key: str = Header(...)):
    """Agent retourne le résultat d'une tâche — générique."""
    verify_key(x_api_key)
    sb_complete_task(req.task_id, req.result)
    for entry in reversed(_conversation_history):
        if entry.get("task_id") == req.task_id:
            entry["response"] = req.result
            entry["responded_at"] = datetime.utcnow().isoformat()
            break
    _save_state()
    return {"status": "ok", "task_id": req.task_id}


# ─── Euclide Bridge (backward compat) ────────────────────────────────────────
@app.post("/euclide/register")
async def euclide_register(req: EuclideRegisterRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    _euclide["online"] = True
    _euclide["registered_at"] = datetime.utcnow().isoformat()
    _euclide["callback_url"] = req.callback_url
    sb_register_agent("euclide", "local", ["code", "deploy", "git", "bash", "notion", "analysis"])
    _save_state()
    return {"status": "registered", "registered_at": _euclide["registered_at"]}


@app.post("/euclide/unregister")
async def euclide_unregister(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    _euclide["online"] = False
    _euclide["registered_at"] = None
    _euclide["callback_url"] = None
    sb_unregister_agent("euclide")
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
    task_id = sb_enqueue_task(req.source or "archimede", "euclide", req.task, req.context or "")
    _conversation_history.append({
        "task_id": task_id, "from": req.source, "to": "euclide",
        "task": req.task, "context": req.context,
        "submitted_at": datetime.utcnow().isoformat(), "response": None, "responded_at": None,
    })
    _save_state()
    return {"status": "queued", "task_id": task_id}


@app.get("/euclide/tasks")
async def euclide_get_tasks(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    task = sb_get_next_task("euclide")
    return {"task": task}


@app.post("/euclide/respond")
async def euclide_respond(req: EuclideRespondRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    sb_complete_task(req.task_id, req.result)
    for entry in reversed(_conversation_history):
        if entry.get("task_id") == req.task_id:
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
    if _sb:
        try:
            rows = _sb.table("agent_tasks").select("status,result").eq("task_id", task_id).execute().data
            if rows:
                return rows[0]
        except Exception:
            pass
    result = _task_results.get(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.post("/euclide/push")
async def euclide_push(req: EuclidePushRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    _euclide_push_queue.append({
        "message": req.message, "category": req.category,
        "pushed_at": datetime.utcnow().isoformat(), "read": False,
    })
    return {"status": "queued", "pending": len(_euclide_push_queue)}


@app.get("/euclide/messages")
async def euclide_messages(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    unread = [m for m in _euclide_push_queue if not m["read"]]
    for m in _euclide_push_queue:
        m["read"] = True
    return {"messages": unread, "count": len(unread)}


# ─── Shared context (Supabase-backed) ────────────────────────────────────────
@app.post("/context/set")
async def context_set(req: ContextSetRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    sb_set_context(req.key, req.value, req.source or "unknown")
    return {"status": "ok", "key": req.key}


@app.get("/context/get")
async def context_get(x_api_key: str = Header(...), key: Optional[str] = None):
    verify_key(x_api_key)
    return sb_get_context(key)


@app.delete("/context/clear")
async def context_clear(x_api_key: str = Header(...), key: Optional[str] = None):
    verify_key(x_api_key)
    sb_delete_context(key)
    return {"status": "cleared"}
