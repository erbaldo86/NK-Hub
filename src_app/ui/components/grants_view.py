"""LabNK UI Component: Grants Catalog View.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""


def render_grants_view() -> str:
    """Genera la sezione del catalogo completo bandi CGM e la search box."""
    return """    <!-- 3. TAB CATALOGO COMPLETO -->
    <div id="catalog-tab" class="tab-content">
        <div class="search-box">
            <input type="text" id="catalog-search" class="search-input" placeholder="Filtra catalogo per titolo, ente o settore..." onkeyup="filterCatalog()">
        </div>
        <div id="grants-container-catalog" class="grants-grid"></div>
    </div>"""
