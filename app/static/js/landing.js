(() => {
    'use strict';

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const revealItems = document.querySelectorAll('[data-reveal]');

    if (reducedMotion || !('IntersectionObserver' in window)) {
        revealItems.forEach((item) => item.classList.add('is-visible'));
    } else {
        const revealObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.14, rootMargin: '0px 0px -6% 0px' });
        revealItems.forEach((item) => revealObserver.observe(item));
    }

    const numberLocale = document.documentElement.lang === 'en' ? 'en-US' : 'fr-FR';
    const formatNumber = (value) => new Intl.NumberFormat(numberLocale).format(value);
    const counters = document.querySelectorAll('[data-counter]');
    const animateCounter = (element) => {
        if (element.dataset.counted === 'true') return;
        element.dataset.counted = 'true';
        const target = Number(element.dataset.counter || 0);
        if (reducedMotion || !target) {
            element.textContent = formatNumber(target);
            return;
        }
        const started = performance.now();
        const duration = 1050;
        const tick = (now) => {
            const progress = Math.min(1, (now - started) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            element.textContent = formatNumber(Math.round(target * eased));
            if (progress < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    };

    if ('IntersectionObserver' in window && !reducedMotion) {
        const counterObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                animateCounter(entry.target);
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.55 });
        counters.forEach((counter) => counterObserver.observe(counter));
    } else {
        counters.forEach(animateCounter);
    }

    const navToggle = document.querySelector('.nav-toggle');
    const mainNav = document.querySelector('.main-nav');
    if (navToggle && mainNav) {
        navToggle.addEventListener('click', () => {
            const open = mainNav.classList.toggle('is-open');
            navToggle.setAttribute('aria-expanded', String(open));
        });
        mainNav.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
            mainNav.classList.remove('is-open');
            navToggle.setAttribute('aria-expanded', 'false');
        }));
    }

    document.querySelectorAll('[data-dialog]').forEach((button) => {
        button.addEventListener('click', () => document.getElementById(button.dataset.dialog)?.showModal());
    });
    document.querySelectorAll('.info-dialog').forEach((dialog) => {
        dialog.querySelector('.dialog-close')?.addEventListener('click', () => dialog.close());
        dialog.addEventListener('click', (event) => {
            const rect = dialog.getBoundingClientRect();
            const outside = event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
            if (outside) dialog.close();
        });
    });

    const form = document.getElementById('contactForm');
    if (form) {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const button = document.getElementById('submitButton');
            const label = document.getElementById('buttonText');
            const spinner = document.getElementById('spinner');
            const status = document.getElementById('formStatus');
            button.disabled = true;
            label.textContent = form.dataset.sending;
            spinner.hidden = false;
            status.textContent = '';
            try {
                const response = await fetch('/send-email', { method: 'POST', body: new FormData(form) });
                if (!response.ok) throw new Error('send_failed');
                form.reset();
                status.textContent = form.dataset.sent;
            } catch (_error) {
                status.textContent = form.dataset.error;
            } finally {
                button.disabled = false;
                label.textContent = form.dataset.submit;
                spinner.hidden = true;
            }
        });
    }
})();
