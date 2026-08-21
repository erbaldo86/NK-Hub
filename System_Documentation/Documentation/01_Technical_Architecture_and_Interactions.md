# ⚙️ Architettura Tecnica & Interazione Agenti (NK-Engine Release v1.0)

> **Documento Tecnico di Livello Ingegneristico** per comprendere l'orchestrazione dei sub-agenti, gli schemi IPC, la Sandbox ed il grafo delle dipendenze (DAG).

---

## 📐 1. Il Grafo Orientato Aciclico (DAG) delle Dipendenze

Tutte le operazioni nell'Ecosistema NK sono ordinate su un **DAG valido**. L'orchestrazione segue l'ordinamento topologico di Kahn:

```mermaid
flowchart TD
    subgraph L0 [Livello L0: Ideazione]
        NK0[NK-Ideator]
    end

    subgraph L1 [Livello L1: Instruction Forge]
        NK1_FORGE[NK-Agent-Instruction-Forge]
    end

    subgraph L2 [Livello L2: Architettura Backend & Async]
        NK2_BA[NK-Backend-Architect]
        NK2_B[NK-Python-Async-Builder]
    end

    subgraph L3 [Livello L3: UX & App Architecture]
        NK3_UX[NK-App-UX-Architect]
    end

    subgraph GOV [Governance & Orchestrazione L3/Tattica]
        HUB[NK-Master-Hub Sovrano L3]
        SESS[NK-Session-Controller Critico Tattico]
        STATE[NK-State-Router DAG & Checksum]
        DELTA[NK-Delta-Architect Two-Stage Grounding]
        BUG[NK-Bug-Diagnostic-Engine RCA]
    end

    subgraph AUDIT [Quality, Security & Verification Swarm] 
        ALIGN[NK-Plan-Aligner Audit Trittico 3/3]
        SEC[NK-Security-Auditor Dual-Shield TAS L1/L2/L3]
        ORACLE[NK-Oracle-Evaluator AST/DOM/Math]
        DAST[NK-Dynamic-Sandbox-StressTester Shadow Sandbox OS]
    end

    subgraph MEM_DOCS [Memoria Episodica & Documentazione]
        MEM[NK-Episodic-Memory-Engine 4 Domini]
        ANCHOR[nk_tracking/anchor/session_anchor.jsonl]
        SCRIBE[NK-Scribe The Scribe Exemption]
    end

    NK0 --> ALIGN
    NK3_UX --> ALIGN
    ALIGN --> NK2_BA
    NK2_BA --> NK2_B
    NK2_B --> NK1_FORGE
    BUG --> |Fast-Track| NK2_B
    BUG --> |Deep-Track| DELTA
    DELTA --> ALIGN
    NK2_B --> |Macro-Fase 1 .staging/| AUDIT
    AUDIT --> |Macro-Fase 2 PASS exit_code 0| HUB
    HUB --> |Macro-Fase 3 Commit Atomico| SCRIBE
    SCRIBE --> MEM
    ANCHOR -. SSOT Ingestione .-> SCRIBE
```

---

## 📡 2. Protocollo IPC & Pointer-Only Return (RULE-10)

All'interno dell'Ecosistema NK, i sub-agenti isolati **non trasmettono mai testi estesi o codice sorgente grezzo** nella chat principale.

### Schema I/O Standard (OpenAPI 3.0 / Pydantic v2):
```json
{
  "status": "SUCCESS" | "FAIL" | "WARN",
  "timestamp": "ISO-8601 String",
  "target_file_uri": "g:/Il mio Drive/Antigravity/...",
  "summary": "Sommario massimo di 3 righe"
}
```

Questo garantisce che l'Agente Principale conservi sempre un **contesto leggero, veloce e fresco**.

---

## 🧪 3. Sandbox Ratchet Loop & Process-Tree Kill

Quando un Builder genera codice Python o System Instructions, il codice viene testato in un processo Sandbox isolato con:
- **Hard Timeout 10s**: Esecuzione monitorata da `psutil` con process-tree kill immediato in caso di loop infiniti.
- **Two-Phase Commit Atomico**: Scrittura su `.commit_ready` ➔ `os.replace` con Win32 Exponential Backoff.
- **Max 3 Cicli di Healing**: Se il test fallisce, la stack trace viene compressa (<80 token) e re-inviata al Builder per la correzione.
