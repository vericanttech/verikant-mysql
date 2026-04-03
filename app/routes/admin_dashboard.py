from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Shop, User, UserShop
from app.extensions import db
from werkzeug.security import generate_password_hash
from functools import wraps

admin_dashboard = Blueprint('admin_dashboard', __name__)

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'superadmin', False):
            return "Forbidden", 403
        return f(*args, **kwargs)
    return decorated_function

@admin_dashboard.route('/admin/shops', methods=['GET', 'POST'])
@login_required
@superadmin_required
def manage_shops():
    # Handle form submissions
    if request.method == 'POST':
        form_type = request.form.get('form_type')
        if form_type == 'create_shop':
            name = request.form['name']
            business_type = request.form.get('business_type')
            shop = Shop(name=name, business_type=business_type, is_active=True)
            db.session.add(shop)
            db.session.commit()
            flash('Shop created!', 'success')
            return redirect(url_for('admin_dashboard.manage_shops'))
        elif form_type == 'create_user':
            username = request.form['username']
            password = request.form['password']
            role = request.form['role']
            shop_id = request.form.get('shop_id')
            # Create user
            user = User(name=username, password_hash=generate_password_hash(password), role=role, is_active=True)
            db.session.add(user)
            db.session.flush()  # Get user.id
            # Optionally assign to shop
            if shop_id:
                user_shop = UserShop(user_id=user.id, shop_id=int(shop_id), role=role, is_active=True)
                db.session.add(user_shop)
                # Set as current shop if not set
                if not user.current_shop_id:
                    user.current_shop_id = int(shop_id)
            db.session.commit()
            flash('User created!', 'success')
            return redirect(url_for('admin_dashboard.manage_shops'))
        elif form_type == 'delete_shop':
            shop_id = request.form['shop_id']
            shop = Shop.query.get(shop_id)
            if shop:
                # Soft delete: deactivate shop and remove all user associations
                shop.is_active = False
                UserShop.query.filter_by(shop_id=shop_id).delete()
                db.session.commit()
                flash('Shop deleted (deactivated) and user associations removed.', 'success')
            return redirect(url_for('admin_dashboard.manage_shops'))
        elif form_type == 'delete_user':
            user_id = request.form['user_id']
            user = User.query.get(user_id)
            if user:
                # Soft delete: deactivate user and remove all shop associations
                user.is_active = False
                UserShop.query.filter_by(user_id=user_id).delete()
                db.session.commit()
                flash('User deleted (deactivated) and shop associations removed.', 'success')
            return redirect(url_for('admin_dashboard.manage_shops'))

    # GET: Show dashboard
    shops = Shop.query.order_by(Shop.id.desc()).all()
    users = User.query.order_by(User.id.desc()).all()
    return render_template('admin/manage_shops.html', shops=shops, users=users) 