"""Service worker script body; version string busts browser cache on deploy."""

from __future__ import annotations


def build_sw_js(version: str) -> str:
    v = version.strip() or "1"
    # Single-quoted CACHE_VERSION in JS
    return f"""/* Vericant SW — bump APP_SW_VERSION in .env to force PWA update */
const CACHE_VERSION = {repr(v)};
const CACHE_PREFIX = 'vericant-static-';
const CACHE_NAME = CACHE_PREFIX + CACHE_VERSION;

self.addEventListener('install', (event) => {{
  self.skipWaiting();
}});

self.addEventListener('activate', (event) => {{
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith(CACHE_PREFIX) && k !== CACHE_NAME)
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
}});

self.addEventListener('fetch', (event) => {{
  const req = event.request;
  if (req.mode === 'navigate') {{
    event.respondWith(fetch(req));
    return;
  }}
  const url = new URL(req.url);
  if (req.method === 'GET' && url.pathname.startsWith('/static/')) {{
    event.respondWith(
      fetch(req)
        .then((res) => {{
          if (res && res.status === 200) {{
            const copy = res.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(req, copy));
          }}
          return res;
        }})
        .catch(() => caches.match(req))
    );
    return;
  }}
  event.respondWith(fetch(req));
}});
"""
