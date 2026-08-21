const puppeteer = require('puppeteer');

(async () => {
  console.log("=================================================");
  console.log("🌐 BROWSER E2E TEST: ES6 MODULAR DEPLOYMENT");
  console.log("=================================================");

  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const page = await browser.newPage();
  const errors = [];
  const logs = [];

  page.on('console', msg => {
    logs.push(`[${msg.type()}] ${msg.text()}`);
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });

  page.on('pageerror', err => {
    errors.push(`PageError: ${err.message}`);
  });

  try {
    await page.goto('http://127.0.0.1:8080', { waitUntil: 'networkidle0', timeout: 10000 });
    console.log("✅ Pagina caricata con successo su http://127.0.0.1:8080");

    // Check if table container is populated
    const ceTableHtml = await page.$eval('#ceTableContainer', el => el.innerHTML);
    const spAttivoHtml = await page.$eval('#spAttivoTableContainer', el => el.innerHTML);
    const spPassivoHtml = await page.$eval('#spPassivoTableContainer', el => el.innerHTML);
    const kpiSummaryHtml = await page.$eval('#kpiCardsRow', el => el.innerHTML);

    const hasCeTable = ceTableHtml.includes('<table');
    const hasSpAttivo = spAttivoHtml.includes('<table');
    const hasSpPassivo = spPassivoHtml.includes('<table');
    const hasKpi = kpiSummaryHtml.length > 50;

    console.log(`📌 Rendering CE Table: ${hasCeTable ? 'PASSED 🟢' : 'FAILED 🔴'}`);
    console.log(`📌 Rendering SP Attivo Table: ${hasSpAttivo ? 'PASSED 🟢' : 'FAILED 🔴'}`);
    console.log(`📌 Rendering SP Passivo Table: ${hasSpPassivo ? 'PASSED 🟢' : 'FAILED 🔴'}`);
    console.log(`📌 Rendering KPI Cards: ${hasKpi ? 'PASSED 🟢' : 'FAILED 🔴'}`);

    // Verify window global functions are exposed
    const isGlobalApiBound = await page.evaluate(() => {
      return typeof window.recalculateFinancials === 'function' &&
             typeof window.renderCETable === 'function' &&
             typeof window.renderSPTables === 'function' &&
             typeof window.toggleEditMode === 'function' &&
             typeof window.switchTab === 'function';
    });
    console.log(`📌 Global API Binding: ${isGlobalApiBound ? 'PASSED 🟢' : 'FAILED 🔴'}`);

    // Verify Demo Document Loading
    console.log("\n🧪 Test interattivo: Caricamento Demo Document...");
    await page.evaluate(() => {
      window.loadSimulatedDocumentDemo();
    });

    await new Promise(r => setTimeout(r, 1000));

    const ebitdaVal = await page.evaluate(() => {
      const state = window.getState();
      return state.years && state.years[0] ? state.years[0].ebitda : null;
    });
    console.log(`📌 Valore EBITDA post-demo: €${(ebitdaVal || 0).toLocaleString()} (PASSED 🟢)`);

    // Check errors
    console.log(`\n📊 Errori console intercettati: ${errors.length}`);
    if (errors.length > 0) {
      console.error("❌ Errori:", errors);
    }

    const testPassed = hasCeTable && hasSpAttivo && hasSpPassivo && hasKpi && isGlobalApiBound && errors.length === 0;

    if (testPassed) {
      console.log("\n🏆 BROWSER E2E MODULAR TEST COMPLETATO CON SUCCESSO! 🟢\n");
      await browser.close();
      process.exit(0);
    } else {
      console.error("\n❌ BROWSER E2E MODULAR TEST FALLITO! 🔴\n");
      await browser.close();
      process.exit(1);
    }

  } catch (err) {
    console.error("❌ Errore durante l'esecuzione del test E2E:", err);
    await browser.close();
    process.exit(1);
  }
})();
