# Northstar Trading — synthetic order procedure
This file contains fully synthetic data created for portfolio demonstration purposes.
Version date: 2025-11-06

## Order entry
Required fields: Capture the internal order code, product ID, approved SKU, quantity, artwork revision and requested dispatch window.
Handover: Sales submits the order worksheet and approved sample reference to the operations queue.
Privacy rule: Do not place personal contact or bank information in the shared worksheet.

## Release control
Release gate: Operations checks the approved sample reference and artwork revision; a reviewer signs the release checklist before production starts.
Revision policy: A changed specification pauses release until a new reviewer decision is recorded.

## Quality inspection
Quality check: Compare the first assembled unit with the approved sample; verify the SKU label, color and carton count before packing the batch.
Exception handling: Quarantine damaged units, attach a defect code and request a corrective-action decision. Do not mix quarantined units into the outgoing cartons.

## Dispatch handover
Handover: Operations provides the packing list and carton-count check to the dispatch coordinator.
Required fields: The dispatch record contains the order code, carton count, inspection decision and approved carrier booking reference.
