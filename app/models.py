from flask_login import UserMixin
from sqlalchemy import CheckConstraint, text
from app.extensions import db
from datetime import datetime


# Mixins
class TimestampMixin:
    @staticmethod
    def _now_local_str():
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    created_at = db.Column(
        db.Text,
        nullable=False,
        default=_now_local_str
    )


class TimestampWithUpdateMixin(TimestampMixin):
    updated_at = db.Column(
        db.Text,
        nullable=False,
        default=TimestampMixin._now_local_str,
        onupdate=TimestampMixin._now_local_str
    )


class ShopModel(db.Model):
    __abstract__ = True


# Core Models
class Shop(ShopModel, TimestampWithUpdateMixin):
    __tablename__ = 'shops'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    business_type = db.Column(db.Text)
    address = db.Column(db.Text)
    email = db.Column(db.Text)
    email_password = db.Column(db.Text)  # New field for email password
    tax_id = db.Column(db.Text)
    currency = db.Column(db.Text, default='FCFA')
    logo_path = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    phones = db.relationship('ShopPhone', backref='shop', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('idx_shop_name', 'name'),
        db.Index('idx_shop_active', 'is_active'),
    )


class ShopPhone(ShopModel, TimestampMixin):
    __tablename__ = 'shop_phones'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    phone = db.Column(db.Text, nullable=False)

    __table_args__ = (
        db.Index('idx_shop_phone_shop', 'shop_id'),
    )


class User(ShopModel, UserMixin, TimestampMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Text, nullable=False)
    password_hash = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    current_shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'))
    superadmin = db.Column(db.Boolean, nullable=False, default=False)

    # Relationships
    shops = db.relationship('Shop', secondary='user_shops', backref='users')

    __table_args__ = (
        db.Index('idx_user_name', 'name', unique=True),
        db.Index('idx_user_active', 'is_active'),
        db.Index('idx_user_current_shop', 'current_shop_id'),
    )


class UserShop(ShopModel, TimestampMixin):
    __tablename__ = 'user_shops'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), primary_key=True)
    role = db.Column(db.Text, nullable=False, default='staff')
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.Index('idx_user_shop_active', 'is_active'),
    )


# Shop-specific Models
class Category(ShopModel, TimestampMixin):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.Text)
    type = db.Column(db.String(50), nullable=False)

    __table_args__ = (
        db.Index('idx_category_shop', 'shop_id'),
        db.Index('idx_category_shop_name', 'shop_id', 'name', unique=True),
        db.Index('idx_category_type', 'type'),
    )


class Product(ShopModel, TimestampWithUpdateMixin):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    selling_price = db.Column(db.REAL, nullable=False)
    buying_price = db.Column(db.REAL, nullable=False)
    stock = db.Column(db.Integer, nullable=False, server_default='0')
    min_stock = db.Column(db.Integer, server_default='0')

    __table_args__ = (
        db.Index('idx_product_shop', 'shop_id'),
        db.Index('idx_product_shop_name', 'shop_id', 'name'),
        db.Index('idx_product_category', 'category_id'),
        db.Index('idx_product_stock', 'stock'),
    )


class Client(ShopModel, TimestampWithUpdateMixin):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    address = db.Column(db.Text)
    phone = db.Column(db.String(50))
    email = db.Column(db.Text)

    __table_args__ = (
        db.Index('idx_client_shop', 'shop_id'),
        db.Index('idx_client_shop_name', 'shop_id', 'name'),
        db.Index('idx_client_phone', 'phone'),
    )


class SalesBill(ShopModel, TimestampMixin):
    __tablename__ = 'sales_bills'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    # Composite-style numbers (e.g. 260225008001) exceed MySQL signed INT; use BIGINT.
    bill_number = db.Column(db.BigInteger, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    total_amount = db.Column(db.REAL, nullable=False)
    paid_amount = db.Column(db.REAL, nullable=False, server_default='0')
    remaining_amount = db.Column(db.REAL, nullable=False, server_default='0')
    date = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(32), server_default='pending')

    __table_args__ = (
        db.Index('idx_sales_bill_shop', 'shop_id'),
        db.Index('idx_sales_bill_number', 'shop_id', 'bill_number', unique=True),
        db.Index('idx_sales_bill_client', 'client_id'),
        db.Index('idx_sales_bill_user', 'user_id'),
        db.Index('idx_sales_bill_date', 'date'),
        db.Index('idx_sales_bill_status', 'status'),
        CheckConstraint("status IN ('pending', 'paid', 'partially_paid', 'cancelled')"),
    )


