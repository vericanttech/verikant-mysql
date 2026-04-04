# =============================================================================
# PASTE THIS FILE'S CONTENTS into PythonAnywhere's WSGI config file, e.g.:
#   /var/www/vericant_pythonanywhere_com_wsgi.py
#
# It is NOT the same as repo-root ``wsgi.py`` (that one is loaded below).
# Edit PROJECT_ROOT if your clone path differs.
# =============================================================================

import os
import sys

# MySQL is local to PA — never use SSH tunnel from a web worker
os.environ.setdefault("SSH_TUNNEL", "0")

PROJECT_ROOT = "/home/vericant/verikant-mysql"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Repo ``wsgi.py`` builds ``application`` via ``create_app()``
from wsgi import application

# Correct scheme/host behind PythonAnywhere HTTPS / reverse proxy
from werkzeug.middleware.proxy_fix import ProxyFix

application.wsgi_app = ProxyFix(
    application.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_prefix=1,
)
