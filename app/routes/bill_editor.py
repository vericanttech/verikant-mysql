from flask import Blueprint, request, redirect, url_for, flash, render_template
from flask_login import login_required, current_user
from app import db
from app.models import SalesBill, SalesDetail, Client, Product
from functools import wraps
from app.utils import admin_required

bill_editor = Blueprint('bill_editor', __name__)

def get_shop_filtered_query(model):
    return model.query.filter_by(shop_id=current_user.current_shop_id)

@bill_editor.route('/edit/client', methods=['POST'])
@login_required
def change_bill_client():
    bill = get_shop_filtered_query(SalesBill).filter_by(id=request.form['bill_id']).first_or_404()
    new_client_id = request.form['client_id']
    client = get_shop_filtered_query(Client).filter_by(id=new_client_id).first()
    if client:
        bill.client_id = client.id
        db.session.commit()
        flash("Client mis à jour avec succès", "success")
    else:
        flash("Client non trouvé", "error")
    return redirect(url_for('bills.bill_detail', bill_id=bill.id))

@bill_editor.route('/edit/add-product', methods=['POST'])
@login_required
@admin_required
def add_product_to_bill():
    bill = get_shop_filtered_query(SalesBill).filter_by(id=request.form['bill_id']).first_or_404()
    product_id = int(request.form['product_id'])
    quantity = float(request.form['quantity'])
    price = float(request.form['price'])
    
    # Check if product already exists in bill
    existing_detail = SalesDetail.query.filter_by(bill_id=bill.id, product_id=product_id).first()
    if existing_detail:
        # Update existing item
        old_total = existing_detail.total_amount
        existing_detail.quantity += quantity
        if price != existing_detail.selling_price:
            existing_detail.selling_price = price
        existing_detail.total_amount = existing_detail.quantity * existing_detail.selling_price
        # Update bill totals
        difference = existing_detail.total_amount - old_total
        bill.total_amount += difference
        bill.remaining_amount += difference
    else:
        # Add new item
        product = Product.query.get(product_id)
        detail = SalesDetail(
            bill_id=bill.id,
            product_id=product.id,
            quantity=quantity,
            selling_price=price,
            buying_price=product.buying_price,
            total_amount=quantity * price
        )
        bill.total_amount += detail.total_amount
        bill.remaining_amount += detail.total_amount
        db.session.add(detail)
    db.session.commit()
    flash("Article ajouté ou mis à jour", "success")
    return redirect(url_for('bills.bill_detail', bill_id=bill.id))

@bill_editor.route('/edit/delete-product', methods=['POST'])
@login_required
@admin_required
def delete_product_from_bill():
    detail = SalesDetail.query.get(request.form['detail_id'])
    bill = SalesBill.query.get(detail.bill_id)
    bill.total_amount -= detail.total_amount
    bill.remaining_amount -= detail.total_amount
    db.session.delete(detail)
    db.session.commit()
    return redirect(url_for('bills.bill_detail', bill_id=bill.id))

@bill_editor.route('/edit/update-price', methods=['POST'])
@login_required
@admin_required
def update_product_price():
    detail = SalesDetail.query.get(request.form['detail_id'])
    old_total = detail.total_amount
    new_price = float(request.form['new_price'])
    detail.selling_price = new_price
    detail.total_amount = detail.quantity * new_price
    bill = SalesBill.query.get(detail.bill_id)
    bill.total_amount += detail.total_amount - old_total
    bill.remaining_amount += detail.total_amount - old_total
    db.session.commit()
    return redirect(url_for('bills.bill_detail', bill_id=bill.id))