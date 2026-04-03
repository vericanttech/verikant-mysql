# app/admin.py
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from .auth import admin_required
from .import db
from .models import ShopProfile

admin = Blueprint('admin', __name__)


@admin.route('/shops', methods=['GET'])
@login_required
@admin_required
def manage_shops():
    shops = ShopProfile.query.all()
    return render_template('auth/manage_shops.html', shops=shops)


@admin.route('/shops/create', methods=['POST'])
@login_required
@admin_required
def create_shop():
    name = request.form.get('name')
    shop = ShopProfile(name=name)
    db.session.add(shop)
    db.session.commit()

    with db.shop_session(shop.id):
        db.create_all()
    flash('Boutique créée avec succès', 'success')
    return redirect(url_for('admin.manage_shops'))