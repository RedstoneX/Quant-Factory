"""Exact allowlist for the qf-research forced SSH command."""

from __future__ import annotations

import os
import shlex
import sys

from agent_gateway.cli import main as cli_main


_READ_WITH_ID = {("candidate", "get"), ("run", "status"), ("run", "results"), ("run", "evidence"), ("lineage", "get")}


def allowed_arguments(command: str) -> list[str]:
    try:
        words = shlex.split(command, posix=True)
    except ValueError as exc:
        raise ValueError("remote command is not valid") from exc
    if not words or words[0] != "qf-agent":
        raise ValueError("only qf-agent commands are allowed")
    args = words[1:]
    if args in (["bootstrap"], ["context", "get"], ["candidate", "list"]):
        return args
    if len(args) == 4 and args[:2] == ["prior", "search"] and args[2] == "--query":
        return args
    if len(args) == 3 and tuple(args[:2]) in _READ_WITH_ID:
        return args
    if args in (["candidate", "validate", "-"], ["candidate", "submit", "-"]):
        return args
    if len(args) == 3 and args[:2] == ["run", "request"]:
        return args
    if len(args) == 7 and args[:3] == ["research", "note", "add"] and args[3] == "--candidate" and args[5:] == ["--file", "-"]:
        return args
    raise ValueError("remote qf-agent command is not in the allowlist")


def main() -> int:
    command = os.environ.get("SSH_ORIGINAL_COMMAND", "")
    try:
        arguments = allowed_arguments(command)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 126
    return cli_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
