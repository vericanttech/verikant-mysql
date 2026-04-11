import os

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for,  make_response
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app.utils import admin_only_action, format_datetime
from app import db
from app.models import SalesBill, SalesDetail, Client, Product, PaymentTransaction, StockMovement, Shop
from app.email_utils import send_balance_notifications
from datetime import datetime, timedelta

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from io import BytesIO
from flask import current_app

import csv
from io import StringIO
from datetime import date

from app.vitrine_helpers import build_vitrine_shop_url, qr_png_data_url
from app.invoice_pdf import build_invoice_pdf_buffer


bills = Blueprint('bills', __name__)


def _parse_vat_from_request(data):
    """Return vat_rate (0–1) or None from POS JSON. Prices are HT."""
    apply_vat = data.get('apply_vat') in (True, 'true', '1', 1)
    raw = data.get('vat_rate')
    if not apply_vat or raw is None or raw == '':
        return None
    try:
        r = float(raw)
    except (TypeError, ValueError):
        return None
    if r <= 0:
        return None
    if r > 1.0:
        r = r / 100.0
    if r > 1.0:
        r = 1.0
    return r


def _parse_discount_from_request(data):
    """Return discount_rate (0–1) or None from POS JSON. Applied on total HT des lignes before TVA."""
    apply_discount = data.get('apply_discount') in (True, 'true', '1', 1)
    raw = data.get('discount_rate_percent')
    if not apply_discount or raw is None or raw == '':
        return None
    try:
        r = float(raw)
    except (TypeError, ValueError):
        return None
    if r <= 0:
        return None
    if r > 1.0:
        r = r / 100.0
    if r > 1.0:
        r = 1.0
    return r


def get_shop_filtered_query(model, additional_filters=None):
    """Helper function to filter queries by shop_id"""
    query = model.query.filter_by(shop_id=current_user.current_shop_id)
    if additional_filters:
        query = query.filter(additional_filters)
    return query


def get_shop_profile():
    """
    Get the current shop based on the current_user's shop_id
    Returns the Shop object or None if not found
    """
    if not current_user or not current_user.current_shop_id:
        return None

    # Get the current shop directly
    current_shop = Shop.query.get(current_user.current_shop_id)

    return current_shop


def _shop_logo_fs_path(shop):
    """Absolute path to shop logo file under the static folder, or None."""
    if not shop or not getattr(shop, "logo_path", None):
        return None
    path = os.path.join(current_app.static_folder, shop.logo_path)
    return path if os.path.isfile(path) else None


@bills.route("/bills/<int:bill_id>/invoice.pdf")
@login_required
def export_bill_invoice_pdf(bill_id):
    bill = (
        get_shop_filtered_query(SalesBill)
        .options(
            joinedload(SalesBill.sales_details).joinedload(SalesDetail.product),
            joinedload(SalesBill.client),
            joinedload(SalesBill.user),
        )
        .filter_by(id=bill_id)
        .first_or_404()
    )
    shop_profile = get_shop_profile()
    vitrine_public_url = None
    if shop_profile and getattr(shop_profile, "is_active", True):
        vitrine_public_url = url_for(
            "vitrine.public_vitrine", shop_id=shop_profile.id, _external=True
        )
    buf = build_invoice_pdf_buffer(
        bill,
        shop_profile,
        vitrine_public_url=vitrine_public_url,
        logo_fs_path=_shop_logo_fs_path(shop_profile),
    )
    fn = f"facture_{bill.bill_number}.pdf"
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'inline; filename="{fn}"'
    return resp


@bills.route('/api/customers/search')
@login_required
def search_customers():
    term = request.args.get('term', '').strip()

    if len(term) < 2:
        return jsonify([])

    customers = Client.query.filter_by(shop_id=current_user.current_shop_id).filter(
        db.or_(
            Client.name.ilike(f'%{term}%'),
            Client.phone.ilike(f'%{term}%')
        )
    ).limit(10).all()

    return jsonify([{
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'email': c.email,
        'address': c.address
    } for c in customers])


