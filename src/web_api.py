"""FastAPI application for the live VinBank guardrails demo."""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.agent import create_protected_agent
from assignment.audit_log import AuditLogPlugin
from assignment.monitoring import MonitoringAlert
from assignment.pipeline import build_production_plugins
from assignment.rate_limiter import RateLimitPlugin
from guardrails.input_guardrails import InputGuardrailPlugin
from guardrails.output_guardrails import OutputGuardrailPlugin
from hitl.hitl import ConfidenceRouter


load_dotenv()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12_000)
    session_id: str | None = Field(default=None, max_length=128)
    user_id: str = Field(default="demo-user", min_length=1, max_length=128)
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)
    action_type: str = Field(default="general", min_length=1, max_length=128)


class ChatResponse(BaseModel):
    request_id: str
    session_id: str
    response: str
    blocked: bool
    layer: str | None
    latency_ms: float
    hitl: dict
    metrics: dict


@asynccontextmanager
async def lifespan(app: FastAPI):
    use_judge = os.getenv("USE_LLM_JUDGE", "false").lower() in {"1", "true", "yes"}
    plugins = build_production_plugins(use_llm_judge=use_judge)
    agent, runner = create_protected_agent(plugins)
    app.state.agent = agent
    app.state.runner = runner
    app.state.plugins = plugins
    app.state.audit = AuditLogPlugin()
    app.state.monitor = MonitoringAlert()
    app.state.router = ConfidenceRouter()
    yield


app = FastAPI(
    title="VinBank Guardrails Demo API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://localhost:8080"
    ).split(",")],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _plugins():
    rate = next(p for p in app.state.plugins if isinstance(p, RateLimitPlugin))
    input_guard = next(
        p for p in app.state.plugins if isinstance(p, InputGuardrailPlugin)
    )
    output_guard = next(
        p for p in app.state.plugins if isinstance(p, OutputGuardrailPlugin)
    )
    return rate, input_guard, output_guard


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "provider": "openai",
        "model": app.state.agent.model,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    audit: AuditLogPlugin = app.state.audit
    monitor: MonitoringAlert = app.state.monitor
    request_id = audit.record_input(user_id=payload.user_id, text=payload.message)
    started = time.perf_counter()
    rate, input_guard, output_guard = _plugins()
    before = {
        "rate": rate.blocked_count,
        "input": input_guard.blocked_count,
        "output": output_guard.blocked_count,
        "redacted": output_guard.redacted_count,
        "judge_checks": output_guard.total_count,
    }

    try:
        response, session = await app.state.runner.run(
            payload.message,
            session_id=payload.session_id,
            user_id=payload.user_id,
        )
    except Exception as exc:
        audit.record_output(
            user_id=payload.user_id,
            text="Model provider error",
            blocked=True,
            layer="provider_error",
            request_id=request_id,
            metadata={"error_type": type(exc).__name__},
        )
        raise HTTPException(status_code=502, detail="Model provider unavailable") from exc

    after = {
        "rate": rate.blocked_count,
        "input": input_guard.blocked_count,
        "output": output_guard.blocked_count,
        "redacted": output_guard.redacted_count,
        "judge_checks": output_guard.total_count,
    }
    if after["rate"] > before["rate"]:
        blocked, layer = True, "rate_limiter"
        monitor.rate_limit_hits += 1
    elif after["input"] > before["input"]:
        blocked, layer = True, "input_guardrail"
    elif after["output"] > before["output"]:
        blocked, layer = True, "llm_judge"
    elif after["redacted"] > before["redacted"]:
        blocked, layer = True, "output_guardrail"
    else:
        blocked, layer = False, None

    monitor.total_requests += 1
    monitor.blocked_requests += int(blocked)
    if output_guard.use_llm_judge:
        monitor.judge_checks += after["judge_checks"] - before["judge_checks"]
        monitor.judge_fails += after["output"] - before["output"]
    monitor.check_metrics()

    hitl = app.state.router.route(
        response,
        confidence=payload.confidence,
        action_type=payload.action_type,
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    audit.record_output(
        user_id=payload.user_id,
        text=response,
        blocked=blocked,
        layer=layer or "model",
        request_id=request_id,
        reviewer_decision="pending" if hitl.requires_human else "not_required",
        action=payload.action_type,
        action_decision=hitl.action,
        metadata={"confidence": payload.confidence},
    )
    return ChatResponse(
        request_id=request_id,
        session_id=session.id,
        response=response,
        blocked=blocked,
        layer=layer,
        latency_ms=latency_ms,
        hitl={
            "action": hitl.action,
            "priority": hitl.priority,
            "requires_human": hitl.requires_human,
            "reason": hitl.reason,
        },
        metrics=monitor.snapshot(),
    )


@app.get("/api/metrics")
async def metrics():
    app.state.monitor.check_metrics()
    return app.state.monitor.snapshot()


@app.get("/api/audit/{request_id}")
async def audit_by_request(request_id: str):
    records = app.state.audit.find_by_request_id(request_id)
    if not records:
        raise HTTPException(status_code=404, detail="request_id not found")
    return {"request_id": request_id, "records": records}
