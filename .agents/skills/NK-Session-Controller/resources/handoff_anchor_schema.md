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
      "enum": ["COMPACT_CHECKPOINT", "SESSION_HANDOFF", "RSI_CONVERGENCE_CHECKPOINT"]
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
