# Knowledge-governance walkthrough provenance

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

## Regenerate

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

No open-source license has been selected for this repository. Public visibility does
not grant general redistribution rights. The repository owner's portfolio uses a
copy of this visual with the same synthetic-data and source attribution.
