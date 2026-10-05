# Segmentation few-shot

This directory contains the multimodal segmentation example used by Prompt S.
The two images are sent in one user turn as page A and page B, followed by the
standard merge decision in `expected.json` as the assistant turn.

This example is separate from `examples_extration`, which is used for wiring
record extraction. Set `VLM_SEGMENT_FEW_SHOT_IMAGES=false` only when debugging
request size or provider limitations.
