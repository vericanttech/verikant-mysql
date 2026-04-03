
document.addEventListener("DOMContentLoaded", () => {
  const grid = document.getElementById("products-grid");
  const paginationContainer = document.getElementById("pagination");
  const searchInput = document.getElementById("search-input");
  const categorySelect = document.getElementById("category-select");

  let currentPage = 1;

  async function fetchProducts(page = 1) {
    const search = searchInput?.value || '';
    const category = categorySelect?.value || '';
    const params = new URLSearchParams({ page, search, category });

    const response = await fetch(`/api/posproducts?${params.toString()}`);
    const data = await response.json();
    renderProducts(data.products);
    renderPagination(data);
    currentPage = data.page;
  }

  function renderProducts(products) {
    grid.innerHTML = ''; // Clear previous
    if (products.length === 0) {
      grid.innerHTML = `<p class="col-span-4 text-center">No products found.</p>`;
      return;
    }

    products.forEach(product => {
      const card = document.createElement("div");
      card.className = "bg-white shadow rounded-lg p-4";
      card.innerHTML = `
        <h3 class="text-lg font-semibold">${product.name}</h3>
        <p class="text-gray-500">Price: ${product.price}</p>
        <p class="text-sm text-gray-400">Stock: ${product.stock}</p>
        <button class="mt-2 bg-blue-500 hover:bg-blue-600 text-white py-1 px-2 rounded">
          Add to Cart
        </button>
      `;
      grid.appendChild(card);
    });
  }

    function renderProducts(products) {
      grid.innerHTML = '';
      if (products.length === 0) {
        grid.innerHTML = `<p class="col-span-4 text-center">Aucun produit trouvé.</p>`;
        return;
      }

      products.forEach(product => {
        const card = document.createElement("div");
        card.className = "product-item bg-white shadow rounded-lg p-4";
        card.setAttribute("data-id", product.id);
        card.setAttribute("data-name", product.name);
        card.setAttribute("data-price", product.price);
        card.setAttribute("data-stock", product.stock);

        card.innerHTML = `
          <h3 class="text-lg font-semibold">${product.name}</h3>
          <p class="text-gray-500">Prix: ${product.price}</p>
          <p class="text-sm text-gray-400">Stock: ${product.stock}</p>
          <button class="mt-2 add-to-cart bg-blue-500 hover:bg-blue-600 text-white py-1 px-2 rounded">
            Ajouter
          </button>
        `;
        grid.appendChild(card);
      });
    }


  // Event listeners
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      fetchProducts(1);
    });
  }

  if (categorySelect) {
    categorySelect.addEventListener("change", () => {
      fetchProducts(1);
    });
  }

  // Initial load
  fetchProducts();
});

function renderPagination(data) {
  paginationContainer.innerHTML = '';

  if (data.pages <= 1) return;

  const createButton = (label, pageNum, isActive = false) => {
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.className = `px-3 py-1 border rounded ${isActive ? 'bg-blue-500 text-white' : 'hover:bg-gray-200'}`;
    btn.onclick = () => fetchProducts(pageNum);
    return btn;
  };

  if (data.has_prev) {
    paginationContainer.appendChild(createButton("«", data.prev_num));
  }

  const delta = 2; // current ± 2
  for (let i = 1; i <= data.pages; i++) {
    if (i === 1 || i === data.pages || (i >= data.page - delta && i <= data.page + delta)) {
      paginationContainer.appendChild(createButton(i, i, i === data.page));
    } else if (
      (i === data.page - delta - 1 && i > 1) ||
      (i === data.page + delta + 1 && i < data.pages)
    ) {
      const dots = document.createElement("span");
      dots.textContent = "...";
      dots.className = "px-2 py-1 text-gray-500";
      paginationContainer.appendChild(dots);
    }
  }

  if (data.has_next) {
    paginationContainer.appendChild(createButton("»", data.next_num));
  }
}


const grid = document.getElementById('products-grid');
window.cart = window.cart || [];

grid.addEventListener('click', function(e) {
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
        price: price,
        quantity: 1,
        maxStock: stock
      });
    }

    updateCartDisplay();
    showNotification('Article ajouté au panier', 'success');
  }
});

