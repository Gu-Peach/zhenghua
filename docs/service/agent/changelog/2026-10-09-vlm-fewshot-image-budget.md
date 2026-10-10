# VLM Few-shot Image Budget

Stage 2 and Stage 3 keep their manifest-backed image examples, but images whose
longest side exceeds `AGENT_MODEL_FEWSHOT_MAX_IMAGE_SIDE` are reduced in the
outgoing request. The default limit is 1800 pixels. Source and target drawing
images are unchanged, and the on-disk example assets remain full resolution.

This addresses providers that reject multi-image requests because their raw
vision patches exceed the processor budget. Offline tests verify that all
Stage 2/3 few-shot images remain present and are resized, while current drawing
images are passed through unchanged. No paid model request was run as part of
this change.
