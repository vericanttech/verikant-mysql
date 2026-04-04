"""
WSGI entry point for PythonAnywhere (and other WSGI hosts).

Web tab → WSGI configuration file should load this module and expose ``application``.
Example path on PythonAnywhere: /home/YOURUSERNAME/verikant-mysql/wsgi.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import create_app

application = create_app()
