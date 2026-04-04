"""Create all tables from models (development helper). Prefer ``flask db upgrade`` for production."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import create_app, db

app = create_app()
with app.app_context():
    db.create_all()
    print("Database initialized successfully!")
