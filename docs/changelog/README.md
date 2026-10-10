# Changelog

This directory records cross-module architecture and product behavior changes.
Detailed application work is archived under `docs/apps/`; service work is
archived under `docs/service/`.

详细变更见 [CHANGELOG.md](./CHANGELOG.md)。

## 2026-10-10

- Restored the local Git metadata from the retained `.git-new` repository, preserving the existing history and `Gu-Peach/zhenghua` origin. Excluded local extraction outputs, caches and environment secrets; enabled tracking of versioned Agent prompt images. This repository maintenance does not implement the proposed stage-persistence changes.

- Documented the proposed durable extraction-stage boundary: typed per-item database outputs, immutable manifests, atomic commit/event barriers and database-backed inputs for the next stage. See [plan](../service/agent/stage-persistence-refactor-plan.md); no runtime or database change has been applied for this proposal.
- Fixed the OpenAI-compatible model request boundary so structured Supervisor context is serialized as JSON string content; multimodal message arrays remain unchanged. This resolves the stage-zero 400 error from providers that reject object-valued `message.content`; the Agent service must reload this code before retrying the live test.
- Made provider-side `response_format` opt-in. Local structured output validation remains enabled through Pydantic, while endpoints that require a server startup flag are no longer sent `response_format` unless `ModelRequest.json_mode=true`.
- Added a detection-only Supervisor conversation flow with terminal-driven HTTP acceptance, streamed planning/dispatch messages and explicit Profile confirmation. The API now remembers recent turns, attachments and pending decisions in bounded per-user, per-conversation process memory; task checkpoints remain separate, and restart/shared-instance or long-term conversation persistence is not implemented.
- Removed the remaining `agent_service.zh_workflow` import-compatibility package and switched its tests to current modules. Legacy Python import paths are no longer supported; existing Agent HTTP/Worker and CLI entry points retain their current behavior.
- Removed the retired adjacent-page segmentation and batch-extraction implementation, its dedicated checkpoint/planner/configuration and compatibility exports. Production Agent/CLI continue to call the new document Graph directly; retained legacy imports forward current capabilities to that same implementation.
- Retired the production dependency on `zh_workflow`: shared document Graph, domain stage models, PDF/checkpoint/export infrastructure and injected ZH Profile policies now own the implementation. Legacy imports forward to those modules; stage artifacts, result proposals and database contracts retain their shapes. See [Agent migration record](../service/agent/changelog/2026-10-10-document-workflow-migration.md).

## 2026-10-08

- Established the project, workspace, drawing and wiring-result domain model.
- Added the gradual monorepo migration plan while preserving legacy frontend
  and backend implementations.
- Selected React + Vite + TypeScript for the new `apps/web` application.
- Standardized the frontend source structure around API, component, hook,
  layout, router, store and view ownership.
- Added module-specific documentation archive rules to `AGENTS.md`.
- Established the Supervisor-led orchestration boundary and deterministic correction routing; runtime Graph integration remains pending the M4 gate.
- Added isolated Page Classifier, Page Scanner and Cross-page Resolver subgraphs backed by the existing ZH stage adapter.

## 2026-10-09

- Completed the Agent-to-Supabase data path: full extraction now creates normalized draft/review result versions atomically; confirmed corrections create accepted versions with optimistic checks and accepted-feedback audit. Correction bundles, model traces, Profile candidates, release gates, evaluations and lifecycle audit are durable in Supabase. Stage agents still cannot issue arbitrary writes, and Profile activation remains human-gated.
- Applied the normalized domain and Agent runtime migrations to the local Supabase stack, added the private `project-assets` hierarchy, persistent run/event/artifact/proposal/checkpoint repositories, a lease-based queue, source-PDF checksum verification, classified page publication, and signed-URL access. The legacy table and public bucket remain untouched; hosted Supabase deployment and Server-owned result transactions remain pending.
- Updated the `apps/web` Mock Supervisor workflow to start only after explicit user activation; PDF workspaces and split drawings appear after Stage 1 completes, while thought and Agent status events stream in stage order.
- Added the Agent Run/Worker/SSE control plane, Supervisor and scoped Correction workflows, plus a sandboxed evaluation and human-gated Profile candidate lifecycle. Production persistence and Server/Web integration remain explicit follow-up work.
- Added a normalized wiring schema migration: project/workspace/drawing/result-version ownership, terminal-strip units with database-assigned wire numbers, queryable connection columns, evidence, RLS and a flattened search view. The legacy JSONB table remains unchanged and remote application is still pending.
- Completed the offline Supervisor orchestration V2: internal first-page Profile Detection, controlled multi-key result lookup and versioned correction, three-state cross-page routing, accepted-feedback diagnosis, explicit Profile candidate authorization, and sanitized diagnosis/candidate events. Production Supabase/Server adapters remain pending.
