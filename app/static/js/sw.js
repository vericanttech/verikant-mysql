const CACHE_NAME = 'vericant-v1';
const OFFLINE_URL = '/offline.html';

// Files to cache
const urlsToCache = [
    '/',
    '/static/css/style.css',
    '/static/images/vericant-icon.svg',
    '/static/images/vericant-icon-192.png',
    '/static/images/vericant-icon-512.png',
    '/static/images/dashboard-preview.png',
    '/static/images/img.png',
    'https://cdn.tailwindcss.com',
    'https://cdnjs.cloudflare.com/ajax/libs/aos/2.3.4/aos.css',
    'https://cdnjs.cloudflare.com/ajax/libs/aos/2.3.4/aos.js',
    OFFLINE_URL
];

// Install service worker
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(urlsToCache))
            .then(() => self.skipWaiting())
    );
});

// Fetch resources
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                return response || fetch(event.request).catch(() => {
                    if (event.request.mode === 'navigate') {
                        return caches.match(OFFLINE_URL);
                    }
                });
            })
    );
});

// Clean up old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});
