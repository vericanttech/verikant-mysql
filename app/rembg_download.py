"""
Download PNG bytes from Replicate’s delivery URLs.

Replicate returns an HTTPS URL; fetching it sometimes fails on Windows with
``SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC`` (transient or AV/proxy). We retry
with ``requests`` (streamed) and fall back to :mod:`urllib`.
"""
from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.request
from typing import List, Optional


def download_replicate_image_url(url: str, max_bytes: int) -> bytes:
    """GET *url*, return body bytes, capped at *max_bytes*. Raises on failure."""
    import requests

    headers = {'User-Agent': 'Verikant/1.0 (rembg)'}
    last_exc: Optional[Exception] = None

    for attempt in range(3):
        try:
            with requests.get(
                url,
                timeout=(30, 180),
                stream=True,
                headers=headers,
            ) as r:
                r.raise_for_status()
                chunks: List[bytes] = []
                total = 0
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError('Image résultat trop volumineuse.')
                    chunks.append(chunk)
                return b''.join(chunks)
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError, OSError) as e:
            last_exc = e
            time.sleep(0.8 * (attempt + 1))
            continue
        except requests.exceptions.RequestException as e:
            last_exc = e
            time.sleep(0.8 * (attempt + 1))
            continue

    # Fallback: urllib (different TLS stack; helps some Windows setups)
    try:
        req = urllib.request.Request(url, headers=headers)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
            data = resp.read()
        if len(data) > max_bytes:
            raise ValueError('Image résultat trop volumineuse.')
        return data
    except urllib.error.HTTPError as e:
        if last_exc:
            raise last_exc from e
        raise
    except Exception:
        if last_exc:
            raise last_exc
        raise
