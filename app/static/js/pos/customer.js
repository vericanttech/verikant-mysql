/**
 * Customer management functionality
 * Handles customer search, selection, and creation
 */

// Initialize variables
let selectedCustomer = null;
const customerSearch = document.getElementById('customer-search');
const customerDetails = document.getElementById('customer-details');

/**
 * Debounce function to limit API calls
 */
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

/**
 * Clear customer selection
 */
function clearCustomerSelection() {
    selectedCustomer = null;
    customerSearch.value = '';
    customerDetails.classList.add('hidden');
    document.getElementById('selected-customer-id').value = '';
}

/**
 * Select a customer and display their details
 */
function selectCustomer(customer) {
    selectedCustomer = customer;
    customerSearch.value = customer.name;
    document.getElementById('selected-customer-id').value = customer.id;
    document.getElementById('selected-customer-name').textContent = customer.name;
    document.getElementById('selected-customer-contact').textContent =
        `${customer.phone ? 'Tél: ' + customer.phone : ''} ${customer.email ? ' | Email: ' + customer.email : ''}`;
    customerDetails.classList.remove('hidden');
}

/**
 * Search for customers as the user types
 */
async function searchCustomers(searchTerm) {
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
}

/**
 * Create a new customer
 */
async function createCustomer(customerData) {
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
            if (typeof window.updateCheckoutTotals === 'function') {
                window.updateCheckoutTotals();
            }
            showNotification('Client créé avec succès', 'success');
            return newCustomer;
        } else {
            throw new Error('Failed to create customer');
        }
    } catch (error) {
        console.error('Error creating customer:', error);
        showNotification('Erreur lors de la création du client', 'error');
        return null;
    }
}

/**
 * Initialize customer-related event listeners (alias for main.js)
 */
function initCustomerEventListeners() {
    initCustomerEvents();
}

/**
 * Initialize customer-related event listeners
 */
function initCustomerEvents() {
    // Customer search with debounce
    customerSearch.addEventListener('input', debounce((e) => {
        searchCustomers(e.target.value.trim());
    }, 300));

    // New customer button
    document.getElementById('new-customer-btn').addEventListener('click', function() {
        closeModal('checkoutModal');
        openModal('newCustomerModal');
    });

    // Save customer button
    document.getElementById('save-customer-btn').addEventListener('click', async function() {
        const form = document.getElementById('new-customer-form');
        const formData = new FormData(form);
        const customerData = Object.fromEntries(formData.entries());
        await createCustomer(customerData);
    });
}

// Export functions for use in other modules
window.customerUtils = {
    selectCustomer,
    clearCustomerSelection,
    createCustomer,
    searchCustomers
};