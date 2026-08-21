# 🛡️ Threat & Bottleneck Audit Report: Remediation Brief & Triptych

**Date:** 2026-08-03
**Target:** Nodo 3 (Chronos & Kairos) - `quality_audit_remediation_brief.md`, `concept_map.md`, `structural_tree.md`, `implementation_plan.md`

## 1. Concurrent I/O Locks & WinError 32 Risks
- **Swarm Batching:** The `quality_audit_remediation_brief.md` uses Swarm Batching. Simultaneous writes by multiple subagents to `session_anchor.jsonl` or discrepancy reports can trigger WinError 32 on Windows/Google Drive. All filesystem state anchoring MUST strictly be centralized through the Main Agent or utilize robust `os.replace` with Win32 Exponential Backoff.
- **Upload Serialization:** `implementation_plan.md` explicitly adds an `asyncio.Lock` in `parse_file_bytes` and enforces a sequential `for...of` upload loop in the frontend. This successfully mitigates race conditions and WinError 32 lock risks on the backend state file.

## 2. FSM Stalls & Headless Execution
- **HTTP 409 Conflict Modal (FSM Stall Risk):** The plan introduces an HTTP 409 response and a frontend confirmation dialog for overwriting "actual" data. In automated E2E tests (CRV 3.0 Oracles) or headless execution, this dialog will cause an FSM stall. The automated test harnesses (`e2e_accountant_stress_runner.py`) MUST be configured to pass the `X-Force-Overwrite: true` header to bypass the dialog.

## 3. Race Conditions
- **State Mutation:** Using `asyncio.Lock` for the file ingestion endpoint handles external concurrency, but the math engine (`civil_code_math_engine.py`) and schema validation must be strictly pure functions to avoid internal asynchronous state mutation races.

## 4. Memory Leaks
- **E2E Stress Runner & DAST:** The Dual-Shield TAS and DOM Reader running against 2.4k+ lines require a strict `psutil` process tree kill. Without aggressive process cleanup, Puppeteer/Chrome instances or AST validation trees could cause memory leaks during the 10-20s timeout loops.
- **In-Memory Extractions:** Utilizing `io.BytesIO` in `ground_truth_extractor.py` is a solid architectural choice. It prevents I/O buildup and relies on GC, avoiding file handle leaks.

## 5. Architectural Gaps & Business Logic Flaws
- **Gap Year Depreciation Reset (Critical Flaw):** Step 1.2 of the implementation plan states that accumulated depreciation (`fondo_amm_immat_acc`) must be *reset* if there is a gap between years. Resetting to 0 is financially incorrect. Depreciation should pause, continue linearly, or require manual interpolation. Resetting it introduces mathematical discrepancies in the balance sheet.
- **DOM Rendering Cap:** The plan proposes a `MAX_VISIBLE_YEARS = 10` limit to prevent browser freezing (layout thrashing). However, there is no mention of a UI control (e.g., pagination or a sliding window) to actually view years beyond the first 10.
- **Limbo Year Sync:** The UI adds a dropdown to change the year of an exception, but it is not specified whether changing this dropdown automatically updates the Exceptions Queue backend ledger in real-time or if it requires a batch confirmation.

## 🎯 Conclusion & Verdict
**Verdict: SUCCESS WITH WARNINGS**

The proposed plan is highly detailed and structurally sound. Before moving to GATE 3/4 execution, the following adjustments must be incorporated:
1. Fix the financial logic flaw regarding the resetting of depreciation on gap years.
2. Ensure automated test harnesses correctly inject `X-Force-Overwrite: true` to prevent HTTP 409 FSM stalls.
3. Centralize the file writing for tracking/reports to avoid Swarm I/O Locks.