class SalesDetail(ShopModel, TimestampMixin):
    __tablename__ = 'sales_details'
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('sales_bills.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    selling_price = db.Column(db.REAL, nullable=False)
    buying_price = db.Column(db.REAL, nullable=False)
    total_amount = db.Column(db.REAL, nullable=False)

    __table_args__ = (
        db.Index('idx_sales_detail_bill', 'bill_id'),
        db.Index('idx_sales_detail_product', 'product_id'),
    )


class StockMovement(ShopModel, TimestampMixin):
    __tablename__ = 'stock_movements'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    movement_type = db.Column(db.String(32), nullable=False)
    reference_id = db.Column(db.Integer)
    reference_type = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.String(32), nullable=False)
    notes = db.Column(db.Text)

    __table_args__ = (
        db.Index('idx_stock_movement_shop', 'shop_id'),
        db.Index('idx_stock_movement_product', 'product_id'),
        db.Index('idx_stock_movement_date', 'date'),
        db.Index('idx_stock_movement_type', 'movement_type'),
        CheckConstraint("movement_type IN ('purchase', 'sale', 'adjustment', 'return')"),
    )


class PaymentTransaction(ShopModel, TimestampMixin):
    __tablename__ = 'payment_transactions'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('sales_bills.id'), nullable=False)
    amount = db.Column(db.REAL, nullable=False)
    payment_method = db.Column(db.String(32), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.String(32), nullable=False)
    notes = db.Column(db.Text)

    __table_args__ = (
        db.Index('idx_payment_shop', 'shop_id'),
        db.Index('idx_payment_bill', 'bill_id'),
        db.Index('idx_payment_date', 'date'),
        db.Index('idx_payment_method', 'payment_method'),
        CheckConstraint("payment_method IN ('cash', 'card', 'check', 'transfer')"),
    )


class Expense(ShopModel, TimestampMixin):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    amount = db.Column(db.REAL, nullable=False)
    date = db.Column(db.String(32), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    description = db.Column(db.Text)

    __table_args__ = (
        db.Index('idx_expense_shop', 'shop_id'),
        db.Index('idx_expense_category', 'category_id'),
        db.Index('idx_expense_date', 'date'),
    )


class Supplier(ShopModel, TimestampMixin):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    contact_person = db.Column(db.Text)
    phone = db.Column(db.Text)
    email = db.Column(db.Text)
    address = db.Column(db.Text)

    __table_args__ = (
        db.Index('idx_supplier_shop', 'shop_id'),
        db.Index('idx_supplier_shop_name', 'shop_id', 'name'),
    )


class SupplierBill(ShopModel, TimestampMixin):
    __tablename__ = 'supplier_bills'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    bill_number = db.Column(db.Text, nullable=False)
    amount = db.Column(db.REAL, nullable=False)
    paid_amount = db.Column(db.REAL, server_default='0')
    date = db.Column(db.String(32), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    __table_args__ = (
        db.Index('idx_supplier_bill_shop', 'shop_id'),
        db.Index('idx_supplier_bill_supplier', 'supplier_id'),
        db.Index('idx_supplier_bill_date', 'date'),
    )


class Note(ShopModel, TimestampWithUpdateMixin):
    __tablename__ = 'notes'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    title = db.Column(db.Text, nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    __table_args__ = (
        db.Index('idx_note_shop', 'shop_id'),
        db.Index('idx_note_user', 'user_id'),
    )


class Loan(ShopModel, TimestampMixin):
    __tablename__ = 'loans'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    borrower_name = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.REAL, nullable=False)
    paid_amount = db.Column(db.REAL, server_default='0')
    loan_date = db.Column(db.String(32), nullable=False)
    due_date = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(32), server_default='active')

    __table_args__ = (
        db.Index('idx_loan_shop', 'shop_id'),
        db.Index('idx_loan_borrower', 'shop_id', 'borrower_name'),
        db.Index('idx_loan_date', 'loan_date'),
        db.Index('idx_loan_status', 'status'),
        CheckConstraint("status IN ('active', 'paid', 'defaulted')"),
    )


class BoutiqueTransaction(ShopModel, TimestampMixin):
    __tablename__ = 'boutique_transactions'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.REAL, nullable=False)
    paid_amount = db.Column(db.REAL, nullable=False)
    date = db.Column(db.String(32), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))

    __table_args__ = (
        db.Index('idx_boutique_transaction_shop', 'shop_id'),
        db.Index('idx_boutique_transaction_date', 'date'),
        db.Index('idx_boutique_transaction_category', 'category_id'),
    )


