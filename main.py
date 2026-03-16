import os
import anthropic
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

from agents.daily_plan import run_daily_plan
from agents.notion_context import fetch_notion_context
from agents.social_stats import fetch_social_stats

app = FastAPI(title="Hermès — 344 Agent Orchestrator", version="1.0.0")

HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "")
client = anthropic.Anthropic()


class DispatchRequest(BaseModel):
    intent: str
    context: Optional[str] = ""
    source: Optional[str] = "unknown"  # archimede | thales | euclide


class DispatchResponse(BaseModel):
    result: str
    intent: str
    source: str


def verify_key(x_api_key: str = Header(...)):
    if HERMES_API_KEY and x_api_key != HERMES_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


INTENT_HANDLERS = {
    "daily_plan": lambda ctx: run_daily_plan(client, ctx),
    "notion_context": lambda ctx: fetch_notion_context(),
    "social_stats": lambda ctx: fetch_social_stats(),
}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes"}


@app.post("/dispatch", response_model=DispatchResponse)
async def dispatch(req: DispatchRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)

    handler = INTENT_HANDLERS.get(req.intent)
    if not handler:
        raise HTTPException(status_code=400, detail=f"Unknown intent: {req.intent}")

    try:
        result = handler(req.context)
        return DispatchResponse(result=result, intent=req.intent, source=req.source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/intents")
async def list_intents(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return {"intents": list(INTENT_HANDLERS.keys())}
