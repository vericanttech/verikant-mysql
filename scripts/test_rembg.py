"""
Quick test for Replicate rembg (same model as app/routes/inventory.py).

Usage (from project root):
  python scripts/test_rembg.py
  python scripts/test_rembg.py path/to/your/photo.jpg

Requires REPLICATE_API_TOKEN in .env and: pip install replicate python-dotenv requests
"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

# Project root = parent of scripts/
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

_DEFAULT_MODEL = "cjwbw/rembg:fb8af171cfa1616ddcf1242c093f9c46bcada5ad4cf6f2fbe8b81b330ec5c003"
# Replicate demo image (no local file needed)
_DEFAULT_IMAGE_URL = (
    "https://replicate.delivery/pbxt/"
    "Ho28olmw8dnOffOz7yjuPK6UGsOPqFUfpCnq1ur8zaAKxiPH/animal-1.jpeg"
)
# If present and no CLI arg, use this file (same as manual inventory test)
_DEFAULT_LOCAL_JPG = Path.home() / "Desktop" / "testing-img.jpg"
_MAX_OUT = 8 * 1024 * 1024


def _output_url(output):
    if output is None:
        return None
    if isinstance(output, Iterator):
        try:
            output = next(output)
        except StopIteration:
            return None
        return _output_url(output)
    if isinstance(output, str) and output.startswith("http"):
        return output
    if isinstance(output, (list, tuple)) and output:
        return _output_url(output[0])
    url_attr = getattr(output, "url", None)
    if callable(url_attr):
        try:
            u = url_attr()
            if isinstance(u, str) and u.startswith("http"):
                return u
        except Exception:
            pass
    u = getattr(output, "url", None)
    if isinstance(u, str) and u.startswith("http"):
        return u
    return None


def main() -> int:
    if load_dotenv:
        load_dotenv(ROOT / ".env")

    token = (os.environ.get("REPLICATE_API_TOKEN") or "").strip()
    if not token:
        print("ERROR: REPLICATE_API_TOKEN is missing in .env (or empty).", file=sys.stderr)
        return 1

    try:
        import replicate
    except ImportError:
        print("ERROR: Install replicate: python -m pip install replicate", file=sys.stderr)
        return 1

    model = (os.environ.get("REPLICATE_REMBG_MODEL") or _DEFAULT_MODEL).strip() or _DEFAULT_MODEL

    if len(sys.argv) >= 2:
        path = Path(sys.argv[1]).expanduser().resolve()
        if not path.is_file():
            print(f"ERROR: File not found: {path}", file=sys.stderr)
            return 1
        image_arg = open(path, "rb")
        close_image = True
        print(f"Input: local file {path}")
    elif _DEFAULT_LOCAL_JPG.is_file():
        path = _DEFAULT_LOCAL_JPG.resolve()
        image_arg = open(path, "rb")
        close_image = True
        print(f"Input: default local file {path}")
    else:
        image_arg = _DEFAULT_IMAGE_URL
        close_image = False
        print("Input: Replicate demo URL (no testing-img.jpg on Desktop)")

    os.environ["REPLICATE_API_TOKEN"] = token
    print(f"Model: {model}")
    print("Calling Replicate…")

    try:
        output = replicate.run(model, input={"image": image_arg})
    finally:
        if close_image:
            image_arg.close()

    url = _output_url(output)
    if not url:
        print(f"ERROR: Unexpected output from replicate.run: {output!r}", file=sys.stderr)
        return 1

    print(f"OK — result URL: {url[:80]}…")

    from app.rembg_download import download_replicate_image_url

    out_path = ROOT / "rembg_test_output.png"
    data = download_replicate_image_url(url, _MAX_OUT)
    out_path.write_bytes(data)
    print(f"Saved: {out_path} ({len(data)} bytes)")
    print("If this file shows your subject on a transparent background, rembg works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
