from flask import Blueprint, render_template, request, flash, redirect, url_for, make_response
from flask_login import login_required, current_user
from sqlalchemy import desc
from app import db
from app.utils import admin_only_action
from app.models import Expense, Category, Check, Supplier, SupplierBill, User
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from io import BytesIO

expenses = Blueprint('expenses', __name__)


# Expense routes
@expenses.route('/expenses', methods=['GET', 'POST'])
@login_required
@admin_only_action('delete_expense', 'edit_expense')
def expense_list():
    if request.method == 'POST':
        try:
            if 'add_expense' in request.form:
                category_name = request.form.get('category_id')

                if category_name == 'other':
                    # Handle new category from "Autre" option
                    new_category_name = request.form.get('other_category')
                    if not new_category_name:
                        flash('Veuillez spécifier la nouvelle catégorie!', 'error')
                        return redirect(url_for('expenses.expense_list'))

                    # Check if category already exists
                    category = Category.query.filter_by(name=new_category_name, type='expense', shop_id=current_user.current_shop_id).first()
                    if not category:
                        # Get the current shop ID
                        shop_id = current_user.current_shop_id
                        if not shop_id:
                            flash("Erreur: L'ID du magasin est manquant!", 'error')
                            return redirect(url_for('expenses.expense_list'))

                        # Create new category
                        category = Category(name=new_category_name, type='expense', shop_id=shop_id)
                        db.session.add(category)
                        db.session.flush()  # Get the ID without committing

                else:
                    # Get existing category by name and shop_id
                    category = Category.query.filter_by(name=category_name, shop_id=current_user.current_shop_id).first()
                    if not category:
                        flash('Catégorie invalide!', 'error')
                        return redirect(url_for('expenses.expense_list'))

                # Create new expense
                expense = Expense(
                    category_id=category.id,
                    amount=float(request.form.get('amount')),
                    date=datetime.strptime(request.form.get('date'), '%Y-%m-%d'),
                    user_id=current_user.id,
                    description=request.form.get('description'),
                    shop_id = current_user.current_shop_id
                )
                db.session.add(expense)
                db.session.commit()
                flash('Dépense ajoutée avec succès!', 'success')

            elif 'edit_expense' in request.form and current_user.role == 'admin':
                expense = Expense.query.get_or_404(request.form.get('expense_id'))
                shop_id = current_user.current_shop_id

                # Handle category selection
                selected_category = request.form.get('category')

                if selected_category == 'other':
                    # Create a new category if "other" was selected
                    other_category_name = request.form.get('other_category')
                    if not other_category_name:
                        flash("Veuillez préciser la nouvelle catégorie!", 'error')
                        return redirect(url_for('expenses.expense_list'))

                    # Check if this category already exists for this shop
                    category = Category.query.filter_by(name=other_category_name, shop_id=shop_id).first()
                    if not category:
                        # Create new category
                        category = Category(name=other_category_name, shop_id=shop_id)
                        db.session.add(category)
                        db.session.flush()  # Get the ID without committing yet
                else:
                    # Get existing category
                    category = Category.query.filter_by(name=selected_category, shop_id=shop_id).first()

                if not category:
                    flash("Catégorie invalide ou n'appartient pas à votre magasin!", 'error')
                    return redirect(url_for('expenses.expense_list'))

                # Update expense details
                expense.category_id = category.id
                expense.amount = float(request.form.get('amount').replace(' ', ''))  # Clean formatting
                expense.description = request.form.get('description', '')  # Use empty string as default

                db.session.commit()
                flash('Dépense mise à jour avec succès!', 'success')

            elif 'delete_expense' in request.form:
                expense_id = request.form.get('expense_id')
                shop_id = current_user.current_shop_id  # Ensure shop ID is used

                # Fetch the expense and ensure it belongs to the current shop
                expense = Expense.query.join(Category).filter(
                    Expense.id == expense_id,
                    Category.shop_id == shop_id
                ).first()

                if not expense:
                    flash("Impossible de supprimer cette dépense: elle n'existe pas ou n'appartient pas à votre "
                          "magasin!",
                          'error')
                    return redirect(url_for('expenses.expense_list'))

                db.session.delete(expense)
                db.session.commit()
                flash('Dépense supprimée avec succès!', 'success')
        except (ValueError, TypeError) as e:
            db.session.rollback()
            flash('Erreur de validation des données!', 'error')
            print(str(e))  # For debugging
        except Exception as e:
            db.session.rollback()
            flash('Une erreur est survenue!', 'error')
            print(str(e))  # For debugging

        return redirect(url_for('expenses.expense_list'))

    # GET request handling
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # Date filtering
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    category_filter = request.args.get('category')

    # Build the base query with joins
    query = db.session.query(
        Expense,
        Category.name.label('category_name'),
        User.name.label('user_name')
    ).join(
        Category, Expense.category_id == Category.id
    ).join(
        User, Expense.user_id == User.id
    ).filter(
        Category.shop_id == current_user.current_shop_id  # Ensure filtering by the current shop
    )

    # Apply filters
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Expense.date.between(start, end))
        except ValueError:
            flash('Format de date invalide!', 'error')

    if category_filter and category_filter != 'all':
        query = query.filter(Category.name == category_filter)

    # Get total amount for filtered expenses
    total_amount = query.with_entities(db.func.sum(Expense.amount)).scalar() or 0

    # Get all expense categories for the current shop
    categories = Category.query.filter_by(type='expense', shop_id=current_user.current_shop_id).all()
    category_list = [category.name for category in categories]  # Just get the names as strings

    # Paginate results
    expenses = query.order_by(desc(Expense.date)).paginate(
        page=page, per_page=per_page, error_out=False
    )
    today_date = datetime.now().strftime('%Y-%m-%d')

    return render_template('expenses/expenses.html',
                           expenses=expenses,
                           categories=category_list,
                           total_amount=total_amount,
                           today_date=today_date)


