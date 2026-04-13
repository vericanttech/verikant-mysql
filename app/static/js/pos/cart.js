// Cart management functions
function initFormatting() {
    // Initialize Cleave.js for number formatting
    const cashReceived = new Cleave('#cash-received', {
        numeral: true,
        numeralDecimalMark: ',',
        delimiter: ' ',
        numeralThousandsGroupStyle: 'thousand'
    });

    // Make cashReceived globally available
    window.cashReceived = cashReceived;
}

function formatNumberFR(value) {
    return new Intl.NumberFormat('fr-FR', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    }).format(value);
}

/** Minimum unit price (buying) when known; legacy carts may omit it (server still validates). */
function cartItemMinUnitPrice(item) {
    if (item.buyingPrice == null || item.buyingPrice === '') return null;
    const n = parseFloat(item.buyingPrice);
    return isNaN(n) ? null : n;
}

function validateCartUnitPrice(item, unitPrice) {
    const minP = cartItemMinUnitPrice(item);
    if (minP == null) return { ok: true };
    if (unitPrice < minP) {
        return {
            ok: false,
            message:
                `Le prix unitaire doit être supérieur ou égal au prix d'achat (minimum ${formatNumberFR(minP)}).`,
        };
    }
    return { ok: true };
}

// Update cart display function
function updateCartDisplay() {
    const cartItems = document.getElementById('cart-items');
    const cartTotal = document.getElementById('cart-total');
    const checkoutBtn = document.getElementById('checkout-btn');
    const receiptDataElement = document.getElementById('receipt-data');
    const currency = receiptDataElement.dataset.shopCurrency;

    cartItems.innerHTML = '';
    let total = 0;

    window.cart.forEach((item, index) => {
        const itemTotal = item.price * item.quantity;
        total += itemTotal;

        const itemElement = document.createElement('div');
        itemElement.className = 'border-b border-gray-200 pb-3 last:border-b-0 md:border-0 md:pb-0 bg-white md:shadow-sm md:rounded-lg overflow-hidden transition-all duration-300 hover:md:shadow-md';
        itemElement.innerHTML = `
            <div class="flex items-start p-2 sm:p-4 md:border-b md:border-gray-100 gap-2">
                <div class="flex-grow min-w-0">
                    <div class="flex justify-between items-start gap-2">
                        <h6 class="text-sm sm:text-lg font-semibold text-gray-800 break-words min-w-0">${item.name}</h6>
                        <button type="button" class="remove-item shrink-0 text-red-500 hover:bg-red-100 p-1.5 sm:p-2 rounded-full transition-colors" data-index="${index}">
                            <i data-lucide="trash-2" class="w-4 h-4 sm:w-5 sm:h-5"></i>
                        </button>
                    </div>
                </div>
            </div>

            <div class="px-2 sm:px-4 py-2 sm:py-3 bg-gray-50 md:bg-gray-50">
                <div class="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
                    <div class="flex-grow min-w-0 w-full sm:w-auto">
                        <label class="block text-xs text-gray-600 mb-1">Prix</label>
                        <div class="relative">
                            <input type="text"
                                   class="price-input w-full px-2 sm:px-3 py-1.5 sm:py-2 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-200 transition-all"
                                   value="${formatNumberFR(item.price.toFixed(2))}"
                                   data-index="${index}"
                            />
                            <span class="absolute inset-y-0 right-0 pr-2 sm:pr-3 flex items-center text-gray-500 text-xs sm:text-sm">${currency}</span>
                        </div>
                    </div>

                    <div class="flex-grow min-w-0 w-full sm:w-auto">
                        <label class="block text-xs text-gray-600 mb-1">Quantité</label>
                        <div class="relative">
                            <textarea
                                class="quantity-input w-full px-2 sm:px-3 py-1.5 sm:py-2 text-sm border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-200 resize-none transition-all"
                                rows="1"
                                data-index="${index}"
                            >${item.quantity}</textarea>
                        </div>
                    </div>
                </div>

                <div class="mt-2 sm:mt-3 text-right">
                    <span class="text-xs sm:text-sm font-medium text-gray-700">
                        Sous-total :
                        <span class="text-blue-600 font-bold tabular-nums">${formatNumberFR(itemTotal.toFixed(2))} ${currency}</span>
                    </span>
                </div>
            </div>
        `;
        cartItems.appendChild(itemElement);
    });

    // Update Lucide icons for the new elements
    lucide.createIcons();

    cartTotal.textContent = `${formatNumberFR(total.toFixed(2))} ${currency}`;
    checkoutBtn.disabled = window.cart.length === 0;

    // Save cart to localStorage
    localStorage.setItem('pos_cart', JSON.stringify(window.cart));

    const checkoutModal = document.getElementById('checkoutModal');
    if (checkoutModal && !checkoutModal.classList.contains('hidden') && typeof window.updateCheckoutTotals === 'function') {
        window.updateCheckoutTotals();
    }
}

