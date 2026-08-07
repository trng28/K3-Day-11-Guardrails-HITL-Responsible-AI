"""Minimal OpenAI Responses API runtime with guardrail plugin callbacks."""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4


DEFAULT_MODEL = "gpt-4o-mini"


@dataclass
class Part:
    text: str | None = None

    @classmethod
    def from_text(cls, *, text: str) -> "Part":
        return cls(text=text)


@dataclass
class Content:
    role: str
    parts: list[Part] = field(default_factory=list)


@dataclass
class LlmResponse:
    content: Content


@dataclass
class InvocationContext:
    user_id: str = "student"
    session_id: str | None = None


class BasePlugin:
    """Provider-neutral callback base used by the lab guardrails."""

    def __init__(self, name: str):
        self.name = name


@dataclass
class OpenAIAgent:
    name: str
    instructions: str
    model: str = DEFAULT_MODEL


@dataclass
class Session:
    id: str
    messages: list[dict[str, str]] = field(default_factory=list)


class OpenAIRunner:
    """Runs an agent and invokes deterministic input/output plugins locally."""

    def __init__(self, *, agent: OpenAIAgent, app_name: str, plugins=None, client=None):
        self.agent = agent
        self.app_name = app_name
        self.plugins = list(plugins or [])
        self._client = client
        self._sessions: dict[str, Session] = {}

    def get_or_create_session(self, session_id: str | None = None) -> Session:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        session = Session(id=session_id or uuid4().hex)
        self._sessions[session.id] = session
        return session

    @staticmethod
    def content_text(content: Content) -> str:
        return "".join(part.text or "" for part in content.parts)

    async def run(self, user_message: str, *, session_id: str | None = None):
        session = self.get_or_create_session(session_id)
        context = InvocationContext(user_id="student", session_id=session.id)
        content = Content(role="user", parts=[Part.from_text(text=user_message)])

        for plugin in self.plugins:
            callback = getattr(plugin, "on_user_message_callback", None)
            if callback is not None:
                blocked = await callback(
                    invocation_context=context, user_message=content
                )
                if blocked is not None:
                    return self.content_text(blocked), session

        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI()

        api_input = [*session.messages, {"role": "user", "content": user_message}]
        response = await self._client.responses.create(
            model=self.agent.model,
            instructions=self.agent.instructions,
            input=api_input,
        )
        response_text = response.output_text or ""
        llm_response = LlmResponse(
            content=Content(role="assistant", parts=[Part.from_text(text=response_text)])
        )

        for plugin in self.plugins:
            callback = getattr(plugin, "after_model_callback", None)
            if callback is not None:
                updated = await callback(
                    callback_context=context, llm_response=llm_response
                )
                if updated is not None:
                    llm_response = updated

        final_text = self.content_text(llm_response.content)
        session.messages.extend([
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": final_text},
        ])
        return final_text, session
