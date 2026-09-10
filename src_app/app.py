"""LabNK Bandi Intelligence — Sovereign Facade & CLI Runner.
Nexus Keystone v1.1.0-Universal | Zero-Mock Engine.
"""

from pathlib import Path
from .core.bootstrap import bootstrap_demo_service, bootstrap_live_service
from .ui.dashboard import DashboardRenderer

__all__ = ["bootstrap_demo_service", "bootstrap_live_service", "main"]


def main() -> None:
    """Esegue la demo da linea di comando e genera la dashboard HTML offline."""
    print("=" * 70)
    print("LAB-NK BANDI INTELLIGENCE — AVVIO SISTEMA")
    print("=" * 70)
    service = bootstrap_demo_service()
    print(f"[+] Database inizializzato: {len(service.list_all_grants())} bandi caricati.")

    prompt = (
        "Cerco finanziamenti a fondo perduto per una startup a Napoli per fare "
        "sviluppo software di intelligenza artificiale"
    )
    print(f"\n[?] [PROVA 1] Esecuzione Ricerca NLP: '{prompt}'")
    intent, ranked_grants, scores = service.search_nlp(prompt)
    if ranked_grants:
        print(f"    -> Intento: Regione={intent.inferred_region} | ATECO={intent.inferred_ateco_codes}")
        print(f"    -> Miglior Risultato: '{ranked_grants[0].titolo}' | Score: {scores[0].overall_match_score}%")

    html_content = DashboardRenderer.render_html(service)
    root_dir = Path(__file__).resolve().parent.parent
    out_path = root_dir / "dashboard.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\n[+] [PROVA 2] Dashboard HTML generata in: {out_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
