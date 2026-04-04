"""Legacy one-off: import from vericant-expenses SQLite. Hardcoded SOURCE_DB — edit before use."""
import sqlite3
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app import create_app
from app.extensions import db
from app.models import (
    Client, Product, SalesBill, SalesDetail, User, Category, Expense, Loan, Supplier, Check, BoutiqueTransaction
)

SHOP_ID = 1
SOURCE_DB = "/home/vericant/POS-Master/schemas/vericant-expenses.db"


def get_or_create_user(session, name):
    user = session.query(User).filter_by(name=name).first()
    if user:
        return user.id
    fallback = session.query(User).filter_by(name='balde').first()
    return fallback.id if fallback else None

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

def get_or_create_category(session, name, icon=None):
    category = session.query(Category).filter_by(name=name, shop_id=SHOP_ID).first()
    if not category:
        category = Category(name=name, icon=icon, type='expense', shop_id=SHOP_ID)
        session.add(category)
        session.commit()
    return category

def get_or_create_supplier(session, name, contact_person=None, phone=None, email=None, address=None):
    supplier = session.query(Supplier).filter_by(name=name, shop_id=SHOP_ID).first()
    if not supplier:
        supplier = Supplier(name=name, contact_person=contact_person, phone=phone, email=email, address=address, shop_id=SHOP_ID)
        session.add(supplier)
        session.commit()
    return supplier

def main():
    app = create_app()
    with app.app_context():
        dest_session = db.session
        src_conn = sqlite3.connect(SOURCE_DB)
        src_conn.row_factory = sqlite3.Row
        src_cur = src_conn.cursor()

        # Clients
        src_cur.execute('SELECT * FROM clients')
        client_map = {}
        for row in src_cur.fetchall():
            client = get_or_create_client(dest_session, row['client_name'], row['client_address'], row['client_phone'], row['client_email'])
            client_map[row['client_name']] = client.id

        # Products
        src_cur.execute('SELECT * FROM products')
        product_map = {}
        for row in src_cur.fetchall():
            product = get_or_create_product(dest_session, row['product_name'], row['selling_price'], row['buying_price'], row['stock'])
            product_map[row['product_name']] = product.id

        # Categories
        src_cur.execute('SELECT * FROM categories')
        category_map = {}
        for row in src_cur.fetchall():
            category = get_or_create_category(dest_session, row['category'], row['icon'])
            category_map[row['category']] = category.id

        # Suppliers
        src_cur.execute('SELECT * FROM suppliers')
        supplier_map = {}
        for row in src_cur.fetchall():
            supplier = get_or_create_supplier(dest_session, row['supplier_name'])
            supplier_map[row['supplier_name']] = supplier.id

        # Bill Numbers (Sales Bills)
        src_cur.execute('SELECT * FROM bill_numbers')
        bill_map = {}
        for row in src_cur.fetchall():
            client_id = client_map.get(row['client_name'])
            user_id = get_or_create_user(dest_session, row['cashier_name'])
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

        # Sales
        src_cur.execute('SELECT * FROM sales')
        for row in src_cur.fetchall():
            product_id = product_map.get(row['product_name'])
            bill_id = bill_map.get(row['bill_number'])
            if not product_id or not bill_id:
                continue
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

        # Expenses
        src_cur.execute('SELECT * FROM expenses')
        for row in src_cur.fetchall():
            user_id = get_or_create_user(dest_session, row['cashier'])
            category_id = category_map.get(row['category'])
            if not category_id:
                continue
            expense = Expense(
                shop_id=SHOP_ID,
                user_id=user_id,
                category_id=category_id,
                amount=row['amount'],
                date=row['date'],
                description=None
            )
            dest_session.add(expense)
        dest_session.commit()

        # Loans
        src_cur.execute('SELECT * FROM loans')
        for row in src_cur.fetchall():
            user_id = get_or_create_user(dest_session, row['cashier'])
            loan = Loan(
                shop_id=SHOP_ID,
                borrower_name=row['name'],
                amount=row['amount'],
                paid_amount=row['paid_amount'],
                loan_date=row['loan_date'],
                due_date=None,
                user_id=user_id,
                status='active'
            )
            dest_session.add(loan)
        dest_session.commit()

        # Checks
        src_cur.execute('SELECT * FROM checks')
        for row in src_cur.fetchall():
            user_id = get_or_create_user(dest_session, row['cashier'])
            check = Check(
                shop_id=SHOP_ID,
                payee_name=row['name'],
                withdrawal_amount=row['withdrawal_amount'],
                date=row['date'],
                user_id=user_id,
                status='pending'
            )
            dest_session.add(check)
        dest_session.commit()

        # Boutique Transactions
        src_cur.execute('SELECT * FROM boutique')
        for row in src_cur.fetchall():
            transaction = BoutiqueTransaction(
                shop_id=SHOP_ID,
                name=row['name'],
                amount=row['paid_amount'],
                paid_amount=row['paid_amount'],
                date=row['date'],
                user_id=get_or_create_user(dest_session, 'balde'),
                category_id=None
            )
            dest_session.add(transaction)
        dest_session.commit()

        # Supplier Bills (if present)
        src_cur.execute('SELECT * FROM suppliers')
        for row in src_cur.fetchall():
            supplier_id = supplier_map.get(row['supplier_name'])
            user_id = get_or_create_user(dest_session, row['cashier'])
            # Only add if bill_number is present
            if row['bill_number']:
                from app.models import SupplierBill
                bill = SupplierBill(
                    shop_id=SHOP_ID,
                    supplier_id=supplier_id,
                    bill_number=row['bill_number'],
                    amount=row['amount'],
                    paid_amount=row['paid_amount'],
                    date=row['date'],
                    user_id=user_id
                )
                dest_session.add(bill)
        dest_session.commit()

        print('Migration from vericant-expenses.db complete.')

if __name__ == '__main__':
    main()