class Check(ShopModel, TimestampMixin):
    __tablename__ = 'checks'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    payee_name = db.Column(db.String(255), nullable=False)
    withdrawal_amount = db.Column(db.REAL, nullable=False)
    date = db.Column(db.String(32), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(32), server_default='pending')

    __table_args__ = (
        db.Index('idx_check_shop', 'shop_id'),
        db.Index('idx_check_date', 'date'),
        db.Index('idx_check_status', 'status'),
        db.Index('idx_check_payee', 'shop_id', 'payee_name'),
        CheckConstraint("status IN ('pending', 'cashed', 'cancelled', 'bounced')"),
    )


# Add relationships to Shop model
Shop.categories = db.relationship('Category', backref='shop', lazy=True)
Shop.products = db.relationship('Product', backref='shop', lazy=True)
Shop.clients = db.relationship('Client', backref='shop', lazy=True)
Shop.sales_bills = db.relationship('SalesBill', backref='shop', lazy=True)
Shop.stock_movements = db.relationship('StockMovement', backref='shop', lazy=True)
Shop.payment_transactions = db.relationship('PaymentTransaction', backref='shop', lazy=True)
Shop.expenses = db.relationship('Expense', backref='shop', lazy=True)
Shop.suppliers = db.relationship('Supplier', backref='shop', lazy=True)
Shop.supplier_bills = db.relationship('SupplierBill', backref='shop', lazy=True)
Shop.notes = db.relationship('Note', backref='shop', lazy=True)
Shop.loans = db.relationship('Loan', backref='shop', lazy=True)
Shop.boutique_transactions = db.relationship('BoutiqueTransaction', backref='shop', lazy=True)
Shop.checks = db.relationship('Check', backref='shop', lazy=True)
Shop.employee_salaries = db.relationship('EmployeeSalary', backref='shop', lazy=True)
Shop.employee_loans = db.relationship('EmployeeLoan', backref='shop', lazy=True)
Shop.employee_loan_payments = db.relationship('EmployeeLoanPayment', backref='shop', lazy=True)

# Add relationships to other models as needed
Category.expenses = db.relationship('Expense', backref='category', lazy=True)
Category.products = db.relationship('Product', backref='category', lazy=True)
Category.boutique_transactions = db.relationship('BoutiqueTransaction', backref='category', lazy=True)

Client.sales_bills = db.relationship('SalesBill', backref='client', lazy=True)

Product.sales_details = db.relationship('SalesDetail', backref='product', lazy=True)
Product.stock_movements = db.relationship('StockMovement', backref='product', lazy=True)

SalesBill.sales_details = db.relationship('SalesDetail', backref='bill', lazy=True)
SalesBill.payments = db.relationship('PaymentTransaction', backref='bill', lazy=True)

Supplier.bills = db.relationship('SupplierBill', backref='supplier', lazy=True)

