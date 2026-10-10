"""Interactive stage-zero HTTP client. No Agent, VLM, PDF-rendering or database tools."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

CASE_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="阶段 0：通过 Agent HTTP 接口进行类型识别与终端确认验收")
    parser.add_argument("pdf", type=Path, nargs="?", help="输入 PDF；省略则从本目录选择")
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--user-id", default="acceptance-terminal")
    parser.add_argument("--conversation-id", default=None, help="使用同一 ID 继续服务端短期会话")
    parser.add_argument(
        "--message", default="请只识别这份 PDF 的图纸类型，告诉我结果并让我确认。暂不提取线表。"
    )
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def choose_pdf(supplied: Path | None) -> Path:
    if supplied:
        path = supplied.resolve()
    else:
        cases = sorted(CASE_ROOT.glob("*.pdf"))
        if not cases:
            raise ValueError("本目录没有 PDF，请提供输入路径。")
        for number, case in enumerate(cases, start=1):
            print(f"{number}. {case.name}")
        answer = input("选择案例序号：").strip()
        if not answer.isdigit() or not 1 <= int(answer) <= len(cases):
            raise ValueError("案例序号无效。")
        path = cases[int(answer) - 1].resolve()
    if not path.is_file():
        raise ValueError(f"文件不存在：{path}")
    return path


def send_turn(
    client: httpx.Client, payload: dict[str, Any], transcript: list[dict[str, Any]]
) -> dict[str, Any]:
    """Send one user input and display server-emitted SSE messages without choosing tools."""
    transcript.append({"kind": "user_input", "payload": payload})
    started = time.perf_counter()
    final: dict[str, Any] | None = None
    event = "message"
    data_lines: list[str] = []
    with client.stream("POST", "/v1/supervisor/turns/stream", json=payload) as response:
        if response.is_error:
            response.read()
            raise ValueError(f"Agent HTTP {response.status_code}: {response.text[:500]}")
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
            elif not line and data_lines:
                data = json.loads("\n".join(data_lines))
                transcript.append({"kind": event, "payload": data})
                data_lines.clear()
                if event == "error":
                    raise ValueError(f"Agent 处理失败：{data.get('detail')}")
                if event == "message":
                    print(
                        f"[Agent/{data.get('event_type', '消息')}] {data.get('user_message', '')}", flush=True
                    )
                elif event == "response":
                    final = data
                    print(f"[Supervisor] {data['user_event']['user_message']}", flush=True)
                    break
    if final is None:
        raise ValueError("事件连接已结束，但未收到最终 response；可使用相同 turn_id 重试。")
    elapsed = time.perf_counter() - started
    transcript.append({"kind": "request_timing", "seconds": round(elapsed, 3)})
    print(f"[耗时] 本轮接口请求 {elapsed:.2f}s")
    return final


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    args = parse_args()
    if os.environ.get("AGENT_ACCEPTANCE_ALLOW_REAL_MODEL", "").lower() not in {"true", "1", "yes"}:
        raise SystemExit("运行真实 Agent 验收前，请设置 AGENT_ACCEPTANCE_ALLOW_REAL_MODEL=true。")
    conversation_id = args.conversation_id or str(uuid4())
    output = args.output_dir or CASE_ROOT / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}-{conversation_id[:8]}"
    output.mkdir(parents=True, exist_ok=True)
    transcript: list[dict[str, Any]] = []
    token = os.environ.get("AGENT_INTERNAL_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    print(f"会话：{conversation_id}\nAgent：{args.base_url}\n输入 /quit 结束；确认后可继续询问，检查记忆。")
    print("此脚本会请求正在运行的 Agent，服务端可能调用真实模型。")
    try:
        with httpx.Client(
            base_url=args.base_url.rstrip("/"), headers=headers, timeout=args.timeout
        ) as client:
            if args.conversation_id and args.pdf is None:
                response = client.get(
                    f"/v1/supervisor/conversations/{conversation_id}", params={"user_id": args.user_id}
                )
                response.raise_for_status()
                transcript.append({"kind": "memory", "payload": response.json()})
                if not response.json().get("history"):
                    raise ValueError("Agent 没有该会话的短期历史；可能已重启或淘汰，请重新上传案例。")
                message = input("用户：").strip()
                attachments: list[str] = []
            else:
                pdf = choose_pdf(args.pdf)
                with pdf.open("rb") as stream:
                    response = client.post(
                        f"/v1/supervisor/conversations/{conversation_id}/attachments",
                        params={"user_id": args.user_id, "filename": pdf.name},
                        content=stream,
                        headers={"Content-Type": "application/pdf"},
                    )
                response.raise_for_status()
                attachment = response.json()
                transcript.append({"kind": "attachment", "payload": attachment})
                attachments = [attachment["attachment_id"]]
                message = args.message
                print(f"用户：{message}")
            while message and message != "/quit":
                payload: dict[str, Any] = {
                    "turn_id": str(uuid4()),
                    "conversation_id": conversation_id,
                    "user_id": args.user_id,
                    "message": message,
                }
                if attachments:
                    payload["attachment_ids"] = attachments
                send_turn(client, payload, transcript)
                # Later turns deliberately contain no attachment/run/profile hints.
                # The Agent must retrieve them from its own conversation memory.
                attachments = []
                message = input("用户：").strip()
            response = client.get(
                f"/v1/supervisor/conversations/{conversation_id}", params={"user_id": args.user_id}
            )
            response.raise_for_status()
            memory = response.json()
            (output / "memory.json").write_text(
                json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            requests_seconds = sum(
                item.get("seconds", 0) for item in transcript if item["kind"] == "request_timing"
            )
            case_names = [item["payload"]["filename"] for item in transcript if item["kind"] == "attachment"]
            summary = {
                "conversation_id": conversation_id,
                "input_cases": case_names,
                "model": memory.get("model_name"),
                "requests_seconds": round(requests_seconds, 3),
                "cost": None,
                "cost_status": "not_reported_by_api",
                "accuracy_verdict": "manual_review_required",
            }
            (output / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"模型：{summary['model']}；案例：{', '.join(case_names) or '继续已有会话'}")
            print("费用：API 未返回，记为 unknown；不按 0 计算。")
        return 0
    except (ValueError, httpx.HTTPError) as exc:
        print(f"验收请求失败：{exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("\n终端输入结束。")
        return 0
    finally:
        (output / "transcript.json").write_text(
            json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"对话记录：{output}")


if __name__ == "__main__":
    raise SystemExit(main())
