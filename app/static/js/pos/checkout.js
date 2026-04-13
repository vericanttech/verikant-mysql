// Checkout and payment functionality
function getCartSubtotalHt() {
    if (!window.cart || !window.cart.length) return 0;
    return window.cart.reduce((s, item) => s + item.price * item.quantity, 0);
}

function updateCheckoutTotals() {
    const receiptDataElement = document.getElementById('receipt-data');
    if (!receiptDataElement) {
        console.warn('[POS TVA] updateCheckoutTotals: #receipt-data missing');
        return;
    }
    const currency = receiptDataElement.dataset.shopCurrency;
    const grossHt = getCartSubtotalHt();
    const discountApplyEl = document.getElementById('discount-apply');
    const discountPctEl = document.getElementById('discount-rate-percent');
    const discountApply = discountApplyEl && discountApplyEl.checked;
    let discountPct = 0;
    if (discountPctEl && discountPctEl.value !== '') {
        discountPct = parseFloat(String(discountPctEl.value).replace(',', '.')) || 0;
    }
    let discountAmt = 0;
    let netHt = grossHt;
    if (discountApply && discountPct > 0) {
        discountAmt = Math.round(grossHt * (discountPct / 100) * 100) / 100;
        netHt = Math.round((grossHt - discountAmt) * 100) / 100;
    }
    const applyEl = document.getElementById('vat-apply');
    const rateEl = document.getElementById('vat-rate-percent');
    const apply = applyEl && applyEl.checked;
    let ratePct = 18;
    if (rateEl && rateEl.value !== '') {
        ratePct = parseFloat(String(rateEl.value).replace(',', '.')) || 0;
    }
    const rate = ratePct / 100;
    let vatAmt = 0;
    let ttc = netHt;
    if (apply && ratePct > 0) {
        vatAmt = Math.round(netHt * rate * 100) / 100;
        ttc = netHt + vatAmt;
    }
    const subEl = document.getElementById('checkout-subtotal-ht');
    const netEl = document.getElementById('checkout-net-ht');
    const discountRow = document.getElementById('checkout-discount-row');
    const discountAmtEl = document.getElementById('checkout-discount-amount');
    const vatDisplay = document.getElementById('checkout-vat-amount');
    const modalTotal = document.getElementById('modal-total');
    if (subEl) subEl.textContent = `${formatNumberFR(grossHt.toFixed(2))} ${currency}`;
    if (netEl) netEl.textContent = `${formatNumberFR(netHt.toFixed(2))} ${currency}`;
    if (discountRow && discountAmtEl) {
        const showDisc = discountApply && discountPct > 0 && discountAmt > 0;
        discountRow.classList.toggle('hidden', !showDisc);
        discountAmtEl.textContent = showDisc
            ? `− ${formatNumberFR(discountAmt.toFixed(2))} ${currency} (${discountPct.toFixed(2).replace(/\.?0+$/, '')}%)`
            : '—';
    }
    if (vatDisplay) vatDisplay.textContent = `${formatNumberFR(vatAmt.toFixed(2))} ${currency}`;
    if (modalTotal) modalTotal.value = `${formatNumberFR(ttc.toFixed(2))} ${currency}`;
    window.__checkoutTtc = ttc;
    window.__checkoutApplyVat = !!(apply && ratePct > 0);
    window.__checkoutVatRatePercent = apply ? ratePct : 0;
    window.__checkoutApplyDiscount = !!(discountApply && discountPct > 0);
    window.__checkoutDiscountPercent = discountApply ? discountPct : 0;
}
window.updateCheckoutTotals = updateCheckoutTotals;

function getCheckoutTotalTtc() {
    if (typeof window.__checkoutTtc === 'number' && !isNaN(window.__checkoutTtc)) {
        return window.__checkoutTtc;
    }
    const cartTotal = document.getElementById('cart-total');
    if (!cartTotal) return 0;
    const rawTotal = cartTotal.textContent
        .replace(/[^\d,]/g, '')
        .replace(/\s/g, '')
        .replace(',', '.');
    return parseFloat(rawTotal) || 0;
}

