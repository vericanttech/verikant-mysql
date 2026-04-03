<script>
document.addEventListener('DOMContentLoaded', function() {
    // Initialize variables
    window.cart = window.cart || [];
    const cartItems = document.getElementById('cart-items');
    const cartTotal = document.getElementById('cart-total');
    const checkoutBtn = document.getElementById('checkout-btn');
    const searchInput = document.getElementById('product-search');

    const customerSearch = document.getElementById('customer-search');
    const customerDetails = document.getElementById('customer-details');
    let selectedCustomer = null;

    // Make modal functions globally accessible
    window.closeModal = function(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('hidden');
            document.body.style.overflow = 'auto';
        }
    };

    // Enhance the existing modal close function a wrapper function?!
    const originalCloseModal = window.closeModal;
    window.closeModal = function(modalId) {
        if (modalId === 'checkoutModal') {
            clearCustomerSelection();
            window.lastBillId = null;
            document.getElementById('print-bill-btn').disabled = true;
        }
        originalCloseModal(modalId);
    };

    window.openModal = function(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden';
        }
    };

    // Update cart display function
    function updateCartDisplay() {
        cartItems.innerHTML = '';
        let total = 0;

        window.cart.forEach((item, index) => {
            const itemTotal = item.price * item.quantity;
            total += itemTotal;

            const itemElement = document.createElement('div');
            itemElement.className = 'flex justify-between items-center p-3 border border-gray-200 rounded-lg';
itemElement.innerHTML = `
    <div class="flex-1">
        <h6 class="font-medium text-gray-900">${item.name}</h6>
        <div class="text-sm text-gray-500">
            <input type="number"
                   class="price-input w-24 px-2 py-1 border rounded"
                   value="${item.price.toFixed(2)}"
                   data-index="${index}"
            /> {{ shop_profile.currency|default('FCFA') }} × ${item.quantity}
        </div>
        <div class="text-sm text-gray-600">Subtotal: ${itemTotal.toFixed(2)} {{ shop_profile.currency|default('FCFA') }}</div>
    </div>

                <div class="flex items-center gap-2">
                    <button class="decrease-quantity p-1 text-gray-600 hover:bg-gray-100 rounded-md" data-index="${index}">
                        <i data-lucide="minus" class="w-4 h-4"></i>
                    </button>
                    <span class="mx-2 min-w-[20px] text-center">${item.quantity}</span>
                    <button class="increase-quantity p-1 text-gray-600 hover:bg-gray-100 rounded-md" data-index="${index}">
                        <i data-lucide="plus" class="w-4 h-4"></i>
                    </button>
                    <button class="remove-item p-1 text-red-500 hover:bg-red-50 rounded-md" data-index="${index}">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                </div>
            `;
            cartItems.appendChild(itemElement);
        });

        // Update Lucide icons for the new elements
        lucide.createIcons();

        cartTotal.textContent = `${total.toFixed(2)} {{ shop_profile.currency|default('FCFA') }}`;
        checkoutBtn.disabled = window.cart.length === 0;

        // Save cart to localStorage
        localStorage.setItem('pos_cart', JSON.stringify(window.cart));
    }

    // Load cart from localStorage on page load
    const savedCart = localStorage.getItem('pos_cart');
    if (savedCart) {
        window.cart = JSON.parse(savedCart);
        updateCartDisplay();
    }

    // Search functionality
    searchInput.addEventListener('input', function(e) {
        const searchTerm = e.target.value.toLowerCase();
        document.querySelectorAll('.product-item').forEach(item => {
            const productName = item.getAttribute('data-name').toLowerCase();
            if (productName.includes(searchTerm)) {
                item.classList.remove('hidden');
            } else {
                item.classList.add('hidden');
            }
        });
    });

    // Add to cart using event delegation
    document.getElementById('products-grid').addEventListener('click', function(e) {
        if (e.target && e.target.classList.contains('add-to-cart')) {
            const productCard = e.target.closest('.product-item');
            const productId = productCard.getAttribute('data-id');
            const productName = productCard.getAttribute('data-name');
            const price = parseFloat(productCard.getAttribute('data-price'));
            const stock = parseInt(productCard.getAttribute('data-stock'));

            const existingItem = window.cart.find(item => item.productId === productId);
            if (existingItem) {
                if (existingItem.quantity < stock) {
                    existingItem.quantity++;
                } else {
                    showNotification('Stock insuffisant !', 'error');
                    return;
                }
            } else {
window.cart.push({
    productId,
    name: productName,
    originalPrice: price,
    price: price,  // This can now be modified
    quantity: 1,
    maxStock: stock
});
            }
            updateCartDisplay();
            showNotification('Article ajouté au panier', 'success');
        }
    });

    // Cart item controls using event delegation
    cartItems.addEventListener('click', function(e) {
        const button = e.target.closest('button');
        const priceInput = e.target.closest('.price-input');

        // Handle price input click separately to allow editing
        if (priceInput) return;

        if (!button) return;

        const index = parseInt(button.getAttribute('data-index'));
        if (isNaN(index)) return;

        const item = window.cart[index];
        const productCard = document.querySelector(`.product-item[data-id="${item.productId}"]`);
        const stock = parseInt(productCard?.getAttribute('data-stock') || item.maxStock);

        if (button.classList.contains('increase-quantity')) {
            if (item.quantity < stock) {
                item.quantity++;
                updateCartDisplay();
            } else {
                showNotification('Stock insuffisant !', 'error');
            }
        } else if (button.classList.contains('decrease-quantity')) {
            if (item.quantity > 1) {
                item.quantity--;
                updateCartDisplay();
            }
        } else if (button.classList.contains('remove-item')) {
            window.cart.splice(index, 1);
            updateCartDisplay();
            showNotification('Article retiré du panier', 'success');
        } else if (button.classList.contains('edit-price')) {
            const currentPrice = item.price;
            const newPrice = prompt('Nouveau prix:', currentPrice);
            const parsedPrice = parseFloat(newPrice);

            if (!isNaN(parsedPrice) && parsedPrice >= 0) {
                item.price = parsedPrice;
                updateCartDisplay();
                showNotification('Prix modifié avec succès', 'success');
            } else if (newPrice !== null) { // if not cancelled
                showNotification('Prix invalide', 'error');
            }
        }
    });


