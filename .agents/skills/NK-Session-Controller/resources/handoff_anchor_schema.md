# 📋 Schema JSON per Handoff Manifest (`v3.0.0-STE100-Unified`)

> **Nodo Proprietario:** `NK-Session-Controller` e `scripts/nk_session_handoff.py` (`[RULE-02.8]`).  
> **Standard Linguistico:** ASD-STE100 Italiano Tecnico (`[RULE-STE100]`).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "NKHandoffManifestV3",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "manifest_version": {
      "type": "string",
      "const": "3.0.0-STE100-Unified"
    },
    "handoff_type": {
      "type": "string",
      "enum": ["COMPACT_CHECKPOINT", "SESSION_HANDOFF", "PASSIVE_STATE_HANDOFF", "RSI_CONVERGENCE_CHECKPOINT"]
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "source_conversation_id": {
      "type": "string"
    },
    "topology": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "pattern": {
          "type": "string",
          "enum": ["HUB_AND_SPOKE_2_TIER", "SWARM_PARALLEL", "RATCHET_RSI"]
        },
        "critic_role": {
          "type": "string",
          "default": "[14] NK-Session-Controller"
        },
        "worker_role": {
          "type": "string",
          "default": "[5] NK-Delta-Architect"
        }
      },
      "required": ["pattern"]
    },
    "active_mode": {
      "type": "string",
      "enum": ["MODE_A_SOVEREIGN", "MODE_B_FAST_TRACK", "MODE_C_VIBE_SPRINT", "MODE_D_DISCOVERY"]
    },
    "milestone_anchor_id": {
      "type": "string"
    },
    "tetralogy_paths": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "concept_map": { "type": "string", "default": "nk_genome/concept_map.md" },
        "structural_tree": { "type": "string", "default": "nk_genome/structural_tree.md" },
        "implementation_plan": { "type": "string", "default": "nk_genome/implementation_plan.md" },
        "repo_map": { "type": "string", "default": "nk_genome/repo_map.md" }
      },
      "required": ["concept_map", "structural_tree", "implementation_plan", "repo_map"]
    },
    "rsi_state": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "iteration": { "type": "integer", "minimum": 0 },
        "delta_k": { "type": "number", "minimum": 0 },
        "fitness_q": { "type": "number", "minimum": 0, "maximum": 100.0 },
        "status": {
          "type": "string",
          "enum": ["CONVERGED_OPTIMAL", "REFINING", "ROLLED_BACK", "ABORTED_OSCILLATION"]
        }
      },
      "required": ["iteration", "delta_k", "fitness_q", "status"]
    },
    "critic_state": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "fsm_state": { "type": "string" },
        "correction_attempts": { "type": "integer", "minimum": 0, "maximum": 4 },
        "last_cold_review_gate": {
          "type": "string",
          "enum": [
            "NONE",
            "GATE_1_SCOPE",
            "GATE_2_CODE_GROUNDING",
            "GATE_3_BRIEF_GROUNDING",
            "GATE_4_PRESERVATION",
            "GATE_5_TRUTH_DAST",
            "GATE_6_RSI_CONVERGENCE",
            "ALL_PASSED"
          ]
        }
      },
      "required": ["fsm_state", "correction_attempts"]
    }
  },
  "required": [
    "manifest_version",
    "handoff_type",
    "timestamp",
    "source_conversation_id",
    "topology",
    "active_mode",
    "milestone_anchor_id",
    "tetralogy_paths",
    "rsi_state",
    "critic_state"
  ]
}
```

---

## ⚓ Ancora Canonica Passive State Handoff (`Template 12`)

1. **Delimitatori Canonici:** Ogni handoff di stato inter-sessione (`Template 12: PASSIVE_SESSION_STATE_HANDOFF`) è racchiuso tra `[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]` e `[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]`.
2. **Compilazione Deterministica:** L'agente genera l'ancora tramite `scripts/nk_session_handoff.py --compile-handoff-prompt` (o `--compile-state-handoff` / `--generate-prompt`).
3. **Bypass Automatico in Ricezione:** `scripts/vibe_sprint_router.py --meta-prompt-gate` rileva l'ancora e imposta `fsm_state="BYPASSED"`, `bypass_reason="STATE_HANDOFF_STANDBY"` e `standby_mode=True`.
4. **Libertà Cognitiva e Divieto di Imperativi (`AP-12`):** L'handoff vieta `INTRINSIC_GOAL`, `INTRINSIC_PLAN`, fasi esecutive e `ask_question` autonome (`STATE_HANDOFF_IMPERATIVE_LEAK`).
5. **Divieto di Tunneling Cognitivo (`AP-13`):** L'handoff vieta piste pre-confezionate (`Pista 1A`), roadmap speculative e scelte chiuse (`STATE_HANDOFF_COGNITIVE_TUNNELING`).
6. **Attesa Attiva in `STANDBY`:** Il modello ricevente acquisisce i fatti verificati in sola lettura e attende l'utente.

