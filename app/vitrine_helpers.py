"""Helpers for public vitrine URLs and QR codes (no Flask request required if PUBLIC_BASE_URL is set)."""
from __future__ import annotations

import base64
import io
import os


def public_base_url() -> str:
    """Base URL for links and QR codes (no trailing slash)."""
    base = (os.environ.get('PUBLIC_BASE_URL') or '').strip().rstrip('/')
    if base:
        return base
    try:
        from flask import has_request_context, request

        if has_request_context():
            return request.url_root.rstrip('/')
    except Exception:
        pass
    return ''


def build_vitrine_shop_url(shop_id: int) -> str:
    """Public vitrine URL. Uses shop primary key so it is always unique (no user-chosen slug)."""
    return f"{public_base_url()}/v/{int(shop_id)}"


def qr_png_bytes(text: str) -> bytes:
    """PNG image bytes for a QR code encoding ``text`` (e.g. vitrine URL)."""
    import qrcode

    buf = io.BytesIO()
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(buf, format="PNG")
    return buf.getvalue()


def qr_png_data_url(text: str) -> str:
    return "data:image/png;base64," + base64.b64encode(qr_png_bytes(text)).decode()


