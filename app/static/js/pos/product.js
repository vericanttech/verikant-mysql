// Product loading and display functionality
let currentPage = 1;
let searchTerm = '';
let categoryId = '';
let products = [];
let perPage = 12;

// Initialize product functionality
function initProductFunctionality() {
    // Get initial search parameters from URL
    const urlParams = new URLSearchParams(window.location.search);
    searchTerm = urlParams.get('search') || '';
    categoryId = urlParams.get('category') || '';
    currentPage = parseInt(urlParams.get('page')) || 1;
    
    // Set search input value from URL parameter
    document.getElementById('product-search').value = searchTerm;
    
    // Load products on page load
    loadProducts();
    
    // Add event listener for search form
    const searchForm = document.getElementById('product-search-form');
    if (searchForm) {
        searchForm.addEventListener('submit', function(e) {
            e.preventDefault();
            searchTerm = document.getElementById('product-search').value;
            currentPage = 1;
            loadProducts();
            updateURL();
        });
    }
}

// Load products via AJAX
function loadProducts() {
    showLoading();
    
    // Build query parameters
    const params = new URLSearchParams();
    params.append('page', currentPage);
    params.append('per_page', perPage);
    
    if (searchTerm) {
        params.append('search', searchTerm);
    }
    
    if (categoryId) {
        params.append('category', categoryId);
    }
    
    // Make API request
    fetch(`/api/posproducts?${params.toString()}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            products = data.products;
            renderProducts(data);
            hideLoading();
            // Add-to-cart is handled by event delegation on #products-grid in cart.js
        })
        .catch(error => {
            console.error('Error loading products:', error);
            showNotification('Erreur lors du chargement des produits', 'error');
            hideLoading();
        });
}

// Render products to the DOM
function renderProducts(data) {
    const productsGrid = document.getElementById('products-grid');
    const { products, pagination } = data;
    
    // Clear existing products
    productsGrid.innerHTML = '';
    
    // Check if no products found
    if (products.length === 0) {
        productsGrid.innerHTML = `
            <div class="col-span-full text-center py-8">
                <p class="text-gray-500">Aucun produit trouvé</p>
            </div>
        `;
        renderPagination({current_page: 1, total_pages: 1});
        return;
    }
    
    // Render each product
    products.forEach(product => {
        const productElement = document.createElement('div');
        productElement.className = 'product-item';
        productElement.setAttribute('data-id', product.id);
        productElement.setAttribute('data-name', product.name);
        productElement.setAttribute('data-price', product.selling_price);
        productElement.setAttribute('data-stock', product.stock);
        
        const imgHtml = product.image_url
            ? `<div class="mb-2"><img src="${product.image_url}" alt="" class="w-20 h-20 object-cover rounded border border-gray-100" loading="lazy" width="80" height="80"></div>`
            : '';
        productElement.innerHTML = `
            <div class="bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow h-full">
                <div class="p-4 flex flex-col items-center">
                    ${imgHtml}
                    <h5 class="text-lg font-medium text-gray-900 mb-2">${product.name}</h5>
                    <p class="text-gray-600 mb-2">${product.currency || 'FCFA'} ${formatNumberFR(product.selling_price)}</p>
                    <p class="text-gray-500 mb-3">Stock : ${product.stock}</p>
                    <button class="add-to-cart px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors ${product.stock <= 0 ? 'opacity-50 cursor-not-allowed' : ''}"
                            ${product.stock <= 0 ? 'disabled' : ''}>
                        Ajouter
                    </button>
                </div>
            </div>
        `;
        
        productsGrid.appendChild(productElement);
    });
    
    // Render pagination
    renderPagination(pagination);
}

// Render pagination controls
function renderPagination(pagination) {
    const paginationNav = document.querySelector('.pagination-container');
    if (!paginationNav) return;
    
    const { current_page, total_pages } = pagination;
    
    let paginationHTML = `<ul class="flex space-x-2">`;
    
    // Page numbers only (no Previous/Next)
    for (let i = 1; i <= total_pages; i++) {
        // Logic to show limited page numbers
        if (
            i === 1 || 
            i === total_pages || 
            (i >= current_page - 1 && i <= current_page + 1)
        ) {
            paginationHTML += `
                <li>
                    <button
                        class="px-3 py-2 ${i === current_page ? 'bg-blue-500 text-white' : 'bg-white text-gray-700 hover:bg-gray-50'} border border-gray-300 rounded-lg"
                        onclick="changePage(${i})">
                        ${i}
                    </button>
                </li>
            `;
        } else if (
            (i === current_page - 2 && current_page > 3) || 
            (i === current_page + 2 && current_page < total_pages - 2)
        ) {
            paginationHTML += `
                <li>
                    <span class="px-3 py-2 bg-white border border-gray-300 rounded-lg text-gray-400 flex items-center justify-center">
                        ...
                    </span>
                </li>
            `;
        }
    }
    
    paginationHTML += `</ul>`;
    paginationNav.innerHTML = paginationHTML;
}

// Change page and reload products
function changePage(page) {
    currentPage = page;
    loadProducts();
    updateURL();
    // Scroll back to top of products section
    document.querySelector('.bg-white.rounded-lg.shadow-md').scrollIntoView({ behavior: 'smooth' });
}

// Update URL with current search parameters
function updateURL() {
    const params = new URLSearchParams();
    
    if (currentPage > 1) {
        params.append('page', currentPage);
    }
    
    if (searchTerm) {
        params.append('search', searchTerm);
    }
    
    if (categoryId) {
        params.append('category', categoryId);
    }
    
    const newURL = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}`;
    window.history.pushState({}, '', newURL);
}

// Show loading indicator
function showLoading() {
    const productsGrid = document.getElementById('products-grid');
    productsGrid.innerHTML = `
        <div class="col-span-full flex justify-center py-12">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        </div>
    `;
}

// Hide loading indicator
function hideLoading() {
    // Loading is removed when products are rendered
}

// Add this new event listener for live search
const searchInput = document.getElementById('product-search');
if (searchInput) {
    searchInput.addEventListener('input', debounce(function() {
        searchTerm = this.value;
        currentPage = 1;
        loadProducts();
        updateURL();
    }, 500)); // 500ms debounce to avoid excessive API calls
}

// Add this debounce function to utils.js or add it here if it doesn't exist
function debounce(func, delay) {
    let timeout;
    return function() {
        const context = this;
        const args = arguments;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}

// Format number with French formatting (using spaces as thousands separator and comma for decimal)
function formatNumberFR(number) {
    return new Intl.NumberFormat('fr-FR').format(number);
}

// Initialize on document ready
document.addEventListener('DOMContentLoaded', function() {
    initProductFunctionality();
    
    // Make the changePage function globally available
    window.changePage = changePage;
});