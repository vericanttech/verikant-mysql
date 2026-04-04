"""Interactive CLI to create a user (not the web ``auth.create_user`` route). Run: python scripts/create_user.py"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash


def create_user(username, password, role='admin'):
    app = create_app()
    with app.app_context():
        user = User(
            name=username,
            password_hash=generate_password_hash(password),
            role=role,
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        print(f"User '{username}' created successfully!")


if __name__ == "__main__":
    username = input("Enter username: ")
    password = input("Enter password: ")
    create_user(username, password)
