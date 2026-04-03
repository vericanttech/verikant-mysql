from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import EmployeeSalary, User, UserShop
from datetime import datetime, timedelta
from app.utils import admin_only_action
from sqlalchemy import desc, func
import calendar

employee_salaries = Blueprint('employee_salaries', __name__)


@employee_salaries.route('/employee-salaries', methods=['GET', 'POST'])
@login_required
@admin_only_action('delete_salary')
def salary_list():
    if request.method == 'POST':
        if 'add_salary' in request.form:
            try:
                salary = EmployeeSalary(
                    shop_id=current_user.current_shop_id,
                    employee_id=int(request.form.get('employee_id')),
                    salary_amount=float(request.form.get('salary_amount')),
                    payment_date=request.form.get('payment_date'),
                    payment_method=request.form.get('payment_method'),
                    month_year=request.form.get('month_year'),
                    notes=request.form.get('notes'),
                    processed_by=current_user.id,
                    status=request.form.get('status', 'paid')
                )
                db.session.add(salary)
                db.session.commit()
                flash('Salaire ajouté avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Erreur lors de l\'ajout du salaire.', 'error')

        elif 'edit_salary' in request.form:
            try:
                salary_id = request.form.get('salary_id')
                salary = EmployeeSalary.query.filter_by(
                    shop_id=current_user.current_shop_id, 
                    id=salary_id
                ).first_or_404()
                
                salary.employee_id = int(request.form.get('employee_id'))
                salary.salary_amount = float(request.form.get('salary_amount'))
                salary.payment_date = request.form.get('payment_date')
                salary.payment_method = request.form.get('payment_method')
                salary.month_year = request.form.get('month_year')
                salary.notes = request.form.get('notes')
                salary.status = request.form.get('status')
                
                db.session.commit()
                flash('Salaire modifié avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Erreur lors de la modification du salaire.', 'error')

        elif 'delete_salary' in request.form:
            try:
                salary_id = request.form.get('salary_id')
                salary = EmployeeSalary.query.filter_by(
                    shop_id=current_user.current_shop_id, 
                    id=salary_id
                ).first_or_404()
                db.session.delete(salary)
                db.session.commit()
                flash('Salaire supprimé avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Erreur lors de la suppression du salaire.', 'error')

    # GET request - Display salaries
    page = request.args.get('page', 1, type=int)
    per_page = 10
    employee_filter = request.args.get('employee_id')
    status_filter = request.args.get('status')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    # Build query
    query = EmployeeSalary.query.filter(
        EmployeeSalary.shop_id == current_user.current_shop_id
    )

    if employee_filter:
        query = query.filter(EmployeeSalary.employee_id == employee_filter)
    
    if status_filter:
        query = query.filter(EmployeeSalary.status == status_filter)
    
    if start_date:
        query = query.filter(EmployeeSalary.payment_date >= start_date)
    
    if end_date:
        query = query.filter(EmployeeSalary.payment_date <= end_date)

    salaries = query.order_by(EmployeeSalary.payment_date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Calculate totals
    totals = query.with_entities(
        db.func.sum(EmployeeSalary.salary_amount).label('total_amount'),
        db.func.count(EmployeeSalary.id).label('total_count')
    ).first()

    # Get employees for filter dropdown
    employees = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id,
        UserShop.is_active == True
    ).order_by(User.name).all()

    # Add employee names to salary objects
    for salary in salaries.items:
        salary.employee_name = User.query.get(salary.employee_id).name
        salary.processor_name = User.query.get(salary.processed_by).name

    return render_template('employee_salaries/salaries.html',
                         salaries=salaries,
                         employees=employees,
                         total_amount=totals.total_amount or 0,
                         total_count=totals.total_count or 0)


@employee_salaries.route('/employee-salaries/add', methods=['GET', 'POST'])
@login_required
@admin_only_action('add_salary')
def add_salary():
    if request.method == 'POST':
        try:
            salary = EmployeeSalary(
                shop_id=current_user.current_shop_id,
                employee_id=int(request.form.get('employee_id')),
                salary_amount=float(request.form.get('salary_amount')),
                payment_date=request.form.get('payment_date'),
                payment_method=request.form.get('payment_method'),
                month_year=request.form.get('month_year'),
                notes=request.form.get('notes'),
                processed_by=current_user.id,
                status=request.form.get('status', 'paid')
            )
            db.session.add(salary)
            db.session.commit()
            flash('Salaire ajouté avec succès!', 'success')
            return redirect(url_for('employee_salaries.salary_list'))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de l\'ajout du salaire.', 'error')

    # Get employees for dropdown
    employees = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id,
        UserShop.is_active == True
    ).order_by(User.name).all()

    return render_template('employee_salaries/add_salary.html', employees=employees)


@employee_salaries.route('/employee-salaries/<int:salary_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_only_action('edit_salary')
def edit_salary(salary_id):
    salary = EmployeeSalary.query.filter_by(
        shop_id=current_user.current_shop_id, 
        id=salary_id
    ).first_or_404()

    if request.method == 'POST':
        try:
            salary.employee_id = int(request.form.get('employee_id'))
            salary.salary_amount = float(request.form.get('salary_amount'))
            salary.payment_date = request.form.get('payment_date')
            salary.payment_method = request.form.get('payment_method')
            salary.month_year = request.form.get('month_year')
            salary.notes = request.form.get('notes')
            salary.status = request.form.get('status')
            
            db.session.commit()
            flash('Salaire modifié avec succès!', 'success')
            return redirect(url_for('employee_salaries.salary_list'))
        except Exception as e:
            db.session.rollback()
            flash('Erreur lors de la modification du salaire.', 'error')

    # Get employees for dropdown
    employees = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id,
        UserShop.is_active == True
    ).order_by(User.name).all()

    return render_template('employee_salaries/edit_salary.html', 
                         salary=salary, employees=employees)


@employee_salaries.route('/employee-salaries/report')
@login_required
@admin_only_action('view_report')
def salary_report():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    employee_id = request.args.get('employee_id')

    query = EmployeeSalary.query.filter(
        EmployeeSalary.shop_id == current_user.current_shop_id
    )

    if start_date:
        query = query.filter(EmployeeSalary.payment_date >= start_date)
    if end_date:
        query = query.filter(EmployeeSalary.payment_date <= end_date)
    if employee_id:
        query = query.filter(EmployeeSalary.employee_id == employee_id)

    salaries = query.order_by(EmployeeSalary.payment_date.desc()).all()

    # Calculate statistics
    total_amount = sum(s.salary_amount for s in salaries)
    total_count = len(salaries)
    
    # Group by employee
    employee_stats = {}
    for salary in salaries:
        employee_name = User.query.get(salary.employee_id).name
        if employee_name not in employee_stats:
            employee_stats[employee_name] = {'total': 0, 'count': 0}
        employee_stats[employee_name]['total'] += salary.salary_amount
        employee_stats[employee_name]['count'] += 1

    # Get employees for filter
    employees = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id,
        UserShop.is_active == True
    ).order_by(User.name).all()

    return render_template('employee_salaries/report.html',
                         salaries=salaries,
                         total_amount=total_amount,
                         total_count=total_count,
                         employee_stats=employee_stats,
                         employees=employees)


@employee_salaries.route('/employee-salaries/api/employees')
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