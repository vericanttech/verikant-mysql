from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import EmployeeLoan, EmployeeLoanPayment, User, UserShop
from datetime import datetime, timedelta
from app.utils import admin_only_action
from sqlalchemy import desc, func

employee_loans = Blueprint('employee_loans', __name__)


@employee_loans.route('/employee-loans', methods=['GET', 'POST'])
@login_required
@admin_only_action('delete_loan')
def loan_list():
    if request.method == 'POST':
        if 'add_loan' in request.form:
            try:
                loan = EmployeeLoan(
                    shop_id=current_user.current_shop_id,
                    employee_id=int(request.form.get('employee_id')),
                    loan_amount=float(request.form.get('loan_amount')),
                    loan_date=request.form.get('loan_date'),
                    due_date=request.form.get('due_date'),
                    loan_purpose=request.form.get('loan_purpose'),
                    approved_by=current_user.id,
                    status=request.form.get('status', 'active'),
                    repayment_schedule=request.form.get('repayment_schedule', 'one-time')
                )
                db.session.add(loan)
                db.session.commit()
                flash('Prêt employé ajouté avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Erreur lors de l\'ajout du prêt.', 'error')

        elif 'make_payment' in request.form:
            try:
                loan_id = request.form.get('loan_id')
                loan = EmployeeLoan.query.filter_by(
                    shop_id=current_user.current_shop_id, 
                    id=loan_id
                ).first_or_404()
                
                payment_amount = float(request.form.get('payment_amount'))
                remaining = loan.loan_amount - loan.paid_amount
                
                if payment_amount > remaining:
                    flash('Le montant du paiement ne peut pas dépasser le solde restant!', 'error')
                else:
                    # Create payment record
                    payment = EmployeeLoanPayment(
                        shop_id=current_user.current_shop_id,
                        loan_id=loan.id,
                        payment_amount=payment_amount,
                        payment_date=request.form.get('payment_date'),
                        payment_method=request.form.get('payment_method'),
                        processed_by=current_user.id,
                        notes=request.form.get('notes')
                    )
                    db.session.add(payment)
                    
                    # Update loan
                    loan.paid_amount += payment_amount
                    if loan.paid_amount >= loan.loan_amount:
                        loan.status = 'paid'
                    
                    db.session.commit()
                    flash('Paiement effectué avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Erreur lors du paiement.', 'error')

        elif 'edit_loan' in request.form:
            try:
                loan_id = request.form.get('loan_id')
                loan = EmployeeLoan.query.filter_by(
                    shop_id=current_user.current_shop_id, 
                    id=loan_id
                ).first_or_404()
                
                loan.employee_id = int(request.form.get('employee_id'))
                loan.loan_amount = float(request.form.get('loan_amount'))
                loan.loan_date = request.form.get('loan_date')
                loan.due_date = request.form.get('due_date')
                loan.loan_purpose = request.form.get('loan_purpose')
                loan.status = request.form.get('status')
                loan.repayment_schedule = request.form.get('repayment_schedule')
                
                db.session.commit()
                flash('Prêt modifié avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Erreur lors de la modification du prêt.', 'error')

        elif 'delete_loan' in request.form:
            try:
                loan_id = request.form.get('loan_id')
                loan = EmployeeLoan.query.filter_by(
                    shop_id=current_user.current_shop_id, 
                    id=loan_id
                ).first_or_404()
                db.session.delete(loan)
                db.session.commit()
                flash('Prêt supprimé avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Erreur lors de la suppression du prêt.', 'error')

    # GET request - Display loans
    page = request.args.get('page', 1, type=int)
    per_page = 10
    employee_filter = request.args.get('employee_id')
    status_filter = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Build query
    query = EmployeeLoan.query.filter(
        EmployeeLoan.shop_id == current_user.current_shop_id
    )

    if employee_filter:
        query = query.filter(EmployeeLoan.employee_id == employee_filter)
    
    if status_filter:
        query = query.filter(EmployeeLoan.status == status_filter)
    
    if start_date:
        query = query.filter(EmployeeLoan.loan_date >= start_date)
    
    if end_date:
        query = query.filter(EmployeeLoan.loan_date <= end_date)

    loans = query.order_by(EmployeeLoan.loan_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Calculate totals
    totals = query.with_entities(
        db.func.sum(EmployeeLoan.loan_amount).label('total_amount'),
        db.func.sum(EmployeeLoan.paid_amount).label('total_paid'),
        db.func.count(EmployeeLoan.id).label('total_count')
    ).first()

    # Get employees for filter dropdown
    employees = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id,
        UserShop.is_active == True
    ).order_by(User.name).all()

    # Add employee names to loan objects
    for loan in loans.items:
        loan.employee_name = User.query.get(loan.employee_id).name
        loan.approver_name = User.query.get(loan.approved_by).name

    return render_template('employee_loans/loans.html',
                         loans=loans,
                         employees=employees,
                         total_amount=totals.total_amount or 0,
                         total_paid=totals.total_paid or 0,
                         total_remaining=(totals.total_amount or 0) - (totals.total_paid or 0),
                         total_count=totals.total_count or 0)


