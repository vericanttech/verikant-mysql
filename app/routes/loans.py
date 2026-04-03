from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models import Loan, User
from datetime import datetime, timedelta
from app.utils import admin_only_action
from sqlalchemy import desc

loans = Blueprint('loans', __name__)


@loans.route('/loans', methods=['GET', 'POST'])
@login_required
@admin_only_action('delete_loan')
def loan_list():
    if request.method == 'POST':
        if 'add_loan' in request.form:
            loan = Loan(
                shop_id=current_user.current_shop_id,
                borrower_name=request.form.get('borrower_name'),
                amount=float(request.form.get('amount')),
                paid_amount=float(request.form.get('paid_amount', 0)),
                loan_date=datetime.strptime(request.form.get('loan_date', datetime.now().strftime('%Y-%m-%d')),
                                            '%Y-%m-%d'),
                due_date=datetime.strptime(request.form.get('due_date'), '%Y-%m-%d') if request.form.get(
                    'due_date') else None,
                user_id=current_user.id,
                status='active'
            )
            db.session.add(loan)
            db.session.commit()
            # flash('Loan added successfully!', 'success')

        elif 'make_payment' in request.form:
            loan_id = request.form.get('loan_id')
            loan = Loan.query.filter_by(shop_id=current_user.current_shop_id, id=loan_id).first_or_404()
            payment_amount = float(request.form.get('payment_amount'))
            remaining = loan.amount - loan.paid_amount
            if payment_amount > remaining:
                flash('Payment amount cannot exceed remaining balance!', 'error')
            else:
                loan.paid_amount += payment_amount
                if loan.paid_amount >= loan.amount:
                    loan.status = 'paid'
                db.session.commit()
                #flash('Payment processed successfully!', 'success')
        elif 'delete_loan' in request.form:
            loan_id = request.form.get('loan_id')
            loan = Loan.query.filter_by(shop_id=current_user.current_shop_id, id=loan_id).first_or_404()
            db.session.delete(loan)
            db.session.commit()
            #flash('Loan deleted successfully!', 'success')

# GET request
    page = request.args.get('page', 1, type=int)
    per_page = 10
    status_filter = request.args.get('status')

    # Use Loan.query to fetch model instances
    query = Loan.query.filter(Loan.shop_id == current_user.current_shop_id)

    if status_filter:
        query = query.filter(Loan.status == status_filter)

    loans = query.order_by(Loan.loan_date.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # Calculate totals
    totals = query.with_entities(
        db.func.sum(Loan.amount).label('total_amount'),
        db.func.sum(Loan.paid_amount).label('total_paid')
    ).first()

    # Include cashier_name in the query if needed
    # Include cashier_name in the query if needed
    for loan in loans.items:
        user = User.query.get(loan.user_id)
        loan.cashier_name = user.name if user else "Unknown User"

    return render_template('loans/loans.html',
                           loans=loans,
                           total_amount=totals.total_amount or 0,
                           total_paid=totals.total_paid or 0,
                           total_remaining=(totals.total_amount or 0) - (totals.total_paid or 0))



