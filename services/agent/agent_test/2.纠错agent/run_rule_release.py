"""HTTP-only candidate evaluation, human review, and human publication."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="从已有候选接续实际评测/人工审核/发布，不重复纠错")
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--user-id", default=os.getenv("AGENT_ACCEPTANCE_USER_ID"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--evaluation-run-id", help="接续已有评测任务，不重新启动")
    args = parser.parse_args()
    if not args.user_id:
        parser.error("需要 --user-id 或 AGENT_ACCEPTANCE_USER_ID")
    if os.getenv("AGENT_ACCEPTANCE_ALLOW_REAL_MODEL", "").lower() not in {"true", "1", "yes"}:
        parser.error("真实评测需 AGENT_ACCEPTANCE_ALLOW_REAL_MODEL=true")
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
            response.raise_for_status()
            data = response.json()
            with (output / "responses.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"path": path, "response": data}, ensure_ascii=False) + "\n")
            return dict(data)

        try:
            candidate = call("GET", f"/v1/profile-candidates/{args.candidate_id}")
            print(json.dumps(candidate, ensure_ascii=False, indent=2))
            run_id = args.evaluation_run_id
            if not run_id:
                if input("实际评测将调用真实模型。输入“开始评测”继续：").strip() != "开始评测":
                    return 2
                run_id = call(
                    "POST",
                    f"/v1/profile-candidates/{args.candidate_id}/evaluations",
                    {"reviewer_id": args.user_id, "allow_real_model": True},
                )["run"]["agent_run_id"]
            print(f"评测任务：{run_id}；中断后可用 --evaluation-run-id 接续。")
            seen: set[str] = set()
            seen_outputs: set[str] = set()
            deadline = time.monotonic() + 7200
            while time.monotonic() < deadline:
                observations = call("GET", f"/v1/runs/{run_id}/model-outputs?user_id={args.user_id}")["items"]
                for observation in observations:
                    key = json.dumps(observation, ensure_ascii=False, sort_keys=True)
                    if key not in seen_outputs:
                        seen_outputs.add(key)
                        print("[模型结构化输出]\n" + json.dumps(observation, ensure_ascii=False, indent=2))
                artifacts = call("GET", f"/v1/runs/{run_id}/artifacts")["items"]
                for artifact in artifacts:
                    key = artifact["artifact_id"]
                    if key in seen:
                        continue
                    seen.add(key)
                    if artifact.get("kind") == "evaluation_case":
                        print(
                            f"[{artifact['variant']}/{artifact['stage']}]\n"
                            + json.dumps(artifact["result"], ensure_ascii=False, indent=2)
                        )
                state = call("GET", f"/v1/runs/{run_id}")["run"]
                if state["status"] in {"FAILED", "CANCELLED"}:
                    raise ValueError(f"评测 {state['status']}：{state.get('error')}；不要重提线表纠错。")
                report_artifact = next((a for a in artifacts if a.get("kind") == "evaluation_report"), None)
                if report_artifact:
                    break
                time.sleep(2)
            else:
                raise TimeoutError("等待评测超时，任务未取消。")
            print(json.dumps(report_artifact, ensure_ascii=False, indent=2))
            if not report_artifact["report"].get("cost_reported"):
                print("费用：供应商未报告，不代表免费。")
            if not report_artifact["gate"]["passed"]:
                print("评测未通过，不得审核发布。")
                return 1
            confirm = {"reviewer_id": args.user_id, "evaluation_run_id": run_id, "confirmed": True}
            if input("检查差异和风险后输入“确认审核”继续：").strip() != "确认审核":
                return 2
            print(
                json.dumps(
                    call("POST", f"/v1/profile-candidates/{args.candidate_id}/approve", confirm),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            if (
                input(
                    f"将发布 {candidate['profile']['key']} 新版本，旧项目不重绑。输入“确认发布”继续："
                ).strip()
                != "确认发布"
            ):
                return 2
            result = call("POST", f"/v1/profile-candidates/{args.candidate_id}/publish", confirm)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except (httpx.HTTPError, ValueError, TimeoutError, EOFError, KeyboardInterrupt) as exc:
            print(f"未完成：{exc}；记录保留，请核对任务/报告后接续。")
            return 1
        finally:
            print(f"记录：{output}")


if __name__ == "__main__":
    raise SystemExit(main())
