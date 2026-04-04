// Main application initialization
document.addEventListener('DOMContentLoaded', function() {
    // Initialize variables
    window.cart = window.cart || [];
    const cartItems = document.getElementById('cart-items');
    const cartTotal = document.getElementById('cart-total');
    const checkoutBtn = document.getElementById('checkout-btn');
    const customerSearch = document.getElementById('customer-search');
    const customerDetails = document.getElementById('customer-details');
    let selectedCustomer = null;

    // Initialize formatting functions
    initFormatting();

    // Load cart from localStorage on page load
    const savedCart = localStorage.getItem('pos_cart');
    if (savedCart) {
        window.cart = JSON.parse(savedCart);
        updateCartDisplay();
    }

    // Initialize event listeners
    initCartEventListeners(cartItems, cartTotal, checkoutBtn);
    initCheckoutEventListeners();
    if (typeof window.initCustomerEventListeners === 'function') {
        window.initCustomerEventListeners(customerSearch, customerDetails);
    }
    initModalEventListeners();

    // Global functions that need to be accessible
    window.clearCart = function() {
        window.cart = [];
        localStorage.removeItem('pos_cart');
        updateCartDisplay();
    };

    // Handle page unload
    window.addEventListener('beforeunload', function() {
        localStorage.setItem('pos_cart', JSON.stringify(window.cart));
    });
});