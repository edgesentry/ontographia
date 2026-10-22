#!/usr/bin/env python3
"""Drive the published `ontographia-mcp` server over stdio with a real LLM.

Flow (the LLM never writes Cypher):

  list_ontology + intent_schema (MCP)
    -> LLM (OpenAI-compatible, e.g. LiteLLM alias ontographia-gemini-3.7) emits Intent JSON
    -> build_cypher (MCP)  [one Intent correction round if ok=false]
    -> execute (MCP, read-only)

Writes a JSON transcript of every MCP call and LLM output.

Usage:
  source scripts/litellm/use-provider.sh gemini-3.7
  export NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=ontographia
  python examples/e2e/v0.1.6-gemini/mcp_client.py \\
    --question "List suppliers for parts in product SKU SPX-100" \\
    --out examples/e2e/v0.1.6-gemini/mcp_transcript_llm.json

  # Replay a saved Intent (no LLM) through build_cypher / execute:
  python examples/e2e/v0.1.6-gemini/mcp_client.py \\
    --question "List suppliers for parts in product SKU SPX-100" \\
    --intent-file examples/e2e/v0.1.6-gemini/intent.json \\
    --out examples/e2e/v0.1.6-gemini/mcp_transcript_replay.json
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata as md
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ontographia.llm.extractors import create_extractor

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ONTOLOGY = ROOT / "examples" / "manufacturing.native.yaml"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tool_payload(result: Any) -> Any:
    """Return the structured tool result (dict), falling back to text JSON."""
    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if isinstance(structured, dict):
        if set(structured) == {"result"}:
            return structured["result"]
        return structured
    texts = [getattr(c, "text", "") for c in (result.content or [])]
    joined = "".join(texts)
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        is_error = getattr(result, "is_error", None)
        if is_error is None:
            is_error = getattr(result, "isError", False)
        return {"text": joined, "is_error": bool(is_error)}


async def run(args: argparse.Namespace) -> dict[str, Any]:
    server_cmd = shutil.which("ontographia-mcp") or "ontographia-mcp"
    server_args = ["--ontology", str(args.ontology)]
    env = dict(os.environ)
    params = StdioServerParameters(command=server_cmd, args=server_args, env=env)

    transcript: dict[str, Any] = {
        "started_at": _now(),
        "question": args.question,
        "ontographia_version": md.version("ontographia"),
        "mcp_sdk_version": md.version("mcp"),
        "intent_source": str(args.intent_file) if args.intent_file else "llm",
        "llm": {
            "backend": os.environ.get("ONTOGRAPHIA_LLM_BACKEND"),
            "model_alias": os.environ.get("OPENAI_MODEL"),
            "base_url": os.environ.get("OPENAI_BASE_URL"),
        },
        "server": {"command": "ontographia-mcp", "args": ["--ontology", args.ontology_rel]},
        "steps": [],
    }
    steps: list[dict[str, Any]] = transcript["steps"]
    extractor = None if args.intent_file else create_extractor("openai")

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            # mcp 1.x exposes camelCase attributes; mcp 2.x uses snake_case.
            info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
            transcript["server_info"] = {
                "name": getattr(info, "name", None),
                "version": getattr(info, "version", None),
                "protocol_version": getattr(init, "protocol_version", None)
                or getattr(init, "protocolVersion", None),
            }
            tools = await session.list_tools()
            steps.append(
                {"step": "tools/list", "tools": [t.name for t in tools.tools]}
            )

            async def call(name: str, arguments: dict[str, Any]) -> Any:
                res = await session.call_tool(name, arguments)
                payload = _tool_payload(res)
                return payload

            ontology = await call("list_ontology", {})
            steps.append(
                {
                    "step": "tools/call list_ontology",
                    "response_summary": {
                        "class_names": ontology.get("class_names"),
                        "relationship_names": ontology.get("relationship_names"),
                        "n_properties": len(ontology.get("properties") or []),
                    },
                }
            )
            schema = await call("intent_schema", {})
            steps.append(
                {
                    "step": "tools/call intent_schema",
                    "response_summary": {
                        "title": schema.get("title"),
                        "top_level_properties": sorted((schema.get("properties") or {}).keys()),
                    },
                }
            )

            if args.intent_file:
                # Replay a saved Intent (no LLM call) through build_cypher / execute.
                intent = json.loads(Path(args.intent_file).read_text(encoding="utf-8"))
                steps.append({"step": "saved intent", "path": str(args.intent_file), "intent": intent})
            else:
                intent = extractor.extract(args.question, schema, ontology=ontology)
                steps.append({"step": "llm intent", "intent": intent})

            built = await call("build_cypher", {"intent": intent})
            steps.append({"step": "tools/call build_cypher", "arguments": {"intent": intent}, "response": built})

            corrections = 0
            while extractor and not built.get("ok") and corrections < args.max_corrections:
                corrections += 1
                error = json.dumps(built.get("errors"), ensure_ascii=False)
                intent = extractor.extract_correction(
                    args.question,
                    schema,
                    ontology=ontology,
                    previous_intent=intent,
                    error=error,
                )
                steps.append({"step": f"llm correction {corrections}", "intent": intent})
                built = await call("build_cypher", {"intent": intent})
                steps.append({"step": "tools/call build_cypher", "arguments": {"intent": intent}, "response": built})

            if built.get("ok"):
                executed = await call("execute", {"intent": intent})
                steps.append({"step": "tools/call execute", "arguments": {"intent": intent}, "response": executed})
                transcript["final"] = {
                    "intent": intent,
                    "query": executed.get("query", built.get("query")),
                    "params": executed.get("params", built.get("params")),
                    "execute_ok": executed.get("ok"),
                    "rows": executed.get("rows"),
                    "row_count": executed.get("row_count"),
                    "errors": executed.get("errors"),
                }
            else:
                transcript["final"] = {"intent": intent, "build_ok": False, "errors": built.get("errors")}

    transcript["finished_at"] = _now()
    return transcript


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--question", required=True)
    parser.add_argument("--ontology", type=Path, default=DEFAULT_ONTOLOGY)
    parser.add_argument("--max-corrections", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--intent-file",
        type=Path,
        default=None,
        help="Replay a saved Intent JSON instead of calling the LLM",
    )
    args = parser.parse_args()
    try:
        args.ontology_rel = str(args.ontology.resolve().relative_to(ROOT))
    except ValueError:
        args.ontology_rel = args.ontology.name
    transcript = asyncio.run(run(args))
    text = json.dumps(transcript, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    print(text)
    return 0 if transcript.get("final", {}).get("execute_ok") else 1


if __name__ == "__main__":
    sys.exit(main())
