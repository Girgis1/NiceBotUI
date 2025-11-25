"""Friendly dashboard log translations for NiceBot UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class LogEntry:
    """Structured entry returned by ``translate_worker_message``."""

    level: str
    message: str
    action: Optional[str] = None
    code: Optional[str] = None
    fatal: bool = False
    dedupe: bool = True


def translate_worker_message(level: str, message: str) -> Optional[LogEntry]:
    """Convert low-level worker logs into friendly dashboard messages."""

    if not message:
        return None

    raw = message.strip()
    if not raw:
        return None

    text = raw.replace("[", "").replace("]", "")
    lowered = text.lower()
    level = (level or "info").lower()

    # Noise that the dashboard should ignore.
    skip_signals = (
        "loop iteration",
        "→ model",
        "starting episode",
        "pausing shared camera streams",
        "resumed shared camera streams",
        "torque hold unavailable, moving to home",
        "using local mode",
        "using server mode",
        "starting policy server",
        "policy server ready",
        "starting robot client",
        "launching client",
        "waiting for vision trigger",
        "vision trigger complete",
        "eval_",
        "dataset:",
        "total steps",
        "step types",
        "step complete",
        "checkpoint",
        "traceback",
        "warning: qt",
        "qt.qpa.",
        "output reading error",
        "force killing process",
        "point ",
    )
    if any(token in lowered for token in skip_signals):
        return None

    # Friendly translations.
    if "robot port not found" in lowered or "no such file or directory: /dev/ttyacm" in lowered:
        return LogEntry(
            level="error",
            message="The robot is unplugged.",
            action="Check the USB cable and power, then reconnect and press Start.",
            code="robot_port_missing",
            fatal=True,
        )

    if "make sure the robot is connected" in lowered:
        return None

    if "failed to connect to motors" in lowered:
        return LogEntry(
            level="error",
            message="We couldn't talk to the robot motors.",
            action="Confirm the robot is powered on and the USB cable is secure, then restart the run.",
            code="motor_connect_failed",
            fatal=True,
        )

    if "unable to connect to motors for torque hold" in lowered:
        return LogEntry(
            level="warning",
            message="The robot couldn't hold its current pose.",
            action="Make sure the robot is online before starting the run.",
            code="torque_hold_failed",
        )

    if "monitor error" in lowered or "execution error" in lowered:
        return LogEntry(
            level="error",
            message="The run stopped because of an unexpected error.",
            action="Check the terminal for details, fix the issue, then try again.",
            code="execution_error",
            fatal=True,
        )

    if "resilience: motor dropout detected" in lowered or "resilience: retrying waypoint" in lowered:
        return LogEntry(
            level="warning",
            message="Motor dropout detected; retrying to reach the waypoint.",
            code="motor_resilience_retry",
        )

    if "resilience: motor bus recovered" in lowered:
        return LogEntry(
            level="success",
            message="Motor link recovered; continuing the run.",
            code="motor_resilience_recovered",
        )

    if "resilience: waypoint not confirmed" in lowered:
        return LogEntry(
            level="warning",
            message="Waypoint not confirmed after retries; continuing.",
            code="motor_resilience_continue",
            dedupe=False,
        )

    if "process exited with code" in lowered or "robot control app closed with code" in lowered:
        return LogEntry(
            level="error",
            message="The robot control app closed unexpectedly.",
            action="Review the terminal output, resolve the issue, and restart the run.",
            code="client_exit",
            fatal=True,
        )

    if "robot control app message:" in lowered:
        body = text.split(":", 1)[-1].strip()
        if body:
            return LogEntry(
                level="error",
                message=body.capitalize(),
                action="Check the robot connection and try again.",
                code="client_message",
                fatal="error" in level,
            )
        return None

    if "robot control app warning:" in lowered:
        body = text.split(":", 1)[-1].strip()
        if body:
            return LogEntry(
                level="warning",
                message=body.capitalize(),
                code="client_warning",
            )
        return None

    if "model execution completed" in lowered or "run completed successfully" in lowered:
        return None

    if "episode " in lowered and "failed" in lowered:
        return LogEntry(
            level="error",
            message="The run stopped because the episode failed.",
            action="Review the terminal for the exact error, fix it, and run again.",
            code="episode_failed",
            fatal=True,
        )

    if "stopping by user" in lowered or "stopped by user" in lowered:
        return LogEntry(
            level="info",
            message="Run cancelled by user.",
            code="user_stop",
        )

    if lowered.startswith("loading model"):
        return LogEntry(
            level="info",
            message="Loading the selected model…",
            code="model_loading",
        )

    if lowered.startswith("loading recording"):
        return LogEntry(
            level="info",
            message="Loading the selected action…",
            code="recording_loading",
        )

    if lowered.startswith("loading sequence"):
        return LogEntry(
            level="info",
            message="Loading the selected sequence…",
            code="sequence_loading",
        )

    if "policy server is ready" in lowered:
        return LogEntry(
            level="info",
            message="Robot control software is ready.",
            code="policy_ready",
        )

    if "policy server could not start" in lowered:
        return LogEntry(
            level="error",
            message="Could not start the robot control software.",
            action="Check the terminal for errors, then restart the run.",
            code="policy_failed",
            fatal=True,
        )

    # If we reach here and the message still has bracket prefixes, skip it.
    if raw.startswith("[") and "]" in raw[:6]:
        return None

    clean = raw.strip()
    if not clean:
        return None

    return LogEntry(level=level, message=clean)
