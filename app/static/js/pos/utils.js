// Utility functions

// Modal management
window.closeModal = function(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = 'auto';
    }
};

// Enhanced modal close function
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

// Initialize modal event listeners
function initModalEventListeners() {
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
}