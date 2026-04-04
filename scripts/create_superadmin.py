"""Legacy SQLite helper: ensure superadmin column and user (hardcoded DB path — edit before use)."""
import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = '/home/vericant/POS-Master/instance/shop.db'  # Updated for PythonAnywhere

SUPERADMIN_USERNAME = 'superadmin'
SUPERADMIN_PASSWORD = 'senegalFSM123'  # Change after first login!


def ensure_superadmin_column(conn):
    cur = conn.cursor()
    # Check if 'superadmin' column exists
    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]
    if 'superadmin' not in columns:
        print("Adding 'superadmin' column to users table...")
        cur.execute("ALTER TABLE users ADD COLUMN superadmin BOOLEAN NOT NULL DEFAULT 0")
        conn.commit()
    else:
        print("'superadmin' column already exists.")

def create_superadmin_user(conn):
    cur = conn.cursor()
    # Check if superadmin user exists
    cur.execute("SELECT id FROM users WHERE name=?", (SUPERADMIN_USERNAME,))
    if cur.fetchone():
        print(f"User '{SUPERADMIN_USERNAME}' already exists.")
        return
    password_hash = generate_password_hash(SUPERADMIN_PASSWORD)
    cur.execute("""
        INSERT INTO users (name, role, password_hash, is_active, superadmin)
        VALUES (?, ?, ?, 1, 1)
    """, (SUPERADMIN_USERNAME, 'admin', password_hash))
    conn.commit()
    print(f"Superadmin user '{SUPERADMIN_USERNAME}' created with default password. Please change it after first login!")

def main():
    conn = sqlite3.connect(DB_PATH)
    ensure_superadmin_column(conn)
    create_superadmin_user(conn)
    conn.close()

if __name__ == '__main__':
    main()
