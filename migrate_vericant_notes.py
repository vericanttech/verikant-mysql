import sys
import os
import sqlite3

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from app.extensions import db
from app.models import Note, User

SHOP_ID = 1
SOURCE_DB = "/home/vericant/POS-Master/schemas/vericant-notes.db"

def get_user_id_by_name(session, name):
    user = session.query(User).filter_by(name=name).first()
    if user:
        return user.id
    fallback = session.query(User).filter_by(name='balde').first()
    return fallback.id if fallback else None

def main():
    app = create_app()
    with app.app_context():
        dest_session = db.session
        src_conn = sqlite3.connect(SOURCE_DB)
        src_conn.row_factory = sqlite3.Row
        src_cur = src_conn.cursor()

        # Migrate notes
        src_cur.execute('SELECT * FROM notes')
        for row in src_cur.fetchall():
            user_name = row['cashier'] if 'cashier' in row.keys() else None
            user_id = get_user_id_by_name(dest_session, user_name)
            content = row['note']
            title = content[:30] if content else 'Note'
            note = Note(
                shop_id=SHOP_ID,
                title=title,
                content=content,
                user_id=user_id,
            )
            dest_session.add(note)
        dest_session.commit()

        print('Migration from vericant-notes.db complete.')

if __name__ == '__main__':
    main() 