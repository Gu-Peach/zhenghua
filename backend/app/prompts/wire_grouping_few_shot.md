# Deprecated grouping prompt

The LangGraph V1 pipeline uses `segment_decision.md`. It evaluates every
adjacent page pair from the original rendered images and allows only
`Project.NR` and the drawing prefix to decide whether pages are merged.

This file remains as a compatibility path for older callers. New code should
configure `VLM_SEGMENT_PROMPT_PATH` or use the default `segment_decision.md`.
