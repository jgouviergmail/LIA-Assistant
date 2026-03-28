"""Service for executing Claude CLI commands on servers.

Supports two execution modes:
- **Local mode** (host="local"): Runs Claude CLI directly via subprocess.
  Used when Claude CLI is installed in the same container as the API.
- **SSH mode** (host=IP/hostname): Runs Claude CLI on a remote server via SSH.
  Used when Claude CLI is on a separate host.

The execution mode is determined automatically from the server config's "host" field.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time
from typing import Any

import structlog
from pydantic import BaseModel, Field

from src.core.config import get_settings
from src.core.constants import (
    DEVOPS_CLAUDE_OUTPUT_FORMAT,
    DEVOPS_DEFAULT_ALLOWED_TOOLS,
    DEVOPS_DEFAULT_SSH_PORT,
)

logger = structlog.get_logger(__name__)

# Sentinel value for local execution (no SSH)
DEVOPS_LOCAL_HOST = "local"


class DevOpsTaskResult(BaseModel):
    """Result from a Claude CLI execution.

    Attributes:
        success: Whether the execution succeeded.
        output: Claude CLI text response.
        session_id: Claude session ID for follow-up via --resume.
        usage: Token usage statistics from Claude CLI.
        duration_ms: Execution duration in milliseconds.
        error: Error message if execution failed.
    """

    success: bool = Field(..., description="Whether the execution succeeded")
    output: str = Field(..., description="Claude CLI text response")
    session_id: str | None = Field(default=None, description="Claude session ID for follow-up")
    usage: dict[str, Any] | None = Field(default=None, description="Token usage statistics")
    duration_ms: int = Field(default=0, description="Execution duration in milliseconds")
    error: str | None = Field(default=None, description="Error message if failed")


class DevOpsService:
    """Service for executing Claude CLI commands locally or on remote servers.

    Manages the full lifecycle of a Claude CLI invocation:
    1. Build the CLI command with appropriate flags and permissions
    2. Execute locally (subprocess) or remotely (SSH)
    3. Parse the JSON output and return structured results
    """

    def _build_claude_args(
        self,
        task: str,
        server_config: dict[str, Any],
        context: str | None = None,
        resume_session: str | None = None,
    ) -> list[str]:
        """Build the claude CLI argument list.

        Args:
            task: Natural language task description.
            server_config: Server configuration dict.
            context: Optional additional context for system prompt.
            resume_session: Optional session ID to resume.

        Returns:
            List of CLI arguments for claude command.
        """
        allowed_tools = server_config.get("allowed_claude_tools", DEVOPS_DEFAULT_ALLOWED_TOOLS)
        disallowed_tools = server_config.get("disallowed_claude_tools", [])

        args = [
            "-p",
            task,
            "--allowedTools",
            ",".join(allowed_tools),
            "--output-format",
            DEVOPS_CLAUDE_OUTPUT_FORMAT,
        ]

        if disallowed_tools:
            args.extend(["--disallowedTools", ",".join(disallowed_tools)])

        if resume_session:
            args.extend(["--resume", resume_session])

        if context:
            args.extend(["--append-system-prompt", context])

        return args

    def _build_shell_command(
        self,
        task: str,
        server_config: dict[str, Any],
        context: str | None = None,
        resume_session: str | None = None,
    ) -> str:
        """Build a shell command string for SSH execution.

        Args:
            task: Natural language task description.
            server_config: Server configuration dict.
            context: Optional additional context for system prompt.
            resume_session: Optional session ID to resume.

        Returns:
            Shell command string ready for SSH execution.
        """
        working_dir = server_config.get("working_directory", "/opt/claude-workspace")
        args = self._build_claude_args(task, server_config, context, resume_session)

        # Shell-escape each argument for SSH transport
        parts = [f"cd {shlex.quote(working_dir)}", "&&", "claude"]
        parts.extend(shlex.quote(arg) for arg in args)

        return " ".join(parts)

    async def execute_claude_task(
        self,
        server_config: dict[str, Any],
        task: str,
        context: str | None = None,
        resume_session: str | None = None,
        timeout: int | None = None,
        max_output_chars: int | None = None,
        side_channel_queue: asyncio.Queue | None = None,
    ) -> DevOpsTaskResult:
        """Execute a Claude CLI task locally or on a remote server.

        Automatically selects local (subprocess) or remote (SSH) execution
        based on the server config's "host" field:
        - host="local" → local subprocess execution
        - host=IP/hostname → SSH execution

        Args:
            server_config: Server configuration dict from settings.
            task: Natural language task description.
            context: Optional additional context.
            resume_session: Optional session ID to resume.
            timeout: Command execution timeout in seconds.
            max_output_chars: Maximum output characters before truncation.
            side_channel_queue: SSE side channel for streaming progress events.

        Returns:
            DevOpsTaskResult with Claude's response and metadata.
        """
        host = server_config.get("host", DEVOPS_LOCAL_HOST)

        if host == DEVOPS_LOCAL_HOST:
            return await self._execute_local(
                server_config=server_config,
                task=task,
                context=context,
                resume_session=resume_session,
                timeout=timeout,
                max_output_chars=max_output_chars,
                side_channel_queue=side_channel_queue,
            )
        else:
            return await self._execute_ssh(
                server_config=server_config,
                task=task,
                context=context,
                resume_session=resume_session,
                timeout=timeout,
                max_output_chars=max_output_chars,
            )

    def _emit_progress(
        self,
        queue: asyncio.Queue | None,
        message: str,
        detail: str = "",
    ) -> None:
        """Emit a progress event to the SSE side channel.

        Fire-and-forget. Never raises.

        Args:
            queue: Side channel queue (None-safe).
            message: Human-readable progress message.
            detail: Optional detail (e.g. command being run).
        """
        if queue is None:
            logger.debug("devops_progress_no_queue", message=message)
            return
        try:
            from src.domains.agents.api.schemas import ChatStreamChunk

            # Use execution_step type — already handled by frontend
            display_message = f"{message}: {detail}" if detail else message
            queue.put_nowait(
                ChatStreamChunk(
                    type="execution_step",
                    content=display_message,
                    metadata={
                        "emoji": "🖥️",
                        "i18n_key": "claude_server_task",
                        "label": display_message,
                        "tool_name": "claude_server_task_tool",
                    },
                )
            )
            logger.debug("devops_progress_emitted", message=message, detail=detail[:100])
        except Exception as e:
            logger.debug("devops_progress_emit_failed", error=str(e), message=message)

    def _parse_stream_event(self, line: str) -> tuple[str, str] | None:
        """Parse a Claude CLI stream-json line into a progress message.

        Args:
            line: A single JSON line from Claude CLI stream output.

        Returns:
            Tuple of (message, detail) for progress, or None to skip.
        """
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None

        event_type = event.get("type")

        if event_type == "assistant":
            # Claude is thinking or calling a tool
            message = event.get("message", {})
            content = message.get("content", [])
            for block in content:
                if block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    cmd = tool_input.get("command", tool_input.get("pattern", ""))
                    desc = tool_input.get("description", "")
                    label = desc or cmd
                    return f"🔧 {tool_name}", label[:200] if label else ""
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        return "💭 Analyse en cours", text[:200]
            return None

        if event_type == "system" and event.get("subtype") == "init":
            return "🚀 Claude CLI démarré", ""

        return None

    async def _execute_local(
        self,
        server_config: dict[str, Any],
        task: str,
        context: str | None = None,
        resume_session: str | None = None,
        timeout: int | None = None,
        max_output_chars: int | None = None,
        side_channel_queue: asyncio.Queue | None = None,
    ) -> DevOpsTaskResult:
        """Execute Claude CLI locally via subprocess with streaming progress.

        Uses --output-format stream-json --verbose to get real-time events,
        emitting progress to the SSE side channel. Falls back to json mode
        if streaming is not available.

        Args:
            server_config: Server configuration dict.
            task: Natural language task description.
            context: Optional additional context.
            resume_session: Optional session ID to resume.
            timeout: Execution timeout in seconds.
            max_output_chars: Maximum output characters.
            side_channel_queue: SSE side channel for progress events.

        Returns:
            DevOpsTaskResult with Claude's response.
        """
        settings = get_settings()
        timeout = timeout or settings.devops_command_timeout
        max_output_chars = max_output_chars or settings.devops_max_output_chars
        working_dir = server_config.get("working_directory", "/opt/claude-workspace")

        # Build args with stream-json format for real-time progress
        allowed_tools = server_config.get("allowed_claude_tools", DEVOPS_DEFAULT_ALLOWED_TOOLS)
        disallowed_tools = server_config.get("disallowed_claude_tools", [])

        stream_args = [
            "-p",
            task,
            "--allowedTools",
            ",".join(allowed_tools),
            "--output-format",
            "stream-json",
            "--verbose",
        ]

        if disallowed_tools:
            stream_args.extend(["--disallowedTools", ",".join(disallowed_tools)])

        if resume_session:
            stream_args.extend(["--resume", resume_session])

        if context:
            stream_args.extend(["--append-system-prompt", context])

        start_time = time.monotonic()

        try:
            logger.info(
                "devops_local_executing",
                working_directory=working_dir,
                task_preview=task[:100],
                streaming=side_channel_queue is not None,
            )

            self._emit_progress(side_channel_queue, "🚀 Investigation en cours...", task[:100])

            process = await asyncio.create_subprocess_exec(
                "claude",
                *stream_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )

            # Read stdout line by line for streaming progress
            result_line: str | None = None
            all_lines: list[str] = []

            async def _read_stream() -> None:
                nonlocal result_line
                assert process.stdout is not None
                async for raw_line in process.stdout:
                    line = raw_line.decode().strip()
                    if not line:
                        continue
                    all_lines.append(line)

                    # Emit progress for intermediate events
                    progress = self._parse_stream_event(line)
                    if progress:
                        self._emit_progress(side_channel_queue, progress[0], progress[1])

                    # Capture the final result line
                    try:
                        parsed = json.loads(line)
                        if parsed.get("type") == "result":
                            result_line = line
                    except json.JSONDecodeError:
                        pass

            await asyncio.wait_for(_read_stream(), timeout=timeout)
            await process.wait()

            duration_ms = int((time.monotonic() - start_time) * 1000)

            if process.returncode != 0:
                stderr_bytes = await process.stderr.read() if process.stderr else b""
                stderr_output = stderr_bytes.decode().strip()
                logger.warning(
                    "devops_claude_cli_error",
                    mode="local",
                    exit_status=process.returncode,
                    stderr=stderr_output[:500],
                )
                return DevOpsTaskResult(
                    success=False,
                    output="",
                    error=f"Exit code {process.returncode}: {stderr_output[:500]}",
                    duration_ms=duration_ms,
                )

            # Parse the result line (last "type":"result" event)
            if result_line:
                return self._parse_claude_output(result_line, duration_ms, max_output_chars)

            # Fallback: join all output
            raw_output = "\n".join(all_lines)
            return self._parse_claude_output(raw_output, duration_ms, max_output_chars)

        except TimeoutError:
            if process and process.returncode is None:
                process.kill()
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning("devops_command_timeout", mode="local", timeout=timeout)
            self._emit_progress(side_channel_queue, "⏱️ Timeout", f"Dépassement de {timeout}s")
            return DevOpsTaskResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout}s",
                duration_ms=duration_ms,
            )
        except FileNotFoundError:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error("devops_claude_cli_not_found", mode="local")
            return DevOpsTaskResult(
                success=False,
                output="",
                error="Claude CLI not found. Ensure it is installed.",
                duration_ms=duration_ms,
            )

    async def _execute_ssh(
        self,
        server_config: dict[str, Any],
        task: str,
        context: str | None = None,
        resume_session: str | None = None,
        timeout: int | None = None,
        max_output_chars: int | None = None,
    ) -> DevOpsTaskResult:
        """Execute Claude CLI on a remote server via SSH.

        Args:
            server_config: Server configuration dict.
            task: Natural language task description.
            context: Optional additional context.
            resume_session: Optional session ID to resume.
            timeout: Execution timeout in seconds.
            max_output_chars: Maximum output characters.

        Returns:
            DevOpsTaskResult with Claude's response.
        """
        import asyncssh

        settings = get_settings()
        timeout = timeout or settings.devops_command_timeout
        max_output_chars = max_output_chars or settings.devops_max_output_chars

        host = server_config["host"]
        port = server_config.get("port", DEVOPS_DEFAULT_SSH_PORT)
        username = server_config["username"]
        ssh_key_path = server_config.get("ssh_key_path")

        command = self._build_shell_command(task, server_config, context, resume_session)

        start_time = time.monotonic()

        try:
            connect_kwargs: dict[str, Any] = {
                "host": host,
                "port": port,
                "username": username,
                "known_hosts": None,
                "connect_timeout": settings.devops_ssh_timeout,
            }
            if ssh_key_path:
                connect_kwargs["client_keys"] = [ssh_key_path]

            logger.info(
                "devops_ssh_connecting",
                host=host,
                port=port,
                username=username,
                task_preview=task[:100],
            )

            async with asyncssh.connect(**connect_kwargs) as conn:
                result = await asyncio.wait_for(
                    conn.run(command, check=False),
                    timeout=timeout,
                )

            duration_ms = int((time.monotonic() - start_time) * 1000)

            if result.exit_status != 0:
                stderr_raw = result.stderr or ""
                stderr_output = stderr_raw if isinstance(stderr_raw, str) else stderr_raw.decode()
                stderr_output = stderr_output.strip()
                logger.warning(
                    "devops_claude_cli_error",
                    mode="ssh",
                    host=host,
                    exit_status=result.exit_status,
                    stderr=stderr_output[:500],
                )
                return DevOpsTaskResult(
                    success=False,
                    output="",
                    error=f"Exit code {result.exit_status}: {stderr_output[:500]}",
                    duration_ms=duration_ms,
                )

            stdout_raw = result.stdout or ""
            raw_output = stdout_raw if isinstance(stdout_raw, str) else stdout_raw.decode()
            raw_output = raw_output.strip()
            return self._parse_claude_output(raw_output, duration_ms, max_output_chars)

        except asyncssh.Error as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.exception("devops_ssh_connection_error", host=host, error=str(e))
            return DevOpsTaskResult(
                success=False,
                output="",
                error=f"SSH connection failed: {e}",
                duration_ms=duration_ms,
            )
        except TimeoutError:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning("devops_command_timeout", mode="ssh", host=host, timeout=timeout)
            return DevOpsTaskResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout}s",
                duration_ms=duration_ms,
            )

    def _parse_claude_output(
        self,
        raw_output: str,
        duration_ms: int,
        max_output_chars: int,
    ) -> DevOpsTaskResult:
        """Parse Claude CLI JSON output into DevOpsTaskResult.

        Args:
            raw_output: Raw stdout from Claude CLI.
            duration_ms: Execution duration.
            max_output_chars: Max chars before truncation.

        Returns:
            Parsed DevOpsTaskResult.
        """
        try:
            data = json.loads(raw_output)
            text_result = data.get("result", raw_output)

            if len(text_result) > max_output_chars:
                text_result = (
                    text_result[:max_output_chars]
                    + f"\n\n[Output truncated at {max_output_chars} characters]"
                )

            return DevOpsTaskResult(
                success=True,
                output=text_result,
                session_id=data.get("session_id"),
                usage=data.get("usage"),
                duration_ms=duration_ms,
            )
        except json.JSONDecodeError:
            output = raw_output[:max_output_chars] if raw_output else "No output"
            return DevOpsTaskResult(
                success=True,
                output=output,
                duration_ms=duration_ms,
            )
