# Schema JSON per Handoff Manifest (v2.0)

Questo schema definisce la struttura formale del file `handoff_manifest_[TIMESTAMP].json` o `dual_handoff_manifest_[TIMESTAMP].json` generato dal Clean Handoff Engine v2.0 e dal Dual Conversation Refresh Protocol.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "handoff_type": {
      "type": "string",
      "enum": ["CONTROLLER_SELF", "WORKER_FORCED", "DUAL_REFRESH", "DECOUPLED_ACTOR_CRITIC_REFRESH"],
      "description": "Indica il tipo di handoff: self-refresh del controller, forzato del worker o dual refresh coordinato."
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "source_conversation_id": {
      "type": "string",
      "description": "L'ID della conversazione in chiusura o del nodo supervisor."
    },
    "topology": {
      "type": "object",
      "properties": {
        "pattern": {
          "type": "string",
          "enum": ["DECOUPLED_ACTOR_CRITIC", "SWARM", "CASCADE", "PARALLEL", "RATCHET"],
          "description": "Topologia multi-agente attiva."
        },
        "critic_role": { "type": "string", "default": "NK-Session-Controller" },
        "worker_role": { "type": "string", "default": "NK-Delta-Architect" }
      },
      "required": ["pattern"]
    },
    "active_mode": {
      "type": "string",
      "enum": ["MODE_A_TRIPTYCH_DRIVEN", "MODE_B_FAST_TRACK"],
      "description": "Modalità di esecuzione attiva: Mode A (Trittico & Two-Stage Grounding) o Mode B (Fast-Track)."
    },
    "milestone_anchor_id": {
      "type": "string",
      "description": "Identificativo deterministico della milestone attiva nel Brief/Piano di Implementazione."
    },
    "triptych_paths": {
      "type": "object",
      "properties": {
        "concept_map": { "type": "string", "default": "G:/Il mio Drive/Antigravity/nk_genome/concept_map.md" },
        "structural_tree": { "type": "string", "default": "G:/Il mio Drive/Antigravity/nk_genome/structural_tree.md" },
        "implementation_plan": { "type": "string", "default": "G:/Il mio Drive/Antigravity/nk_genome/implementation_plan.md" }
      },
      "required": ["concept_map", "structural_tree", "implementation_plan"]
    },
    "project_context": {
      "type": "object",
      "properties": {
        "project_name": { "type": "string" },
        "workspace_root": { "type": "string" },
        "critical_files": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "path": { "type": "string" },
              "sha256": { "type": "string" },
              "size_bytes": { "type": "integer" }
            },
            "required": ["path", "sha256"]
          }
        },
        "architectural_decisions": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Decisioni chiave prese nella sessione precedente."
        },
        "active_constraints": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Vincoli NK attivi (es. 'RULE-01', 'RULE-02.6', 'RULE-02.7', 'RULE-03')."
        }
      },
      "required": ["workspace_root"]
    },
    "critic_state": {
      "type": "object",
      "properties": {
        "fsm_state": { "type": "string", "description": "Stato FSM del Critico (es. ACTIVE_SUPERVISION, AWAITING_RECEIPT)." },
        "conversation_id": { "type": "string", "description": "URI conversation:// del Critico." },
        "correction_attempts": {
          "type": "integer",
          "minimum": 0,
          "maximum": 3,
          "description": "Contatore del Circuit Breaker di correzione (hard-cap max 3)."
        },
        "last_cold_review_gate": {
          "type": "string",
          "enum": [
            "NONE",
            "GATE_1_SCOPE",
            "GATE_2_CODE_GROUNDING",
            "GATE_2BIS_BRIEF_GROUNDING",
            "GATE_3_PRESERVATION",
            "GATE_4_TRUTH",
            "GATE_5_DELEGATION",
            "ALL_PASSED"
          ]
        },
        "pending_reviews": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "required": ["fsm_state", "correction_attempts"]
    },
    "worker_state": {
      "type": "object",
      "properties": {
        "worker_id": { "type": "string", "description": "URI conversation:// del Worker monitorato." },
        "skill_name": { "type": "string", "description": "Nome della skill del Worker (es. NK-Delta-Architect)." },
        "fsm_state": { "type": "string", "description": "Stato operativo del Worker." },
        "last_execution_receipt": {
          "type": "object",
          "properties": {
            "stage_a_brief_grounding_verified": { "type": "boolean" },
            "stage_b_code_grounding_verified": { "type": "boolean" },
            "milestone_anchor_id": { "type": "string" },
            "diff_applied": { "type": "boolean" },
            "test_exit_code": { "type": "integer" }
          }
        },
        "pending_tasks": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "fsm_state": {
      "type": "object",
      "properties": {
        "controller_state": { "type": "string" },
        "worker_state": { "type": "string" },
        "pending_actions": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    },
    "session_memory": {
      "type": "object",
      "properties": {
        "completed_tasks": {
          "type": "array",
          "items": { "type": "string" }
        },
        "failed_tasks": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "task": { "type": "string" },
              "reason": { "type": "string" }
            }
          }
        },
        "key_learnings": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Pattern e anti-pattern appresi."
        }
      }
    },
    "genome_update_performed": {
      "type": "boolean",
      "description": "Vero se è stato eseguito il sync dei file di Genome durante la Fase 1."
    }
  },
  "required": [
    "handoff_type",
    "timestamp",
    "source_conversation_id",
    "topology",
    "active_mode",
    "project_context",
    "critic_state"
  ]
}
```
