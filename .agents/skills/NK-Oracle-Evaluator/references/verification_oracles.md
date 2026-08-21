# 🔬 Specifiche Operative degli Oracoli Deterministici (CRV 2.0)

## 1. DOM Reader Oracle (Chrome DevTools / Puppeteer)
- **Scopo:** Ispezionare gli elementi reali del DOM renderizzato dall'applicazione web nel browser.
- **Tool Usato:** `chrome-devtools-mcp` -> `evaluate_script` oppure `puppeteer` -> `puppeteer_evaluate`.
- **Timeout:** 20 secondi (con kill ricorsivo `psutil` in caso di hang).
- **Regola:** Leggere `innerText` o `value` dei selettori specificati nel test (es. `#ceTableBody tr:last-child td:nth-child(2)`).

## 2. AST & Sandbox Oracle (Python Execution Engine)
- **Scopo:** Eseguire l'analisi sintattica (`ast.parse`) e i test unitari in un ambiente effimero (%TEMP%).
- **Timeout:** 10 secondi.
- **Requisito:** Exit Code `0`. Qualsiasi exit code > 0 determina la bocciatura immediata della patch.

## 3. Math Ground Truth Oracle (Extractor Engine)
- **Scopo:** Estrarre la tabella di verità (Ground Truth) direttamente dal file sorgente dell'utente (ODS, PDF, XLSX) tramite librerie esterne isolate (`pandas`, `ezodf`, `pypdf`).
- **Verifica:** Calcolo della discrepanza assoluta $| \text{Valore DOM} - \text{Valore Sorgente} |$. Tolleranza massima per arrotondamenti: $\le €0.01$.

## 4. Visual Layout Oracle (Visual Diffing)
- **Scopo:** Catturare uno screenshot headless tramite Puppeteer per verificare assenza di sovrapposizioni visive o UI freeze.
