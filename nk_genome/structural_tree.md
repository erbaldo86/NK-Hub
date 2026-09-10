# 🏛️ NK Genome: Structural Tree Master (v1.7.0-RepoMap Refined)
### *Albero Strutturale, Contratti di Modulo & Topologia Ecosistema Antigravity*

> **Badge di Certificazione:** 🛡️ [NK-SUPER-BRIEF-STATUS: AUDITED_AND_OPTIMIZED 🟢]  
> **Milestone Anchor:** `NK-MS-20260910-AST-REPOMAP-V170`  
> **Versione Target:** `v1.7.0-RepoMap`  

---

## 🌳 1. Mappatura della Topologia del Repository

```text
G:/Il mio Drive/Antigravity/
├── .agents/
│   ├── AGENTS.md                                # Regolamento di Sistema v1.6.0-VibeEnhanced
│   ├── rules/
│   │   └── anti_crash_rules.md                  # Regole di protezione Windows, Win32 & I/O
│   └── skills/                                  # 16 Skill Vocazionali Canoniche
│       ├── NK-Master-Hub/                       # Sovrano Infrastrutturale L3 (2PC Mutex)
│       ├── NK-Session-Controller/               # Sovrano Critico (Repo-Map Graduated Injector)
│       ├── NK-Python-Async-Builder/             # Builder Core (Staging Builder)
│       ├── NK-Delta-Architect/                  # Patch Architect (Two-Stage Grounding)
│       ├── NK-Bug-Diagnostic-Engine/            # RCA Engine (SBFL Ochiai + Call Graph)
│       ├── NK-Security-Auditor/                 # Threat Audit L1/L2/L3
│       ├── NK-Oracle-Evaluator/                 # Oracolo Deterministico Cold Audit
│       ├── NK-App-UX-Architect/                 # UI/UX Architect (Frontend Skeleton)
│       └── ... (altre 8 skill vocazionali)
├── .github/
│   ├── workflows/
│   │   └── ci.yml                               # GitHub Actions CI Continuous Verification
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.yml                       # Form guidato segnalazione bug
│       └── feature_request.yml                  # Form guidato proposte feature
├── nk_genome/                                   # Single Source of Truth Concettuale (Tetralogia Sovrana)
│   ├── concept_map.md                           # Master Brief & Concept Map v1.7.0-RepoMap Refined
│   ├── structural_tree.md                       # Topologia & Contratti dei Moduli v1.7.0 Refined
│   ├── implementation_plan.md                   # Piano Operativo & Roadmap v1.7.0 Refined
│   ├── repo_map.md                              # Snapshot Permanente AST Repo-Map (Nuovo 4° Pilastro)
│   └── PATCH_NOTES.md                           # Changelog SSOT Ufficiale
├── nk_tracking/                                 # Tracciamento e Baseline
│   ├── anchor/
│   │   └── session_anchor.jsonl                 # SSOT Activity Anchor
│   ├── quality_baseline.json                    # Ratchet Baseline di Qualità (109 Test / 100.0% PASS)
│   └── reports_and_briefs/                      # Audit Reports & Telemetria
├── scripts/                                     # Motori Core & Infrastruttura di Sistema
│   ├── __init__.py
│   ├── ast_guard_validator.py                   # Static AST Guard (PEP 634/695)
│   ├── ast_repo_mapper.py                       # High-Density AST Repo-Map Engine (v1.7.0 UPGRADED)
│   ├── async_heartbeat_signaler.py              # Anti-Freeze Pulse Sentinel (15-20s pulse)
│   ├── dast_sandbox_runner.py                   # Real DAST Sandbox Runner & Line Tracer
│   ├── invisible_healing_loop.py                # Autonomous Triage Fast-Loop (Max 3 cicli)
│   ├── memory_3tier_engine.py                   # 3-Tier Memory Engine (Tier 1 <=350 tok)
│   ├── oracle_evaluator_l3.py                   # Oracolo Deterministico L3
│   ├── preflight_health_check.py                # Boot Sanitizer & WAL TTL 60s Purge
│   ├── quality_baseline_manager.py              # Baseline Compliance & Ratchet Check
│   ├── safe_cleanup_dev_servers.py              # Anti-Lock & Server Process Cleanup
│   ├── sbfl_engine.py                           # Spectrum-Based Fault Localization
│   ├── vibe_sprint_router.py                    # Vibe Coding Triple-Speed Router (Mode C/B/A)
│   ├── win32_2pc_engine.py                      # Win32 Named Mutex & 2PC Atomic Engine
│   └── schemas/                                 # Contratti Pydantic v2 Strict Mode
├── tests/                                       # Suite Permanente di Piattaforma (109 Test / 15 File)
│   ├── test_win32_2pc.py
│   ├── test_dast_sandbox.py
│   ├── test_ast_repo_mapper.py                  # Test Suite Repo-Map Engine (Expanded)
│   ├── test_ast_guard_validator.py
│   ├── test_memory_3tier.py
│   ├── test_sbfl_engine.py
│   ├── test_invisible_healing_loop.py
│   ├── test_schemas_and_contracts.py
│   └── test_oracle_ground_truth_l3.py
├── LICENSE                                      # Licenza MIT Ufficiale
├── README.md                                    # Presentazione Master in Inglese (Default)
├── README.it.md                                 # Presentazione Master in Italiano
├── requirements.txt                             # Dipendenze con vincoli rigidi
└── install.ps1 / install.sh                     # Setup ambiente automatico
```

---

## 📋 2. Contratti del Modulo `scripts/ast_repo_mapper.py` (v1.7.0 Refined)

| Struttura / Metodo | Input | Output | Invariante Architetturale |
| :--- | :--- | :--- | :--- |
| `RepoMapConfig` | `max_tokens: int = 1024`, `mode: str = 'auto'`, `cache_dir: Optional[Path] = None`, `polyglot: bool = True`, `focal_files: List[str] = []` | Modello Pydantic v2 Validato | Valida la coerenza dei tetti di token ($\ge 128, \le 4096$) |
| `RepoMapGenerator.generate()` | `root_dir: Path`, `config: RepoMapConfig` | `RepoMapResult` (`content: str`, `token_count: int`, `cached: bool`, `elapsed_ms: float`) | Applica Two-Tier Clustering e Karpathy Slicer multi-focale |
| `IncrementalFileCache` | `file_path: Path` | `Optional[List[SymbolNode]]` | Hit cache se `mtime` e `size` invariati; re-parse solo se modificato |
| `AtomicCacheManager` | `payload: dict`, `cache_path: Path` | `None` (Atomico) | Scrittura su `repo_map_cache.<uuid>.tmp` e `os.replace` atomico |
| `PolyglotExtractor` | `file_path: Path`, `source: str` | `List[SymbolNode]` | Parsing resiliente a stub incompleti per Python, JS, TS, HTML, CSS |
| `GraduatedSkillAdapter` | `skill_name: str`, `speed_mode: str` | `int` (Token Cap dedicato) | 256 tok Mode C, 512 tok Mode B, 1024 tok Mode A, 0 tok Blacklist |
| `CLI Interface` | Argomenti CLI (`--repo-map`, `--mode`, `--tokens`, `--json`) | Stdout / JSON | Esecuzione rapida senza dipendenze esterne |
