# 🗺️ HIGH-DENSITY AST REPO-MAP (Tetralogia Sovrana Snapshot)

## 📄 scripts/ast_repo_mapper.py
  class SymbolType(str, Enum):
  class EdgeType(str, Enum):
  class SymbolNode(BaseModel):
  class SymbolEdge(BaseModel):
  class SymbolGraph(BaseModel):
  class PageRankResult(BaseModel):
  class SliceResult(BaseModel):
  class RepoMapConfig(BaseModel):
  class RepoMapResult(BaseModel):
  class ResilientParser:
  class SymbolExtractor(ast.NodeVisitor):
  class PolyglotExtractor:
  class PersonalizedPageRank:
  class KarpathySurgicalSlicer:
  class AtomicCacheManager:
  class RepoMapGenerator:
  class GraduatedSkillAdapter:
  def estimate_tokens(text: str) -> int
  def export_markdown_snapshot(root_dir: Path, output_path: Path, max_tokens: int=1024) -> RepoMapResult
  def main() -> None

## 📄 scripts/micro_hud_renderer.py
  class GateEntry(BaseModel):
  class HUDState(BaseModel):
  class MicroHUDRenderer:
    def __init__(self, version: str='v1.1', default_gates: Optional[Sequence[str]]=('G1', 'G2', 'G3', 'G4', 'G5'), bar_width: int=10) -> None
    def set_progress(self, percent: int) -> MicroHUDRenderer
    def set_gate(self, gate_id: str, status: GateStatus, description: Optional[str]=None) -> MicroHUDRenderer
    def set_all_gates(self, statuses: Dict[str, GateStatus]) -> MicroHUDRenderer
    def set_mutex(self, status: MutexStatus) -> MicroHUDRenderer
    def set_tier1_budget(self, used: int, cap: int=350) -> MicroHUDRenderer
    def set_agent_context(self, agent_id: str, domain: Optional[str]=None) -> MicroHUDRenderer
    def set_elapsed_time(self, seconds: float) -> MicroHUDRenderer
    def _build_progress_bar(self) -> str
    def _build_gates_string(self) -> str
    def render(self, include_extras: bool=False) -> str
    def render_markdown_block(self, include_extras: bool=False) -> str
    def render_pulse(cls, step: str, percent: int, pulse_status: str='ALIVE') -> str

## 📄 .agents/skills/NK-Master-Hub/scripts/test_hub.py
  def raises(expected_exception)
  def assert_raises(exc_type, func, *args, **kwargs)
  def test_pid_exists()
  def test_process_safe_file_lock()
  def test_process_safe_file_lock_orphan()
  def test_ipc_payload_nesting_validator()
  def test_change_router_cycle_detection()
  def test_change_router_depth_limit()
  def test_change_router_valid_sort()
  def test_safe_parser()
  def test_orchestrator_flow()

## 📄 scripts/safe_cleanup_dev_servers.py
  def get_pids_listening_on_ports(ports)
  def kill_pid_tree(pid)
  def run_cleanup()

### 📦 Moduli Secondari (Riepilogo Compatto)
- `scripts/ast_guard_validator.py`: (52 simboli: ViolationType, SYNTAX_ERROR, SIGNATURE_MUTATION +49)
- `scripts/sbfl_engine.py`: (31 simboli: SpectrumCounts, total_failed, total_passed +28)
- `scripts/memory_3tier_engine.py`: (41 simboli: MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MOVEFILE_COPY_ALLOWED +38)
- `scripts/dast_sandbox_runner.py`: (27 simboli: _HAS_PSUTIL, psutil, SandboxConfig +24)
- `src_app/ui/dashboard.py`: (8 simboli: ASSETS_DIR, STYLES_PATH, CLIENT_JS_PATH +5)
- `src_app/catalog/repository.py`: (17 simboli: GrantsRepository, __init__, _index_grant +14)
- `tests/test_document_processing_step3.py`: (10 simboli: create_sample_pdf, create_sample_zip, test_pdf_extractor_metadata_and_pages +7)
- `scripts/schemas/dual_ledgers.py`: (29 simboli: TaskStatus, EventType, canonical_json_bytes +26)
- `scripts/invisible_healing_loop.py`: (21 simboli: T, estimate_token_count, SBFLLocation +18)
- ... [+109 altri moduli secondari omessi per budget]
