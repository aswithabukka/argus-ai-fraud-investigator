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

import json
import sys

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

import config

_APP = "argus"
_USER = "analyst"


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


async def run_agent(agent: LlmAgent, prompt: str, session_id: str) -> tuple[str, list[dict]]:
    """Run `agent` on `prompt`; return (final_text, tool_calls)."""
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


def parse_json_output(text: str):
    """Parse an agent's JSON output, tolerating markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())
