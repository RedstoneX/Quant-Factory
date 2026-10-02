"""Provider-neutral qf-agent command-line client."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
from uuid import uuid4

from agent_gateway.contracts import GATEWAY_PROTOCOL, MAX_REQUEST_BYTES


DEFAULT_SOCKET = "/run/quant-factory/agent-gateway.sock"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qf-agent")
    parser.add_argument("--socket", default=os.environ.get("QF_AGENT_SOCKET", DEFAULT_SOCKET))
    parser.add_argument("--agent", default=os.environ.get("QF_AGENT_ID"))
    parser.add_argument("--pretty", action="store_true")
    commands = parser.add_subparsers(dest="group", required=True)

    context = commands.add_parser("context")
    context.add_subparsers(dest="action", required=True).add_parser("get")

    prior = commands.add_parser("prior")
    prior_search = prior.add_subparsers(dest="action", required=True).add_parser("search")
    prior_search.add_argument("--query", required=True)

    candidate = commands.add_parser("candidate")
    candidate_actions = candidate.add_subparsers(dest="action", required=True)
    for action in ("validate", "submit"):
        command = candidate_actions.add_parser(action)
        command.add_argument("file")
        if action == "submit":
            _lineage_options(command)
    candidate_actions.add_parser("list")
    candidate_get = candidate_actions.add_parser("get")
    candidate_get.add_argument("candidate_id")

    run = commands.add_parser("run")
    run_actions = run.add_subparsers(dest="action", required=True)
    run_request = run_actions.add_parser("request")
    run_request.add_argument("candidate_id")
    for action in ("status", "results", "evidence"):
        command = run_actions.add_parser(action)
        command.add_argument("run_id")

    research = commands.add_parser("research")
    research_actions = research.add_subparsers(dest="action", required=True)
    note = research_actions.add_parser("note")
    note_actions = note.add_subparsers(dest="note_action", required=True)
    note_add = note_actions.add_parser("add")
    note_add.add_argument("--candidate", dest="candidate_id", required=True)
    note_add.add_argument("--file", required=True)

    lineage = commands.add_parser("lineage")
    lineage_get = lineage.add_subparsers(dest="action", required=True).add_parser("get")
    lineage_get.add_argument("candidate_id")
    return parser


def _lineage_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--parent-candidate")
    parser.add_argument("--parent-run")
    parser.add_argument("--change-reason")
    parser.add_argument("--evidence-cited")
    parser.add_argument("--rule-changed")
    parser.add_argument("--material-difference")
    parser.add_argument("--falsification")
    parser.add_argument("--bounded-search-space")


def request_document(args: argparse.Namespace) -> dict[str, object]:
    if not args.agent:
        raise ValueError("--agent or QF_AGENT_ID is required")
    operation, arguments, payload = _operation(args)
    return {
        "protocol": GATEWAY_PROTOCOL,
        "request_id": f"req_{uuid4().hex}",
        "agent": args.agent,
        "operation": operation,
        "arguments": arguments,
        "payload": payload,
    }


def _operation(args: argparse.Namespace) -> tuple[str, dict[str, object], str | None]:
    payload = None
    arguments: dict[str, object] = {}
    if args.group == "context":
        return "context.get", arguments, payload
    if args.group == "prior":
        return "prior.search", {"query": args.query}, payload
    if args.group == "candidate":
        if args.action in {"validate", "submit"}:
            payload = _read_payload(args.file)
            if args.action == "submit":
                lineage = {
                    "parent_candidate_id": args.parent_candidate,
                    "parent_run_id": args.parent_run,
                    "change_reason": args.change_reason,
                    "evidence_cited": args.evidence_cited,
                    "rule_changed": args.rule_changed,
                    "material_difference": args.material_difference,
                    "falsification": args.falsification,
                    "bounded_search_space": args.bounded_search_space,
                }
                if any(value is not None for value in lineage.values()):
                    arguments["lineage"] = lineage
            return f"candidate.{args.action}", arguments, payload
        if args.action == "get":
            arguments["candidate_id"] = args.candidate_id
        return f"candidate.{args.action}", arguments, payload
    if args.group == "run":
        arguments[f"{'candidate' if args.action == 'request' else 'run'}_id"] = (
            args.candidate_id if args.action == "request" else args.run_id
        )
        return f"run.{args.action}", arguments, payload
    if args.group == "research":
        return "research.note.add", {"candidate_id": args.candidate_id}, _read_payload(args.file)
    if args.group == "lineage":
        return "lineage.get", {"candidate_id": args.candidate_id}, payload
    raise ValueError("unsupported command")


def _read_payload(path: str) -> str:
    if path == "-":
        text = sys.stdin.read(MAX_REQUEST_BYTES + 1)
    else:
        text = Path(path).read_text()
    if len(text.encode()) > MAX_REQUEST_BYTES:
        raise ValueError("input exceeds gateway request size limit")
    return text


def send(document: dict[str, object], socket_path: str) -> dict[str, object]:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("request exceeds gateway size limit")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(120)
        client.connect(socket_path)
        client.sendall(encoded)
        response = b""
        while not response.endswith(b"\n"):
            chunk = client.recv(65_536)
            if not chunk:
                break
            response += chunk
            if len(response) > MAX_REQUEST_BYTES * 4:
                raise RuntimeError("gateway response exceeds size limit")
    document = json.loads(response)
    if not isinstance(document, dict):
        raise RuntimeError("gateway response is invalid")
    return document


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        response = send(request_document(args), args.socket)
    except (OSError, RuntimeError, ValueError) as exc:
        response = {"protocol": GATEWAY_PROTOCOL, "ok": False, "error": {"code": "client_error", "message": str(exc)}}
    print(json.dumps(response, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
