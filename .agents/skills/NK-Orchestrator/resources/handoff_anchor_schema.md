# 📋 Schema JSON per Handoff Manifest (`v1.0.0-Generation`)

> **Nodo Proprietario:** `NK-Orchestrator` e `NK_Hub/scripts/nk_session_handoff.py` (`[RULE-02.8]`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

```json
{
 "$schema": "https://json-schema.org/draft/2020-12/schema",
 "title": "NKHandoffManifest",
 "type": "object",
 "additionalProperties": false,
 "properties": {
  "manifest_version": {
   "type": "string",
   "default": "1.0.0-Generation",
   "anyOf": [{"enum": ["1.0.0-Generation"]}, {"pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+(?:-[A-Za-z0-9._-]+)?$"}]
  },
  "handoff_type": {
   "type": "string",
   "enum": ["COMPACT_CHECKPOINT", "SESSION_HANDOFF", "PASSIVE_STATE_HANDOFF", "RSI_CONVERGENCE_CHECKPOINT"]
  },
  "timestamp": {"type": "string", "format": "date-time"},
  "source_conversation_id": {"type": "string"},
  "topology": {
   "type": "object",
   "additionalProperties": false,
   "properties": {
    "pattern": {"type": "string", "enum": ["HUB_AND_SPOKE_2_TIER", "SWARM_PARALLEL", "RATCHET_RSI"]},
    "critic_role": {"type": "string", "default": "NK-Orchestrator"},
    "worker_role": {"type": "string", "default": "[4] NK-Delta-Architect"}
   },
   "required": ["pattern"]
  },
  "active_mode": {"type": "string", "enum": ["MODE_A_SOVEREIGN", "MODE_B_FAST_TRACK", "MODE_C_VIBE_SPRINT", "MODE_D_DISCOVERY"]},
  "milestone_anchor_id": {"type": "string"},
  "pentad_paths": {
   "type": "object",
   "additionalProperties": false,
   "properties": {
    "concept_map": {"type": "string", "default": "nk_genome/concept_map.md"},
    "structural_tree": {"type": "string", "default": "nk_genome/structural_tree.md"},
    "implementation_plan": {"type": "string", "default": "nk_genome/implementation_plan.md"},
    "repo_map": {"type": "string", "default": "nk_genome/repo_map.md"},
    "modules_dir": {"type": "string", "default": "nk_genome/modules"}
   },
   "required": ["concept_map", "structural_tree", "implementation_plan", "repo_map"]
  },
  "rsi_state": {
   "type": "object",
   "additionalProperties": false,
   "properties": {
    "iteration": {"type": "integer", "minimum": 0},
    "delta_k": {"type": "number", "minimum": 0},
    "fitness_q": {"type": "number", "minimum": 0, "maximum": 100.0},
    "status": {"type": "string", "enum": ["CONVERGED_OPTIMAL", "REFINING", "ROLLED_BACK", "ABORTED_OSCILLATION"]}
   },
   "required": ["iteration", "delta_k", "fitness_q", "status"]
  },
  "critic_state": {
   "type": "object",
   "additionalProperties": false,
   "properties": {
    "fsm_state": {"type": "string"},
    "correction_attempts": {"type": "integer", "minimum": 0, "maximum": 4},
    "last_cold_review_gate": {
     "type": "string",
     "enum": ["NONE", "GATE_1_SCOPE", "GATE_2_CODE_GROUNDING", "GATE_3_BRIEF_GROUNDING", "GATE_4_PRESERVATION", "GATE_5_TRUTH_DAST", "GATE_6_RSI_CONVERGENCE", "ALL_PASSED"]
    }
   },
   "required": ["fsm_state", "correction_attempts"]
  }
 },
 "required": ["manifest_version", "handoff_type", "timestamp", "source_conversation_id", "topology", "active_mode", "milestone_anchor_id", "pentad_paths", "rsi_state", "critic_state"]
}
```

---

## ⚓ Ancora Canonica Passive State Handoff (`Template 12`)

1. **Delimitatori:** `Template 12` (`PASSIVE_SESSION_STATE_HANDOFF`) usa `[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]` e `[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]`.
2. **Compilazione:** Usa `scripts/nk_session_handoff.py --compile-handoff-prompt`, `--compile-state-handoff` o `--generate-prompt`.
3. **Bypass in Ricezione:** `scripts/vibe_sprint_router.py --meta-prompt-gate` imposta `fsm_state="BYPASSED"`, `bypass_reason="STATE_HANDOFF_STANDBY"` e `standby_mode=True`.
4. **Libertà (`AP-12`):** Vieta `INTRINSIC_GOAL`, `INTRINSIC_PLAN`, fasi esecutive e `ask_question` (`STATE_HANDOFF_IMPERATIVE_LEAK`).
5. **Anti-Tunneling (`AP-13`):** Vieta piste pre-confezionate (`Pista 1A`), roadmap e scelte chiuse (`STATE_HANDOFF_COGNITIVE_TUNNELING`).
6. **Attesa `STANDBY`:** Il modello acquisisce i fatti verificati in sola lettura e attende l'utente.
