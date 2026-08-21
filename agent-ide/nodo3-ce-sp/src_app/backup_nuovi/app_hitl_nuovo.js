let globalState = {
    ledger: {},
    exceptionsQueue: []
};

document.getElementById('uploadBtn').addEventListener('click', async () => {
    const fileInput = document.getElementById('fileUpload');
    if (!fileInput.files[0]) return;

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        const response = await fetch("http://localhost:8000/api/v1/ingest/parse_pdf", {
            method: "POST",
            body: formData
        });
        const data = await response.json();
        
        globalState.exceptionsQueue = data.exceptions_queue || [];
        if (data.ledger && data.ledger.length > 0) {
            globalState.ledger = data.ledger[0];
            renderLedger();
        }
        renderExceptions();

    } catch (e) {
        console.error("Error parsing", e);
    }
});

function renderExceptions() {
    const section = document.getElementById('reconciliationHub');
    const tbody = document.querySelector('#exceptionsTable tbody');
    tbody.innerHTML = '';
    
    if (globalState.exceptionsQueue.length > 0) {
        section.classList.remove('hidden');
        globalState.exceptionsQueue.forEach(exc => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${exc.year}</td>
                <td>${exc.type}</td>
                <td>${exc.description}</td>
                <td>${exc.suggested_mapping}</td>
                <td contenteditable="true" class="limbo-amount">${exc.amount}</td>
                <td>${exc.confidence || '-'}</td>
                <td>
                    <button onclick="approveException('${exc.id}', '${exc.suggested_mapping}')">Approve</button>
                </td>
            `;
            
            const amtCell = tr.querySelector('.limbo-amount');
            amtCell.addEventListener('input', () => {
                amtCell.classList.add('manual-override');
                exc.amount = parseFloat(amtCell.innerText);
            });
            tbody.appendChild(tr);
        });
    } else {
        section.classList.add('hidden');
    }
}

function renderLedger() {
    const status = document.getElementById('quadraturaStatus');
    if (globalState.ledger.isQuadrato) {
        status.innerHTML = 'Status: <span class="quadratura-ok">Quadrato 🟢</span>';
    } else {
        status.innerHTML = 'Status: <span class="quadratura-ko">Sbilanciato 🔴</span>';
    }

    const fields = ['ricavi', 'altri_ricavi', 'tot_ricavi'];
    fields.forEach(field => {
        const row = document.querySelector(`tr[data-field="${field}"]`);
        if (row && globalState.ledger[field]) {
            const amountCell = row.querySelector('.amount-cell');
            const confCell = row.querySelector('.conf-cell');
            const actionCell = row.querySelector('.action-cell');
            
            // Only update if not already manually overridden
            if (!amountCell.classList.contains('manual-override')) {
                amountCell.innerText = globalState.ledger[field].value;
                confCell.innerText = globalState.ledger[field].confidence;
            }
        }
    });
}

// Add event listeners for god mode on ledger
document.querySelectorAll('.amount-cell').forEach(cell => {
    cell.addEventListener('input', (e) => {
        const row = e.target.closest('tr');
        const field = row.getAttribute('data-field');
        
        cell.classList.add('manual-override');
        
        const actionCell = row.querySelector('.action-cell');
        if (!actionCell.innerHTML.includes('✏️')) {
            actionCell.innerHTML += '<span class="pencil-icon" title="Manual Override">✏️</span>';
        }

        // Update local state (in a real app, we might recalculate quadratura here)
        if (!globalState.ledger[field]) globalState.ledger[field] = {};
        globalState.ledger[field].value = parseFloat(cell.innerText);
        
        console.log(`MANUAL_OVERRIDE on ${field}: new value ${cell.innerText}`);
    });
});

window.approveException = function(id, suggested_mapping) {
    const excIndex = globalState.exceptionsQueue.findIndex(e => e.id === id);
    if (excIndex > -1) {
        const exc = globalState.exceptionsQueue[excIndex];
        
        // Move to ledger
        if (!globalState.ledger[suggested_mapping]) {
            globalState.ledger[suggested_mapping] = {};
        }
        globalState.ledger[suggested_mapping].value = exc.amount;
        
        // Remove from limbo
        globalState.exceptionsQueue.splice(excIndex, 1);
        
        // Mark cell as manual override
        const row = document.querySelector(`tr[data-field="${suggested_mapping}"]`);
        if (row) {
            const cell = row.querySelector('.amount-cell');
            cell.innerText = exc.amount;
            cell.classList.add('manual-override');
            const actionCell = row.querySelector('.action-cell');
            if (!actionCell.innerHTML.includes('✏️')) {
                actionCell.innerHTML += '<span class="pencil-icon" title="Manual Override">✏️</span>';
            }
        }
        
        renderExceptions();
    }
};
