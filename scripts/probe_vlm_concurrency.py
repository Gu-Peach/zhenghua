from __future__ import annotations

"""Probe an OpenAI-compatible VLM with small multimodal requests.

Examples:
    python scripts/probe_vlm_concurrency.py
    python scripts/probe_vlm_concurrency.py --levels 1 2 4 8
"""

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.config import load_settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe VLM concurrency without running a PDF job.")
    parser.add_argument(
        "--levels",
        type=int,
        nargs="+",
        default=[1, 2, 4],
        help="Concurrent request levels to test.",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=Path("backend/app/cases/test/1.png"),
        help="Small local image used for the probe.",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args()


async def _probe_level(
    client: httpx.AsyncClient,
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    level: int,
) -> dict[str, Any]:
    started = time.perf_counter()

    async def one(index: int) -> dict[str, Any]:
        request_started = time.perf_counter()
        try:
            response = await client.post(endpoint, headers=headers, json=payload)
            result: dict[str, Any] = {
                "index": index,
                "ok": response.is_success,
                "status": response.status_code,
                "seconds": round(time.perf_counter() - request_started, 2),
            }
            if not response.is_success:
                result["error"] = response.text[:200]
            return result
        except Exception as exc:  # noqa: BLE001 - probe should report every failure.
            return {
                "index": index,
                "ok": False,
                "seconds": round(time.perf_counter() - request_started, 2),
                "error": f"{type(exc).__name__}: {exc}"[:200],
            }

    results = await asyncio.gather(*(one(index) for index in range(1, level + 1)))
    return {
        "level": level,
        "wall_seconds": round(time.perf_counter() - started, 2),
        "successes": sum(1 for result in results if result["ok"]),
        "failures": sum(1 for result in results if not result["ok"]),
        "results": results,
    }


async def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    image_path = args.image.resolve()
    if not image_path.is_file():
        raise SystemExit(f"Probe image not found: {image_path}")
    image_url = "data:image/png;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload: dict[str, Any] = {
        "model": settings.model,
        "temperature": 0,
        "max_tokens": 8,
        "messages": [
            {"role": "system", "content": "Return only OK."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Read this image and reply OK."},
                    {"type": "image_url", "image_url": {"url": image_url, "detail": "low"}},
                ],
            },
        ],
    }
    if settings.enable_thinking is not None:
        payload["chat_template_kwargs"] = {"enable_thinking": settings.enable_thinking}
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    timeout = httpx.Timeout(args.timeout, connect=min(20.0, args.timeout))
    print(f"endpoint={settings.chat_completions_url}")
    print(f"model={settings.model}")
    async with httpx.AsyncClient(timeout=timeout) as client:
        results = []
        for level in args.levels:
            if level < 1:
                raise SystemExit("Concurrency levels must be positive integers.")
            result = await _probe_level(client, settings.chat_completions_url, headers, payload, level)
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)

    if results and results[0]["successes"] == 0:
        print("Conclusion: the service is unavailable even at concurrency=1.")
        return 2
    for result in results:
        if result["failures"]:
            print(f"Conclusion: highest fully successful tested level is below {result['level']}.")
            return 1
    print(f"Conclusion: all tested levels succeeded; tested up to concurrency={results[-1]['level']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run(_parse_args())))
