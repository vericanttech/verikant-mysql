from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime, timedelta
from app import db
from app.auth import admin_required
from app.models import (
    SalesBill, Category, Product, Expense,
    Check, Loan, BoutiqueTransaction, SalesDetail, Client,
    PaymentTransaction
)
from app.sales_visibility import sales_bill_vat_only_clause

dashboard = Blueprint('dashboard', __name__)


def get_shop_filter():
    """Helper to get current shop filter"""
    return [entity.shop_id == current_user.current_shop_id for entity in
            [SalesBill, Product, Expense, Check, Loan, BoutiqueTransaction, Client]]


@dashboard.route('/')
@dashboard.route('/dashboard')
@login_required
@admin_required
def index():
    # Setup date range for filtering with defaults and handling user input
    today = datetime.now()

    # Default to current month if no date parameters are provided
    default_end_date = today.strftime('%Y-%m-%d')
    default_start_date = today.replace(day=1).strftime('%Y-%m-%d')

    # Get date parameters from request
    start_date = request.args.get('start_date', default_start_date)
    end_date = request.args.get('end_date', default_end_date)

    # Convert string dates to datetime objects for filtering
    try:
        start_datetime = datetime.strptime(f"{start_date} 00:00:00", '%Y-%m-%d %H:%M:%S')
        end_datetime = datetime.strptime(f"{end_date} 23:59:59", '%Y-%m-%d %H:%M:%S')
    except ValueError:
        # Handle invalid date format by using defaults
        start_datetime = datetime.strptime(f"{default_start_date} 00:00:00", '%Y-%m-%d %H:%M:%S')
        end_datetime = datetime.strptime(f"{default_end_date} 23:59:59", '%Y-%m-%d %H:%M:%S')

    # Pagination parameters
    page = request.args.get('stock_page', 1, type=int)
    per_page = 4

    # Get current shop_id
    shop_id = current_user.current_shop_id

    vat_clause = sales_bill_vat_only_clause()

    # Invoice-level totals are the accounting source of truth: amount_ht already
    # includes the invoice discount, while VAT remains separate from revenue.
    bill_stats_q = (
        db.session.query(
            func.sum(SalesBill.amount_ht).label('net_sales'),
            func.sum(SalesBill.vat_amount).label('vat_payable'),
            func.sum(SalesBill.total_amount).label('invoiced_total'),
            func.sum(SalesBill.remaining_amount).label('outstanding_balance'),
        )
        .filter(
            SalesBill.date.between(start_datetime, end_datetime),
            SalesBill.shop_id == shop_id,
            SalesBill.status != 'cancelled',
        )
    )
    if vat_clause is not None:
        bill_stats_q = bill_stats_q.filter(vat_clause)
    bill_stats = bill_stats_q.first()

    net_sales = bill_stats.net_sales or 0
    vat_payable = bill_stats.vat_payable or 0
    invoiced_total = bill_stats.invoiced_total or 0
    outstanding_balance = bill_stats.outstanding_balance or 0

    # Cost of goods sold belongs to the same invoice period as its revenue.
    cogs_q = (
        db.session.query(
            func.sum(SalesDetail.quantity * SalesDetail.buying_price)
        )
        .join(SalesBill, SalesDetail.bill_id == SalesBill.id)
        .filter(
            SalesBill.date.between(start_datetime, end_datetime),
            SalesBill.shop_id == shop_id,
            SalesBill.status != 'cancelled',
        )
    )
    if vat_clause is not None:
        cogs_q = cogs_q.filter(vat_clause)
    cost_of_goods_sold = cogs_q.scalar() or 0

    # Cash is reported by the date it was actually received, independently of
    # the invoice date. Joining the bill preserves the shop's VAT-only view.
    payments_q = (
        db.session.query(func.sum(PaymentTransaction.amount))
        .join(SalesBill, PaymentTransaction.bill_id == SalesBill.id)
        .filter(
            PaymentTransaction.date.between(start_datetime, end_datetime),
            PaymentTransaction.shop_id == shop_id,
            SalesBill.status != 'cancelled',
        )
    )
    if vat_clause is not None:
        payments_q = payments_q.filter(vat_clause)
    payments_collected = payments_q.scalar() or 0

    # Expense Statistics Query with date filter
    total_expenses = (
            db.session.query(func.sum(Expense.amount))
            .filter(
                Expense.date.between(start_datetime, end_datetime),
                Expense.shop_id == shop_id
            )
            .scalar() or 0
    )

    # Recent Sales Query with date filter
    recent_q = (
        db.session.query(SalesBill, Client)
        .outerjoin(Client, SalesBill.client_id == Client.id)
        .filter(
            SalesBill.date.between(start_datetime, end_datetime),
            SalesBill.shop_id == shop_id
        )
    )
    if vat_clause is not None:
        recent_q = recent_q.filter(vat_clause)
    recent_sales = (
        recent_q.order_by(SalesBill.date.desc())
        .limit(5)
        .all()
    )

    # Recent Expenses Query with date filter
    recent_expenses = (
        db.session.query(Expense)
        .filter(
            Expense.date.between(start_datetime, end_datetime),
            Expense.shop_id == shop_id
        )
        .order_by(Expense.date.desc())
        .limit(5)
        .all()
    )

    # Low Stock Products Query (no date filter needed for inventory)
    low_stock_products = (
        db.session.query(Product)
        .filter(
            Product.stock <= Product.min_stock,
            Product.shop_id == shop_id
        )
        .order_by(Product.stock.asc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Active Loans Query (with date filter consideration)
    active_loans = (
        db.session.query(Loan)
        .filter(
            Loan.status == 'active',
            Loan.amount > Loan.paid_amount,
            Loan.loan_date <= end_datetime,
            Loan.shop_id == shop_id
        )
        .order_by(Loan.loan_date.desc())
        .limit(5)
        .all()
    )

    # VAT is a liability, not revenue. Discounts are already reflected in
    # net_sales, so they now correctly reduce both gross and net profit.
    gross_profit = net_sales - cost_of_goods_sold
    net_profit = gross_profit - total_expenses

    return render_template(
        'dashboard/index.html',
        net_sales=net_sales,
        total_expenses=total_expenses,
        gross_profit=gross_profit,
        net_profit=net_profit,
        invoiced_total=invoiced_total,
        payments_collected=payments_collected,
        outstanding_balance=outstanding_balance,
        vat_payable=vat_payable,
        recent_sales=recent_sales,
        recent_expenses=recent_expenses,
        low_stock_products=low_stock_products,
        active_loans=active_loans,
        default_start_date=start_date,
        default_end_date=end_date
    )
