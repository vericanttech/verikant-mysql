from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.utils import admin_only_action
from app import db
from app.models import Client, SalesBill
from sqlalchemy import desc

clients = Blueprint('clients', __name__)


@clients.route('/clients', methods=['GET', 'POST'])
@login_required
@admin_only_action('delete_client')
def client_list():
    shop_id = current_user.current_shop_id  # Assuming the shop_id is tied to the current user

    if request.method == 'POST':
        if 'add_client' in request.form:
            client = Client(
            shop_id=shop_id,  # Add shop_id to the client
            name=request.form.get('client_name'),
            address = request.form.get('client_address'),
            phone = request.form.get('client_phone'),
            email = request.form.get('client_email')
            )
            db.session.add(client)
            db.session.commit()
            #flash('Client added successfully!', 'success')

        elif 'edit_client' in request.form:
            client = Client.query.get_or_404(request.form.get('client_id'))
            client.name = request.form.get('name')
            client.address = request.form.get('address')
            client.phone = request.form.get('phone')
            client.email = request.form.get('email')
            db.session.commit()
            flash('Client updated successfully!', 'success')

        elif 'delete_client' in request.form:
            client = Client.query.get_or_404(request.form.get('client_id'))
            db.session.delete(client)
            db.session.commit()
            #flash('Client deleted successfully!', 'success')

        return redirect(url_for('clients.client_list'))

    # GET request
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search = request.args.get('search', '').strip()

    query = Client.query.filter_by(shop_id=shop_id)  # Filter by shop_id

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Client.name.ilike(search_term),
                Client.address.ilike(search_term),
                Client.phone.ilike(search_term),
                Client.email.ilike(search_term)
            )
        )

    clients = query.order_by(Client.name).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template('clients/clients.html', clients=clients, search=search)


@clients.route('/clients/<int:client_id>')
@login_required
def client_detail(client_id):
    shop_id = current_user.current_shop_id # Assuming the shop_id is tied to the current user
    client = Client.query.filter_by(id=client_id, shop_id=shop_id).first_or_404()  # Ensure client is tied to the shop

    # Get client's bills
    page = request.args.get('page', 1, type=int)
    per_page = 10

    bills = SalesBill.query.filter_by(client_id=client_id, shop_id=shop_id) \
        .order_by(desc(SalesBill.date)) \
        .paginate(page=page, per_page=per_page, error_out=False)

    # Calculate client statistics
    stats = SalesBill.query.filter_by(client_id=client_id, shop_id=shop_id) \
        .with_entities(
            db.func.sum(SalesBill.total_amount).label('total_purchases'),
            db.func.sum(SalesBill.paid_amount).label('total_paid'),
            db.func.count(SalesBill.id).label('total_bills')
        ).first()

    return render_template('clients/detail.html',
                           client=client,
                           bills=bills,
                           stats=stats)



@clients.route('/api/clients/search')
@login_required
def client_search():
    """API endpoint for client search (used in select dropdowns)"""
    shop_id = current_user.current_shop_id # Assuming the shop_id is tied to the current user
    search = request.args.get('q', '').strip()

    query = Client.query.filter_by(shop_id=shop_id)  # Filter by shop_id

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Client.name.ilike(search_term),
                Client.phone.ilike(search_term)
            )
        )

    clients = query.limit(10).all()

    return [{
        'id': client.id,
        'text': f"{client.name} ({client.phone})" if client.phone else client.name
    } for client in clients]
