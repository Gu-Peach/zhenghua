"""Gate B terminal client: HTTP inputs and displays only, no Agent/database tools."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

ROOT = Path(__file__).resolve().parent
TERMINAL = {"SUCCEEDED", "NEEDS_REVIEW", "FAILED", "CANCELLED", "WAITING_INPUT"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate B：业务 PDF 上传、终端确认、持久三阶段与 SSE 验收")
    parser.add_argument("pdf", type=Path, nargs="?")
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--user-id", default=os.getenv("AGENT_ACCEPTANCE_USER_ID"),
                        help="已有 Supabase Auth 用户 UUID（不创建用户）")
    parser.add_argument("--project-name")
    parser.add_argument("--run-id", help="服务重启/断线后只监看已有任务，不重传、不重复提取")
    parser.add_argument("--expected", type=Path, help="人工确认的预期扁平行 JSON，按行序进行字段级比较")
    parser.add_argument("--max-wait", type=float, default=7200)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def json_request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = client.request(method, path, **kwargs)
    if response.is_error:
        raise ValueError(f"HTTP {response.status_code}: {response.text[:600]}")
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("HTTP response must be a JSON object.")
    return result


def turn(client: httpx.Client, payload: dict[str, Any], transcript: list[dict[str, Any]]) -> dict[str, Any]:
    transcript.append({"kind": "input", "payload": payload})
    final = None
    event, data = "message", []
    with client.stream("POST", "/v1/supervisor/turns/stream", json=payload) as response:
        if response.is_error:
            response.read()
            raise ValueError(f"HTTP {response.status_code}: {response.text[:600]}")
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
            elif not line and data:
                value = json.loads("\n".join(data))
                data.clear()
                transcript.append({"kind": event, "payload": value})
                if event == "error":
                    raise ValueError(f"Agent 处理失败：{value.get('detail')}")
                if event == "message":
                    print(f"[Agent/{value.get('event_type')}] {value.get('user_message')}", flush=True)
                elif event == "response":
                    final = value
                    print(f"[Supervisor] {value['user_event']['user_message']}", flush=True)
    if final is None:
        raise ValueError("未收到最终 response；记录中的同一 turn_id 可在会话尚存时重试。")
    return dict(final)


def watch(
    client: httpx.Client, run_id: str, transcript: list[dict[str, Any]], deadline: float,
) -> dict[str, Any]:
    cursor = -1
    while time.monotonic() < deadline:
        try:
            with client.stream("GET", f"/v1/runs/{run_id}/events/stream",
                               headers={"Last-Event-ID": str(cursor)}) as response:
                if response.is_error:
                    response.read()
                    raise ValueError(f"HTTP {response.status_code}: {response.text[:600]}")
                for line in response.iter_lines():
                    if time.monotonic() >= deadline:
                        raise TimeoutError("等待达到上限；任务未被取消，可用 --run-id 继续监看。")
                    if line.startswith("data:"):
                        value = json.loads(line[5:].strip())
                        if value["seq"] <= cursor:
                            continue
                        cursor = value["seq"]
                        transcript.append({"kind": "run_event", "payload": value})
                        stage = value.get("stage") or "RUN"
                        print(f"[Supervisor/{stage}/{value['event_type']}] {value.get('message', '')}",
                              flush=True)
            run = json_request(client, "GET", f"/v1/runs/{run_id}")["run"]
            if run["status"] in TERMINAL:
                return dict(run)
        except httpx.TransportError as exc:
            transcript.append({"kind": "stream_reconnect", "error_type": type(exc).__name__,
                               "after_seq": cursor})
        time.sleep(1)
    raise TimeoutError("等待达到上限；任务未被取消，可用 --run-id 继续监看。")


def field_diff(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare only manually supplied expected fields; generated UUIDs need not be pinned."""
    differences = []
    if len(expected) != len(actual):
        differences.append({"field": "row_count", "expected": len(expected), "actual": len(actual)})
    for index, row in enumerate(expected):
        for field, value in row.items():
            observed = actual[index].get(field) if index < len(actual) else None
            if value != observed:
                differences.append({"row": index, "field": field, "expected": value, "actual": observed})
    return differences


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    args = arguments()
    if os.getenv("AGENT_ACCEPTANCE_ALLOW_REAL_MODEL", "").lower() not in {"true", "1", "yes"}:
        raise SystemExit("请先显式设置 AGENT_ACCEPTANCE_ALLOW_REAL_MODEL=true。")
    if not args.user_id:
        raise SystemExit("请提供 --user-id 或 AGENT_ACCEPTANCE_USER_ID：已有 Supabase Auth 用户 UUID。")
    user_id = str(UUID(args.user_id))
    if args.max_wait <= 0:
        raise SystemExit("--max-wait 必须大于零。")
    if not args.run_id and args.pdf is None:
        cases = sorted(ROOT.glob("*.pdf"))
        for index, pdf in enumerate(cases, 1):
            print(f"{index}. {pdf.name}")
        if not cases:
            raise SystemExit("请提供 PDF 路径。")
        selection = int(input("选择案例序号："))
        if not 1 <= selection <= len(cases):
            raise SystemExit("案例序号无效。")
        args.pdf = cases[selection - 1]
    conversation = str(uuid4())
    output = args.output_dir or ROOT / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}-{conversation[:8]}"
    output.mkdir(parents=True, exist_ok=True)
    transcript: list[dict[str, Any]] = []
    report: dict[str, Any] = {"model": None, "case": str(args.pdf) if args.pdf else None,
                              "cost": None, "cost_status": "unknown", "acceptance": "not_completed",
                              "conversation_id": conversation, "user_id": user_id}
    started = time.monotonic()
    token = os.getenv("AGENT_INTERNAL_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with httpx.Client(base_url=args.base_url.rstrip("/"), headers=headers, timeout=600) as client:
            run_id = args.run_id
            if not run_id:
                pdf = args.pdf.resolve()
                imported = json_request(client, "POST", "/v1/imports", params={
                    "user_id": user_id, "conversation_id": conversation,
                    "project_name": args.project_name or pdf.stem, "filename": pdf.name,
                }, headers={"Idempotency-Key": conversation}, content=pdf.read_bytes())
                report["import"] = imported
                print(f"项目：{imported['project_id']}；PDF：{imported['page_count']} 页；"
                      f"Agent：{args.base_url}")
                message = "请识别这份 PDF 的图纸类型让我确认，确认后执行三阶段提取并落库。"
                while True:
                    print(f"用户：{message}")
                    reply = turn(client, {
                        "turn_id": str(uuid4()), "conversation_id": conversation,
                        "user_id": user_id, "message": message,
                    }, transcript)
                    run_id = (reply.get("receipt") or {}).get("agent_run_id")
                    if run_id:
                        break
                    message = input("用户（确认 / 指定类型 / /quit）：").strip()
                    if message == "/quit":
                        report["acceptance"] = "user_stopped_before_extraction"
                        return 0
            report["agent_run_id"] = run_id
            print(f"持久任务：{run_id}；断线/服务重启后可用 --run-id {run_id} 继续监看。", flush=True)
            # This read also checks user/run binding before watching an internal SSE feed.
            json_request(client, "GET", f"/v1/runs/{run_id}/summary", params={"user_id": user_id})
            run = watch(client, run_id, transcript, time.monotonic() + args.max_wait)
            summary = json_request(client, "GET", f"/v1/runs/{run_id}/summary", params={"user_id": user_id})
            report.update({"run": run, "stages": summary, "model": summary["model_name"]})
            project_id = run["project_id"]
            report["tree"] = json_request(client, "GET", f"/v1/projects/{project_id}/tree",
                                          params={"user_id": user_id})
            receipt = summary.get("final_receipt") or {}
            rows: list[dict[str, Any]] = []
            version = receipt.get("result_version_id")
            if version:
                while True:
                    page = json_request(client, "GET", f"/v1/projects/{project_id}/results", params={
                        "user_id": user_id, "result_version_id": version, "offset": len(rows), "limit": 100,
                    })
                    rows.extend(page["items"])
                    if not page["has_more"]:
                        break
            report["rows"] = rows
            if args.expected:
                expected = json.loads(args.expected.read_text(encoding="utf-8"))
                if not isinstance(expected, list):
                    raise ValueError("expected 必须是人工确认的扁平行数组。")
                report["field_differences"] = field_diff(expected, rows)
            report["acceptance"] = "manual_review_required"
            if run["status"] not in {"SUCCEEDED", "NEEDS_REVIEW"}:
                report["acceptance"] = "execution_not_successful"
                raise ValueError(f"任务状态 {run['status']}，请检查持久事件及错误。")
            print(f"[Supervisor] 任务处理完成：{run['status']}；数据库结果 {len(rows)} 条。")
            print("接口执行完成不等于准确率验收通过；请检查字段差异/人工复核报告。")
            return 0
    except (ValueError, OSError, httpx.HTTPError, KeyboardInterrupt) as exc:
        report["error"] = str(exc)[:1000]
        print(f"验收未完成：{exc}", file=sys.stderr)
        return 1
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (output / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        (output / "summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        print(f"验收记录：{output}")


if __name__ == "__main__":
    raise SystemExit(main())