function initCheckoutEventListeners() {
    const vatApply = document.getElementById('vat-apply');
    const vatRate = document.getElementById('vat-rate-percent');
    if (vatApply) {
        vatApply.addEventListener('change', function (e) {
            console.log('[POS TVA] vat-apply change', { checked: e.target.checked, id: e.target.id });
            updateCheckoutTotals();
        });
        vatApply.addEventListener('click', function (e) {
            console.log('[POS TVA] vat-apply click', { checked: e.target.checked });
        });
    } else {
        console.warn('[POS TVA] #vat-apply not found — TVA checkbox missing from DOM');
    }
    if (vatRate) {
        vatRate.addEventListener('input', function (e) {
            console.log('[POS TVA] vat-rate-percent input', { value: e.target.value });
            updateCheckoutTotals();
        });
    } else {
        console.warn('[POS TVA] #vat-rate-percent not found');
    }
    const discountApply = document.getElementById('discount-apply');
    const discountRate = document.getElementById('discount-rate-percent');
    if (discountApply) {
        discountApply.addEventListener('change', function () {
            updateCheckoutTotals();
        });
    }
    if (discountRate) {
        discountRate.addEventListener('input', function () {
            updateCheckoutTotals();
        });
    }

    // Calculate change
    document.getElementById('cash-received').addEventListener('input', function () {
        const total = getCheckoutTotalTtc();

        // Step 2: Get raw value from Cleave instance instead of parsing the formatted input
        const received = parseFloat(window.cashReceived.getRawValue()) || 0;
        const change = received - total;

        // Step 3: Update change display with formatted value
        const changeDisplay = document.getElementById('change-amount');
        changeDisplay.value = change >= 0
            ? `${formatNumberFR(change)} ${document.getElementById('receipt-data').dataset.shopCurrency}`
            : '';

        // Step 4: Enable/disable button
        const completeSaleBtn = document.getElementById('complete-sale-btn');
        completeSaleBtn.disabled = received < 0 || isNaN(received);

        if (completeSaleBtn.disabled) {
            completeSaleBtn.classList.add('opacity-50', 'cursor-not-allowed');
            completeSaleBtn.classList.remove('hover:bg-blue-600');
        } else {
            completeSaleBtn.classList.remove('opacity-50', 'cursor-not-allowed');
            completeSaleBtn.classList.add('hover:bg-blue-600');
        }
    });

    // Complete sale
    document.getElementById('complete-sale-btn').addEventListener('click', async function() {
        try {
            const billNumber = await getNextBillNumber();
            if (!billNumber) return;

            // Get the raw value from the Cleave instance instead of parsing the formatted string
            const cashReceivedValue = window.cashReceived.getRawValue();
            const cashReceivedAmount = parseFloat(cashReceivedValue) || 0;

            // Improved parsing of the total amount
            const cartTotal = document.getElementById('cart-total');
            const customerId = document.getElementById('selected-customer-id').value;

            if (isNaN(cashReceivedAmount) || cashReceivedAmount < 0) {
                showNotification('Veuillez entrer un montant valide', 'error');
                return;
            }

            if (typeof validateCartUnitPrice === 'function' && window.cart && window.cart.length) {
                for (const item of window.cart) {
                    const v = validateCartUnitPrice(item, item.price);
                    if (!v.ok) {
                        showNotification(v.message, 'error');
                        return;
                    }
                }
            }

            const applyVat = !!window.__checkoutApplyVat;
            const vatRatePct = window.__checkoutVatRatePercent;
            const applyDiscount = !!window.__checkoutApplyDiscount;
            const discountPct = window.__checkoutDiscountPercent || 0;
            console.log('[POS TVA] process_sale payload (vat)', { apply_vat: applyVat, vat_rate: applyVat ? vatRatePct : null });

            const response = await fetch('/api/process_sale', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    items: window.cart.map(item => ({
                        product_id: item.productId,
                        quantity: item.quantity,
                        price: item.price,
                        total: item.price * item.quantity
                    })),
                    bill_number: billNumber,
                    client_id: customerId || null,
                    initial_payment: cashReceivedAmount,
                    payment_method: 'cash',
                    apply_vat: applyVat,
                    vat_rate: applyVat ? vatRatePct : null,
                    apply_discount: applyDiscount,
                    discount_rate_percent: applyDiscount ? discountPct : null
                })
            });

            const result = await response.json();
            if (response.ok) {
                if (result.bill_id) {
                    window.lastBillId = result.bill_id;
                    document.getElementById('print-bill-btn').disabled = false;
                }
                showNotification('Vente terminée avec succès !', 'success');
                window.cart = [];
                localStorage.removeItem('pos_cart');
                updateCartDisplay();
            } else {
                throw new Error(result.error || 'Erreur lors du traitement de la vente');
            }
        } catch (error) {
            showNotification(`Erreur lors du traitement de la vente : ${error.message}`, 'error');
        }
    });

    // Print bill functionality
    document.getElementById('print-bill-btn').addEventListener('click', async function () {
        if (!window.lastBillId) {
            showNotification('Aucune facture à imprimer', 'error');
            return;
        }

        const print_format = document.getElementById('print-format').value;

        if (print_format === 'bluetooth') {
            try {
                // Fetch bill data
                const response = await fetch(`/bills/${window.lastBillId}/print/bluetooth`);
                const billData = await response.json();
                showNotification('Raw bill data: ' + JSON.stringify(billData), 'info');

                // Connect to the Bluetooth printer
                const device = await navigator.bluetooth.requestDevice({
                    filters: [
                        { namePrefix: 'YCP807-UB' },
                        { namePrefix: 'POS' }
                    ],
                    optionalServices: ['000018f0-0000-1000-8000-00805f9b34fb']
                });

                const server = await device.gatt.connect();
                const service = await server.getPrimaryService('000018f0-0000-1000-8000-00805f9b34fb');
                const characteristic = await service.getCharacteristic('00002af1-0000-1000-8000-00805f9b34fb');

                // Format receipt data and encode
                const printData = formatReceiptData(billData.bill_data);
                const encoder = new TextEncoder();
                const data = encoder.encode(printData);

                // Send data in chunks of up to 512 bytes
                const CHUNK_SIZE = 256; // Reduced chunk size
                for (let i = 0; i < data.length; i += CHUNK_SIZE) {
                    const chunk = data.slice(i, i + CHUNK_SIZE);
                    await characteristic.writeValue(chunk);
                    // Add a small delay between chunks
                    await new Promise(resolve => setTimeout(resolve, 50));
                }

                showNotification('Impression terminée', 'success');
            } catch (error) {
                console.error('Bluetooth printing error:', error);
                showNotification('Erreur d\'impression Bluetooth: ' + error.message, 'error');
            }
        } else {
            // Non-Bluetooth printing (web-based)
            try {
                const printWindow = window.open(`/bills/${window.lastBillId}/print/${print_format}`, '_blank');
                if (printWindow) {
                    printWindow.focus();
                } else {
                    showNotification('Veuillez autoriser les popups pour imprimer la facture', 'error');
                }
            } catch (error) {
                console.error('Error printing bill:', error);
                showNotification('Erreur lors de l\'impression de la facture', 'error');
            }
        }
    });
}

