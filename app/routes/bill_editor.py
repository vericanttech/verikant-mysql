from flask import Blueprint, request, redirect, url_for, flash, render_template, abort
from flask_login import login_required, current_user
from app import db
from app.models import SalesBill, SalesDetail, Client, Product
from functools import wraps
from app.utils import admin_required, recalculate_sales_bill_totals
from app.sales_visibility import abort_if_bill_hidden_in_vat_mode
from app.pricing_validation import validate_unit_selling_not_below_buying

bill_editor = Blueprint('bill_editor', __name__)

def get_shop_filtered_query(model):
    return model.query.filter_by(shop_id=current_user.current_shop_id)

@bill_editor.route('/edit/client', methods=['POST'])
@login_required
def change_bill_client():
    bill = get_shop_filtered_query(SalesBill).filter_by(id=request.form['bill_id']).first_or_404()
    abort_if_bill_hidden_in_vat_mode(bill)
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
    abort_if_bill_hidden_in_vat_mode(bill)
    product_id = int(request.form['product_id'])
    quantity = float(request.form['quantity'])
    price = float(request.form['price'])
    product = get_shop_filtered_query(Product).filter_by(id=product_id).first_or_404()

    try:
        validate_unit_selling_not_below_buying(price, product.buying_price, product.name)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('bills.bill_detail', bill_id=bill.id))

    # Check if product already exists on bill
    existing_detail = SalesDetail.query.filter_by(bill_id=bill.id, product_id=product_id).first()
    if existing_detail:
        # Update existing item
        existing_detail.quantity += quantity
        if price != existing_detail.selling_price:
            existing_detail.selling_price = price
        existing_detail.total_amount = existing_detail.quantity * existing_detail.selling_price
    else:
        # Add new item
        detail = SalesDetail(
            bill_id=bill.id,
            product_id=product.id,
            quantity=quantity,
            selling_price=price,
            buying_price=product.buying_price,
            total_amount=quantity * price,
        )
        db.session.add(detail)
    recalculate_sales_bill_totals(bill)
    db.session.commit()
    flash("Article ajouté ou mis à jour", "success")
    return redirect(url_for('bills.bill_detail', bill_id=bill.id))

@bill_editor.route('/edit/delete-product', methods=['POST'])
@login_required
@admin_required
def delete_product_from_bill():
    detail = SalesDetail.query.get(request.form['detail_id'])
    if not detail:
        abort(404)
    bill = SalesBill.query.get(detail.bill_id)
    abort_if_bill_hidden_in_vat_mode(bill)
    db.session.delete(detail)
    db.session.flush()
    recalculate_sales_bill_totals(bill)
    db.session.commit()
    return redirect(url_for('bills.bill_detail', bill_id=bill.id))

@bill_editor.route('/edit/update-price', methods=['POST'])
@login_required
@admin_required
def update_product_price():
    detail = SalesDetail.query.get(request.form['detail_id'])
    if not detail:
        abort(404)
    new_price = float(request.form['new_price'])
    product = get_shop_filtered_query(Product).filter_by(id=detail.product_id).first_or_404()
    try:
        validate_unit_selling_not_below_buying(new_price, product.buying_price, product.name)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('bills.bill_detail', bill_id=detail.bill_id))
    detail.selling_price = new_price
    detail.total_amount = detail.quantity * new_price
    bill = SalesBill.query.get(detail.bill_id)
    abort_if_bill_hidden_in_vat_mode(bill)
    recalculate_sales_bill_totals(bill)
    db.session.commit()
    return redirect(url_for('bills.bill_detail', bill_id=bill.id))