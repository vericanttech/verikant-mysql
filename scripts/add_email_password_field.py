#!/usr/bin/env python3
"""
Legacy SQLite ALTER: add email_password column to shops. Prefer Alembic for schema changes.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import create_app
from app.extensions import db
from sqlalchemy import text

def add_email_password_field():
    """Add email_password field to Shop table"""
    app = create_app()

    with app.app_context():
        try:
            db.session.execute(text("ALTER TABLE shops ADD COLUMN email_password TEXT"))
            db.session.commit()
            print("✅ Successfully added email_password field to Shop table")

        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("ℹ️  email_password field already exists")
            else:
                print(f"❌ Error adding email_password field: {e}")

if __name__ == "__main__":
    add_email_password_field()