cartItems.addEventListener('change', function(e) {
    if (e.target.classList.contains('price-input')) {
        const index = parseInt(e.target.getAttribute('data-index'));
        if (isNaN(index)) return;

        const newPrice = parseFloat(e.target.value);
        const item = window.cart[index];

        if (!isNaN(newPrice) && newPrice >= 0) {
            item.price = newPrice;
            updateCartDisplay();
            showNotification('Prix modifié avec succès', 'success');
        } else {
            e.target.value = item.price.toFixed(2);
            showNotification('Prix invalide', 'error');
        }
    }
});
    // Checkout process
    checkoutBtn.addEventListener('click', function() {
        document.getElementById('modal-total').value = cartTotal.textContent;
        document.getElementById('cash-received').value = '';
        document.getElementById('change-amount').value = '';
        window.openModal('checkoutModal');
    });

    // Change this part in the cash-received input handler:
    document.getElementById('cash-received').addEventListener('input', function() {
        const total = parseFloat(cartTotal.textContent.replace(' FCFA', ''));
        const received = parseFloat(this.value) || 0;
        const change = received - total;
        document.getElementById('change-amount').value = change >= 0 ? `${change.toFixed(2)} {{ shop_profile.currency|default('FCFA') }}` : '';

        // Update this validation to enable button if amount is not negative
        const completeSaleBtn = document.getElementById('complete-sale-btn');
        completeSaleBtn.disabled = received < 0 || isNaN(received);

        if (received < 0 || isNaN(received)) {
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

        const cashReceived = parseFloat(document.getElementById('cash-received').value);
        const total = parseFloat(cartTotal.textContent.replace(' FCFA', ''));
        const customerId = document.getElementById('selected-customer-id').value;

        if (isNaN(cashReceived) || cashReceived < 0) {
            showNotification('Veuillez entrer un montant valide', 'error');
            return;
        }

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
                initial_payment: cashReceived,
                payment_method: 'cash'
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

            let cmds = '';
            // Initialize printer
            cmds += '\x1B\x40';     // Initialize
            cmds += '\x1B\x21\x00'; // Normal font
            cmds += '\x1D\x21\x00'; // Normal size
            cmds += '\x1B\x74\x00'; // CP437 charset

            // Header - Centered
            cmds += '\x1B\x61\x01'; // Center align
            cmds += '\x1B\x21\x08'; // Emphasized
            cmds += '{{ shop_profile.name }}\n';
            cmds += '\x1B\x21\x00'; // Normal
            {% if shop_profile.phones %}
            cmds += 'Tel: {% for phone in shop_profile.phones %}{{ phone.phone }}{% if not loop.last %}, {% endif %}{% endfor %}\n';
            {% endif %}
            {% if shop_profile.address %}
            cmds += '{{ shop_profile.address }}\n';
            {% endif %}
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
            const currencyText = " {{ shop_profile.currency|default('FCFA') }}";

            // Format TOTAL
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


// Helper function for debouncing
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Cleanup functions
function clearCustomerSelection() {
    selectedCustomer = null;
    customerSearch.value = '';
    customerDetails.classList.add('hidden');
    document.getElementById('selected-customer-id').value = '';
}

    // Customer Search Function
    customerSearch.addEventListener('input', debounce(async function(e) {
    const searchTerm = e.target.value.trim();
    if (searchTerm.length < 2) {
        customerDetails.classList.add('hidden');
        return;
    }

    try {
        const response = await fetch(`/api/customers/search?term=${encodeURIComponent(searchTerm)}`);
        const customers = await response.json();

        if (customers.length > 0) {
            // Create dropdown for results
            const dropdown = document.createElement('div');
            dropdown.className = 'absolute z-10 w-full bg-white border border-gray-200 rounded-lg shadow-lg mt-1';
            dropdown.id = 'customer-dropdown';

            customers.forEach(customer => {
                const item = document.createElement('div');
                item.className = 'p-3 hover:bg-gray-50 cursor-pointer';
                item.innerHTML = `
                    <div class="font-medium">${customer.name}</div>
                    <div class="text-sm text-gray-600">${customer.phone || ''}</div>
                `;

                item.addEventListener('click', () => {
                    selectCustomer(customer);
                    dropdown.remove();
                });

                dropdown.appendChild(item);
            });

            // Remove existing dropdown if any
            const existingDropdown = document.getElementById('customer-dropdown');
            if (existingDropdown) existingDropdown.remove();

            customerSearch.parentNode.appendChild(dropdown);
        }
    } catch (error) {
        console.error('Error searching customers:', error);
        showNotification('Erreur lors de la recherche des clients', 'error');
    }
}, 300));

function selectCustomer(customer) {
    selectedCustomer = customer;
    customerSearch.value = customer.name;
    document.getElementById('selected-customer-id').value = customer.id;
    document.getElementById('selected-customer-name').textContent = customer.name;
    document.getElementById('selected-customer-contact').textContent =
        `${customer.phone ? 'Tél: ' + customer.phone : ''} ${customer.email ? ' | Email: ' + customer.email : ''}`;
    customerDetails.classList.remove('hidden');
}

// New customer functionality
document.getElementById('new-customer-btn').addEventListener('click', function() {
    closeModal('checkoutModal');
    openModal('newCustomerModal');
});

document.getElementById('save-customer-btn').addEventListener('click', async function() {
    const form = document.getElementById('new-customer-form');
    const formData = new FormData(form);
    const customerData = Object.fromEntries(formData.entries());

    try {
        const response = await fetch('/api/customers', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(customerData)
        });

        if (response.ok) {
            const newCustomer = await response.json();
            selectCustomer(newCustomer);
            closeModal('newCustomerModal');
            openModal('checkoutModal');
            showNotification('Client créé avec succès', 'success');
        } else {
            throw new Error('Failed to create customer');
        }
    } catch (error) {
        console.error('Error creating customer:', error);
        showNotification('Erreur lors de la création du client', 'error');
    }
});

    // Notification function
    function showNotification(message, type = 'success', duration = 3000) {
        const notification = document.createElement('div');
        // Added different colors for info type and made notification wider
        notification.className = `fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg transform transition-all duration-300 translate-y-0 z-50 max-w-md ${
            type === 'success' ? 'bg-green-500' :
            type === 'info' ? 'bg-blue-500' :
            'bg-red-500'
        } text-white`;
        notification.textContent = message;

        // Check for existing notifications and stack them
        const existingNotifications = document.querySelectorAll('[data-notification]');
        const offset = existingNotifications.length * 80;
        notification.style.top = `${offset + 16}px`; // 16px is the original top-4 spacing

        notification.setAttribute('data-notification', '');
        document.body.appendChild(notification);

        // Animate in
        requestAnimationFrame(() => {
            notification.style.transform = 'translateY(0)';
        });

        // Remove after specified duration
        setTimeout(() => {
            notification.style.transform = 'translateY(-100%)';
            setTimeout(() => {
                notification.remove();
                // Reposition remaining notifications
                document.querySelectorAll('[data-notification]').forEach((notif, index) => {
                    notif.style.top = `${index * 80 + 16}px`;
                });
            }, 300);
        }, duration);
    }

    // Clear cart function
    window.clearCart = function() {
        window.cart = [];
        localStorage.removeItem('pos_cart');
        updateCartDisplay();
    };

    // Modal close handlers
    document.querySelectorAll('[id$="Modal"]').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                window.closeModal(modal.id);
            }
        });
    });

    // Handle escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('[id$="Modal"]').forEach(modal => {
                if (!modal.classList.contains('hidden')) {
                    window.closeModal(modal.id);
                }
            });
        }
    });

    // Handle page unload
    window.addEventListener('beforeunload', function() {
        localStorage.setItem('pos_cart', JSON.stringify(window.cart));
    });
});
</script>