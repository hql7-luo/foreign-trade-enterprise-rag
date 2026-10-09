# Knowledge-governance walkthrough provenance

## Four-stage overview

[The overview](governance-overview.png) presents four large stages for the README.
The separate `governance-stage-01.png` through `governance-stage-04.png` assets contain
only cropped actual UI regions and white spacing, for responsive portfolio cards.
Their `-480.png` alternatives use the same crops. Editorial headings, large numeric
summaries and explanations are added **outside** the captured UI in the overview.
No UI labels, answers, values, citations or source excerpts were redrawn or generated.

| Stage | Actual source regions | What the crop proves |
|---|---|---|
| 01 — approved knowledge | [Original answer](screenshots/03-grounded-product.png) | Current approved MOQ 144 units, citing catalog row 2 |
| 02 — pending proposal | [Original pending comparison](screenshots/08-pending-conflict.png) | Current 144 and proposed 180; the proposal is explicitly not authoritative until approved |
| 03 — approval and history | [Original Product Master timeline](screenshots/10-master-provenance.png) | Current approved 180 and historical 144 remain distinct |
| 04 — answer after reindex | [Original updated answer](screenshots/12-governed-answer.png) and [original evidence drawer](screenshots/13-governed-evidence.png) | Answer 180 cites the approved change; the excerpt records approved MOQ 180 and the review note |

Stages 02, 03 and 04 vertically combine separate rectangular crops, with white gaps.
Stage 03 focuses on status and value; it omits long source fields from the crop rather
than recreating them. Those fields remain visible in the linked full timeline capture.
The compressed story groups operations; approval and reindex are still separate.
[Source staging](screenshots/07-controlled-ingestion.png),
[approval confirmation](screenshots/09-review-approved.png) and the
[completed Admin reindex](screenshots/11-index-updated.png) remain available in full.

All business records belong to the **fictional Northstar Trading company and are fully
synthetic**. The captures show an actual application run of a proposed MOQ change
144 → 180; they do not establish real customer use, time savings or commercial benefit.
Employee, Reviewer and Admin are application permission roles, not claims about a
human project team. The README states the confirmed personal AI-assisted contribution.

[The new source manifest](governance-overview.sources.json) records the reviewed source
revision `1593b56f5e2fa4ef10892b945fed8c2ea5e40ed8`, original PNG hashes, exact
`[left, top, right, bottom]` pixel crop coordinates, uniform resize dimensions,
white-canvas placement, output dimensions and output hashes. Coordinates follow
Pillow's half-open box convention. Sources are RGB PNGs; processing uses Lanczos
resampling and optimized PNG output. Each 960px and 480px stage is generated directly
from the source crops, rather than enlarging an already exported 480px image.

The main stages are **960 × 283**, **960 × 634**, **960 × 500** and **960 × 670** pixels;
each is below 500 KB. The overview is **800 × 2876** pixels. The original captures are
1920 × 1080 bitmap images: a larger export does not add details absent from the source.
Click the linked full frame for wider context. The 480px alternatives and overview
are presentation versions, not separate evidence or new application runs.

## Preserved six-step detail

`governance-workflow.png` is a layout of six cropped **actual application screenshots**.
`governance-workflow-mobile.png` presents the same steps in one column for small screens.
Only labels, numbering, arrows and white margins were added. No UI, answer, evidence,
metric or customer result was reconstructed or generated.

The screen captures came from the public Northstar recording described in
[the recording runbook](recording_runbook.md). Northstar and all business records
are fully synthetic. This example changes a product's approved MOQ from 144 to
180 units; it does not demonstrate an actual customer's purchase or business benefit.

| Step | Actual capture | Meaning |
|---|---|---|
| 01 | [Employee answer](screenshots/03-grounded-product.png) | Existing approved value and citations |
| 02 | [Controlled submission](screenshots/07-controlled-ingestion.png) | Admin stages evidence and creates a review item |
| 03 | [Pending comparison](screenshots/08-pending-conflict.png) | Reviewer sees old/new values, evidence and approve/reject controls |
| 04 | [Product Master history](screenshots/10-master-provenance.png) | Approved replacement and prior value coexist |
| 05 | [Completed reindex](screenshots/11-index-updated.png) | Admin completes the controlled index job |
| 06 | [Updated answer](screenshots/12-governed-answer.png) | New approved value with a citation to the change |

Steps are read left to right, then top to bottom. The illustrated take follows the
approval path; rejection remains a supported decision and does not replace the
current fact. Approval and reindex are separate operations. Role permissions and
governance behavior are implemented in `app/approval.py`, `app/database/sqlite.py`,
`app/api/routes.py` and `app/ingestion/pipeline.py`.

The UI source and application behavior are unchanged from these captures in the
reviewed revision `757c874316f56701cdeb529054dce149049c688c`; that revision updated
dependencies and runtime support. The screenshot files remain the original captures.

## Regenerate the preserved six-step detail

```bash
uv sync --frozen --extra dev
uv run python -m scripts.build_governance_visual
```

The locked environment already includes Pillow. Arial or DejaVu Sans must be available;
font choice can affect raster bytes but not the underlying crop or business values.
[The generated manifest](governance-workflow.sources.json) records each original image's
SHA-256 digest and crop coordinates, plus both output digests. The desktop visual is
1600 × 1675 pixels and approximately 315 KB; the one-column mobile alternative is
800 × 3073 pixels and approximately 324 KB. Both show the same six steps.
Click to enlarge for the smaller UI text.

The four-stage assets are a separate presentation of the same original run. Their
source manifest above records the crop/resize/composition recipe; the six-stage
generator and assets, full original frames, architecture and MP4 remain unchanged.

No open-source license has been selected for this repository. Public visibility does
not grant general redistribution rights. The repository owner's portfolio uses a
copy of this visual with the same synthetic-data and source attribution.
