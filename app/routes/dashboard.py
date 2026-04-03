from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime, timedelta
from app import db
from app.auth import admin_required
from app.models import (
    SalesBill, Category, Product, Expense,
    Check, Loan, BoutiqueTransaction, SalesDetail, Client
)

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

    # Sales Statistics Query with date filter
    sales_stats = (
        db.session.query(
            func.sum(SalesDetail.total_amount).label('total_sales'),
            func.sum(
                SalesDetail.quantity *
                (SalesDetail.selling_price - SalesDetail.buying_price)
            ).label('total_profit')
        )
        .join(SalesBill, SalesDetail.bill_id == SalesBill.id)
        .filter(
            SalesBill.date.between(start_datetime, end_datetime),
            SalesBill.shop_id == shop_id
        )
        .first()
    )

    total_sales = sales_stats.total_sales or 0
    total_profit = sales_stats.total_profit or 0

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
    recent_sales = (
        db.session.query(SalesBill, Client)
        .outerjoin(Client, SalesBill.client_id == Client.id)
        .filter(
            SalesBill.date.between(start_datetime, end_datetime),
            SalesBill.shop_id == shop_id
        )
        .order_by(SalesBill.date.desc())
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

    # Calculate net profit
    net_profit = total_profit - total_expenses

    return render_template(
        'dashboard/index.html',
        total_sales=total_sales,
        total_expenses=total_expenses,
        net_profit=net_profit,
        recent_sales=recent_sales,
        recent_expenses=recent_expenses,
        low_stock_products=low_stock_products,
        active_loans=active_loans,
        default_start_date=start_date,
        default_end_date=end_date
    )