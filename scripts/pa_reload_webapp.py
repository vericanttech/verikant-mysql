"""Reload your PythonAnywhere web app via the official API (after git pull on PA, etc.).

Create a token: Account → API token tab on PythonAnywhere.
Do not commit tokens; use env vars or CI secrets.

  set PA_API_TOKEN=...
  set PA_DEPLOY_USERNAME=yourusername
  set PA_WEBAPP_DOMAIN=yourusername.pythonanywhere.com
  set PA_API_HOST=www.pythonanywhere.com
  python scripts/pa_reload_webapp.py

EU accounts: PA_API_HOST=eu.pythonanywhere.com

API docs: https://help.pythonanywhere.com/pages/API/
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    token = os.environ.get("PA_API_TOKEN", "").strip()
    username = os.environ.get("PA_DEPLOY_USERNAME", "").strip()
    domain = os.environ.get("PA_WEBAPP_DOMAIN", "").strip()
    host = os.environ.get("PA_API_HOST", "www.pythonanywhere.com").strip()

    if not token or not username or not domain:
        print(
            "Set PA_API_TOKEN, PA_DEPLOY_USERNAME, and PA_WEBAPP_DOMAIN.",
            file=sys.stderr,
        )
        return 1

    path = f"/api/v0/user/{username}/webapps/{domain}/reload/"
    url = f"https://{host}{path}"
    req = urllib.request.Request(
        url,
        method="POST",
        data=b"",
        headers={"Authorization": f"Token {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(resp.status, body or "(empty body)")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err}", file=sys.stderr)
        return 1
    except OSError as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
