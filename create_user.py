from app import create_app, db
from app.models import User
from werkzeug.security import generate_password_hash


def create_user(username, password):
    app = create_app()
    with app.app_context():
        user = User(
            username=username,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        print(f"User '{username}' created successfully!")


if __name__ == "__main__":
    username = input("Enter username: ")
    password = input("Enter password: ")
    create_user(username, password)
