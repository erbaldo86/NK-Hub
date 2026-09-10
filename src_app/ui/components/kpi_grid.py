"""LabNK UI Component: KPI Grid.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""


def render_kpi_grid(total_grants: int, open_grants: int, total_budget: float) -> str:
    """Genera la griglia dei KPI sintetici della dashboard."""
    return f"""    <!-- KPIs Metric Bar -->
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-title">Bandi Monitorati</div>
            <div class="kpi-value">{total_grants}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Bandi Aperti</div>
            <div class="kpi-value" style="color: var(--accent);">{open_grants}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Dotazione Totale Stanziata</div>
            <div class="kpi-value">€ {total_budget:,.0f}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Fonti Istituzionali</div>
            <div class="kpi-value">110+ Tier 1/2/3</div>
        </div>
    </div>"""
