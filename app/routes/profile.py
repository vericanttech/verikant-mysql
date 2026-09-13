from flask import Blueprint, render_template, request, jsonify, url_for, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from app import db
from app.auth import admin_required
from app.models import (
    BoutiqueTransaction, Check, EmployeeLoan, EmployeeSalary, Expense, Loan,
    Product, SalesBill, Shop, ShopPhone, SupplierBill, UserShop,
)
from app.currencies import (
    COUNTRIES, country_options, currency_for_country, currency_label,
    normalize_country_code, shop_currency_code,
)
from app.ui_i18n import current_ui_language

UPLOAD_FOLDER = os.path.join('app', 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

profile = Blueprint('profile', __name__)


def shop_currency_is_locked(shop):
    """Currency becomes immutable once prices or financial history exist."""
    models = (
        Product, SalesBill, Expense, SupplierBill, Loan, BoutiqueTransaction,
        Check, EmployeeSalary, EmployeeLoan,
    )
    return any(
        db.session.query(model.id).filter(model.shop_id == shop.id).first() is not None
        for model in models
    )


def get_current_shop():
    """Get current shop with proper admin access control."""
    if not current_user.current_shop_id:
        return None

    current_shop = Shop.query.get(current_user.current_shop_id)
    if not current_shop or not current_shop.is_active:
        return None

    # Allow global admin
    if current_user.role == 'admin':
        return current_shop

    # Allow shop admin
    user_shop = UserShop.query.filter_by(
        user_id=current_user.id,
        shop_id=current_shop.id,
        role='admin',
        is_active=True
    ).first()

    return current_shop if user_shop else None


@profile.route('/shop-profile', methods=['GET'])
@login_required
@admin_required
def view_profile():
    shop = get_current_shop()
    if not shop:
        return jsonify({'error': 'No access to shop profile'}), 403
    language = current_ui_language()
    selected_country = normalize_country_code(shop.country_code)
    selected_currency = shop_currency_code(shop)
    return render_template(
        'profile/shop_profile.html',
        current_shop=shop,
        currency_locked=shop_currency_is_locked(shop),
        currency_options=country_options(language),
        selected_country=selected_country,
        selected_country_name=COUNTRIES[selected_country]['name_en' if language == 'en' else 'name_fr'],
        selected_currency=selected_currency,
        selected_currency_label=currency_label(selected_currency),
    )


@profile.route('/shop-profile/phone', methods=['POST'])
@login_required
@admin_required
def add_phone():
    shop = get_current_shop()
    if not shop:
        return jsonify({'error': 'No access to shop profile'}), 403

    phone = request.form.get('phone')
    if not phone:
        return jsonify({'error': 'Phone number is required'}), 400

    try:
        new_phone = ShopPhone(shop_id=shop.id, phone=phone)
        db.session.add(new_phone)
        db.session.commit()

        return jsonify({
            'success': True,
            'phone': {
                'id': new_phone.id,
                'phone': new_phone.phone
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@profile.route('/shop-profile/phone/<int:phone_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_phone(phone_id):
    shop = get_current_shop()
    if not shop:
        return jsonify({'error': 'No access to shop profile'}), 403

    phone = ShopPhone.query.get_or_404(phone_id)

    # Verify phone belongs to current shop
    if phone.shop_id != shop.id:
        return jsonify({'error': 'Phone number not found'}), 404

    try:
        db.session.delete(phone)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@profile.route('/shop-profile/update', methods=['POST'])
@login_required
@admin_required
def update_profile():
    shop = get_current_shop()
    if not shop:
        return jsonify({'error': 'No access to shop profile'}), 403

    try:
        field = request.form.get('field')
        value = request.form.get('value')

        # Add debugging
        print(f"Updating field: {field} with value: {value}")

        # Check if field exists in model
        valid_fields = [
            'name', 'business_type', 'address', 'email', 'email_password',
            'tax_id', 'country_code', 'show_all_sales',
        ]
        if field not in valid_fields:
            return jsonify({'error': f'Invalid field: {field}'}), 400

        # Update the field
        if field == 'show_all_sales':
            coerced = str(value).lower() in ('true', '1', 'on', 'yes')
            setattr(shop, field, coerced)
            value = coerced
        elif field == 'country_code':
            requested_country = (value or '').strip().upper()
            if requested_country not in COUNTRIES:
                return jsonify({'error': 'Unsupported country or currency'}), 400
            current_country = normalize_country_code(shop.country_code)
            if requested_country != current_country and shop_currency_is_locked(shop):
                return jsonify({
                    'error': 'Currency cannot be changed after products or financial activity exist.'
                }), 409
            code = currency_for_country(requested_country)
            shop.country_code = requested_country
            shop.currency_code = code
            shop.currency = currency_label(code)
            language = current_ui_language()
            value = requested_country
            display_value = (
                COUNTRIES[requested_country]['name_en' if language == 'en' else 'name_fr']
                + f" · {code} ({currency_label(code)})"
            )
        else:
            setattr(shop, field, value)
        db.session.commit()

        return jsonify({
            'success': True,
            'value': value,
            'display_value': locals().get('display_value', value),
            'currency_code': shop.currency_code,
            'currency_label': shop.currency,
        })

    except Exception as e:
        print(f"Error updating profile: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# Add this new route to handle logo deletion
@profile.route('/shop-profile/logo/cleanup', methods=['POST'])
@login_required
@admin_required
def cleanup_old_logo():
    try:
        old_path = request.json.get('old_path')
        if not old_path:
            return jsonify({'error': 'No path provided'}), 400

        # Extract the filename from the static URL
        old_path = old_path.split('static/')[-1] if 'static/' in old_path else old_path

        # Construct full file path
        full_path = os.path.join(current_app.static_folder, old_path)

        # Check if file exists and delete
        if os.path.exists(full_path):
            os.remove(full_path)
            return jsonify({'success': True})

        return jsonify({'success': True, 'message': 'File not found, might be already deleted'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Modify the existing update_logo route to include the old path in response
@profile.route('/shop-profile/logo', methods=['POST'])
@login_required
@admin_required
def update_logo():
    shop = get_current_shop()
    if not shop:
        return jsonify({'error': 'No access to shop profile'}), 403

    if 'logo' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['logo']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        try:
            # Store old logo path for cleanup
            old_logo_path = shop.logo_path

            # Create shop-specific folder
            shop_folder = os.path.join(UPLOAD_FOLDER, f'shop_{shop.id}')
            os.makedirs(shop_folder, exist_ok=True)

            # Save file with shop-specific prefix
            filename = f"shop_{shop.id}_{secure_filename(file.filename)}"
            filepath = os.path.join(shop_folder, filename)
            file.save(filepath)

            # Update database with relative path
            shop.logo_path = f'uploads/shop_{shop.id}/{filename}'
            db.session.commit()

            return jsonify({
                'success': True,
                'logo_url': url_for('static', filename=shop.logo_path),
                'old_path': old_logo_path
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Invalid file type'}), 400

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
