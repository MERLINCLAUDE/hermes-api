import os
import anthropic
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from agents.daily_plan import run_daily_plan
from agents.notion_context import fetch_notion_context
from agents.social_stats import fetch_social_stats
from agents.content_strategy import run_content_strategy
from agents.life_coach import run_life_coach
from agents.security_monitor import run_security_monitor

app = FastAPI(title="Hermès — 344 Agent Orchestrator", version="2.0.0")

HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
client = anthropic.Anthropic()


class DispatchRequest(BaseModel):
    intent: str
    context: Optional[str] = ""
    task: Optional[str] = ""
    source: Optional[str] = "unknown"


class DispatchResponse(BaseModel):
    result: str
    intent: str
    source: str


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
