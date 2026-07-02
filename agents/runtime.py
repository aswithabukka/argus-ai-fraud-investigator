"""Thin, transparent wrapper around the ADK run loop.

Every agent in Argus is an ADK `LlmAgent`. This module runs one agent to
completion on a single prompt and returns:
  - the final text (JSON when the agent has an `output_schema`), and
  - the list of tool calls it made (name + args), for the audit trail.

Keeping this explicit — rather than hiding it behind a multi-agent framework
graph — is deliberate: the orchestration logic lives in plain Python
(`orchestrator.py`) where it can be read and explained.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.genai import types
from google.genai.errors import ClientError, ServerError
from mcp import StdioServerParameters

import config

_APP = "argus"
_USER = "analyst"

# Free-tier Gemini occasionally returns transient 503 (high demand) or 429 (rate
# limit). These are not bugs — retry with backoff before giving up. For 429s the
# API usually tells us how long to wait ("Please retry in 12.3s"); honor that.
_MAX_ATTEMPTS = 6
_TRANSIENT_CODES = {429, 500, 503}
_BACKOFF_CAP = 65
_RETRY_HINT_RE = re.compile(r"retry in ([0-9.]+)s")


def load_prompt(name: str) -> str:
    return (config.PROMPTS_DIR / f"{name}.md").read_text()


def make_mcp_toolset() -> McpToolset:
    """Connect to the local Argus MCP server (tools/mcp_server.py) over stdio."""
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,  # same interpreter — works in venv, Kaggle, Docker
                args=["-m", "tools.mcp_server"],
                cwd=str(config.ROOT),
            )
        )
    )


def _is_transient(err: Exception) -> bool:
    code = getattr(err, "code", None)
    return isinstance(err, (ServerError, ClientError)) and code in _TRANSIENT_CODES


async def _run_once(agent: LlmAgent, prompt: str, session_id: str) -> tuple[str, list[dict]]:
    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=_APP, session_service=session_service)
    await session_service.create_session(app_name=_APP, user_id=_USER, session_id=session_id)

    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    tool_calls: list[dict] = []

    async for event in runner.run_async(
        user_id=_USER, session_id=session_id, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    tool_calls.append({"name": fc.name, "args": dict(fc.args or {})})
        if event.is_final_response() and event.content and event.content.parts:
            text = event.content.parts[0].text
            if text:
                final_text = text

    return final_text, tool_calls


async def run_agent(agent: LlmAgent, prompt: str, session_id: str) -> tuple[str, list[dict]]:
    """Run `agent` on `prompt`; return (final_text, tool_calls).

    Retries transient Gemini errors (429/500/503) with exponential backoff, and
    re-runs on the same session_id suffixed by the attempt so each retry is clean.
    """
    last_err: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return await _run_once(agent, prompt, f"{session_id}-a{attempt}")
        except Exception as e:  # noqa: BLE001 — inspect then decide
            if not _is_transient(e) or attempt == _MAX_ATTEMPTS - 1:
                raise
            last_err = e
            backoff = min(_BACKOFF_CAP, 5 * (2 ** attempt))  # 5,10,20,40,65,65
            hint = _RETRY_HINT_RE.search(str(e))
            wait = min(_BACKOFF_CAP, float(hint.group(1)) + 1) if hint else backoff
            print(f"  [retry] {agent.name}: transient {getattr(e, 'code', '?')} — "
                  f"backing off {wait:.0f}s (attempt {attempt + 1}/{_MAX_ATTEMPTS})")
            await asyncio.sleep(wait)
    raise last_err  # unreachable, but keeps type-checkers happy


def parse_json_output(text: str):
    """Parse an agent's JSON output, tolerating markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