# Employee Models
class EmployeeSalary(ShopModel, TimestampMixin):
    __tablename__ = 'employee_salaries'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    salary_amount = db.Column(db.REAL, nullable=False)
    payment_date = db.Column(db.String(32), nullable=False)
    payment_method = db.Column(db.String(32), nullable=False)
    month_year = db.Column(db.String(16), nullable=False)  # YYYY-MM format
    notes = db.Column(db.Text)
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(32), server_default='paid')

    __table_args__ = (
        db.Index('idx_employee_salary_shop', 'shop_id'),
        db.Index('idx_employee_salary_employee', 'employee_id'),
        db.Index('idx_employee_salary_date', 'payment_date'),
        db.Index('idx_employee_salary_month', 'month_year'),
        db.Index('idx_employee_salary_status', 'status'),
        CheckConstraint("payment_method IN ('cash', 'bank', 'check')"),
        CheckConstraint("status IN ('paid', 'pending', 'cancelled')"),
    )


class EmployeeLoan(ShopModel, TimestampMixin):
    __tablename__ = 'employee_loans'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    loan_amount = db.Column(db.REAL, nullable=False)
    paid_amount = db.Column(db.REAL, server_default='0')
    loan_date = db.Column(db.String(32), nullable=False)
    due_date = db.Column(db.Text)
    loan_purpose = db.Column(db.Text)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(32), server_default='active')
    repayment_schedule = db.Column(db.Text)  # monthly, weekly, one-time

    __table_args__ = (
        db.Index('idx_employee_loan_shop', 'shop_id'),
        db.Index('idx_employee_loan_employee', 'employee_id'),
        db.Index('idx_employee_loan_date', 'loan_date'),
        db.Index('idx_employee_loan_status', 'status'),
        CheckConstraint("status IN ('active', 'paid', 'defaulted')"),
        CheckConstraint("repayment_schedule IN ('monthly', 'weekly', 'one-time')"),
    )


class EmployeeLoanPayment(ShopModel, TimestampMixin):
    __tablename__ = 'employee_loan_payments'
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=False)
    loan_id = db.Column(db.Integer, db.ForeignKey('employee_loans.id'), nullable=False)
    payment_amount = db.Column(db.REAL, nullable=False)
    payment_date = db.Column(db.String(32), nullable=False)
    payment_method = db.Column(db.String(32), nullable=False)
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    notes = db.Column(db.Text)

    __table_args__ = (
        db.Index('idx_employee_loan_payment_shop', 'shop_id'),
        db.Index('idx_employee_loan_payment_loan', 'loan_id'),
        db.Index('idx_employee_loan_payment_date', 'payment_date'),
        db.Index('idx_employee_loan_payment_method', 'payment_method'),
        CheckConstraint("payment_method IN ('cash', 'bank', 'check')"),
    )


# Add User relationships
User.expenses = db.relationship('Expense', backref='user', lazy=True)
User.checks = db.relationship('Check', backref='user', lazy=True)
User.sales_bills = db.relationship('SalesBill', backref='user', lazy=True)
User.notes = db.relationship('Note', backref='user', lazy=True)
User.stock_movements = db.relationship('StockMovement', backref='user', lazy=True)
User.payment_transactions = db.relationship('PaymentTransaction', backref='user', lazy=True)
User.supplier_bills = db.relationship('SupplierBill', backref='user', lazy=True)
User.loans = db.relationship('Loan', backref='user', lazy=True)
User.boutique_transactions = db.relationship('BoutiqueTransaction', backref='user', lazy=True)
User.employee_salaries = db.relationship('EmployeeSalary', foreign_keys='EmployeeSalary.employee_id', backref='employee', lazy=True)
User.processed_salaries = db.relationship('EmployeeSalary', foreign_keys='EmployeeSalary.processed_by', backref='processor', lazy=True)
User.employee_loans = db.relationship('EmployeeLoan', foreign_keys='EmployeeLoan.employee_id', backref='employee', lazy=True)
User.approved_loans = db.relationship('EmployeeLoan', foreign_keys='EmployeeLoan.approved_by', backref='approver', lazy=True)
User.processed_loan_payments = db.relationship('EmployeeLoanPayment', foreign_keys='EmployeeLoanPayment.processed_by', backref='processor', lazy=True)