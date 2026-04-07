"""Generate JPEG share cards for vitrine products (Pillow). Cached on disk 24h.

Design: full-bleed product photo as background, gradient overlays top + bottom,
shop identity on top, product name + price overlaid at bottom.
1080×1350px — Instagram Stories / WhatsApp portrait safe zone compliant.
"""
from __future__ import annotations

import hashlib
import io
import math
import os
import re
import textwrap
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Product, Shop, VitrineProductSelection

CACHE_SUBDIR      = "vitrine_share_cards"
CACHE_MAX_AGE_SEC = 24 * 60 * 60
JPEG_QUALITY      = 92
CARD_W, CARD_H    = 1080, 1350

# ── Palette ───────────────────────────────────────────────────────────────────
GREEN       = (90, 186, 122)
GREEN_DIM   = (42, 122, 75)
GOLD        = (200, 168, 75)
GOLD_LIGHT  = (252, 211, 77)
WHITE       = (255, 255, 255)
OFF_WHITE   = (235, 230, 215)
MUTED       = (180, 175, 160)
BLUE_BADGE  = (147, 197, 253)
RED_SOFT    = (252, 165, 165)
FALLBACK_BG = (18, 22, 14)


# ── Font helpers ──────────────────────────────────────────────────────────────

def _find_font_path(bold: bool = False) -> str | None:
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            os.path.join(os.environ.get("WINDIR", ""), "Fonts", "arialbd.ttf"),
        ] if bold else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            os.path.join(os.environ.get("WINDIR", ""), "Fonts", "arial.ttf"),
        ]
    )
    for p in candidates:
        if p and os.path.isfile(p):
            try:
                from PIL import ImageFont
                ImageFont.truetype(p, 12)
                return p
            except OSError:
                continue
    return None


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    path = _find_font_path(bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


# ── Measurement helpers ───────────────────────────────────────────────────────

def _tw(draw, text: str, font) -> int:
    return draw.textbbox((0, 0), text, font=font)[2]

def _th(draw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[3] - bb[1]

def _center_text(draw, cx: int, y: int, text: str, font, fill):
    draw.text((cx - _tw(draw, text, font) // 2, y), text, fill=fill, font=font)


# ── Gradient overlay ──────────────────────────────────────────────────────────

def _vertical_gradient_overlay(img, y_start: int, height: int,
                                color_top: tuple, color_bot: tuple):
    from PIL import Image, ImageDraw
    strip = Image.new("RGBA", (CARD_W, height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(strip)
    for row in range(height):
        t = row / max(height - 1, 1)
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * t)
        a = int(color_top[3] + (color_bot[3] - color_top[3]) * t)
        sd.line([(0, row), (CARD_W, row)], fill=(r, g, b, a))
    img.paste(strip, (0, y_start), strip)


# ── Fallback background (no product photo) ────────────────────────────────────

def _render_fallback_bg(img, draw):
    """Dark editorial background when no product photo is available."""
    for y in range(CARD_H):
        t = y / (CARD_H - 1)
        r = int(FALLBACK_BG[0] * (1 - t * 0.3))
        g = int(FALLBACK_BG[1] * (1 - t * 0.1))
        b = FALLBACK_BG[2]
        draw.line([(0, y), (CARD_W, y)], fill=(r, g, b))

    # Diagonal gold slash
    from PIL import Image, ImageDraw as PID
    slash = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    sd = PID.Draw(slash)
    angle = math.radians(-20)
    cx, cy = CARD_W * 0.75, CARD_H * 0.3
    hw, hh = 260, 1100
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    def rot(px, py):
        return (int(cx + px*cos_a - py*sin_a), int(cy + px*sin_a + py*cos_a))
    sd.polygon([rot(-hw,-hh), rot(hw,-hh), rot(hw,hh), rot(-hw,hh)], fill=(*GOLD, 22))
    img.paste(slash, (0, 0), slash)

    # Dot grid texture
    from PIL import Image as PI
    ov = PI.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    from PIL import ImageDraw as PID2
    od = PID2.Draw(ov)
    for gy in range(0, CARD_H, 54):
        for gx in range(0, CARD_W, 54):
            od.ellipse([gx-1, gy-1, gx+1, gy+1], fill=(255, 255, 255, 10))
    img.paste(ov, (0, 0), ov)


# ── Photo cover-crop ──────────────────────────────────────────────────────────

def _load_and_cover(path: Path, w: int, h: int):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    scale = max(w / im.width, h / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    ox, oy = (nw - w) // 2, (nh - h) // 2
    return im.crop((ox, oy, ox + w, oy + h))


# ── Logo circle ───────────────────────────────────────────────────────────────

def _paste_logo_circle(img, shop, static_root: str, cx: int, cy: int, radius: int):
    from PIL import Image, ImageDraw
    size = radius * 2
    circle_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cd = ImageDraw.Draw(circle_img)
    pasted = False

    if shop.logo_path:
        lpath = Path(static_root) / shop.logo_path
        if lpath.is_file():
            try:
                lg = Image.open(lpath).convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
                mask = Image.new("L", (size, size), 0)
                ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
                r, g, b = lg.split()
                circle_img = Image.merge("RGBA", (r, g, b, mask))
                pasted = True
            except OSError:
                pass

    if not pasted:
        cd.ellipse([0, 0, size, size], fill=(*GREEN_DIM, 230))
        initial = (shop.name or "?")[:1].upper()
        f = _font(radius, bold=True)
        ibb = cd.textbbox((0, 0), initial, font=f)
        iw, ih = ibb[2] - ibb[0], ibb[3] - ibb[1]
        cd.text((radius - iw//2, radius - ih//2 - 4), initial, fill=WHITE, font=f)

    # White ring
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([0, 0, size, size], outline=(255, 255, 255, 70), width=3)
    circle_img.paste(ring, (0, 0), ring)
    img.paste(circle_img, (cx - radius, cy - radius), circle_img)


# ── Pill badge ────────────────────────────────────────────────────────────────

def _pill_badge(img, draw, text: str, x: int, y: int,
                bg_rgba, text_color, border_rgba=None, font=None,
                pad_x: int = 28, pad_y: int = 12):
    from PIL import Image, ImageDraw
    if font is None:
        font = _font(28, bold=True)
    tw = _tw(draw, text, font)
    th = _th(draw, text, font)
    px, py = pad_x, pad_y
    pw, ph = tw + px * 2, th + py * 2
    pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    pd.rounded_rectangle([0, 0, pw, ph], radius=ph // 2, fill=bg_rgba,
                          outline=border_rgba, width=2 if border_rgba else 0)
    pd.text((px, py), text, fill=text_color, font=font)
    img.paste(pill, (x, y), pill)
    return pw, ph


def _pill_badge_right(img, draw, text: str, right_x: int, y: int,
                      bg_rgba, text_color, border_rgba=None, font=None):
    """Place pill so its *right* edge aligns with `right_x` (for stacking on photo)."""
    if font is None:
        font = _font(28, bold=True)
    tw = _tw(draw, text, font)
    th = _th(draw, text, font)
    px, py = 28, 12
    pw = tw + px * 2
    x = right_x - pw
    return pw, _pill_badge(img, draw, text, x, y, bg_rgba, text_color, border_rgba, font)[1]


# ── Main generator ────────────────────────────────────────────────────────────

def generate_share_card_jpeg(
    shop: "Shop",
    product: "Product",
    selection: "VitrineProductSelection",
    vitrine_url: str,
    static_root: str,
) -> bytes:
    from PIL import Image, ImageDraw

    img  = Image.new("RGB", (CARD_W, CARD_H), FALLBACK_BG)
    draw = ImageDraw.Draw(img)

    # 1. Full-bleed product photo
    has_photo = False
    if product.image_path:
        ppath = Path(static_root) / product.image_path
        if ppath.is_file():
            try:
                img.paste(_load_and_cover(ppath, CARD_W, CARD_H), (0, 0))
                has_photo = True
            except OSError:
                pass

    if not has_photo:
        _render_fallback_bg(img, draw)

    draw = ImageDraw.Draw(img)

    # 2. Gradient overlays
    _vertical_gradient_overlay(img, 0, 340,
        color_top=(0, 0, 0, 215), color_bot=(0, 0, 0, 0))
    _vertical_gradient_overlay(img, CARD_H - 600, 600,
        color_top=(0, 0, 0, 0),  color_bot=(0, 0, 0, 235))

    draw = ImageDraw.Draw(img)

    # 3. Fonts
    f_shop      = _font(40,  bold=False)
    f_name_lg   = _font(90,  bold=True)
    f_name_md   = _font(72,  bold=True)
    f_name_sm   = _font(58,  bold=True)
    f_price     = _font(110, bold=True)
    f_price_cur = _font(52,  bold=False)
    f_old_price = _font(46,  bold=False)
    f_badge     = _font(30,  bold=True)
    f_small     = _font(32,  bold=False)
    f_tiny      = _font(24,  bold=False)

    MARGIN = 64

    # 4. Shop header
    LOGO_R  = 46
    logo_cx = MARGIN + LOGO_R
    logo_cy = 52 + LOGO_R
    _paste_logo_circle(img, shop, static_root, logo_cx, logo_cy, LOGO_R)
    draw = ImageDraw.Draw(img)

    shop_name = (shop.name or "Boutique")[:50]
    draw.text(
        (logo_cx + LOGO_R + 22, logo_cy - _th(draw, shop_name, f_shop) // 2),
        shop_name, fill=(*OFF_WHITE, 230), font=f_shop,
    )

    # 5. Badges (top-right, stacked rightward → leftward)
    is_new   = getattr(selection, "is_new_arrival", False)
    is_promo = bool(getattr(selection, "is_promo", False))
    curr     = (shop.currency or "FCFA").strip()
    sp       = float(product.selling_price or 0)
    has_disc = (
        is_promo
        and shop.vitrine_discount_percent
        and float(shop.vitrine_discount_percent) > 0
    )
    dpct  = float(shop.vitrine_discount_percent) if has_disc else 0.0
    after = sp * (1 - dpct / 100.0) if has_disc else sp

    # Badges: same row over the photo (top-right), right-aligned stack: [Nouveauté][−X%]
    badge_right = CARD_W - MARGIN
    badge_y = 60
    badge_gap = 14

    if has_disc:
        pw, _ = _pill_badge_right(
            img, draw, f"−{round(dpct)}%",
            badge_right, badge_y,
            bg_rgba=(*GOLD, 215), text_color=(28, 18, 0),
            border_rgba=(*GOLD_LIGHT, 180), font=f_badge,
        )
        draw = ImageDraw.Draw(img)
        badge_right -= pw + badge_gap

    if is_new:
        _pill_badge_right(
            img, draw, "Nouveauté",
            badge_right, badge_y,
            bg_rgba=(18, 55, 110, 210), text_color=(235, 245, 255),
            border_rgba=(120, 180, 255, 200), font=f_badge,
        )
        draw = ImageDraw.Draw(img)

    # Separator under header
    sep_y = logo_cy + LOGO_R + 24
    draw.line([(MARGIN, sep_y), (CARD_W - MARGIN, sep_y)], fill=(255, 255, 255, 28), width=1)

    # 6. Footer
    FOOTER_H = 90
    footer_y  = CARD_H - FOOTER_H - 30
    phones    = [str(ph.phone) for ph in (shop.phones or [])][:2]
    fy = footer_y
    phone_pill_gap = 8
    for ph in phones:
        label = re.sub(r"\s+", " ", ph)[:38]
        _, ph_h = _pill_badge(
            img, draw, label, MARGIN, fy,
            bg_rgba=(*GOLD, 220),
            text_color=(28, 18, 0),
            border_rgba=(*GOLD_LIGHT, 200),
            font=f_small,
            pad_x=14,
            pad_y=10,
        )
        draw = ImageDraw.Draw(img)
        fy += ph_h + phone_pill_gap

    _center_text(draw, CARD_W // 2, footer_y + FOOTER_H - 14,
                 "Prix indicatifs — à confirmer en caisse", f_tiny, fill=(255, 255, 255, 55))

    draw.line([(MARGIN, footer_y - 22), (CARD_W - MARGIN, footer_y - 22)],
              fill=(255, 255, 255, 25), width=1)

    # 7. Price block (anchored above footer; extra gap vs separator line)
    price_bot = footer_y - 58

    if has_disc:
        price_str = f"{round(after):,}".replace(",", "\u202f")
        ph_h      = _th(draw, price_str, f_price)
        price_y   = price_bot - ph_h
        draw.text((MARGIN, price_y), price_str, fill=GREEN, font=f_price)
        draw.text(
            (MARGIN + _tw(draw, price_str, f_price) + 16,
             price_y + ph_h - _th(draw, curr, f_price_cur) - 8),
            curr, fill=(*GREEN, 150), font=f_price_cur,
        )
        # Strikethrough old price
        old_str = f"{round(sp):,} {curr}".replace(",", "\u202f")
        old_y   = price_y - _th(draw, old_str, f_old_price) - 16
        draw.text((MARGIN, old_y), old_str, fill=MUTED, font=f_old_price)
        ow = _tw(draw, old_str, f_old_price)
        oh = _th(draw, old_str, f_old_price)
        draw.line([(MARGIN, old_y + oh//2 + 2), (MARGIN + ow, old_y + oh//2 + 2)],
                  fill=(*MUTED, 200), width=3)
        name_bot = old_y - 24
    else:
        price_str = f"{round(sp):,}".replace(",", "\u202f")
        ph_h      = _th(draw, price_str, f_price)
        price_y   = price_bot - ph_h
        draw.text((MARGIN, price_y), price_str, fill=GREEN, font=f_price)
        draw.text(
            (MARGIN + _tw(draw, price_str, f_price) + 16,
             price_y + ph_h - _th(draw, curr, f_price_cur) - 8),
            curr, fill=(*GREEN, 150), font=f_price_cur,
        )
        name_bot = price_y - 24

    if getattr(product, "stock", 1) <= 0:
        draw.text((MARGIN, name_bot - 54), "Rupture de stock",
                  fill=RED_SOFT, font=f_small)
        name_bot -= 60

    # 8. Product name (bottom-anchored, auto-sizes)
    pname = (product.name or "Produit").strip()
    if   len(pname) <= 16: fn, max_c, lh = f_name_lg, 16, 104
    elif len(pname) <= 26: fn, max_c, lh = f_name_md, 22, 84
    else:                  fn, max_c, lh = f_name_sm, 28, 70

    lines = textwrap.wrap(pname, width=max_c)[:3]
    if len(textwrap.wrap(pname, width=max_c)) > 3:
        lines[-1] = lines[-1][:max_c - 1] + "…"

    y = name_bot - lh * len(lines)
    for line in lines:
        draw.text((MARGIN, y), line, fill=WHITE, font=fn)
        y += lh

    # 9. Top accent bar
    for yb in range(5):
        draw.line([(0, yb), (CARD_W, yb)], fill=GREEN)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True, subsampling=0)
    return buf.getvalue()


# ── Cache helpers (public API unchanged) ──────────────────────────────────────

def _cache_dir(instance_path: str) -> Path:
    p = Path(instance_path) / CACHE_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def cache_key(
    shop_id: int,
    product_id: int,
    row_id: int,
    is_promo: bool,
    is_new_arrival: bool,
    discount,
    selling_price,
    product_updated: str | None,
    image_path: str | None,
) -> str:
    raw = "|".join([
        str(shop_id), str(product_id), str(row_id),
        "1" if is_promo else "0",
        "1" if is_new_arrival else "0",
        str(discount if discount is not None else ""),
        str(selling_price),
        str(product_updated or ""),
        str(image_path or ""),
        "v8",
    ])
    return hashlib.sha256(raw.encode()).hexdigest()


def prune_cache_dir(instance_path: str, max_age_sec: int = CACHE_MAX_AGE_SEC,
                    max_files_per_run: int = 200) -> None:
    d = _cache_dir(instance_path)
    now = time.time()
    n = 0
    try:
        for f in d.iterdir():
            if n >= max_files_per_run:
                break
            if not f.is_file() or f.suffix.lower() not in (".jpg", ".jpeg"):
                continue
            try:
                if now - f.stat().st_mtime > max_age_sec:
                    f.unlink(missing_ok=True)
                    n += 1
            except OSError:
                pass
    except OSError:
        pass


def cached_jpeg_path(instance_path: str, key_hex: str) -> Path:
    return _cache_dir(instance_path) / f"{key_hex}.jpg"


def get_or_create_cached_jpeg(
    instance_path: str,
    shop: "Shop",
    product: "Product",
    selection: "VitrineProductSelection",
    vitrine_url: str,
    static_root: str,
) -> bytes:
    key = cache_key(
        shop.id, product.id, selection.id,
        bool(selection.is_promo),
        bool(getattr(selection, "is_new_arrival", False)),
        shop.vitrine_discount_percent,
        product.selling_price,
        getattr(product, "updated_at", None),
        product.image_path,
    )
    prune_cache_dir(instance_path)
    path = cached_jpeg_path(instance_path, key)
    if path.is_file():
        try:
            if time.time() - path.stat().st_mtime <= CACHE_MAX_AGE_SEC:
                return path.read_bytes()
        except OSError:
            pass
    data = generate_share_card_jpeg(shop, product, selection, vitrine_url, static_root)
    try:
        path.write_bytes(data)
    except OSError:
        pass
    return data