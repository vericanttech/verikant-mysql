"""Legacy one-off: import from vericant-store SQLite into the app DB. Hardcoded SOURCE_DB — edit before use."""
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import create_app
from app.extensions import db
from app.models import Client, Product, SalesBill, SalesDetail, User

SHOP_ID = 1
SOURCE_DB = "/home/vericant/POS-Master/schemas/vericant-store.db"


def get_or_create_client(session, name, address, phone, email):
    client = session.query(Client).filter_by(name=name, shop_id=SHOP_ID).first()
    if not client:
        client = Client(name=name, address=address, phone=phone, email=email, shop_id=SHOP_ID)
        session.add(client)
        session.commit()
    return client

def get_or_create_product(session, name, selling_price, buying_price, stock):
    product = session.query(Product).filter_by(name=name, shop_id=SHOP_ID).first()
    if not product:
        product = Product(name=name, selling_price=selling_price, buying_price=buying_price, stock=stock, shop_id=SHOP_ID)
        session.add(product)
        session.commit()
    return product

def get_user_id_by_name(session, name):
    user = session.query(User).filter_by(name=name).first()
    if user:
        return user.id
    # fallback to 'balde'
    fallback = session.query(User).filter_by(name='balde').first()
    return fallback.id if fallback else None

def main():
    app = create_app()
    with app.app_context():
        dest_session = db.session
        src_conn = sqlite3.connect(SOURCE_DB)
        src_conn.row_factory = sqlite3.Row
        src_cur = src_conn.cursor()

        # 1. Migrate clients
        src_cur.execute('SELECT * FROM clients')
        client_map = {}  # name -> id
        for row in src_cur.fetchall():
            client = get_or_create_client(dest_session, row['client_name'], row['client_address'], row['client_phone'], row['client_email'])
            client_map[row['client_name']] = client.id

        # 2. Migrate products
        src_cur.execute('SELECT * FROM products')
        product_map = {}  # name -> id
        for row in src_cur.fetchall():
            product = get_or_create_product(dest_session, row['product_name'], row['selling_price'], row['buying_price'], row['stock'])
            product_map[row['product_name']] = product.id

        # 3. Migrate bill_numbers to sales_bills
        src_cur.execute('SELECT * FROM bill_numbers')
        bill_map = {}  # bill_number -> id
        for row in src_cur.fetchall():
            client_id = client_map.get(row['client_name'])
            user_id = get_user_id_by_name(dest_session, row['cashier_name'])
            bill = SalesBill(
                shop_id=SHOP_ID,
                bill_number=row['bill_number'],
                client_id=client_id,
                user_id=user_id,
                total_amount=(row['montant_payer'] + row['montant_restant']),
                paid_amount=row['montant_payer'],
                remaining_amount=row['montant_restant'],
                date=row['date'],
                status='paid' if row['montant_restant'] == 0 else 'pending',
            )
            dest_session.add(bill)
            dest_session.commit()
            bill_map[row['bill_number']] = bill.id

        # 4. Migrate sales to sales_details
        src_cur.execute('SELECT * FROM sales')
        for row in src_cur.fetchall():
            product_id = product_map.get(row['product_name'])
            bill_id = bill_map.get(row['bill_number'])
            if not product_id or not bill_id:
                continue  # skip if mapping failed
            detail = SalesDetail(
                bill_id=bill_id,
                product_id=product_id,
                quantity=row['quantity'],
                selling_price=row['selling_price'],
                buying_price=row['buying_price'],
                total_amount=row['total_sales'],
            )
            dest_session.add(detail)
        dest_session.commit()

        print('Migration from vericant-store.db complete.')

if __name__ == '__main__':
    main()
