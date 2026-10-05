# LangGraph V1

The wiring extraction agent is a four-node `StateGraph`:

```text
pdf_to_images -> segment -> extract_wiring -> assemble_xlsx
```

`segment` sends every adjacent pair of rendered pages to the VLM. `Prompt S`
allows only `Project.NR` and the drawing prefix to affect the decision. The
results are merged with a union-find implementation, so no second feature or
reference detector is involved in V1.

When `VLM_SEGMENT_FEW_SHOT_IMAGES=true`, the two images in
`backend/app/prompts/example_segment/` are inserted before the current page
pair, followed by the standard merge JSON in `expected.json`.

Run the smallest end-to-end example from the repository root:

```powershell
pip install -r backend/requirements.txt
python -m backend.cli --agent-pdf path\to\drawing.pdf -o outputs\wiring-table.xlsx --agent-output-mode single_xlsx
```

For the frontend library layout, use a directory as the output path:

```powershell
python -m backend.cli --agent-pdf path\to\drawing.pdf -o frontend\public\library\agent-job --agent-output-mode library
```

The `library` mode writes the segment page images, `source-pages.json`,
`groups/<segment-id>/records.json`, and `groups/<segment-id>/wiring-table.xlsx`,
plus `agent/merge_decisions.json`, `agent/segments.json`, `agent/errors.json`,
and validation warnings. The API uses this mode automatically.

`SegmentDecider` is the replacement boundary. A future implementation can
replace `VLMSegmentDecider` in `build_wiring_graph` without changing the graph
nodes or state shape.
