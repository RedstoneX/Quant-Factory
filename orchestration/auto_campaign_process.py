"""Run one automatic test in a child process so a crash cannot stop the gateway."""

from __future__ import annotations

import multiprocessing
from multiprocessing.connection import Connection
from typing import Any, Callable

from orchestration.auto_campaign import AutoTestOutcome, AutoTestRequest, safe_detail

ChildTarget = Callable[[AutoTestRequest], AutoTestOutcome]


def _child_main(target: ChildTarget, request: AutoTestRequest, sender: Connection) -> None:
    try:
        outcome = target(request)
    except BaseException as exc:
        # The parent records one plain line; the child still exits with the error.
        sender.send(_document(AutoTestOutcome("failed", "run_error", safe_detail(f"{type(exc).__name__}: {exc}"))))
        sender.close()
        raise
    sender.send(_document(outcome))
    sender.close()


def _document(outcome: AutoTestOutcome) -> dict[str, Any]:
    return {
        "state": outcome.state,
        "reason_code": outcome.reason_code,
        "reason_detail": outcome.reason_detail,
        "run_id": outcome.run_id,
    }


def run_in_child(
    request: AutoTestRequest, *, target: ChildTarget, timeout_seconds: float | None
) -> AutoTestOutcome:
    """Start a fresh interpreter for one run; a timeout terminates only that child."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child_main, args=(target, request, sender))
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout_seconds):
            process.terminate()
            process.join(10)
            if process.is_alive():
                process.kill()
            return AutoTestOutcome(
                "failed", "run_timeout", f"The test exceeded its {timeout_seconds:g}-second limit and was stopped."
            )
        try:
            document = receiver.recv()
        except EOFError:
            process.join(10)
            return AutoTestOutcome(
                "failed", "run_error", f"The test process exited with code {process.exitcode} before reporting."
            )
        process.join(10)
        return AutoTestOutcome(
            str(document["state"]),
            str(document["reason_code"]),
            document.get("reason_detail"),
            document.get("run_id"),
        )
    finally:
        receiver.close()
