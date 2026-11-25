# Schema Handoff V2 (v1.0.0-Generation)
> SSOT `HANDOFF_V2`: [`handoff_contracts.py`](../../../../scripts/schemas/handoff_contracts.py) (`strict=True, extra="forbid", frozen=True`).
## 1. `NKHandoffManifest` (`1.0.0-Generation`)
* `manifest_version, handoff_type` (`COMPACT_CHECKPOINT|SESSION_HANDOFF|PASSIVE_STATE_HANDOFF|RSI_CONVERGENCE_CHECKPOINT`), `timestamp, source_conversation_id, active_mode` (`MODE_A..D`), `milestone_anchor_id`.
* `topology` (`HUB_AND_SPOKE_2_TIER|SWARM_PARALLEL|RATCHET_RSI`), `pentad_paths` (`nk_genome/`).
* `rsi_state` (`iteration, delta_k, fitness_q, CONVERGED_OPTIMAL|REFINING|ROLLED_BACK|ABORTED_OSCILLATION`), `critic_state` (`fsm_state, correction_attempts 0..4, GATE_1_SCOPE..GATE_6_RSI_CONVERGENCE|ALL_PASSED`).
## 2. `NKHandoffEnvelopeV2` (`"2.0.0"`)
* `NKHandoffEnvelopeV2`: `schema_version` `"2.0.0"`, `handoff_id, manifest, payload, envelope_sha256` (`--handoff-file, external_live_calls_prohibited=True, pii_redacted_count >= 0`).
* `PassiveStandbyPayloadV2`: `PASSIVE_STANDBY`, `ecosystem_repos, ignored_non_nk_dirs: StrictTuple[str]=(), transcript_raw_jsonl_included=False`.
* `ActiveContinuationPayloadV2`: `ACTIVE_CONTINUATION`, `active_brief_id` (`^IB-\d{8}-[A-Z0-9]{6}$`), `target_repo_ids, requirements, staging_diffs`.
* `RepoSnapshotV2`: `repo_id, repo_root, is_external, state_sha256, oracle_lock_status, staging_entries, patch_notes_head, action_policy_hint` (`LIVE_PYTEST_ARTIFACT|DISK_BASELINE_UNVERIFIED_IN_SESSION|FALLBACK_UNVERIFIED`).
* `PatchNotesHeadV2`: `present_on_disk, rel_path, patch_notes_sha256, first_section_title, first_section_excerpt` (`<= 280` char, `<= 6` righe).
* `StagingEntryV2` (`StagingFileDiffV2`): `rel_path, sha256, OWN_SESSION|EXTERNAL_CONCURRENT` (`diff_patch=None, DO_NOT_TOUCH_OR_PROMOTE`).
* `RequirementClauseV2`: `req_id` (`^R[1-9]\d*$`), `text, status` (`PENDING|IN_PROGRESS|BLOCKED|VERIFIED_DONE`).
## 3. Legacy, Ancore e `AP-14..16`
* Sessione: `version, milestone, conversation_id, steps, steps_tail_window, tokens, actual_tokens, estimated_tokens, turn, turn_phase, handoff_template, standby_mode`.
* Stato/Brief: `baseline_tests, baseline_pass_rate_pct, prompt_lint, state_sha256, staging_state_sha256, dirty_files, project_root, project_dirty_files, stash_patch, unverified_claims, intent_brief_path, intent_brief_sha256, pending_actions, last_summary, last_failed_checks`.
* Ancore: `HANDOFF_V2:PASSIVE_STANDBY`, `HANDOFF_V2:ACTIVE_CONTINUATION`, `PASSIVE_STATE_HANDOFF` (`[NK-ANCHOR:START/END:...]`).
* Wire: `# [NK-HANDOFF-V2]`, `(",",":")` vs indentato. Marcatori: `nk_tracking, nk_genome, .staging, .agents, scripts, src, src_app, backend, frontend, tests, .git`.
* `AP-14..16`: `resolve_session_tracking_dir` vieta `"auto"`; CID esenti; `REPO_OUT_OF_SCOPE`; JSON strict; URL/IPv6/email/DSN/KV; `PATCH_NOTES` isolati.