@bills.route('/api/customers', methods=['POST'])
@login_required
def create_customer():
    data = request.json

    try:
        customer = Client(
            shop_id=current_user.current_shop_id,
            name=data['name'],
            phone=data.get('phone'),
            email=data.get('email'),
            address=data.get('address')
        )
        db.session.add(customer)
        db.session.commit()

        return jsonify({
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'email': customer.email,
            'address': customer.address
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@bills.route('/bills/<int:bill_id>/print/<print_format>')
@login_required
def print_bill(bill_id, print_format='standard'):
    bill = get_shop_filtered_query(SalesBill).filter_by(id=bill_id).first_or_404()
    shop_profile = get_shop_profile()

    if print_format == 'bluetooth':
        gross_ht = sum(float(d.total_amount) for d in bill.sales_details)
        return jsonify({
            'bill_data': {
                'company_name': shop_profile.name if shop_profile else '',
                'company_tax_id': shop_profile.tax_id if shop_profile else '',
                'phone': ', '.join(phone.phone for phone in shop_profile.phones) if shop_profile and shop_profile.phones else '',
                'bill_number': bill.bill_number,
                'date': bill.date,
                'client': {
                    'name': bill.client.name if bill.client else None,
                    'phone': bill.client.phone if bill.client else None
                },
                'items': [{
                    'name': detail.product.name,
                    'quantity': detail.quantity,
                    'price': detail.selling_price,
                    'total': detail.total_amount
                } for detail in bill.sales_details],
                'gross_amount_ht': gross_ht,
                'discount_rate': bill.discount_rate,
                'discount_amount': bill.discount_amount,
                'amount_ht': bill.amount_ht,
                'vat_rate': bill.vat_rate,
                'vat_amount': bill.vat_amount,
                'total_amount': bill.total_amount,
                'paid_amount': bill.paid_amount,
                'remaining_amount': bill.remaining_amount
            }
        })

    template = 'bills/print_thermal.html' if print_format == 'thermal' else 'bills/print.html'
    vitrine_public_url = None
    vitrine_qr_data_url = None
    if shop_profile and getattr(shop_profile, 'is_active', True):
        vitrine_public_url = build_vitrine_shop_url(shop_profile.id)
        try:
            vitrine_qr_data_url = qr_png_data_url(vitrine_public_url)
        except Exception:
            vitrine_qr_data_url = None
    return render_template(
        template,
        bill=bill,
        details=bill.sales_details,
        payments=bill.payments,
        shop_profile=shop_profile,
        vitrine_public_url=vitrine_public_url,
        vitrine_qr_data_url=vitrine_qr_data_url,
    )


@bills.route('/pos')
@login_required
def pos():
    return render_template('pos/pos.html')

@bills.route('/api/posproducts')
@login_required
def api_products():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    category_id = request.args.get('category')
    search = request.args.get('search', '').strip()

    query = get_shop_filtered_query(Product)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if search:
        search_term = f'%{search}%'
        query = query.filter(Product.name.ilike(search_term))

    products_page = query.paginate(page=page, per_page=per_page, error_out=False)

    # Get shop currency from profile
    shop_profile = get_shop_profile()
    currency = shop_profile.currency if shop_profile else 'FCFA'

    # Build products JSON response
    products_data = []
    for product in products_page.items:
        products_data.append({
            'id': product.id,
            'name': product.name,
            'selling_price': product.selling_price,
            'stock': product.stock,
            'currency': currency,
            'image_url': url_for('static', filename=product.image_path) if product.image_path else None,
        })

    # Build pagination data
    pagination = {
        'current_page': products_page.page,
        'total_pages': products_page.pages,
        'has_prev': products_page.has_prev,
        'has_next': products_page.has_next,
        'total_items': products_page.total
    }

    return jsonify({
        'products': products_data,
        'pagination': pagination
    })





@bills.route('/api/products')
@login_required
def get_products():
    products = get_shop_filtered_query(Product).filter(Product.stock > 0).all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'price': p.selling_price,
        'stock': p.stock,
        'category': p.category.name if p.category else None,
        'image_url': url_for('static', filename=p.image_path) if p.image_path else None,
    } for p in products])


