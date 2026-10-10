#!/usr/bin/env python3
"""
Minimal MCP (Model Context Protocol) server that exposes an image-generation
tool backed by a self-hosted OpenAI-compatible gateway.

Why this exists: the built-in image generation tool of some desktop agents is
tied to a product-level "app connection" authorization that is unavailable when
the agent is pointed at a third-party OpenAI-compatible endpoint. This server
re-implements the capability as a plain MCP tool so that any client supporting
MCP can generate images through the gateway (subscription-backed, no official
API key required).

Transport: stdio, JSON-RPC 2.0 (one JSON object per line).
Dependencies: Python 3.8+ standard library only.

Environment:
  BJJL_IMAGE_GATEWAY  gateway base URL (default: https://aigateway.evenbetter.tech:8443)
  BJJL_IMAGE_API_KEY  gateway API key (required)
  BJJL_IMAGE_MODEL    model used to drive image generation (default: gpt-6-luna)
  BJJL_IMAGE_OUT_DIR  output directory (default: ~/.codex/generated_images)
"""

import base64
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path

SERVER_NAME = "bjjl-imagegen"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"

GATEWAY = os.environ.get("BJJL_IMAGE_GATEWAY",
                         "https://aigateway.evenbetter.tech:8443").rstrip("/")
API_KEY = os.environ.get("BJJL_IMAGE_API_KEY", "").strip()
MODEL = os.environ.get("BJJL_IMAGE_MODEL", "gpt-6-luna").strip()
OUT_DIR = Path(os.environ.get("BJJL_IMAGE_OUT_DIR") or (Path.home() / ".codex" / "generated_images"))

TOOL_SCHEMA = {
    "name": "generate_image",
    "description": (
        "Generate an image from a text prompt and save it as a PNG file. "
        "Use this whenever the user asks for a picture, illustration, poster, "
        "logo concept, product mockup, sprite, or any raster image. "
        "Returns the absolute path of the generated PNG."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Detailed description of the image to generate. "
                               "Include subject, style, composition and mood.",
            },
            "filename": {
                "type": "string",
                "description": "Optional output filename (without directory). "
                               "Defaults to a generated timestamped name.",
            },
        },
        "required": ["prompt"],
    },
}


def log(msg: str) -> None:
    """Diagnostics go to stderr so they never corrupt the stdio protocol."""
    print(f"[{SERVER_NAME}] {msg}", file=sys.stderr, flush=True)


def generate_image_via_gateway(prompt: str, timeout: int = 300) -> dict:
    """Call the gateway's Responses API with the image_generation tool and
    return the first completed image payload."""
    if not API_KEY:
        raise RuntimeError(
            "BJJL_IMAGE_API_KEY is not set. Configure it in the MCP server env."
        )

    body = {
        "model": MODEL,
        "instructions": "You are a helpful assistant that generates images.",
        "input": [{
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }],
        "tools": [{"type": "image_generation"}],
        "tool_choice": "auto",
        "stream": True,
        "store": False,
    }
    req = urllib.request.Request(
        GATEWAY + "/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + API_KEY,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    images = []
    revised = None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                ev = json.loads(payload)
            except json.JSONDecodeError:
                continue

            etype = ev.get("type", "")
            if "error" in etype or (isinstance(ev.get("error"), dict)):
                raise RuntimeError(f"gateway error: {json.dumps(ev.get('error'))[:300]}")

            item = ev.get("item") or {}
            if item.get("type") == "image_generation_call" and item.get("result"):
                images.append(item)
                revised = item.get("revised_prompt") or revised

    if not images:
        raise RuntimeError(
            "gateway returned no image. Verify BJJL_IMAGE_API_KEY and BJJL_IMAGE_MODEL, "
            "and that the gateway forwards the image_generation tool."
        )

    item = images[-1]
    data = base64.b64decode(item["result"] + "=" * ((4 - len(item["result"]) % 4) % 4))
    return {
        "data": data,
        "size": item.get("size"),
        "format": item.get("output_format") or "png",
        "revised_prompt": revised,
    }


def handle_generate_image(args: dict) -> str:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")

    result = generate_image_via_gateway(prompt)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = (args.get("filename") or "").strip()
    if not filename:
        filename = f"img-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.png"
    if not filename.lower().endswith(".png"):
        filename += ".png"
    # keep writes inside the output directory
    out_path = OUT_DIR / Path(filename).name
    if out_path.exists():
        out_path = OUT_DIR / f"{out_path.stem}-{uuid.uuid4().hex[:4]}.png"
    out_path.write_bytes(result["data"])

    lines = [
        f"Image generated successfully.",
        f"File: {out_path}",
        f"Size on disk: {len(result['data']) / 1024:.1f} KB",
    ]
    if result.get("size"):
        lines.append(f"Dimensions: {result['size']}")
    if result.get("revised_prompt"):
        lines.append(f"Revised prompt: {result['revised_prompt']}")
    return "\n".join(lines)


TOOLS = {"generate_image": handle_generate_image}


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def reply(msg_id, result=None, error=None) -> None:
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    send(out)


def main() -> None:
    log(f"started. gateway={GATEWAY} model={MODEL} out_dir={OUT_DIR}")
    if not API_KEY:
        log("WARNING: BJJL_IMAGE_API_KEY is empty; tool calls will fail.")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method")
        msg_id = msg.get("id")

        if method == "initialize":
            reply(msg_id, {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            })
        elif method in ("notifications/initialized", "initialized"):
            continue
        elif method == "tools/list":
            reply(msg_id, {"tools": [TOOL_SCHEMA]})
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            handler = TOOLS.get(name)
            if handler is None:
                reply(msg_id, error={"code": -32601, "message": f"unknown tool: {name}"})
                continue
            try:
                text = handler(args)
                reply(msg_id, {"content": [{"type": "text", "text": text}], "isError": False})
            except Exception as exc:  # surface the failure to the model
                log(f"tool error: {exc}")
                reply(msg_id, {
                    "content": [{"type": "text", "text": f"Image generation failed: {exc}"}],
                    "isError": True,
                })
        elif method == "ping":
            reply(msg_id, {})
        elif msg_id is not None:
            reply(msg_id, error={"code": -32601, "message": f"unsupported method: {method}"})


if __name__ == "__main__":
    main()
