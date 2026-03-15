from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from janitor.ai.provider import AIProvider, AIResponse, ToolCall
from janitor.ai.tools import READ_ONLY_TOOLS, TOOL_DEFINITIONS
from janitor.models.issue import Issue, IssueStatus
from janitor.models.metrics import SystemSnapshot

if TYPE_CHECKING:
    from janitor.actions.executor import ActionExecutor

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 10

SYSTEM_PROMPT = """\
You are Janitor, a Proxmox server monitoring and debugging AI agent.

Your job is to:
1. Analyze server metrics, logs, and status information
2. Identify the root cause of issues
3. Suggest or execute fixes based on your available tools

When analyzing issues:
- Be specific about what you observe
- Correlate metrics with log entries when possible
- Rank potential causes by likelihood
- Suggest the least disruptive fix first

When suggesting actions:
- Explain what the action will do and why
- Note any risks or side effects
- Prefer restarting services over rebooting nodes
- Only suggest run_ssh_command for diagnostic commands, not destructive ones

Format your analysis clearly with sections:
**Problem**: What's happening
**Root Cause**: Most likely cause
**Recommended Action**: What to do about it
"""


class AIDebugger:
    def __init__(
        self,
        provider: AIProvider,
        executor: ActionExecutor,
    ) -> None:
        self._provider = provider
        self._executor = executor

    async def analyze_issue(self, issue: Issue, snapshot: SystemSnapshot) -> Issue:
        context = self._build_context(issue, snapshot)
        messages: list[dict[str, Any]] = [{"role": "user", "content": context}]

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self._provider.chat(
                messages=messages,
                tools=TOOL_DEFINITIONS,
                system=SYSTEM_PROMPT,
            )

            if not response.tool_calls:
                issue.ai_analysis = response.content
                self._extract_suggested_action(issue, response.content)
                if issue.ai_suggested_action and issue.status == IssueStatus.OPEN:
                    issue.status = IssueStatus.AWAITING_APPROVAL
                break

            # Handle tool calls
            messages.append(self._format_assistant_message(response))
            for tc in response.tool_calls:
                result = await self._execute_tool(tc)
                messages.append(self._format_tool_result(tc, result))

        issue.touch()
        return issue

    async def interactive_session(self, user_query: str, snapshot: SystemSnapshot) -> str:
        context = f"Current system state:\n{snapshot.summary_text()}\n\nUser question: {user_query}"
        messages: list[dict[str, Any]] = [{"role": "user", "content": context}]

        for _ in range(MAX_TOOL_ROUNDS):
            response = await self._provider.chat(
                messages=messages,
                tools=TOOL_DEFINITIONS,
                system=SYSTEM_PROMPT,
            )

            if not response.tool_calls:
                return response.content

            messages.append(self._format_assistant_message(response))
            for tc in response.tool_calls:
                result = await self._execute_tool(tc)
                messages.append(self._format_tool_result(tc, result))

        return "Reached maximum tool call depth. Here's what I found so far."

    async def _execute_tool(self, tc: ToolCall) -> str:
        if tc.name in READ_ONLY_TOOLS:
            # Read-only tools bypass the executor
            return await self._executor.execute_read_only(tc.name, tc.arguments)
        else:
            result = await self._executor.execute(tc.name, tc.arguments, auto=True)
            return result.message

    def _build_context(self, issue: Issue, snapshot: SystemSnapshot) -> str:
        parts = [
            f"## Alert: {issue.title}",
            f"**Server**: {issue.server_name}",
            f"**Severity**: {issue.severity.value}",
            f"**Description**: {issue.description}",
            "",
            "## Current System Snapshot",
            snapshot.summary_text(),
        ]

        if issue.log_excerpt:
            parts.extend(["", "## Recent Logs (last lines)", issue.log_excerpt[:3000]])

        if issue.metrics_snapshot:
            parts.extend(
                ["", "## Metrics at Alert Time", json.dumps(issue.metrics_snapshot, indent=2)]
            )

        return "\n".join(parts)

    def _format_assistant_message(self, response: AIResponse) -> dict[str, Any]:
        """Format for the provider's expected message format."""
        # This works for both Anthropic and OpenAI message formats
        content: list[dict[str, Any]] = []
        if response.content:
            content.append({"type": "text", "text": response.content})
        for tc in response.tool_calls:
            content.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                }
            )
        return {"role": "assistant", "content": content}

    def _format_tool_result(self, tc: ToolCall, result: str) -> dict[str, Any]:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result,
                }
            ],
        }

    def _extract_suggested_action(self, issue: Issue, analysis: str) -> None:
        """Try to identify if the AI suggested a specific tool action."""
        analysis_lower = analysis.lower()
        if "restart_vm" in analysis_lower or "reboot" in analysis_lower and "vm" in analysis_lower:
            issue.ai_suggested_action = "restart_vm"
            issue.action_type = "restart_vm"
        elif "restart" in analysis_lower and "service" in analysis_lower:
            issue.ai_suggested_action = "restart_service"
            issue.action_type = "restart_service"