@employee_loans.route('/employee-loans/add', methods=['GET', 'POST'])
@login_required
@admin_only_action('add_loan')
def add_loan():
    if request.method == 'POST':
        try:
            loan = EmployeeLoan(
                shop_id=current_user.current_shop_id,
                employee_id=int(request.form.get('employee_id')),
                loan_amount=float(request.form.get('loan_amount')),
                loan_date=request.form.get('loan_date'),
                due_date=request.form.get('due_date'),
                loan_purpose=request.form.get('loan_purpose'),
                approved_by=current_user.id,
                status=request.form.get('status', 'active'),
                repayment_schedule=request.form.get('repayment_schedule', 'one-time')
            )
            db.session.add(loan)
            db.session.commit()
            flash('Prêt employé ajouté avec succès!', 'success')
            return redirect(url_for('employee_loans.loan_list'))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de l\'ajout du prêt.', 'error')

    # Get employees for dropdown
    employees = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id,
        UserShop.is_active == True
    ).order_by(User.name).all()

    return render_template('employee_loans/add_loan.html', employees=employees)


@employee_loans.route('/employee-loans/<int:loan_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_only_action('edit_loan')
def edit_loan(loan_id):
    loan = EmployeeLoan.query.filter_by(
        shop_id=current_user.current_shop_id, 
        id=loan_id
    ).first_or_404()

    if request.method == 'POST':
        try:
            loan.employee_id = int(request.form.get('employee_id'))
            loan.loan_amount = float(request.form.get('loan_amount'))
            loan.loan_date = request.form.get('loan_date')
            loan.due_date = request.form.get('due_date')
            loan.loan_purpose = request.form.get('loan_purpose')
            loan.status = request.form.get('status')
            loan.repayment_schedule = request.form.get('repayment_schedule')
            
            db.session.commit()
            flash('Prêt modifié avec succès!', 'success')
            return redirect(url_for('employee_loans.loan_list'))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de la modification du prêt.', 'error')

    # Get employees for dropdown
    employees = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id,
        UserShop.is_active == True
    ).order_by(User.name).all()

    return render_template('employee_loans/edit_loan.html', 
                         loan=loan, employees=employees)


@employee_loans.route('/employee-loans/<int:loan_id>/payments')
@login_required
@admin_only_action('view_payments')
def loan_payments(loan_id):
    loan = EmployeeLoan.query.filter_by(
        shop_id=current_user.current_shop_id, 
        id=loan_id
    ).first_or_404()

    payments = EmployeeLoanPayment.query.filter_by(
        loan_id=loan_id
    ).order_by(EmployeeLoanPayment.payment_date.desc()).all()

    # Add processor names
    for payment in payments:
        payment.processor_name = User.query.get(payment.processed_by).name

    loan.employee_name = User.query.get(loan.employee_id).name
    loan.approver_name = User.query.get(loan.approved_by).name

    return render_template('employee_loans/loan_payments.html',
                         loan=loan, payments=payments)


@employee_loans.route('/employee-loans/report')
@login_required
@admin_only_action('view_report')
def loan_report():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    employee_id = request.args.get('employee_id')
    status_filter = request.args.get('status')

    query = EmployeeLoan.query.filter(
        EmployeeLoan.shop_id == current_user.current_shop_id
    )

    if start_date:
        query = query.filter(EmployeeLoan.loan_date >= start_date)
    if end_date:
        query = query.filter(EmployeeLoan.loan_date <= end_date)
    if employee_id:
        query = query.filter(EmployeeLoan.employee_id == employee_id)
    if status_filter:
        query = query.filter(EmployeeLoan.status == status_filter)

    loans = query.order_by(EmployeeLoan.loan_date.desc()).all()

    # Calculate statistics
    total_amount = sum(l.loan_amount for l in loans)
    total_paid = sum(l.paid_amount for l in loans)
    total_remaining = total_amount - total_paid
    total_count = len(loans)
    
    # Group by employee
    employee_stats = {}
    for loan in loans:
        employee_name = User.query.get(loan.employee_id).name
        if employee_name not in employee_stats:
            employee_stats[employee_name] = {
                'total_amount': 0, 
                'total_paid': 0, 
                'count': 0
            }
        employee_stats[employee_name]['total_amount'] += loan.loan_amount
        employee_stats[employee_name]['total_paid'] += loan.paid_amount
        employee_stats[employee_name]['count'] += 1

    # Get employees for filter
    employees = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id,
        UserShop.is_active == True
    ).order_by(User.name).all()

    return render_template('employee_loans/report.html',
                         loans=loans,
                         total_amount=total_amount,
                         total_paid=total_paid,
                         total_remaining=total_remaining,
                         total_count=total_count,
                         employee_stats=employee_stats,
                         employees=employees)


@employee_loans.route('/employee-loans/api/employees')
@login_required
def get_employees():
    employees = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id,
        UserShop.is_active == True
    ).order_by(User.name).all()
    
    return jsonify([{
        'id': emp.id,
        'name': emp.name,
        'role': emp.role
    } for emp in employees]) 