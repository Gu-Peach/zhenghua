"""Mixed correction/no-rule-issue acceptance. HTTP/UI inputs only; no Agent/DB tools."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx

ROOT = Path(__file__).resolve().parent
TERMINAL = {"SUCCEEDED", "NEEDS_REVIEW", "FAILED", "CANCELLED", "WAITING_INPUT"}
RULE_CAUSES = {
    "PROFILE_ROUTING_ERROR",
    "PAGE_CLASSIFICATION_ERROR",
    "PROMPT_RULE_GAP",
    "CROSS_PAGE_RESOLUTION_ERROR",
    "DETERMINISTIC_RULE_ERROR",
}
FIELDS = (
    "principle_number",
    "start_code",
    "start_description",
    "start_terminal",
    "end_code",
    "end_description",
    "end_terminal",
    "current_value",
    "remark",
    "color_mark",
    "is_cross_page",
    "terminal_strip",
    "voltage_level",
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="纠错纯 HTTP 终端验收：支持规则候选确认与拒绝")
    parser.add_argument(
        "--expect-rule-issue",
        action="store_true",
        help="按规则有问题案例运行；候选出现后允许确认并继续 Profile Patch/Eval 流程",
    )
    parser.add_argument("--project-id", default=os.getenv("AGENT_ACCEPTANCE_PROJECT_ID"))
    parser.add_argument("--user-id", default=os.getenv("AGENT_ACCEPTANCE_USER_ID"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8100")
    parser.add_argument("--conversation-id", default=None)
    parser.add_argument("--message", help="一条自然语言混合纠错输入；省略则在终端输入")
    parser.add_argument("--message-file", type=Path, help="UTF-8 自然语言输入，不是工具命令")
    parser.add_argument("--expected", type=Path, help="人工预期 JSON：{连接ID: {字段: 正确值}}")
    parser.add_argument("--run-id", help="仅监看已有任务/输出，不提交输入或确认，不算完整验收")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-wait", type=float, default=7200, help="每个后台任务等待上限（秒）")
    parser.add_argument("--request-timeout", type=float, default=600)
    return parser.parse_args()


class Stopped(Exception):
    pass


class Acceptance:
    def __init__(
        self,
        client: httpx.Client,
        *,
        project: str,
        user: str,
        conversation: str,
        output: Path,
        max_wait: float,
    ) -> None:
        self.client, self.project, self.user, self.conversation = client, project, user, conversation
        self.output, self.max_wait = output, max_wait
        self.seen_artifacts: set[str] = set()
        self.seen_traces: set[str] = set()
        self.report: dict[str, Any] = {
            "acceptance": "INCOMPLETE",
            "checks": {},
            "runs": [],
            "project_id": project,
            "conversation_id": conversation,
            "models": [],
            "cost": None,
            "cost_status": "provider_not_reported",
            "reasoning_exposed": False,
        }
        self.output.mkdir(parents=True, exist_ok=True)

    def log(self, kind: str, payload: Any) -> None:
        with (self.output / "transcript.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"kind": kind, "payload": payload}, ensure_ascii=False) + "\n")
        self.save()

    def save(self) -> None:
        (self.output / "summary.json").write_text(
            json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def show(self, title: str, value: Any) -> None:
        print(f"\n[{title}]\n{json.dumps(value, ensure_ascii=False, indent=2)}", flush=True)

    def request(self, path: str, **params: Any) -> dict[str, Any]:
        response = self.client.get(path, params=params)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("HTTP response must be an object.")
        return value

    def ask(self, prompt: str) -> str:
        try:
            answer = input(prompt).strip()
        except EOFError as exc:
            raise Stopped("终端输入结束。") from exc
        if not answer or answer == "/quit":
            raise Stopped("用户退出；已运行的任务没有被脚本取消。")
        return answer

    def turn(self, message: str, hint: dict[str, str] | None = None) -> dict[str, Any]:
        payload = {
            "turn_id": str(uuid4()),
            "conversation_id": self.conversation,
            "user_id": self.user,
            "project_id": self.project,
            "message": message,
            "target_hint": hint or {},
        }
        self.log("user_input", payload)
        final = None
        event = "message"
        lines: list[str] = []
        with self.client.stream("POST", "/v1/supervisor/turns/stream", json=payload) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    lines.append(line[5:].strip())
                elif not line and lines:
                    value = json.loads("\n".join(lines))
                    lines.clear()
                    self.log(f"supervisor_{event}", value)
                    if event == "error":
                        raise ValueError(f"Supervisor：{value.get('detail')}")
                    if event == "message":
                        print(
                            f"[Supervisor/{value.get('event_type')}] {value.get('user_message')}", flush=True
                        )
                    elif event == "response":
                        final = value
                        self.show("Supervisor 决策与理由", value["decision"])
                        print(f"[Supervisor] {value['user_event']['user_message']}", flush=True)
        if final is None:
            raise ValueError("未收到最终响应；不要盲目重发提交，请根据已记录 turn/proposal ID 核对状态。")
        try:
            outputs = self.request(
                f"/v1/supervisor/conversations/{self.conversation}/turns/{payload['turn_id']}/model-output",
                user_id=self.user,
            )
            self.print_traces(outputs)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            print("[观测提示] 当前服务没有模型输出接口；请加载新代码。决策/阶段产物仍会记录。")
        return final

    def print_traces(self, outputs: dict[str, Any]) -> None:
        for trace in outputs.get("items", []):
            key = trace["trace_id"]
            if key in self.seen_traces:
                continue
            self.seen_traces.add(key)
            self.log("model_output", trace)
            self.show(f"模型输出/{trace.get('agent')}/{trace.get('model')}", trace)
            if trace.get("model") and trace["model"] not in self.report["models"]:
                self.report["models"].append(trace["model"])
            if trace.get("output_available"):
                agents = self.report.setdefault("output_agents", [])
                if trace.get("agent") not in agents:
                    agents.append(trace.get("agent"))

    def observations(self, run_id: str) -> list[dict[str, Any]]:
        artifacts = self.request(f"/v1/runs/{run_id}/artifacts")["items"]
        for artifact in artifacts:
            key = artifact["artifact_id"]
            if key in self.seen_artifacts:
                continue
            self.seen_artifacts.add(key)
            kind = artifact.get("kind")
            if kind == "correction_batch":
                batch = artifact["batch"]
                value = {
                    name: batch.get(name)
                    for name in ("feedback_ids", "direct_patch", "stage2", "stage2_stage3")
                }
                self.report["batch"] = value
                self.show("Agent 批次规划", value)
            elif kind == "correction_stage_item":
                value = {
                    "stage": artifact.get("stage"),
                    "item_id": artifact.get("item_id"),
                    "result": artifact.get("result"),
                }
                self.report.setdefault("stages", []).append(artifact.get("stage"))
                self.show("阶段结构化结果", value)
            elif kind == "correction_item":
                value = {"plan": artifact.get("plan"), "proposal": artifact.get("proposal")}
                self.show("纠错路径理由与字段修订", value)
            elif kind == "improvement_diagnosis":
                value = {
                    name: artifact.get(name)
                    for name in ("diagnoses", "candidate_recommended", "authorization_required", "reason")
                }
                self.show("归因依据与规则判定", value)
                self.report["diagnosis"] = value
            elif kind == "profile_candidate":
                value = {"candidate_id": artifact.get("candidate", {}).get("candidate_id")}
                self.report["unexpected_candidate"] = value
                self.show("错误：本测试不应生成候选", value)
            else:
                continue
            self.log("artifact_output", {"artifact_id": key, "kind": kind, "data": value})
        try:
            self.print_traces(self.request(f"/v1/runs/{run_id}/model-outputs", user_id=self.user))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
        return artifacts

    def watch(self, run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if run_id not in self.report["runs"]:
            self.report["runs"].append(run_id)
        deadline, cursor = time.monotonic() + self.max_wait, -1
        while time.monotonic() < deadline:
            try:
                with self.client.stream(
                    "GET", f"/v1/runs/{run_id}/events/stream", headers={"Last-Event-ID": str(cursor)}
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if time.monotonic() >= deadline:
                            raise TimeoutError("等待超时；任务未被取消，可用 --run-id 监看。")
                        if not line.startswith("data:"):
                            continue
                        value = json.loads(line[5:].strip())
                        if value["seq"] <= cursor:
                            continue
                        cursor = value["seq"]
                        self.log("run_event", value)
                        print(
                            f"[Agent/{value.get('stage') or 'RUN'}/{value['event_type']}] "
                            f"{value.get('message', '')}",
                            flush=True,
                        )
                        if value["event_type"] in {
                            "STAGE_COMPLETED",
                            "PROPOSAL_CREATED",
                            "RUN_FAILED",
                            "HUMAN_INPUT_REQUIRED",
                            "RUN_COMPLETED",
                        }:
                            self.observations(run_id)
                run = self.request(f"/v1/runs/{run_id}")["run"]
                artifacts = self.observations(run_id)
                if run["status"] in TERMINAL:
                    self.log("run_state", run)
                    if run["status"] in {"FAILED", "CANCELLED"}:
                        raise ValueError(f"任务 {run_id} {run['status']}：{run.get('error')}")
                    return run, artifacts
            except httpx.TransportError as exc:
                self.log(
                    "stream_reconnect",
                    {"run_id": run_id, "after_seq": cursor, "error_type": type(exc).__name__},
                )
            time.sleep(1)
        raise TimeoutError("等待超时；任务未被取消，可用 --run-id 监看。")

    def rows(self) -> dict[str, Any]:
        offset, result, rows = 0, None, []
        while True:
            page = self.request(
                f"/v1/projects/{self.project}/results",
                user_id=self.user,
                offset=offset,
                limit=500,
                **(
                    {"result_version_id": result["result_version_id"]}
                    if result and result.get("result_version_id")
                    else {}
                ),
            )
            if result and (result["result_version_id"], result["result_revision"]) != (
                page["result_version_id"],
                page["result_revision"],
            ):
                raise ValueError("分页期间结果发生改变，无法给出一致性验收结论。")
            result = page
            rows.extend(page["items"])
            if not page["has_more"]:
                result["items"] = rows
                return result
            offset += len(page["items"])

    def execute(
        self,
        message: str,
        expected: dict[str, dict[str, Any]] | None,
        *,
        expect_rule_issue: bool = False,
    ) -> None:
        before = self.rows()
        profiles_before = self.request("/v1/profiles")["items"]
        self.log("results_before", before)
        reply = self.turn(message)
        for _ in range(12):
            receipt = reply.get("receipt") or {}
            if receipt.get("workflow") == "CORRECTION" and receipt.get("agent_run_id"):
                break
            reply = self.turn(self.ask("用户（补充目标；/quit 退出）："))
        else:
            raise ValueError("未进入纠错任务。")
        correction_run = receipt["agent_run_id"]
        run, artifacts = self.watch(correction_run)
        if run["status"] != "NEEDS_REVIEW":
            raise ValueError("纠错未返回待确认 proposal。")
        proposals = [item["proposal_id"] for item in artifacts if item.get("kind") == "result_proposal"]
        if len(proposals) != 1:
            raise ValueError("没有唯一 proposal，不能代替 Agent 猜测要确认哪一份。")
        proposal = self.request(f"/v1/proposals/{proposals[0]}")
        self.show("请人工检查 before/after，再决定是否提交", proposal)
        self.log("proposal", proposal)
        if not proposal.get("operations") or not all(
            proposal.get("validation", {}).get(key) is True
            for key in ("schema_valid", "business_rules_valid")
        ):
            raise ValueError("proposal 无可提交改动或未通过校验；请查看阶段输出并补充有效样例。")
        reply = self.turn(self.ask("用户（输入确认提交；/quit 不提交退出）："), {"proposal_id": proposals[0]})
        for _ in range(8):
            receipt = reply.get("receipt") or {}
            if receipt.get("payload", {}).get("correction_committed") is True:
                break
            reply = self.turn(
                self.ask("用户（根据 Agent 问题回复；/quit 退出）："), {"proposal_id": proposals[0]}
            )
        else:
            raise ValueError("修订尚未确认提交。")
        committed = receipt["payload"]
        self.report["commit"] = committed
        after = self.rows()
        self.log("results_after", after)
        checks = self.report["checks"]
        old = {row["connection_id"]: row for row in before["items"]}
        new = {row["connection_id"]: row for row in after["items"]}
        checks["in_place"] = committed.get("update_mode") == "in_place"
        checks["stable_ids"] = old.keys() == new.keys()
        checks["stable_generation"] = before["result_version_id"] == after["result_version_id"]
        checks["revision_matches_receipt"] = after["result_revision"] == committed.get("result_revision")
        checks["stable_wire_and_unit"] = all(
            (row.get("wire_number"), row.get("wiring_unit_id"))
            == (new.get(key, {}).get("wire_number"), new.get(key, {}).get("wiring_unit_id"))
            for key, row in old.items()
        )
        checks["proposal_fields_applied"] = all(
            str(new.get(op["target_id"], {}).get(field)) == str(op["after"].get(field))
            for op in proposal["operations"]
            for field in FIELDS
            if field in op.get("after", {})
        )
        changed = {op["target_id"] for op in proposal["operations"]}
        checks["unrelated_fields_unchanged"] = all(
            all(row.get(field) == new.get(key, {}).get(field) for field in FIELDS)
            for key, row in old.items()
            if key not in changed
        )
        if expected is not None:
            checks["human_expected_fields"] = all(
                str(new.get(key, {}).get(field)) == str(value)
                for key, fields in expected.items()
                for field, value in fields.items()
            )
        self.show("原位落库验收", checks)
        improvement = committed.get("improvement_run_id")
        if not improvement:
            raise ValueError("修订已生效，但归因未启动；记录中保存了 commit，请勿重新注错。")
        run, artifacts = self.watch(improvement)
        diagnosis = next((item for item in artifacts if item.get("kind") == "improvement_diagnosis"), None)
        if diagnosis is None:
            raise ValueError("没有归因产物，不能判断规则是否有问题。")
        diagnoses = diagnosis.get("diagnoses") or []
        checks["rules_no_issue"] = bool(diagnoses) and all(
            item.get("profile_candidate_required") is False
            and item.get("category") not in RULE_CAUSES
            and item.get("category") != "SOURCE_INSUFFICIENT"
            for item in diagnoses
        )
        self.report["evidence_insufficient"] = any(
            item.get("category") == "SOURCE_INSUFFICIENT" for item in diagnoses
        )
        checks["no_candidate_recommended"] = diagnosis.get("candidate_recommended") is False
        self.report["field_accuracy_validated"] = checks.get("human_expected_fields")
        if diagnosis.get("candidate_recommended"):
            if not expect_rule_issue:
                print("[预期偏差] Agent 建议规则候选；本脚本只允许人工拒绝，拒绝不等于证明规则没问题。")
                while True:
                    answer = self.ask("用户（输入“拒绝规则候选”继续，/quit 退出）：")
                    if answer in {"拒绝规则候选", "拒绝", "不修改规则"}:
                        break
                    print("本案例不授权创建候选，请明确拒绝或退出。")
                reply = self.turn(answer, {"agent_run_id": improvement})
            else:
                print("[规则问题] Agent 已给出修改建议；确认后将直接修改并启用新规则包，不进行评测。")
                while True:
                    answer = self.ask("用户（输入“确认规则修改”继续，或“拒绝规则候选”退出）：")
                    if answer in {"确认规则修改", "确认修改规则", "确认"}:
                        reply = self.turn(answer, {"agent_run_id": improvement})
                        break
                    if answer in {"拒绝规则候选", "拒绝", "不修改规则"}:
                        reply = self.turn(answer, {"agent_run_id": improvement})
                        break
                    print("请明确输入确认或拒绝。")
            if not (reply.get("receipt") or {}).get("agent_run_id"):
                raise ValueError("拒绝未恢复归因任务，记录已保存。")
            run, artifacts = self.watch(improvement)
            events = self.request(f"/v1/runs/{improvement}/events")["items"]
            checks["rejection_applied"] = any(
                event.get("metrics", {}).get("candidate_declined") is True for event in events
            )
            self.report["candidate_rejection"] = "declined" if checks["rejection_applied"] else "not_applied"
            if expect_rule_issue and answer in {"确认规则修改", "确认修改规则", "确认"}:
                self.report["candidate_authorization"] = "requested"
                self.report["candidate_rejection"] = "not_requested"
        else:
            print("[规则候选] 未建议创建候选，无待拒绝事项；本轮不调用 ProfilePatchBuilder。")
            self.report["candidate_rejection"] = "not_needed"
        checks["diagnosis_finished"] = run["status"] == "SUCCEEDED"
        checks["no_candidate_created"] = not any(
            item.get("kind") in {"profile_candidate", "profile_candidate_pending", "profile_rule_update"}
            for item in artifacts
        )
        if expect_rule_issue:
            checks["rule_issue_detected"] = bool(diagnoses) and bool(diagnosis.get("candidate_recommended"))
            checks["candidate_authorization_requested"] = (
                self.report.get("candidate_authorization") == "requested"
            )
            checks.pop("no_candidate_created", None)
            if self.report.get("candidate_authorization") == "requested":
                checks["rules_updated"] = any(
                    item.get("kind") == "profile_rule_update"
                    and item.get("candidate", {}).get("status") == "ACTIVE"
                    for item in artifacts
                )
        checks["production_profiles_unchanged"] = profiles_before == self.request("/v1/profiles")["items"]
        if expect_rule_issue and self.report.get("candidate_authorization") == "requested":
            checks.pop("production_profiles_unchanged", None)
        batch = self.report.get("batch", {})
        stages = self.report.get("stages", [])
        checks["mixed_three_routes"] = all(
            batch.get(key) for key in ("direct_patch", "stage2", "stage2_stage3")
        )
        checks["stage2_and_stage3_outputs"] = "PAGE_SCAN" in stages and "CROSS_PAGE_COMPLETION" in stages
        checks["model_outputs_observed"] = {
            "supervisor",
            "page_scan",
            "cross_page_completion",
            "improvement_diagnoser",
        }.issubset(set(self.report.get("output_agents", [])))
        self.report["acceptance"] = (
            "PASS"
            if all(checks.values())
            else "INCOMPLETE"
            if self.report["evidence_insufficient"]
            else "FAIL"
        )
        self.show("验收结论（链路执行不等于准确率通过）", self.report)


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = arguments()
    if os.getenv("AGENT_ACCEPTANCE_ALLOW_REAL_MODEL", "").lower() not in {"true", "1", "yes"}:
        raise SystemExit("请显式设置 AGENT_ACCEPTANCE_ALLOW_REAL_MODEL=true；服务可能调用真实模型。")
    if not args.user_id or not args.project_id:
        raise SystemExit("请指定 --project-id 和已有 --user-id（或对应 AGENT_ACCEPTANCE_* 环境变量）。")
    project, user = str(UUID(args.project_id)), str(UUID(args.user_id))
    if args.max_wait <= 0 or args.request_timeout <= 0 or (args.message and args.message_file):
        raise SystemExit("等待/超时需大于零；--message 与 --message-file 不能同时使用。")
    conversation = args.conversation_id or str(uuid4())
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S")
    output = args.output_dir or ROOT / "runs" / f"{stamp}-{conversation[:8]}"
    token = os.getenv("AGENT_INTERNAL_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    started = time.monotonic()
    print(
        f"项目：{project}\n会话：{conversation}\nAgent：{args.base_url}\n"
        "只显示公开任务计划、诊断依据和结构化输出，不输出内部推理链。"
    )
    with httpx.Client(
        base_url=args.base_url.rstrip("/"), headers=headers, timeout=args.request_timeout
    ) as client:
        acceptance = Acceptance(
            client,
            project=project,
            user=user,
            conversation=conversation,
            output=output,
            max_wait=args.max_wait,
        )
        try:
            if args.run_id:
                acceptance.watch(str(UUID(args.run_id)))
                acceptance.report["acceptance"] = "MONITOR_ONLY"
                return 0
            expected = json.loads(args.expected.read_text(encoding="utf-8-sig")) if args.expected else None
            if expected is not None and (
                not isinstance(expected, dict)
                or not expected
                or not all(isinstance(value, dict) and value for value in expected.values())
            ):
                raise ValueError("--expected 必须为非空 {连接ID: {字段: 预期值}} 对象。")
            message = args.message or (
                args.message_file.read_text(encoding="utf-8-sig").strip()
                if args.message_file
                else acceptance.ask("用户（输入一条包含直接答案＋同页重识别＋跨页重识别的消息）：")
            )
            acceptance.report["case_input"] = message
            acceptance.execute(message, expected, expect_rule_issue=args.expect_rule_issue)
            return 0 if acceptance.report["acceptance"] == "PASS" else 1
        except (Stopped, KeyboardInterrupt) as exc:
            acceptance.report.update(acceptance="INCOMPLETE", stopped=str(exc) or "用户中断")
            print("[退出] 任务未被脚本取消，记录已保留。")
            return 2
        except (ValueError, OSError, httpx.HTTPError) as exc:
            acceptance.report.update(acceptance="ERROR", error=str(exc)[:1200])
            print(f"[验收未完成] {exc}", file=sys.stderr)
            return 1
        finally:
            acceptance.report["elapsed_seconds"] = round(time.monotonic() - started, 3)
            acceptance.save()
            print(f"验收记录：{output}")


if __name__ == "__main__":
    raise SystemExit(main())
