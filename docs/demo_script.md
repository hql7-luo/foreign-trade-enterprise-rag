# Definitive 2–3 minute synthetic demo

All actions use fictional Northstar Trading. Start a fresh local operator runtime. Generate
credentials locally and keep the credential file and terminal outside the recording.

| Time | Action | What the viewer learns |
|---|---|---|
| 0:00–0:10 | Employee login; show Knowledge Desk | Role-separated internal tool |
| 0:10–0:30 | Ask `NSTR-VESSEL-731 material, capacity and MOQ?` | Steel / 500 ml / 144 units, each cited |
| 0:30–0:43 | Open a catalog citation | Source filename, row, SKU and bounded excerpt |
| 0:43–0:57 | Ask `What is the current lead time for NSTR-LANTERN-864?` | Explicit unverified field, no invented deadline |
| 0:57–1:13 | Ask `Historical NSTR-VESSEL-731 payment terms and Incoterms?` | Archived terms are not current policy |
| 1:13–1:25 | Admin: upload `data/demo/updates/northstar-proposed-update.csv`; create review items | New data is a proposal, not authority |
| 1:25–1:48 | Reviewer: inspect 144 → 180 units, evidence and version; add note and approve | Auditable human decision |
| 1:48–2:01 | Product Master: search `NSTR-VESSEL-731`; inspect `moq` history | Approved value and prior version coexist |
| 2:01–2:08 | Admin: re-index configured source; wait for completed job | Retrieval catches up with governed state |
| 2:08–2:30 | Employee: ask `NSTR-VESSEL-731 MOQ?`; open its citation | Answer and evidence both show 180 units |

Suggested reviewer note: `Synthetic replenishment revision verified against the proposed source.`
Do not omit reindexing. Verify the final excerpt, not only the answer text. Credential entry
and role-switch waits may be omitted from captured time; never fabricate a successful action.
