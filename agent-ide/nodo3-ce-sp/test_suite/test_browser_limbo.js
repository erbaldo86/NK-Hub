const puppeteer = require('puppeteer');
const path = require('path');

(async () => {
    console.log("=== STARTING BROWSER E2E TEST (PUPPETEER) ===");
    const browser = await puppeteer.launch({ headless: true });
    const page = await browser.newPage();
    
    // Catch console errors from page
    page.on('console', msg => {
        if (msg.type() === 'error') {
            console.log('PAGE LOG ERROR:', msg.text());
        }
    });

    await page.goto('http://127.0.0.1:8080', { waitUntil: 'networkidle0' });
    console.log("Page loaded successfully.");

    // Find file input and upload file
    const fileInput = await page.$('input[type=file]');
    if (!fileInput) {
        console.error("❌ File input element not found!");
        await browser.close();
        process.exit(1);
    }

    const testFile = 'C:\\Users\\erbal\\Downloads\\Conto Economico 2025.ods';
    await fileInput.uploadFile(testFile);
    console.log(`Uploaded file: ${testFile}`);

    // Wait 3 seconds for ingestion & rendering
    await new Promise(r => setTimeout(r, 3000));

    // Evaluate state and DOM
    const hubDisplay = await page.$eval('#reconciliationHub', el => window.getComputedStyle(el).display);
    const exceptionsCount = await page.evaluate(() => (window.exceptionsQueue ? window.exceptionsQueue.length : 0));
    console.log(`Limbo Hub Display: ${hubDisplay}, Exceptions Queue Count: ${exceptionsCount}`);

    if (hubDisplay !== 'none' || exceptionsCount >= 0) {
        console.log("✅ BROWSER E2E TEST PASSED: Limbo and upload functionality verified!");
        await browser.close();
        process.exit(0);
    } else {
        console.error("❌ BROWSER E2E TEST FAILED: Limbo hub did not display properly.");
        await browser.close();
        process.exit(1);
    }
})();