async function getNextBillNumber() {
    try {
        const response = await fetch('/api/get_next_bill_number');
        const data = await response.json();
        if (response.ok) {
            return data.bill_number;
        } else {
            throw new Error(data.error || 'Failed to get bill number');
        }
    } catch (error) {
        console.error('Error getting bill number:', error);
        showNotification('Error getting bill number', 'error');
        return null;
    }
}

function formatReceiptData(data) {
    showNotification('Formatting receipt data...', 'info');

    const receiptDataElement = document.getElementById('receipt-data');
    const shopName = receiptDataElement.dataset.shopName;
    const shopPhones = JSON.parse(receiptDataElement.dataset.shopPhones);
    const shopAddress = receiptDataElement.dataset.shopAddress;
    const shopCurrency = receiptDataElement.dataset.shopCurrency;

    let cmds = '';
    // Initialize printer
    cmds += '\x1B\x40';     // Initialize
    cmds += '\x1B\x21\x00'; // Normal font
    cmds += '\x1D\x21\x00'; // Normal size
    cmds += '\x1B\x74\x00'; // CP437 charset

    // Header - Centered
    cmds += '\x1B\x61\x01'; // Center align
    cmds += '\x1B\x21\x08'; // Emphasized
    cmds += `${shopName}\n`;
    cmds += '\x1B\x21\x00'; // Normal

    if (shopPhones && shopPhones.length > 0) {
        cmds += 'Tel: ';
        shopPhones.forEach((phone, index) => {
            cmds += phone.phone;
            if (index < shopPhones.length - 1) {
                cmds += ', ';
            }
        });
        cmds += '\n';
    }

    if (shopAddress) {
        cmds += `${shopAddress}\n`;
    }
    cmds += '\n';

    // Reset alignment before bill info
    cmds += '\x1B\x61\x00'; // Left align
    cmds += `Facture #: ${data.bill_number || ''}\n`;
    cmds += `Date: ${data.date || ''}\n`;
    cmds += '-'.repeat(45) + '\n';

    if (data.client) {
        cmds += `Client: ${data.client.name || ''}\n`;
        if (data.client.phone) {
            cmds += `Tel: ${data.client.phone}\n`;
        }
    }
    cmds += '\n';

    // Table header
    cmds += 'Article                  Qte  Prix    Total\n';
    cmds += '-'.repeat(45) + '\n';

    // Items
    if (Array.isArray(data.items)) {
        data.items.forEach(item => {
            const name = item.name || '';
            const lines = chunkString(name, 20);

            // First line with all columns - preserve original number format
            cmds += `${lines[0].padEnd(20)}     ${item.quantity}x   ${item.price}    ${item.total}\n`;

            // Additional lines for long product names
            for (let i = 1; i < lines.length; i++) {
                cmds += lines[i] + '\n';
            }
        });
    }

    cmds += '-'.repeat(45) + '\n';

    // Reset alignment before totals
    cmds += '\x1B\x61\x00'; // Reset to left align first
    const formatNumber = (num) => {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    };

    // Calculate padding for right alignment
    const lineWidth = 40; // Total line width
    // Format currency correctly
    const currencyText = ` ${shopCurrency}`;

    const discAmt = data.discount_amount != null ? Number(data.discount_amount) : 0;
    const grossHt = data.gross_amount_ht != null ? Number(data.gross_amount_ht) : null;
    if (discAmt > 0 && grossHt != null) {
        cmds += `Sous-total HT:${" ".repeat(Math.max(0, lineWidth - 14 - formatNumber(grossHt).length - currencyText.length))}${formatNumber(grossHt)}${currencyText}\n`;
        const dr = data.discount_rate != null ? Number(data.discount_rate) : 0;
        const dPct = dr > 0 && dr <= 1 ? (dr * 100).toFixed(2).replace(/\.?0+$/, '') : '';
        cmds += `Remise${dPct ? ' (' + dPct + '%)' : ''}:${" ".repeat(Math.max(0, lineWidth - 8 - formatNumber(discAmt).length - currencyText.length))}-${formatNumber(discAmt)}${currencyText}\n`;
    }
    const vatAmt = data.vat_amount != null ? Number(data.vat_amount) : 0;
    if (vatAmt > 0 && data.amount_ht != null) {
        cmds += `Total HT:${" ".repeat(Math.max(0, lineWidth - 9 - formatNumber(data.amount_ht).length - currencyText.length))}${formatNumber(data.amount_ht)}${currencyText}\n`;
        const vr = data.vat_rate != null ? Number(data.vat_rate) : 0;
        const ratePctDisplay = vr > 0 && vr <= 1 ? (vr * 100).toFixed(2).replace(/\.?0+$/, '') : (vr > 0 ? String(vr) : '');
        cmds += `TVA${ratePctDisplay ? ' (' + ratePctDisplay + '%)' : ''}:${" ".repeat(Math.max(0, lineWidth - 6 - formatNumber(vatAmt).length - currencyText.length))}${formatNumber(vatAmt)}${currencyText}\n`;
        cmds += '-'.repeat(45) + '\n';
    } else if (discAmt > 0 && data.amount_ht != null && vatAmt <= 0) {
        cmds += `HT apres remise:${" ".repeat(Math.max(0, lineWidth - 15 - formatNumber(data.amount_ht).length - currencyText.length))}${formatNumber(data.amount_ht)}${currencyText}\n`;
        cmds += '-'.repeat(45) + '\n';
    }

    // Format TOTAL (TTC)
    const totalValue = formatNumber(data.total_amount);
    const totalLabel = "TOTAL:";
    const totalPadding = lineWidth - totalLabel.length - totalValue.length - currencyText.length;
    cmds += `${totalLabel}${" ".repeat(totalPadding)}${totalValue}${currencyText}\n`;

    if (data.paid_amount) {
        // Format PAYE
        const payeValue = formatNumber(data.paid_amount);
        const payeLabel = "Paye:";
        const payePadding = lineWidth - payeLabel.length - payeValue.length - currencyText.length;
        cmds += `${payeLabel}${" ".repeat(payePadding)}${payeValue}${currencyText}\n`;

        // Format RESTE
        const resteValue = formatNumber(data.remaining_amount);
        const resteLabel = "Reste:";
        const restePadding = lineWidth - resteLabel.length - resteValue.length - currencyText.length;
        cmds += `${resteLabel}${" ".repeat(restePadding)}${resteValue}${currencyText}\n`;
    }

    // Center align for thank you message
    cmds += '\x1B\x61\x01'; // Center align
    cmds += '\nMerci de votre confiance!\n\n';

    // Set barcode height - reduce from default
    cmds += '\x1D\x68\x30';  // Height: 48 dots (about 6mm) - you can adjust this value (range 1-255)

    // Set barcode width
    cmds += '\x1D\x77\x03';  // Width: 3 (slightly wider than default) - range is 2-6

    // Center alignment for barcode
    cmds += '\x1B\x61\x01';  // Center align

    // Print barcode
    cmds += '\x1D\x6B';      // GS k
    cmds += '\x04';          // Select CODE39
    cmds += data.bill_number; // Data to encode
    cmds += '\x00';          // NUL - End of data

    // Add some spacing after barcode
    cmds += '\n'.repeat(4);  // Reduced spacing after barcode

    // Cut paper
    cmds += '\x1D\x56\x00';

    return cmds;
}

// Helper function to chunk strings
function chunkString(str, length) {
    const chunks = [];
    let remaining = str;
    while (remaining.length > 0) {
        chunks.push(remaining.slice(0, length));
        remaining = remaining.slice(length);
    }
    return chunks.length ? chunks : [''];
}