@bills.route('/api/product/<int:product_id>')
@login_required
def get_product(product_id):
    product = get_shop_filtered_query(Product).filter_by(id=product_id).first_or_404()
    return jsonify({
        'id': product.id,
        'name': product.name,
        'price': product.selling_price,
        'stock': product.stock,
        'image_url': url_for('static', filename=product.image_path) if product.image_path else None,
    })


@bills.route('/api/process_sale', methods=['POST'])
@login_required
def process_sale():
    data = request.json
    print(data)
    items = data.get('items', [])
    client_id = data.get('client_id')
    initial_payment = float(data.get('initial_payment', 0))
    shop_id = current_user.current_shop_id

    if not items:
        return jsonify({'error': 'No items in sale'}), 400

    try:
        gross_ht = sum(float(item['total']) for item in items)
        discount_rate = _parse_discount_from_request(data)
        if discount_rate is not None:
            discount_amount = round(gross_ht * discount_rate, 2)
            amount_ht = round(gross_ht - discount_amount, 2)
        else:
            discount_amount = 0.0
            discount_rate = None
            amount_ht = gross_ht
        vat_rate = _parse_vat_from_request(data)
        if vat_rate is not None:
            vat_amount = round(amount_ht * vat_rate, 2)
        else:
            vat_amount = 0.0
        total_amount = amount_ht + vat_amount

        # Calculate remaining amount, ensuring it's never negative
        remaining_amount = max(0, total_amount - initial_payment)

        # Determine if there's change to be given back
        change_amount = max(0, initial_payment - total_amount)

        # Adjust paid amount to not exceed total amount
        actual_paid_amount = min(initial_payment, total_amount)

        bill = SalesBill(
            shop_id=shop_id,
            bill_number=int(data.get('bill_number')),
            client_id=client_id,
            amount_ht=amount_ht,
            discount_rate=discount_rate,
            discount_amount=discount_amount,
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            total_amount=total_amount,
            paid_amount=actual_paid_amount,
            remaining_amount=remaining_amount,
            user_id=current_user.id,
            date=datetime.now(),
            status='paid' if remaining_amount == 0 else 'partially_paid'
        )
        db.session.add(bill)
        db.session.flush()

        if actual_paid_amount > 0:
            payment = PaymentTransaction(
                shop_id=shop_id,
                bill_id=bill.id,
                amount=actual_paid_amount,
                payment_method=data.get('payment_method', 'cash'),
                user_id=current_user.id,
                date=datetime.now(),
                notes='Initial payment during sale'
            )
            db.session.add(payment)

            # Record change amount if any
            if change_amount > 0:
                payment.notes += f' (Monnaie rendue: {change_amount})'

        for item in items:
            product = get_shop_filtered_query(Product).filter_by(id=item['product_id']).first()
            if not product:
                raise ValueError(f"Product {item['product_id']} not found")

            quantity = float(item['quantity'])  # Allow decimal quantities
            if product.stock < quantity:
                raise ValueError(f"Insufficient stock for {product.name}")

            detail = SalesDetail(
                bill_id=bill.id,
                product_id=product.id,
                quantity=quantity,  # Save quantity as float
                selling_price=float(item['price']),
                buying_price=product.buying_price,
                total_amount=float(item['total'])
            )
            db.session.add(detail)

            product.stock -= quantity  # Reduce stock with decimals

            movement = StockMovement(
                shop_id=shop_id,
                product_id=product.id,
                quantity=-quantity,  # Use float for fractional stock tracking
                movement_type='sale',
                reference_id=bill.id,
                reference_type='sale',
                user_id=current_user.id,
                date=datetime.now(),
                notes=f'Vente depuis facture #{bill.bill_number}'
            )
            db.session.add(movement)

        db.session.commit()
        return jsonify({
            'message': 'Sale processed successfully',
            'bill_id': bill.id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400


@bills.route('/bills', methods=['GET', 'POST'])
@login_required
@admin_only_action('delete_bill')
def bill_list():
    if request.method == 'POST':
        if 'add_bill' in request.form:
            client = get_shop_filtered_query(Client).filter_by(id=request.form.get('client_id')).first()
            total_amount = float(request.form.get('total_amount'))
            initial_payment = float(request.form.get('paid_amount'))

            bill = SalesBill(
                shop_id=current_user.current_shop_id,
                bill_number=int(request.form.get('bill_number')),
                client_id=client.id if client else None,
                amount_ht=total_amount,
                discount_rate=None,
                discount_amount=0,
                vat_rate=None,
                vat_amount=0,
                total_amount=total_amount,
                paid_amount=initial_payment,
                remaining_amount=total_amount - initial_payment,
                user_id=current_user.id,
                date=datetime.now(),
                status='paid' if initial_payment >= total_amount else 'partially_paid'
            )
            db.session.add(bill)

            if initial_payment > 0:
                payment = PaymentTransaction(
                    shop_id=current_user.current_shop_id,
                    bill_id=bill.id,
                    amount=initial_payment,
                    payment_method='cash',
                    user_id=current_user.id,
                    date=datetime.now(),
                    notes='Initial payment'
                )
                db.session.add(payment)

            db.session.commit()
            flash('Bill added successfully!', 'success')

        elif 'make_payment' in request.form:
            print("function was called!")
            bill = get_shop_filtered_query(SalesBill).filter_by(id=request.form.get('bill_id')).first_or_404()
            payment_amount = float(request.form.get('payment_amount'))

            if payment_amount > bill.remaining_amount:
                flash('Payment amount cannot exceed remaining balance!', 'error')
            else:
                payment = PaymentTransaction(
                    shop_id=current_user.current_shop_id,
                    bill_id=bill.id,
                    amount=payment_amount,
                    payment_method=request.form.get('payment_method', 'cash'),
                    user_id=current_user.id,
                    date=datetime.now(),
                    notes=request.form.get('notes')
                )
                db.session.add(payment)

                bill.paid_amount += payment_amount
                bill.remaining_amount -= payment_amount
                bill.status = 'paid' if bill.remaining_amount == 0 else 'partially_paid'

                db.session.commit()
                flash('Payment processed successfully!', 'success')

        elif 'delete_bill' in request.form:
            bill = get_shop_filtered_query(SalesBill).filter_by(id=request.form.get('bill_id')).first_or_404()
            try:
                sale_details = SalesDetail.query.filter_by(bill_id=bill.id).all()

                for detail in sale_details:
                    product = get_shop_filtered_query(Product).filter_by(id=detail.product_id).first()
                    if product:
                        # Restore stock
                        product.stock += detail.quantity

                        # Log stock movement
                        movement = StockMovement(
                            shop_id=current_user.current_shop_id,
                            product_id=product.id,
                            quantity=detail.quantity,
                            movement_type='return',
                            reference_id=bill.id,
                            reference_type='bill',
                            user_id=current_user.id,
                            date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            notes='Retour stock suite à la suppression de la facture'
                        )
                        db.session.add(movement)

                PaymentTransaction.query.filter_by(bill_id=bill.id).delete()
                SalesDetail.query.filter_by(bill_id=bill.id).delete()
                db.session.delete(bill)
                db.session.commit()
                flash('Facture supprimée, stock rétabli et mouvement enregistré.', 'success')

            except Exception as e:
                db.session.rollback()
                flash(f'Erreur lors de la suppression: {str(e)}', 'error')
        return redirect(url_for('bills.bill_list'))

    page = request.args.get('page', 1, type=int)
    per_page = 30
    # Modified query filtering:
    query = get_shop_filtered_query(SalesBill)

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date and end_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(SalesBill.date.between(start, end))

    client_id = request.args.get('client_id')
    client_name = request.args.get('client_name', '').strip()

    if client_id:
        query = query.filter(SalesBill.client_id == client_id)
    elif client_name:
        query = query.join(Client).filter(Client.name.ilike(f"%{client_name}%"))

    # Add filter for unpaid bills
    show_unpaid = request.args.get('show_unpaid')
    if show_unpaid == 'true':
        query = query.filter(SalesBill.remaining_amount > 0)

    show_overdue = request.args.get('overdue_payments') == 'true'
    if show_overdue:
        # Subquery to get the latest payment date for each bill
        from sqlalchemy.orm import aliased
        from sqlalchemy import and_, func
        LastPayment = aliased(PaymentTransaction)
        subq = db.session.query(
            PaymentTransaction.bill_id,
            func.max(PaymentTransaction.date).label('last_payment_date')
        ).group_by(PaymentTransaction.bill_id).subquery()

        # Use full datetime string for 7 days ago as cutoff
        week_ago_dt = datetime.now() - timedelta(days=7)
        week_ago_str = week_ago_dt.strftime('%Y-%m-%d %H:%M:%S.%f')
        query = query.join(subq, SalesBill.id == subq.c.bill_id)
        query = query.filter(
            SalesBill.remaining_amount > 0,
            subq.c.last_payment_date < week_ago_str
        )

    paginated_bills = query.order_by(SalesBill.date.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    filtered_bills = query.all()
    total_paid = sum(bill.paid_amount for bill in filtered_bills)
    total_remaining = sum(bill.remaining_amount for bill in filtered_bills)
    clients = get_shop_filtered_query(Client).order_by(Client.name).all()

    return render_template('bills/bills.html',
                           bills=paginated_bills.items,
                           pagination=paginated_bills,
                           total_paid=total_paid,
                           total_remaining=total_remaining,
                           clients=clients)


@bills.route('/bills/<int:bill_id>')
@login_required
def bill_detail(bill_id):
    bill = get_shop_filtered_query(SalesBill).options(
        joinedload(SalesBill.payments).joinedload(PaymentTransaction.user),
    ).filter_by(id=bill_id).first_or_404()
    clients = get_shop_filtered_query(Client).order_by(Client.name).all()
    products = get_shop_filtered_query(Product).all()
    payments_sorted = sorted(
        bill.payments,
        key=lambda p: ((p.created_at or ''), p.id or 0),
    )
    return render_template('bills/detail.html',
                           bill=bill,
                           details=bill.sales_details,
                           payments=payments_sorted,
                           all_products=products,
                           clients=clients)


@bills.route('/sales')
@login_required
def sale_list():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    start_date = request.args.get('start')
    end_date = request.args.get('end')
    query = SalesDetail.query.join(SalesBill).filter(
        SalesBill.shop_id == current_user.current_shop_id
    )

    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1, microseconds=-1)
            query = query.filter(SalesBill.date.between(start_dt, end_dt))
        except ValueError as e:
            current_app.logger.error(f"Date parsing error: {e}")
            pass

    # Pagination
    paginated_sales = query.order_by(SalesBill.date.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    filtered_sales = query.all()
    total_sales = sum(sale.total_amount for sale in filtered_sales)
    total_profit = sum(sale.total_amount - (sale.buying_price * sale.quantity)
                       for sale in filtered_sales)

    return render_template('sales/sales.html',
                           sales=paginated_sales.items,
                           pagination=paginated_sales,
                           total_sales=total_sales,
                           total_profit=total_profit)





@bills.route('/api/get_next_bill_number', methods=['GET'])
@login_required
def get_next_bill_number():
    shop_id = current_user.current_shop_id
    user_id = current_user.id

    try:
        today = datetime.now().date()

        last_bill = get_shop_filtered_query(SalesBill).filter(
            SalesBill.user_id == user_id,
            func.date(SalesBill.date) == today
        ).order_by(SalesBill.bill_number.desc()).first()

        date_prefix = today.strftime('%d%m%y')
        user_prefix = f"{user_id:03d}"

        if last_bill:
            last_sequence = int(str(last_bill.bill_number)[-3:])
            next_sequence = last_sequence + 1
        else:
            next_sequence = 1

        new_bill_number = int(f"{date_prefix}{user_prefix}{next_sequence:03d}")

        return jsonify({
            'bill_number': new_bill_number
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 400


#@bills.route('/export_sales')
#@login_required
#def export_sales():
   # print("accessed!")


@bills.route('/stock_movements')
@login_required
def stock_movements():
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Base query with shop filter
    query = get_shop_filtered_query(StockMovement)
    # Add the user id to know who did what in the stock inventory.

    # Get filter parameters
    product_id = request.args.get('product_id', type=int)
    movement_type = request.args.get('movement_type')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    # Apply filters
    if product_id:
        query = query.filter(StockMovement.product_id == product_id)
    if movement_type:
        query = query.filter(StockMovement.movement_type == movement_type)
    if date_from:
        query = query.filter(StockMovement.date >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        query = query.filter(StockMovement.date <= datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))

    # Order by date descending
    query = query.order_by(StockMovement.date.desc())

    # Paginate results
    movements = query.paginate(page=page, per_page=per_page)

    # Get products for filter dropdown
    products = get_shop_filtered_query(Product).order_by(Product.name).all()

    return render_template(
        'stock_movement/stock_movements.html',
        movements=movements,
        products=products,
        movement_types=['sale', 'purchase', 'adjustment', 'return'],
        selected_product=product_id,
        selected_type=movement_type,
        date_from=date_from,
        date_to=date_to
    )


@bills.route('/export_sales_pdf')
@login_required
def export_sales_pdf():
    start_date = request.args.get('start')
    end_date = request.args.get('end')

    # If no dates provided, use today's date
    if not start_date or not end_date:
        today = date.today()
        start_date = today.strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

    # Build query
    query = SalesDetail.query.join(SalesBill).filter(
        SalesBill.shop_id == current_user.current_shop_id
    )

    if start_date and end_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1, microseconds=-1)
            query = query.filter(SalesBill.date.between(start_dt, end_dt))
        except ValueError as e:
            current_app.logger.error(f"Date parsing error: {e}")

    sales = query.order_by(SalesBill.date.desc()).all()

    # Calculate totals
    total_sales = sum(sale.total_amount for sale in sales)
    total_profit = sum(sale.total_amount - (sale.buying_price * sale.quantity) for sale in sales)

    # Get currency from shop profile
    shop_profile = get_shop_profile()
    currency = shop_profile.currency if shop_profile else 'FCFA'

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))

    # Get styles
    styles = getSampleStyleSheet()

    # Company name style (larger, bold, centered)
    company_style = ParagraphStyle(
        'CompanyTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=10,
        alignment=TA_CENTER,
        textColor=colors.darkblue
    )

    # Report title style (smaller than company name)
    title_style = ParagraphStyle(
        'ReportTitle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=30,
        alignment=TA_CENTER
    )

    fiscal_style = ParagraphStyle(
        'FiscalInfo',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_CENTER,
        textColor=colors.black,
        spaceAfter=12
    )

    # Build PDF content
    elements = []

    # Add company name first (centered and prominent)
    if shop_profile and shop_profile.name:
        company_title = Paragraph(f"<b>{shop_profile.name}</b>", company_style)
        elements.append(company_title)
        if shop_profile.tax_id:
            fiscal_info = Paragraph(f"NIF / Numéro fiscal: {shop_profile.tax_id}", fiscal_style)
            elements.append(fiscal_info)
        elements.append(Spacer(1, 10))

    # Add report title below company name
    if start_date == end_date:
        title_text = f"Rapport des Ventes - {start_date}"
    else:
        title_text = f"Rapport des Ventes - Du {start_date} au {end_date}"

    title = Paragraph(title_text, title_style)
    elements.append(title)
    elements.append(Spacer(1, 20))

    # Prepare table data
    if current_user.role == 'admin':
        headers = ['Date', 'N° Facture', 'Produit', 'Qté', 'Prix/U', 'Total', 'Bénéfice']
    else:
        headers = ['Date', 'N° Facture', 'Produit', 'Qté', 'Prix/U', 'Total']

    data = [headers]

    # Add data rows
    for sale in sales:
        row = [
            format_datetime(sale.bill.date),
            str(sale.bill.bill_number),
            sale.product.name,
            str(sale.quantity),
            f"{sale.selling_price:,.0f} {currency}",
            f"{sale.total_amount:,.0f} {currency}"
        ]

        if current_user.role == 'admin':
            profit = sale.total_amount - (sale.buying_price * sale.quantity)
            row.append(f"{profit:,.0f} {currency}")

        data.append(row)

    # Add totals row
    if current_user.role == 'admin':
        totals_row = ['', '', '', '', 'TOTAUX:', f"{total_sales:,.0f} {currency}", f"{total_profit:,.0f} {currency}"]
    else:
        totals_row = ['', '', '', '', 'TOTAUX:', f"{total_sales:,.0f} {currency}"]

    data.append(totals_row)

    # Create table
    table = Table(data)

    # Style the table
    table_style = [
        # Header row styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

        # Data rows styling
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.beige, colors.white]),

        # Totals row styling
        ('BACKGROUND', (0, -1), (-1, -1), colors.lightblue),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 10),

        # General table styling
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]

    table.setStyle(TableStyle(table_style))
    elements.append(table)

    # Add summary at the bottom
    elements.append(Spacer(1, 20))
    summary_style = ParagraphStyle(
        'Summary',
        parent=styles['Normal'],
        fontSize=12,
        alignment=TA_RIGHT
    )

    summary_text = f"<b>Résumé:</b><br/>"
    summary_text += f"Nombre de ventes: {len(sales)}<br/>"
    summary_text += f"Total des ventes: {total_sales:,.0f} {currency}<br/>"

    if current_user.role == 'admin':
        summary_text += f"Bénéfice total: {total_profit:,.0f} {currency}<br/>"

    summary_text += f"Généré le: {datetime.now().strftime('%d/%m/%Y')}"

    summary = Paragraph(summary_text, summary_style)
    elements.append(summary)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    # Create response
    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'

    # Generate filename
    if start_date == end_date:
        filename = f"rapport_ventes_{start_date}.pdf"
    else:
        filename = f"rapport_ventes_{start_date}_au_{end_date}.pdf"

    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response