@expenses.route('/expenses/export-pdf')
@login_required
def export_expenses_pdf():
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    category_filter = request.args.get('category')

    query = db.session.query(
        Expense,
        Category.name.label('category_name'),
        User.name.label('user_name')
    ).join(
        Category, Expense.category_id == Category.id
    ).join(
        User, Expense.user_id == User.id
    ).filter(
        Category.shop_id == current_user.current_shop_id
    )

    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Expense.date.between(start, end))
        except ValueError:
            flash('Format de date invalide!', 'error')
            return redirect(url_for('expenses.expense_list'))

    if category_filter and category_filter != 'all':
        query = query.filter(Category.name == category_filter)

    filtered_expenses = query.order_by(desc(Expense.date)).all()
    total_amount = query.with_entities(db.func.sum(Expense.amount)).scalar() or 0

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=50,
        bottomMargin=30
    )
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'ExpenseTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=14,
        alignment=1,
        textColor=colors.HexColor('#1f2937')
    )

    elements.append(Paragraph("Rapport des Dépenses", title_style))

    date_line = f"Généré le: {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    filters_line = "Filtres: "
    if start_date and end_date:
        filters_line += f"Période {start_date} -> {end_date}"
    else:
        filters_line += "Toutes les dates"
    if category_filter and category_filter != 'all':
        filters_line += f" | Catégorie: {category_filter}"
    else:
        filters_line += " | Toutes les catégories"

    elements.append(Paragraph(date_line, styles['Normal']))
    elements.append(Paragraph(filters_line, styles['Normal']))
    elements.append(Spacer(1, 14))

    table_data = [['Date', 'Catégorie', 'Montant', 'Caissier']]
    currency = "FCFA"

    for expense, category_name, user_name in filtered_expenses:
        amount = f"{expense.amount:,.2f}".replace(',', ' ') + f" {currency}"
        expense_date = expense.date
        if hasattr(expense_date, 'strftime'):
            formatted_date = expense_date.strftime('%d/%m/%Y')
        else:
            # Fallback for legacy/string date values
            try:
                formatted_date = datetime.strptime(str(expense_date), '%Y-%m-%d').strftime('%d/%m/%Y')
            except ValueError:
                try:
                    formatted_date = datetime.strptime(
                        str(expense_date), '%Y-%m-%d %H:%M:%S'
                    ).strftime('%d/%m/%Y')
                except ValueError:
                    formatted_date = str(expense_date)
        table_data.append([
            formatted_date,
            category_name or '-',
            amount,
            user_name or '-'
        ])

    if len(table_data) == 1:
        table_data.append(['-', '-', '0.00 FCFA', '-'])

    table = Table(table_data, colWidths=[1.2 * inch, 2.2 * inch, 1.5 * inch, 1.8 * inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b4c6b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),
        ('ALIGN', (3, 1), (3, -1), 'LEFT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('GRID', (0, 0), (-1, -1), 0.75, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 12))

    total_text = f"<b>Total des dépenses:</b> {total_amount:,.2f}".replace(',', ' ') + f" {currency}"
    elements.append(Paragraph(total_text, styles['Normal']))

    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()

    response = make_response(pdf_data)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = (
        f'attachment; filename=depenses_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf'
    )
    return response



# Checks routes
@expenses.route('/checks', methods=['GET', 'POST'])
@login_required
@admin_only_action('delete_check')
def check_list():
    if request.method == 'POST':
        if 'add_check' in request.form:
            check = Check(
                shop_id=current_user.current_shop_id,
                payee_name=request.form.get('payee_name'),
                withdrawal_amount=float(request.form.get('withdrawal_amount')),
                date=datetime.strptime(request.form.get('date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d'),
                user_id=current_user.id,
                status='pending'
            )
            db.session.add(check)
            db.session.commit()
            #flash('Check added successfully!', 'success')

        if 'delete_check' in request.form:
            check_id = request.form.get('check_id')
            check = Check.query.filter_by(
                shop_id=current_user.current_shop_id,
                id=check_id
            ).first_or_404()
            db.session.delete(check)
            db.session.commit()
            flash('Check deleted successfully!', 'success')

        if 'edit_check' in request.form:
            check_id = request.form.get('check_id')
            check = Check.query.filter_by(
                shop_id=current_user.current_shop_id,
                id=check_id
            ).first_or_404()
            check.payee_name = request.form.get('payee_name')
            check.withdrawal_amount = float(request.form.get('withdrawal_amount'))
            #check.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
            db.session.commit()
            #flash('Check updated successfully!', 'success')

        if 'update_status' in request.form:
            check_id = request.form.get('check_id')
            new_status = request.form.get('status')
            if new_status not in ['pending', 'cashed', 'cancelled', 'bounced']:
                flash('Invalid status!', 'error')
            else:
                check = Check.query.filter_by(
                    shop_id=current_user.current_shop_id,
                    id=check_id
                ).first_or_404()
                check.status = new_status
                db.session.commit()
                #flash(f'Check status updated to {new_status}!', 'success')

        return redirect(url_for('expenses.check_list'))

    # GET request handling
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # Date filter
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    status_filter = request.args.get('status')

    # Build query
    query = Check.query.filter_by(shop_id=current_user.current_shop_id)

    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            query = query.filter(Check.date.between(start, end))
        except ValueError:
            flash('Invalid date format', 'error')

    if status_filter:
        query = query.filter(Check.status == status_filter)

    # Get results
    checks = query.order_by(desc(Check.date)).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Calculate totals
    total_amount = query.with_entities(db.func.sum(Check.withdrawal_amount)).scalar() or 0

    # Get status counts
    status_counts = {
        status: query.filter(Check.status == status).count()
        for status in ['pending', 'cashed', 'cancelled', 'bounced']
    }

    return render_template('checks/checks.html',
                           checks=checks,
                           total_amount=total_amount,
                           status_counts=status_counts,
                           start_date=start_date,
                           end_date=end_date,
                           current_status=status_filter)


@expenses.route('/suppliers', methods=['GET', 'POST'])
@login_required
def supplier_list():
    if request.method == 'POST':
        if 'add_supplier' in request.form:
            try:
                # Create new supplier
                supplier = Supplier(
                    name=request.form.get('supplier_name'),
                    contact_person=request.form.get('supplier_data'),
                    shop_id=current_user.current_shop_id
                )
                db.session.add(supplier)
                db.session.flush()  # Get the supplier ID before committing

                # Create initial bill if amount is provided
                amount = float(request.form.get('amount', 0))
                if amount > 0:
                    bill = SupplierBill(
                        supplier_id=supplier.id,
                        bill_number=request.form.get('bill_number'),
                        amount=amount,
                        paid_amount=float(request.form.get('paid_amount', 0)),
                        date=datetime.now().strftime('%Y-%m-%d'),
                        user_id=current_user.id,
                        shop_id=current_user.current_shop_id
                    )
                    db.session.add(bill)

                db.session.commit()
                #flash('Fournisseur ajouté avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Une erreur est survenue: ' + str(e), 'error')
                print(str(e))

        elif 'add_bill' in request.form:
            try:
                # Create new bill for existing supplier
                bill = SupplierBill(
                    supplier_id=request.form.get('supplier_id'),
                    bill_number=request.form.get('bill_number'),
                    amount=float(request.form.get('amount')),
                    paid_amount=float(request.form.get('paid_amount', 0)),
                    date=datetime.now().strftime('%Y-%m-%d'),
                    user_id=current_user.id,
                    shop_id=current_user.current_shop_id
                )
                db.session.add(bill)
                db.session.commit()
                #flash('Facture ajoutée avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Une erreur est survenue: ' + str(e), 'error')
                print(str(e))

        elif 'edit_bill' in request.form:
            try:
                # Get the bill ID from the form
                bill_id = request.form.get('bill_id')

                # Find the bill in the database
                bill = SupplierBill.query.filter_by(
                    id=bill_id,
                    shop_id=current_user.current_shop_id
                ).first_or_404()

                # Update bill details
                bill.bill_number = request.form.get('bill_number')
                bill.amount = float(request.form.get('amount'))
                bill.paid_amount = float(request.form.get('paid_amount'))

                db.session.commit()
                #flash('Facture mise à jour avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Une erreur est survenue: ' + str(e), 'error')
                print(str(e))

        elif 'make_payment' in request.form:
            try:
                # Get the bill ID from the form
                bill_id = request.form.get('bill_id')

                # Find the bill in the database
                bill = SupplierBill.query.filter_by(
                    id=bill_id,
                    shop_id=current_user.current_shop_id
                ).first_or_404()

                # Process the payment
                payment_amount = float(request.form.get('payment_amount'))
                remaining = bill.amount - bill.paid_amount

                if payment_amount > remaining:
                    flash('Le paiement ne peut pas dépasser le montant restant!', 'error')
                else:
                    bill.paid_amount += payment_amount
                    db.session.commit()
                    flash('Paiement traité avec succès!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Une erreur est survenue: ' + str(e), 'error')
                print(str(e))

        return redirect(url_for('expenses.supplier_list'))

    # GET request: Fetch suppliers with bills for current shop
    page = request.args.get('page', 1, type=int)
    suppliers = SupplierBill.query.join(Supplier) \
        .filter(SupplierBill.shop_id == current_user.current_shop_id) \
        .order_by(desc(SupplierBill.date)) \
        .paginate(page=page, per_page=10, error_out=False)

    # Get all suppliers for the dropdown in the new bill modal
    all_suppliers = Supplier.query.filter_by(shop_id=current_user.current_shop_id).all()

    return render_template('suppliers/suppliers.html',
                           suppliers=suppliers,
                           all_suppliers=all_suppliers)


@expenses.route('/supplier/<int:supplier_id>/bills', methods=['GET', 'POST'])
@login_required
def supplier_bills(supplier_id):
    supplier = Supplier.query.filter_by(
        id=supplier_id,
        shop_id=current_user.current_shop_id
    ).first_or_404()

    if request.method == 'POST':
        if 'add_bill' in request.form:
            bill = SupplierBill(
                supplier_id=supplier.id,
                bill_number=request.form.get('bill_number'),
                amount=float(request.form.get('amount')),
                paid_amount=float(request.form.get('paid_amount', 0)),
                date=datetime.strptime(request.form.get('date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d'),
                user_id=current_user.id,
                shop_id=current_user.current_shop_id
            )
            db.session.add(bill)
            db.session.commit()
            flash('Supplier bill added successfully!', 'success')

        elif 'make_payment' in request.form:
            bill = SupplierBill.query.filter_by(
                id=request.form.get('bill_id'),
                shop_id=current_user.current_shop_id
            ).first_or_404()
            payment_amount = float(request.form.get('payment_amount'))

            remaining = bill.amount - bill.paid_amount
            if payment_amount > remaining:
                flash('Payment amount cannot exceed remaining balance!', 'error')
            else:
                bill.paid_amount += payment_amount
                db.session.commit()
                flash('Payment processed successfully!', 'success')

        return redirect(url_for('expenses.supplier_bills', supplier_id=supplier_id))

    page = request.args.get('page', 1, type=int)
    bills = SupplierBill.query.filter_by(
        supplier_id=supplier_id,
        shop_id=current_user.current_shop_id
    ).order_by(desc(SupplierBill.date)) \
        .paginate(page=page, per_page=10, error_out=False)

    total_amount = SupplierBill.query.filter_by(
        supplier_id=supplier_id,
        shop_id=current_user.current_shop_id
    ).with_entities(
        db.func.sum(SupplierBill.amount).label('total'),
        db.func.sum(SupplierBill.paid_amount).label('paid')
    ).first()

    return render_template('suppliers/supplier_bills.html',
                           supplier=supplier,
                           bills=bills,
                           total_amount=total_amount.total or 0,
                           total_paid=total_amount.paid or 0,
                           remaining=((total_amount.total or 0) - (total_amount.paid or 0)))
