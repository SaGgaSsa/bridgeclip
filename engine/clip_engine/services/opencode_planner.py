"""
OpenCode CLI planner - local clip selection without OpenRouter.

Runs ``opencode run`` non-interactively (``--pure --agent build
--format json``) with an exact configurable model, feeds the transcript via
a prompt file (never argv), and extracts only the final response text from
the JSON event stream. Shares the IntelligencePlanner parsing/finalizing so
bounds, overlap and sentence snapping behave like the OpenRouter path.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

OPENCODE_DEFAULT_MODEL = "opencode/muse-spark-1.3-contributor-free"
OPENCODE_MAX_PROMPT_CHARS = 120_000
OPENCODE_MAX_OUTPUT_BYTES = 2 * 1024 * 1024

OPENCODE_MISSING_MESSAGE = (
    "OpenCode CLI is not available. Install opencode and sign in, then retry."
)
OPENCODE_TIMEOUT_MESSAGE = "OpenCode planning timed out"
OPENCODE_INVALID_MESSAGE = "OpenCode returned an unusable planning response"
LOCAL_NO_TRANSCRIPT_MESSAGE = (
    "Local planning needs a transcript and has no vision model"
)


class OpenCodePlannerError(Exception):
    """Fixed-message OpenCode planning failure (no provider details)."""

    def __init__(self, message: str, *, retryable: bool = False):
        self.retryable = retryable
        super().__init__(message)


def build_opencode_args(command: str, model: str) -> list[str]:
    """Fixed CLI shape: no shell, no --auto/--share, exact model only."""
    return [
        command, "run",
        "--pure", "--agent", "build", "--format", "json",
        "--model", model,
    ]


def build_opencode_prompt(
    system_prompt: str,
    transcript_text: str,
    clip_count: int,
    min_duration: int,
    max_duration: int,
    longform: bool = False,
) -> str:
    """Prompt file content: read-only instruction + transcript + JSON contract."""
    if len(transcript_text) > OPENCODE_MAX_PROMPT_CHARS:
        transcript_text = transcript_text[:OPENCODE_MAX_PROMPT_CHARS]
    schema_hint = (
        '{"insights": str, "clips": ['
        '{"start_time": seconds, "end_time": seconds, "summary": "2-7 words", '
        '"scores": {"hook": 0-10, "standalone": 0-10, "arc": 0-10, '
        '"quotability": 0-10, "ending": 0-10}, "tags": [...], "emphasis": [...]'
        + (', "skip": [{"start_time": s, "end_time": s}], '
           '"chapters": [{"time": s, "title": str}], "description": str' if longform else '')
        + '}]}'
    )
    return (
        f"{system_prompt}\n\n"
        "You are running inside a read-only OpenCode session. "
        "Do not edit files, run commands, or use tools that modify or execute "
        "anything. Output text only.\n\n"
        f"Transcript:\n{transcript_text}\n\n"
        f"Select up to {clip_count} clips of {min_duration}-{max_duration} seconds. "
        f"Return ONLY JSON matching this shape: {schema_hint}"
    )


def _reject_failed_tool_use(node: dict) -> None:
    """Reject a tool_use event whose state reports failure.

    Such events surface permission denials, auto-rejected calls and failed
    tool executions even when the CLI exits 0; accepting the accompanying
    text would silently ignore that the model was blocked from doing its job.
    """
    if node.get("type") != "tool_use":
        return
    state = node.get("state")
    if isinstance(state, dict) and str(state.get("status", "")).lower() in ("error", "rejected", "denied"):
        raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)


def _collect_texts(node) -> list[str]:
    """Collect candidate assistant strings from a decoded JSON event."""
    found: list[str] = []
    if isinstance(node, str):
        if "clips" in node or "start_time" in node:
            found.append(node)
    elif isinstance(node, dict):
        _reject_failed_tool_use(node)
        # Direct error/permission markers surface even with exit 0, including
        # auto-rejected tool calls in non-interactive sessions.
        marker = json.dumps(node).lower()
        if any(k in marker for k in ("permission denied", "permission rejected", "tool failed", "tool rejected", "error")):
            # Only treat explicit error objects as failures, not clip text
            # mentioning the word "error".
            if node.get("type") in ("error", "tool_error", "permission_error") or "error" in node:
                raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)
        for key in ("text", "content", "output", "response", "message", "data"):
            if key in node:
                found.extend(_collect_texts(node[key]))
        # Generic walk for nested parts arrays.
        for value in node.values():
            if isinstance(value, (dict, list)):
                found.extend(_collect_texts(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_texts(item))
    return found


def extract_final_response(stdout_text: str) -> str:
    """Extract the final JSON answer from ``opencode --format json`` output.

    Raises OpenCodePlannerError on empty output, permission/tool errors, or
    when no JSON object with clips/insights can be found (even with exit 0).
    """
    if not stdout_text or not stdout_text.strip():
        raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)
    if len(stdout_text.encode("utf-8")) > OPENCODE_MAX_OUTPUT_BYTES:
        raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)
    candidates: list[str] = []
    for line in stdout_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            decoded = json.loads(line)
        except ValueError:
            # A bare JSON blob (not JSON-lines) may still be the answer.
            if "clips" in line and line.lstrip().startswith("{"):
                candidates.append(line)
            continue
        candidates.extend(_collect_texts(decoded))
    # Whole-stdout fallback: single JSON document instead of JSON-lines.
    if not candidates:
        try:
            decoded = json.loads(stdout_text)
            candidates.extend(_collect_texts(decoded))
        except ValueError:
            pass
    for text in reversed(candidates):
        try:
            parsed = json.loads(text)
        except ValueError:
            # Fenced or prefixed JSON: extract the outermost object.
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                continue
            try:
                parsed = json.loads(text[start:end + 1])
            except ValueError:
                continue
        if isinstance(parsed, dict) and isinstance(parsed.get("clips"), list):
            return json.dumps(parsed)
        if isinstance(parsed, list):
            return json.dumps({"insights": "", "clips": parsed})
    raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)


def resolve_opencode_command(command: str) -> str:
    """Resolve the CLI to an executable path before spawning (shell stays off).

    On Windows a bare ``opencode`` resolves to ``opencode.CMD`` through PATH,
    which ``subprocess.run([...], shell=False)`` does not do on its own and
    reports as FileNotFoundError. ``shutil.which`` performs that lookup, so
    resolve here and spawn the resolved path directly.
    """
    from clip_engine.config import is_safe_opencode_command

    if not is_safe_opencode_command(command):
        raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)
    if os.path.isabs(command):
        if not os.path.isfile(command):
            raise OpenCodePlannerError(OPENCODE_MISSING_MESSAGE)
        return command
    resolved = shutil.which(command)
    if not resolved:
        raise OpenCodePlannerError(OPENCODE_MISSING_MESSAGE)
    return resolved


# Scoped config for the child CLI session. A deny-all permission set was
# reproduced to break the exact fork model with FreeTierError 403 even when
# the run uses no tools, so permissions stay on "ask": in this non-interactive
# session (no --auto/--share) tool calls are auto-rejected instead, and any
# rejection surfacing in the event stream is still detected as a failure
# (see _reject_failed_tool_use and the error markers in _collect_texts).
# Written to a temp file per run and pointed at via OPENCODE_CONFIG so a
# permissive user-level config is never inherited.
OPENCODE_RESTRICTIVE_CONFIG = (
    '{"permission": {"*": "ask", "read": "allow", "edit": "ask", "bash": "ask"}}'
)


def write_restrictive_opencode_config(workdir: str) -> str:
    """Write the read-only child config; returns its absolute path."""
    path = os.path.join(workdir, "opencode-config.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(OPENCODE_RESTRICTIVE_CONFIG)
    return path


def build_child_env(config_path: str) -> dict:
    """Child environment: no secrets, no inherited CLI config.

    Drops OPENROUTER_API_KEY (the local path must never expose it) and any
    inherited OPENCODE_CONFIG (which could be permissive), then points
    OPENCODE_CONFIG at the restrictive temp file.
    """
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("OPENCODE_CONFIG", None)
    env["OPENCODE_CONFIG"] = config_path
    return env


def _child_env_without_secrets() -> dict:
    env = dict(os.environ)
    env.pop("OPENROUTER_API_KEY", None)
    env.pop("OPENCODE_CONFIG", None)
    return env


def _run_opencode_sync(
    args: list[str],
    prompt_bytes: bytes,
    timeout: int,
    cwd: str,
    env: dict,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, input=prompt_bytes, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout, shell=False, check=False,
        env=env,
    )


async def run_opencode_prompt(
    prompt_text: str,
    *,
    model: str = OPENCODE_DEFAULT_MODEL,
    command: str = "opencode",
    timeout_seconds: int = 300,
) -> str:
    """Write the prompt to a workdir file and return the final JSON text."""
    if len(prompt_text.encode("utf-8")) > OPENCODE_MAX_PROMPT_CHARS * 4:
        raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)
    validate_opencode_settings(model, command, timeout_seconds)
    resolved = resolve_opencode_command(command)
    args = build_opencode_args(resolved, model)
    prompt_bytes = prompt_text.encode("utf-8")
    with tempfile.TemporaryDirectory(prefix="opencode-prompt-") as workdir:
        prompt_path = Path(workdir) / "prompt.md"
        prompt_path.write_bytes(prompt_bytes)
        config_path = write_restrictive_opencode_config(workdir)
        env = build_child_env(config_path)
        # Prompt goes via stdin/file so the transcript never appears in argv.
        try:
            completed = await asyncio.to_thread(
                _run_opencode_sync, args, prompt_bytes, timeout_seconds, workdir, env,
            )
        except FileNotFoundError:
            raise OpenCodePlannerError(OPENCODE_MISSING_MESSAGE) from None
        except subprocess.TimeoutExpired:
            raise OpenCodePlannerError(OPENCODE_TIMEOUT_MESSAGE, retryable=True) from None
        except OSError:
            raise OpenCodePlannerError(OPENCODE_MISSING_MESSAGE) from None
    if completed.returncode != 0:
        # Never log stderr itself: provider output can carry private data.
        # It is only inspected in memory for the install/login hint.
        logger.warning("opencode exited with code %s", completed.returncode)
        stderr = (completed.stderr or b"").decode("utf-8", "replace")[:500].lower()
        if "not found" in stderr or "no such" in stderr or "login" in stderr or "auth" in stderr:
            raise OpenCodePlannerError(OPENCODE_MISSING_MESSAGE)
        raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)
    stdout = (completed.stdout or b"").decode("utf-8", "replace")
    if len((completed.stdout or b"")) > OPENCODE_MAX_OUTPUT_BYTES:
        raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)
    return extract_final_response(stdout)


def validate_opencode_settings(model: str, command: str, timeout_seconds: int) -> None:
    """Validate CLI settings before spawning (raises OpenCodePlannerError)."""
    from clip_engine.config import is_safe_opencode_command, is_safe_opencode_model

    if not is_safe_opencode_model(model):
        raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)
    if not is_safe_opencode_command(command):
        raise OpenCodePlannerError(OPENCODE_INVALID_MESSAGE)
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 1200:
        raise OpenCodePlannerError(OPENCODE_TIMEOUT_MESSAGE, retryable=True)
