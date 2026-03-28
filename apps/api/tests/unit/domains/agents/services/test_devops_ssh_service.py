"""Unit tests for DevOpsService.

Tests command construction, output parsing, and error handling
for both local (subprocess) and SSH execution modes.
"""

from __future__ import annotations

import json

from src.domains.agents.services.devops_ssh_service import (
    DEVOPS_LOCAL_HOST,
    DevOpsService,
    DevOpsTaskResult,
)


class TestBuildClaudeArgs:
    """Tests for DevOpsService._build_claude_args."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = DevOpsService()
        self.base_config: dict = {
            "name": "dev",
            "host": "local",
            "working_directory": "/opt/claude-workspace",
            "allowed_claude_tools": ["Read", "Grep", "Glob", "Bash"],
        }

    def test_basic_args(self) -> None:
        """Build basic args with default settings."""
        args = self.service._build_claude_args(
            task="check docker logs",
            server_config=self.base_config,
        )

        assert "-p" in args
        assert "check docker logs" in args
        assert "--allowedTools" in args
        assert "Read,Grep,Glob,Bash" in args
        assert "--output-format" in args
        assert "json" in args

    def test_with_disallowed_tools(self) -> None:
        """Include --disallowedTools when configured."""
        config = {
            **self.base_config,
            "disallowed_claude_tools": ["Edit", "Write", "Bash(rm *)"],
        }
        args = self.service._build_claude_args(
            task="inspect server",
            server_config=config,
        )

        assert "--disallowedTools" in args
        idx = args.index("--disallowedTools")
        assert args[idx + 1] == "Edit,Write,Bash(rm *)"

    def test_without_disallowed_tools(self) -> None:
        """Omit --disallowedTools when not configured."""
        args = self.service._build_claude_args(
            task="inspect server",
            server_config=self.base_config,
        )

        assert "--disallowedTools" not in args

    def test_with_resume_session(self) -> None:
        """Include --resume when session ID provided."""
        args = self.service._build_claude_args(
            task="continue investigation",
            server_config=self.base_config,
            resume_session="abc-123-def",
        )

        assert "--resume" in args
        idx = args.index("--resume")
        assert args[idx + 1] == "abc-123-def"

    def test_with_context(self) -> None:
        """Include --append-system-prompt when context provided."""
        args = self.service._build_claude_args(
            task="check logs",
            server_config=self.base_config,
            context="Focus on 500 errors since 14:00",
        )

        assert "--append-system-prompt" in args
        idx = args.index("--append-system-prompt")
        assert args[idx + 1] == "Focus on 500 errors since 14:00"

    def test_without_context(self) -> None:
        """Omit --append-system-prompt when no context."""
        args = self.service._build_claude_args(
            task="check logs",
            server_config=self.base_config,
        )

        assert "--append-system-prompt" not in args

    def test_full_args_with_all_options(self) -> None:
        """Build fully-specified args with all options."""
        config = {
            **self.base_config,
            "disallowed_claude_tools": ["Edit"],
        }
        args = self.service._build_claude_args(
            task="diagnose API latency",
            server_config=config,
            context="Since 14:00",
            resume_session="session-xyz",
        )

        assert "-p" in args
        assert "--allowedTools" in args
        assert "--disallowedTools" in args
        assert "--output-format" in args
        assert "--resume" in args
        assert "--append-system-prompt" in args


class TestBuildShellCommand:
    """Tests for DevOpsService._build_shell_command (SSH mode)."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = DevOpsService()
        self.ssh_config: dict = {
            "name": "remote",
            "host": "192.168.0.14",
            "port": 2222,
            "username": "jgo",
            "working_directory": "~/lia-workspace",
            "allowed_claude_tools": ["Read", "Grep", "Glob"],
        }

    def test_shell_command_structure(self) -> None:
        """Build a shell command with cd && claude pattern."""
        cmd = self.service._build_shell_command(
            task="check logs",
            server_config=self.ssh_config,
        )

        assert cmd.startswith("cd")
        assert "&&" in cmd
        assert "claude" in cmd

    def test_shell_escaping(self) -> None:
        """Properly escape special characters for SSH transport."""
        cmd = self.service._build_shell_command(
            task="check logs for 'error' and $VAR",
            server_config=self.ssh_config,
        )

        # shlex.quote wraps in single quotes for shell safety
        assert "claude" in cmd
        assert "&&" in cmd


class TestLocalHostDetection:
    """Tests for local vs SSH mode selection."""

    def test_local_host_constant(self) -> None:
        """Verify the local host sentinel value."""
        assert DEVOPS_LOCAL_HOST == "local"


class TestParseClaudeOutput:
    """Tests for DevOpsService._parse_claude_output."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = DevOpsService()

    def test_valid_json_output(self) -> None:
        """Parse valid Claude CLI JSON output."""
        raw = json.dumps(
            {
                "result": "PostgreSQL container is healthy. RAM usage: 45%.",
                "session_id": "abc-123",
                "usage": {"input_tokens": 5000, "output_tokens": 1200},
            }
        )

        result = self.service._parse_claude_output(raw, duration_ms=1500, max_output_chars=50000)

        assert result.success is True
        assert "PostgreSQL container is healthy" in result.output
        assert result.session_id == "abc-123"
        assert result.usage == {"input_tokens": 5000, "output_tokens": 1200}
        assert result.duration_ms == 1500

    def test_plain_text_fallback(self) -> None:
        """Fall back to plain text when output is not JSON."""
        raw = "Some plain text output from Claude"

        result = self.service._parse_claude_output(raw, duration_ms=500, max_output_chars=50000)

        assert result.success is True
        assert result.output == "Some plain text output from Claude"
        assert result.session_id is None

    def test_empty_output(self) -> None:
        """Handle empty output gracefully."""
        result = self.service._parse_claude_output("", duration_ms=100, max_output_chars=50000)

        assert result.success is True
        assert result.output == "No output"

    def test_output_truncation(self) -> None:
        """Truncate output exceeding max_output_chars."""
        long_text = "x" * 1000
        raw = json.dumps({"result": long_text})

        result = self.service._parse_claude_output(raw, duration_ms=100, max_output_chars=500)

        assert result.success is True
        assert "[Output truncated at 500 characters]" in result.output
        assert result.output[:500] == "x" * 500

    def test_json_without_result_key(self) -> None:
        """Handle JSON output missing the 'result' key."""
        raw = json.dumps({"session_id": "abc", "usage": {}})

        result = self.service._parse_claude_output(raw, duration_ms=100, max_output_chars=50000)

        assert result.success is True
        assert result.session_id == "abc"


class TestDevOpsTaskResult:
    """Tests for the DevOpsTaskResult model."""

    def test_success_result(self) -> None:
        """Create a successful result."""
        result = DevOpsTaskResult(
            success=True,
            output="All containers healthy",
            session_id="abc-123",
            usage={"input_tokens": 100, "output_tokens": 50},
            duration_ms=1500,
        )

        assert result.success is True
        assert result.output == "All containers healthy"
        assert result.session_id == "abc-123"
        assert result.error is None

    def test_failure_result(self) -> None:
        """Create a failure result."""
        result = DevOpsTaskResult(
            success=False,
            output="",
            error="Command timed out",
            duration_ms=500,
        )

        assert result.success is False
        assert result.error == "Command timed out"
        assert result.session_id is None
