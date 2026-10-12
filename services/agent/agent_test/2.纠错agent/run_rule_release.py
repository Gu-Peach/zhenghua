"""HTTP-only explicit confirmation of an existing rule modification; no model evaluation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="确认并直接启用已有规则修改包，不评测、不重复纠错")
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--user-id", default=os.getenv("AGENT_ACCEPTANCE_USER_ID"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    args = parser.parse_args()
    if not args.user_id:
        parser.error("需要 --user-id 或 AGENT_ACCEPTANCE_USER_ID")
    for stream in (sys.stdout, sys.stdin):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    output = Path(__file__).parent / "runs" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-rule-release")
    output.mkdir(parents=True, exist_ok=True)
    token = os.getenv("AGENT_INTERNAL_TOKEN")
    headers = {"Authorization": "Bearer " + token} if token else {}
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=600) as client:

        def call(method: str, path: str, value: dict[str, Any] | None = None) -> dict[str, Any]:
            response = client.request(method, path, json=value)
            try:
                data = response.json()
            except ValueError:
                data = {"detail": "接口返回非 JSON 响应"}
            with (output / "responses.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {"path": path, "status": response.status_code, "response": data}, ensure_ascii=False
                    )
                    + "\n"
                )
            if response.is_error:
                raise ValueError(f"HTTP {response.status_code}：{data.get('detail', data)}")
            return dict(data)

        try:
            candidate = call("GET", f"/v1/profile-candidates/{args.candidate_id}")
            print(json.dumps(candidate, ensure_ascii=False, indent=2))
            if (
                input("检查修改内容后输入“确认规则修改”直接启用（不进行模型评测）：").strip()
                != "确认规则修改"
            ):
                return 2
            result = call(
                "POST",
                f"/v1/profile-candidates/{args.candidate_id}/confirm",
                {"reviewer_id": args.user_id, "confirmed": True},
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print("规则修改已落地并启用；已有项目未自动切换规则版本。")
            return 0
        except (httpx.HTTPError, ValueError, EOFError, KeyboardInterrupt) as exc:
            print(f"未完成：{exc}；核对记录后以同一候选接续，不要重复纠错。")
            return 1
        finally:
            print(f"记录：{output}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