function initCartEventListeners(cartItems, cartTotal, checkoutBtn) {
    // Add to cart using event delegation
    document.getElementById('products-grid').addEventListener('click', function(e) {
        const addBtn = e.target.closest('.add-to-cart');
        if (!addBtn || addBtn.disabled) {
            return;
        }
        const productCard = addBtn.closest('.product-item');
        if (!productCard) return;
        const productId = productCard.getAttribute('data-id');
        const productName = productCard.getAttribute('data-name');
        const price = parseFloat(productCard.getAttribute('data-price'));
        const buyingRaw = productCard.getAttribute('data-buying-price');
        const buyingPrice = buyingRaw !== null && buyingRaw !== '' ? parseFloat(buyingRaw) : NaN;
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
                price: price,
                buyingPrice: !isNaN(buyingPrice) ? buyingPrice : null,
                quantity: 1,
                maxStock: stock
            });
        }
        updateCartDisplay();
        showNotification('Article ajouté au panier', 'success');
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

        if (button.classList.contains('remove-item')) {
            window.cart.splice(index, 1);
            updateCartDisplay();
            showNotification('Article retiré du panier', 'success');
        } else if (button.classList.contains('edit-price')) {
            const currentPrice = item.price;
            const newPrice = prompt('Nouveau prix:', currentPrice);
            const parsedPrice = parseFloat(newPrice);

            if (!isNaN(parsedPrice) && parsedPrice >= 0) {
                const v = validateCartUnitPrice(item, parsedPrice);
                if (!v.ok) {
                    showNotification(v.message, 'error');
                    return;
                }
                item.price = parsedPrice;
                updateCartDisplay();
                showNotification('Prix modifié avec succès', 'success');
            } else if (newPrice !== null) { // if not cancelled
                showNotification('Prix invalide', 'error');
            }
        }
    });

    cartItems.addEventListener('change', function (e) {
        if (e.target.classList.contains('price-input')) {
            const index = parseInt(e.target.dataset.index);
            if (isNaN(index)) return;

            // Convert input value properly
            let newPrice = e.target.value.replace(',', '.'); // Convert comma to dot
            newPrice = parseFloat(newPrice); // Convert to a valid number

            const item = window.cart[index];

            if (!isNaN(newPrice) && newPrice >= 0) {
                const v = validateCartUnitPrice(item, newPrice);
                if (!v.ok) {
                    e.target.value = formatNumberFR(item.price.toFixed(2));
                    showNotification(v.message, 'error');
                    return;
                }
                item.price = newPrice;
                updateCartDisplay();
                showNotification('Prix modifié avec succès', 'success');
            } else {
                e.target.value = item.price.toFixed(2);
                showNotification('Prix invalide', 'error');
            }
        } else if (e.target.classList.contains('quantity-input')) {
            const index = parseInt(e.target.dataset.index);
            if (isNaN(index)) return;

            let newValue = e.target.value.replace(',', '.'); // Convert comma to dot
            newValue = parseFloat(newValue);

            const item = window.cart[index];
            const productCard = document.querySelector(`.product-item[data-id="${item.productId}"]`);
            const stock = parseInt(productCard?.getAttribute('data-stock') || item.maxStock);

            if (!isNaN(newValue) && newValue > 0 && newValue <= stock) {
                item.quantity = newValue;
                updateCartDisplay();
                showNotification('Quantité modifiée avec succès', 'success');
            } else {
                e.target.value = item.quantity;
                if (isNaN(newValue) || newValue < 1) {
                    showNotification('Quantité invalide', 'error');
                } else {
                    showNotification('Stock insuffisant', 'error');
                }
            }
        }
    });

    // Checkout process
    checkoutBtn.addEventListener('click', function() {
        document.getElementById('cash-received').value = '';
        document.getElementById('change-amount').value = '';
        window.openModal('checkoutModal');
        console.log('[POS TVA] checkout modal opened, cart lines:', window.cart?.length ?? 0);
        if (typeof window.updateCheckoutTotals === 'function') {
            window.updateCheckoutTotals();
        }
    });
}