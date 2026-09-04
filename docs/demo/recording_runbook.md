# Public demo recording

[Actual recording](enterprise-rag-demo.mp4): **155.62 seconds, 1920×1080, silent H.264 MP4**, approximately 3.7 MB.
This is a new recording of this public edition. No old private-project video or screenshots
were reused. Every displayed business value comes from the new synthetic Northstar sources.

## What was executed

An isolated headless Chrome session used the running React/FastAPI application and local
Qdrant state. Playwright performed real interactions and asserted API results, visible values,
approval provenance and the final citation excerpt. The recording contains no mocked responses,
reconstructed UI, narration, music, private browser tabs or desktop notifications.

| Time | Scene |
|---|---|
| 0:00 | Safe login screen; credential entry omitted |
| 0:07 | Employee workspace |
| 0:13 | Product: material, capacity and MOQ 144 units |
| 0:29 | Catalog evidence drawer |
| 0:43 | Current lantern lead time is unverified |
| 0:58 | Historical payment and trade terms, not current policy |
| 1:15 | Admin stages a synthetic proposal |
| 1:25 | Reviewer compares 144 → 180 units and source evidence |
| 1:39 | Approval confirmation |
| 1:48 | Product Master history and prior value |
| 2:03 | Completed controlled reindex |
| 2:09 | Employee answer now uses 180 units |
| 2:24 | Approved-change citation shows the same new value |

The first take had an obscured answer due to capture-time scrolling. Only the recorder's
waiting/scrolling was corrected; no application or benchmark behavior was changed. The final
take was encoded from 545 actual captured viewport frames. The decoder read all 546 output
samples (including the terminal hold) successfully. All fourteen scene checkpoints were
visually reviewed. Frame-level OCR and byte/metadata privacy checks supplement that review.

## Reproduce or record manually

1. Start a fresh isolated runtime following the README; never connect private sources.
2. Start the frontend, open a 1920×1080 browser viewport and follow [the exact script](../demo_script.md).
3. Read generated credentials off-screen. Pause capture during every role change; do not
   display a terminal, browser storage inspector, password or access token.
4. Stage only `data/demo/updates/northstar-proposed-update.csv`. Record real approval and
   reindex success. The final answer **and source excerpt** must show 180 units.
5. Inspect the entire output for readability and privacy before publishing.

Automation is in `scripts/record_public_demo.mjs`. It requires an existing Playwright
installation (set `PLAYWRIGHT_MODULE` to its module location) and Chrome. A clean runtime
credential file can be supplied through `DEMO_CREDENTIALS_FILE`; use
`DEMO_RECORDING_OUTPUT=data/private/new-recording` to avoid overwriting a take.
`DEMO_FRONTEND_URL` selects the loopback frontend.

The validation host had no ffmpeg or npx. A native macOS AVFoundation encoder was used
instead; Swift source is included in `scripts/encode_demo.swift` and `scripts/inspect_demo.swift`.
On another platform, use a normal screen recorder or Playwright's video support and inspect
the resulting MP4. Raw frames and local credential files must stay ignored.

This compact MP4 is included directly; no Git LFS or hosted video URL is required. Uploading
it as a GitHub Release asset later is optional. No external video upload has been performed.