@bills.route('/send-balance-notifications', methods=['POST'])
@login_required
@admin_only_action('send_balance_notifications')
def send_balance_notifications_route():
    """
    Send balance notifications to all clients with unpaid bills
    """
    try:
        # Get shop information
        shop = get_shop_profile()
        if not shop:
            flash('Shop not found', 'error')
            return redirect(url_for('bills.bill_list'))
        
        if not shop.email:
            flash('Shop email not configured. Please configure shop email first.', 'error')
            return redirect(url_for('bills.bill_list'))
        
        if not shop.email_password:
            flash('Email password not configured. Please configure email password in shop profile first.', 'error')
            return redirect(url_for('bills.bill_list'))
        
        # Use stored email password from database
        email_password = shop.email_password
        
        # Send balance notifications
        success, message = send_balance_notifications(shop.id, email_password)
        
        if success:
            flash(message, 'success')
        else:
            flash(message, 'error')
        
        return redirect(url_for('bills.bill_list'))
        
    except Exception as e:
        flash(f'Error sending balance notifications: {str(e)}', 'error')
        return redirect(url_for('bills.bill_list'))


@bills.route('/bills/<int:bill_id>/send-reminder', methods=['POST'])
@login_required
@admin_only_action('send_balance_notifications')
def send_single_bill_reminder_route(bill_id):
    """
    Send a reminder for a single bill to its client
    """
    shop = get_shop_profile()
    if not shop:
        flash('Shop not found', 'error')
        return redirect(url_for('bills.bill_detail', bill_id=bill_id))
    if not shop.email or not shop.email_password:
        flash('Email ou mot de passe du magasin non configuré.', 'error')
        return redirect(url_for('bills.bill_detail', bill_id=bill_id))
    from app.email_utils import send_single_bill_reminder
    success, message = send_single_bill_reminder(bill_id, shop.id, shop.email_password)
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    return redirect(url_for('bills.bill_detail', bill_id=bill_id))





