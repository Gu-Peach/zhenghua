# 独立Agent清理待确认清单

2026-10-16。状态：待用户明确确认，以下文件尚未删除。

自动审批拒绝批量改写核心入口及删除92个文件，理由为范围超过当前清理Agent的明确授权、可能破坏现有服务。此文档将原拟议操作列成可审阅范围，不代表已执行。

## 保留边界

- 保留独立extraction_agent的初扫/补全/校验/页Graph、规则、图片Few-shot、独立CLI、完成页checkpoint。
- 保留用户未提交的提取/前后端/Schema/样例改动；删除清单与已有修改文件交集为0。
- 保留共享Model Gateway、Profile注册/包校验、类型、事件/工具基础及提取依赖；ScopedExtractionRunner需将通用事件发布依赖从旧run_control解耦，保留其行为及已有冒烟。
- 不删PDF、图片、运行产物、数据库对象、Storage或历史迁移，不重启服务。
- explain_agent和profile_agent仅有职责README，尚未实现；不在本轮接入Deep Agents或新增服务。

## 拟改写的入口

- src/main.py：去掉旧Supervisor/Worker/导入/纠错/自完善装配，保留共享服务入口。
- api/routes/profiles.py、api/dependencies.py、api/schemas/__init__.py：改为本地规则只读和原内部认证。
- api/routes/health.py：不探测已删除的旧projects表，不创建Worker。
- domain/models/__init__.py、domain/schema.py和Schema checksum：移除退休契约，声明独立能力；当前尚未改写。

## 拟删除文件

### 旧验收和发布脚本（13）

- `services/agent/agent_test/0.detection_test/run_acceptance.py`
- `services/agent/agent_test/1.3stage/run_acceptance.py`
- `services/agent/agent_test/2.纠错agent/run_acceptance.py`
- `services/agent/agent_test/2.纠错agent/run_rule_release.py`
- `services/agent/scripts/cleanup_gate_a_tests.py`
- `services/agent/scripts/publish_profile_package.py`
- `services/agent/scripts/run_gate_a_fake_worker.py`
- `services/agent/scripts/test_profile_detection.py`
- `services/agent/scripts/upload_profile_package.py`
- `services/agent/scripts/verify_candidate_inputs.py`
- `services/agent/scripts/verify_gate_a_migrations.py`
- `services/agent/scripts/verify_supabase_agent_database_workflows.py`
- `services/agent/scripts/verify_supabase_production_foundation.py`

### 仅服务旧链路的适配层（16）

- `services/agent/src/agent/extraction_agent/application/extraction_run_executor.py`
- `services/agent/src/infrastructure/business_imports.py`
- `services/agent/src/infrastructure/conversation_memory.py`
- `services/agent/src/infrastructure/correction_data.py`
- `services/agent/src/infrastructure/project_assets.py`
- `services/agent/src/infrastructure/queue.py`
- `services/agent/src/infrastructure/result_data.py`
- `services/agent/src/infrastructure/source_documents.py`
- `services/agent/src/infrastructure/supabase_improvement.py`
- `services/agent/src/infrastructure/supabase_profile_packages.py`
- `services/agent/src/infrastructure/supabase_repositories.py`
- `services/agent/src/infrastructure/supabase_result_data.py`
- `services/agent/src/tools/event_presenter.py`
- `services/agent/src/tools/improvement_intake.py`
- `services/agent/src/tools/profile_detection.py`
- `services/agent/src/tools/result_data.py`

### 旧Agent实现（6）

- `services/agent/src/agents/__init__.py`
- `services/agent/src/agents/evaluation_judge.py`
- `services/agent/src/agents/improvement_diagnoser.py`
- `services/agent/src/agents/profile_patch_builder.py`
- `services/agent/src/agents/profile_router.py`
- `services/agent/src/agents/supervisor.py`

### 旧API与Supervisor契约（9）

- `services/agent/src/api/routes/imports.py`
- `services/agent/src/api/routes/improvement.py`
- `services/agent/src/api/routes/proposals.py`
- `services/agent/src/api/routes/runs.py`
- `services/agent/src/api/routes/supervisor.py`
- `services/agent/src/api/schemas/improvement.py`
- `services/agent/src/api/schemas/runs.py`
- `services/agent/src/api/schemas/supervisor.py`
- `services/agent/src/domain/models/supervisor.py`

### 旧任务和工作流编排（16）

- `services/agent/src/application/__init__.py`
- `services/agent/src/application/candidate_evaluation.py`
- `services/agent/src/application/candidate_release.py`
- `services/agent/src/application/correction_workflow.py`
- `services/agent/src/application/improvement_run_executor.py`
- `services/agent/src/application/improvement_workflow.py`
- `services/agent/src/application/model_output_view.py`
- `services/agent/src/application/profile_assignment.py`
- `services/agent/src/application/profile_detection.py`
- `services/agent/src/application/profile_package_lifecycle.py`
- `services/agent/src/application/run_control.py`
- `services/agent/src/application/run_read_models.py`
- `services/agent/src/application/supervisor_conversation.py`
- `services/agent/src/application/supervisor_handlers.py`
- `services/agent/src/application/worker.py`
- `services/agent/src/application/workflow_registry.py`

### 旧根Graph（8）

- `services/agent/src/graphs/__init__.py`
- `services/agent/src/graphs/correction/__init__.py`
- `services/agent/src/graphs/improvement/__init__.py`
- `services/agent/src/graphs/profile_detection/__init__.py`
- `services/agent/src/graphs/profile_detection/graph.py`
- `services/agent/src/graphs/profile_detection/state.py`
- `services/agent/src/graphs/supervisor/__init__.py`
- `services/agent/src/graphs/supervisor/graph.py`

### 对应旧测试（24）

- `services/agent/tests/integration/test_detection_conversation_api.py`
- `services/agent/tests/integration/test_extraction_worker_unittest.py`
- `services/agent/tests/integration/test_gate_a_real_supabase.py`
- `services/agent/tests/integration/test_gate_b_http.py`
- `services/agent/tests/integration/test_gate_b_real_supabase.py`
- `services/agent/tests/integration/test_profile_detection_graph.py`
- `services/agent/tests/integration/test_supervisor_agent_chain_unittest.py`
- `services/agent/tests/unit/test_candidate_evaluation_release.py`
- `services/agent/tests/unit/test_confirmed_rule_update.py`
- `services/agent/tests/unit/test_correction_batches_and_packages.py`
- `services/agent/tests/unit/test_correction_confirmation.py`
- `services/agent/tests/unit/test_improvement_diagnosis_schema.py`
- `services/agent/tests/unit/test_in_place_result_patches.py`
- `services/agent/tests/unit/test_model_output_view.py`
- `services/agent/tests/unit/test_profile_package_lifecycle.py`
- `services/agent/tests/unit/test_profile_patch_schema.py`
- `services/agent/tests/unit/test_profile_router.py`
- `services/agent/tests/unit/test_remaining_agents_unittest.py`
- `services/agent/tests/unit/test_rule_release_http.py`
- `services/agent/tests/unit/test_supabase_infrastructure.py`
- `services/agent/tests/unit/test_supabase_result_persistence.py`
- `services/agent/tests/unit/test_supervisor.py`
- `services/agent/tests/unit/test_supervisor_chat.py`
- `services/agent/tests/unit/test_worker_failure_logging.py`

## 确认后的验证

静态导入/孤立引用、Profile资源清单、独立提取离线冒烟、共享基础单元、精简API与鉴权契约、当前Server默认回归。默认不调用真实模型或数据库。
