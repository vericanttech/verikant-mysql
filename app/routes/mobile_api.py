import hashlib
import hmac
import math
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from app.extensions import db
from app.models import (
    Category,
    Client,
    Expense,
    Loan,
    MobileCashierOperation,
    MobileRefreshToken,
    MobileSaleSubmission,
    PaymentTransaction,
    Product,
    ProductBarcode,
    SalesBill,
    SalesDetail,
    Shop,
    StockMovement,
    User,
    UserShop,
)


mobile_api = Blueprint('mobile_api', __name__, url_prefix='/api/v1')


def _utc_now():
    return datetime.now(timezone.utc)


def _utc_text(value):
    return value.astimezone(timezone.utc).isoformat()


def _access_lifetime():
    return int(current_app.config.get('MOBILE_ACCESS_TOKEN_SECONDS', 900))


def _refresh_lifetime():
    return int(current_app.config.get('MOBILE_REFRESH_TOKEN_DAYS', 30))


def _access_serializer():
    return URLSafeTimedSerializer(
        current_app.config['SECRET_KEY'], salt='verikant-mobile-access-v1'
    )


def _issue_access_token(user_id, shop_id):
    return _access_serializer().dumps(
        {'type': 'access', 'user_id': user_id, 'shop_id': shop_id}
    )


def _refresh_hash(raw_token):
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def _new_refresh_token(user_id, shop_id):
    raw_token = secrets.token_urlsafe(48)
    token = MobileRefreshToken(
        token_hash=_refresh_hash(raw_token),
        user_id=user_id,
        shop_id=shop_id,
        expires_at=_utc_text(_utc_now() + timedelta(days=_refresh_lifetime())),
    )
    db.session.add(token)
    return raw_token, token


def _username_fingerprint(username):
    key = str(current_app.config['SECRET_KEY']).encode('utf-8')
    normalized = (username or '').strip().casefold().encode('utf-8')
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()[:16]


def _json_error(message, status):
    return jsonify({'error': message}), status


def _client_operation_id(data):
    operation_id = str(data.get('client_operation_id') or '').strip()
    if not operation_id:
        return None
    try:
        uuid.UUID(operation_id)
    except (ValueError, AttributeError):
        raise ValueError('Identifiant local d’opération invalide.')
    return operation_id


def _existing_cashier_operation(operation_id, operation_type):
    if not operation_id:
        return None
    operation = MobileCashierOperation.query.filter_by(
        shop_id=g.mobile_shop.id,
        client_operation_id=operation_id,
    ).first()
    if operation and operation.operation_type != operation_type:
        raise ValueError('Cet identifiant local appartient à une autre opération.')
    return operation


def _remember_cashier_operation(operation_id, operation_type, response):
    if not operation_id:
        return
    db.session.add(MobileCashierOperation(
        shop_id=g.mobile_shop.id,
        user_id=g.mobile_user.id,
        client_operation_id=operation_id,
        operation_type=operation_type,
        response_payload=response,
    ))


def mobile_token_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        header = request.headers.get('Authorization', '')
        if not header.startswith('Bearer '):
            return _json_error('Jeton d’accès manquant.', 401)

        token = header[7:].strip()
        try:
            payload = _access_serializer().loads(token, max_age=_access_lifetime())
        except SignatureExpired:
            return _json_error('Jeton d’accès expiré.', 401)
        except BadSignature:
            return _json_error('Jeton d’accès invalide.', 401)

        if payload.get('type') != 'access':
            return _json_error('Jeton d’accès invalide.', 401)

        user = db.session.get(User, payload.get('user_id'))
        shop = db.session.get(Shop, payload.get('shop_id'))
        membership = None
        if user and shop:
            membership = db.session.get(UserShop, (user.id, shop.id))

        if (
            not user
            or not shop
            or not membership
            or not user.is_active
            or not shop.is_active
            or not membership.is_active
        ):
            return _json_error('Compte ou magasin indisponible.', 403)

        g.mobile_user = user
        g.mobile_shop = shop
        g.mobile_membership = membership
        return view(*args, **kwargs)

    return wrapped


def _login_user(username, password):
    candidates = User.query.filter(
        func.lower(User.name) == username.lower()
    ).order_by(User.id.asc()).all()
    matches = []
    for candidate in candidates:
        try:
            if candidate.password_hash and check_password_hash(
                candidate.password_hash, password
            ):
                matches.append(candidate)
        except (TypeError, ValueError):
            current_app.logger.warning(
                'mobile_auth_event=invalid_password_hash user_id=%s', candidate.id
            )

    if len(matches) == 1:
        return matches[0]
    exact = [candidate for candidate in matches if candidate.name == username]
    return exact[0] if len(exact) == 1 else None


def _session_payload(user, shop, membership, refresh_token):
    return {
        'access_token': _issue_access_token(user.id, shop.id),
        'refresh_token': refresh_token,
        'expires_in': _access_lifetime(),
        'user': {
            'id': user.id,
            'name': user.name,
            'role': membership.role,
            'language_code': user.preferred_language,
        },
        'shop': {
            'id': shop.id,
            'name': shop.name,
            'country_code': shop.country_code,
            'currency_code': shop.currency_code,
        },
    }


@mobile_api.post('/auth/login')
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username') or '').strip()
    password = str(data.get('password') or '')
    fingerprint = _username_fingerprint(username)

    if not username or not password:
        return _json_error('Nom d’utilisateur et mot de passe requis.', 400)

    user = _login_user(username, password)
    if not user or not user.is_active or not user.current_shop_id:
        current_app.logger.warning(
            'mobile_auth_event=login_failed username_fp=%s', fingerprint
        )
        return _json_error('Identifiants incorrects.', 401)

    shop = db.session.get(Shop, user.current_shop_id)
    membership = db.session.get(UserShop, (user.id, user.current_shop_id))
    if not shop or not shop.is_active or not membership or not membership.is_active:
        return _json_error('Compte ou magasin indisponible.', 403)

    raw_refresh, _ = _new_refresh_token(user.id, shop.id)
    db.session.commit()
    current_app.logger.warning(
        'mobile_auth_event=login_success user_id=%s shop_id=%s', user.id, shop.id
    )
    return jsonify({'data': _session_payload(user, shop, membership, raw_refresh)})


def _active_refresh_token(raw_token):
    if not raw_token:
        return None
    token = MobileRefreshToken.query.filter_by(
        token_hash=_refresh_hash(raw_token), revoked_at=None
    ).first()
    if not token:
        return None
    try:
        expires_at = datetime.fromisoformat(token.expires_at)
    except (TypeError, ValueError):
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return token if expires_at > _utc_now() else None


@mobile_api.post('/auth/refresh')
def refresh():
    data = request.get_json(silent=True) or {}
    token = _active_refresh_token(str(data.get('refresh_token') or ''))
    if not token:
        return _json_error('Session expirée. Reconnectez-vous.', 401)

    user = db.session.get(User, token.user_id)
    shop = db.session.get(Shop, token.shop_id)
    membership = db.session.get(UserShop, (token.user_id, token.shop_id))
    if (
        not user
        or not shop
        or not membership
        or not user.is_active
        or not shop.is_active
        or not membership.is_active
    ):
        return _json_error('Compte ou magasin indisponible.', 403)

    token.revoked_at = _utc_text(_utc_now())
    token.last_used_at = token.revoked_at
    raw_refresh, _ = _new_refresh_token(user.id, shop.id)
    db.session.commit()
    return jsonify({'data': _session_payload(user, shop, membership, raw_refresh)})


@mobile_api.post('/auth/logout')
def logout():
    data = request.get_json(silent=True) or {}
    token = _active_refresh_token(str(data.get('refresh_token') or ''))
    if token:
        token.revoked_at = _utc_text(_utc_now())
        db.session.commit()
    return jsonify({'data': {'logged_out': True}})


@mobile_api.put('/preferences')
@mobile_token_required
def update_preferences():
    data = request.get_json(silent=True) or {}
    language = str(data.get('language_code') or '').strip().lower()
    if language not in ('fr', 'en'):
        return _json_error('Langue non prise en charge.', 400)
    g.mobile_user.preferred_language = language
    db.session.commit()
    return jsonify({'data': {'language_code': language}})


@mobile_api.get('/sync/bootstrap')
@mobile_token_required
def bootstrap():
    shop = g.mobile_shop
    products = Product.query.filter_by(shop_id=shop.id).order_by(Product.name).all()
    return jsonify(
        {
            'data': {
                'user': {
                    'id': g.mobile_user.id,
                    'language_code': g.mobile_user.preferred_language,
                },
                'shop': {
                    'id': shop.id,
                    'name': shop.name,
                    'country_code': shop.country_code,
                    'currency_code': shop.currency_code,
                },
                'products': [
                    {
                        'id': product.id,
                        'name': product.name,
                        'category_id': product.category_id,
                        'buying_price': product.buying_price,
                        'selling_price': product.selling_price,
                        'stock': product.stock,
                        'image_url': url_for(
                            'static', filename=product.image_path, _external=True
                        )
                        if product.image_path
                        else None,
                        # Keep the singular value during the Flutter transition.
                        'barcode': next(
                            (
                                barcode.code
                                for barcode in product.barcodes
                                if barcode.is_primary
                            ),
                            product.barcodes[0].code if product.barcodes else None,
                        ),
                        'barcodes': [
                            {
                                'code': barcode.code,
                                'quantity_multiplier': barcode.quantity_multiplier,
                                'is_primary': barcode.is_primary,
                            }
                            for barcode in sorted(
                                product.barcodes,
                                key=lambda item: (not item.is_primary, item.id),
                            )
                        ],
                        'updated_at': product.updated_at,
                    }
                    for product in products
                ],
            }
        }
    )


def _product_payload(product):
    ordered = sorted(product.barcodes, key=lambda item: (not item.is_primary, item.id))
    primary = next((item for item in ordered if item.is_primary), ordered[0] if ordered else None)
    return {
        'id': product.id,
        'name': product.name,
        'category_id': product.category_id,
        'buying_price': product.buying_price,
        'selling_price': product.selling_price,
        'stock': product.stock,
        'min_stock': product.min_stock,
        'image_url': url_for('static', filename=product.image_path, _external=True)
        if product.image_path else None,
        'barcode': primary.code if primary else None,
        'barcodes': [
            {
                'code': item.code,
                'quantity_multiplier': item.quantity_multiplier,
                'is_primary': item.is_primary,
            }
            for item in ordered
        ],
        'updated_at': product.updated_at,
    }


def _positive_number(value, label, allow_zero=False):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} invalide.')
    if number < 0 or (not allow_zero and number == 0):
        raise ValueError(f'{label} invalide.')
    return number


def _category_for_shop(category_id, category_type=None):
    if category_id in (None, ''):
        return None
    try:
        category_id = int(category_id)
    except (TypeError, ValueError):
        return None
    query = Category.query.filter_by(id=category_id, shop_id=g.mobile_shop.id)
    if category_type:
        query = query.filter_by(type=category_type)
    return query.first()


@mobile_api.get('/catalog')
@mobile_token_required
def catalog():
    products = Product.query.filter_by(shop_id=g.mobile_shop.id).order_by(Product.name).all()
    categories = Category.query.filter_by(shop_id=g.mobile_shop.id).order_by(Category.name).all()
    return jsonify({'data': {
        'products': [_product_payload(product) for product in products],
        'categories': [
            {'id': item.id, 'name': item.name, 'type': item.type}
            for item in categories
        ],
    }})


def _replace_product_barcodes(product, values):
    if values is None:
        return
    if not isinstance(values, list):
        raise ValueError('Liste de codes-barres invalide.')
    ProductBarcode.query.filter_by(product_id=product.id, shop_id=g.mobile_shop.id).delete()
    seen = set()
    for index, value in enumerate(values):
        data = value if isinstance(value, dict) else {'code': value}
        code = str(data.get('code') or '').strip()
        if not code or code in seen:
            continue
        if len(code) > 128:
            raise ValueError('Code-barres trop long.')
        seen.add(code)
        multiplier = int(data.get('quantity_multiplier') or 1)
        if multiplier <= 0:
            raise ValueError('Multiplicateur de code-barres invalide.')
        db.session.add(ProductBarcode(
            shop_id=g.mobile_shop.id,
            product_id=product.id,
            code=code,
            quantity_multiplier=multiplier,
            is_primary=bool(data.get('is_primary')) or index == 0,
        ))


@mobile_api.post('/products')
@mobile_token_required
def create_product():
    data = request.get_json(silent=True) or {}
    name = str(data.get('name') or '').strip()
    if not name:
        return _json_error('Nom du produit requis.', 400)
    category = _category_for_shop(data.get('category_id'))
    try:
        product = Product(
            shop_id=g.mobile_shop.id,
            name=name,
            category_id=category.id if category else None,
            buying_price=_positive_number(data.get('buying_price', 0), "Prix d’achat", allow_zero=True),
            selling_price=_positive_number(data.get('selling_price'), 'Prix de vente'),
            stock=int(_positive_number(data.get('stock', 0), 'Stock', allow_zero=True)),
            min_stock=int(_positive_number(data.get('min_stock', 0), 'Stock minimum', allow_zero=True)),
        )
        db.session.add(product)
        db.session.flush()
        _replace_product_barcodes(product, data.get('barcodes'))
        db.session.commit()
    except (ValueError, IntegrityError) as exc:
        db.session.rollback()
        return _json_error(str(exc) if isinstance(exc, ValueError) else 'Code-barres déjà utilisé.', 409)
    return jsonify({'data': _product_payload(product)}), 201


@mobile_api.put('/products/<int:product_id>')
@mobile_token_required
def update_product(product_id):
    product = Product.query.filter_by(id=product_id, shop_id=g.mobile_shop.id).first()
    if not product:
        return _json_error('Produit introuvable.', 404)
    data = request.get_json(silent=True) or {}
    try:
        if 'name' in data:
            name = str(data.get('name') or '').strip()
            if not name:
                raise ValueError('Nom du produit requis.')
            product.name = name
        if 'category_id' in data:
            category = _category_for_shop(data.get('category_id'))
            product.category_id = category.id if category else None
        if 'buying_price' in data:
            product.buying_price = _positive_number(data['buying_price'], "Prix d’achat", allow_zero=True)
        if 'selling_price' in data:
            product.selling_price = _positive_number(data['selling_price'], 'Prix de vente')
        if 'min_stock' in data:
            product.min_stock = int(_positive_number(data['min_stock'], 'Stock minimum', allow_zero=True))
        _replace_product_barcodes(product, data.get('barcodes') if 'barcodes' in data else None)
        db.session.commit()
    except (ValueError, IntegrityError) as exc:
        db.session.rollback()
        return _json_error(str(exc) if isinstance(exc, ValueError) else 'Code-barres déjà utilisé.', 409)
    return jsonify({'data': _product_payload(product)})


@mobile_api.post('/products/<int:product_id>/stock')
@mobile_token_required
def receive_stock(product_id):
    product = Product.query.filter_by(id=product_id, shop_id=g.mobile_shop.id).with_for_update().first()
    if not product:
        return _json_error('Produit introuvable.', 404)
    data = request.get_json(silent=True) or {}
    try:
        quantity = int(_positive_number(data.get('quantity'), 'Quantité'))
    except ValueError as exc:
        return _json_error(str(exc), 400)
    product.stock += quantity
    db.session.add(StockMovement(
        shop_id=g.mobile_shop.id,
        product_id=product.id,
        quantity=quantity,
        movement_type='purchase',
        reference_type='mobile_stock_receipt',
        user_id=g.mobile_user.id,
        date=datetime.now(),
        notes=str(data.get('notes') or 'Entrée de stock mobile').strip(),
    ))
    db.session.commit()
    return jsonify({'data': _product_payload(product)})


@mobile_api.route('/clients', methods=['GET', 'POST'])
@mobile_token_required
def mobile_clients():
    if request.method == 'GET':
        clients = Client.query.filter_by(shop_id=g.mobile_shop.id).order_by(Client.name).all()
        return jsonify({'data': {'clients': [
            {'id': item.id, 'name': item.name, 'phone': item.phone, 'address': item.address}
            for item in clients
        ]}})
    data = request.get_json(silent=True) or {}
    name = str(data.get('name') or '').strip()
    if not name:
        return _json_error('Nom du client requis.', 400)
    client = Client(
        shop_id=g.mobile_shop.id,
        name=name,
        phone=str(data.get('phone') or '').strip() or None,
        address=str(data.get('address') or '').strip() or None,
    )
    db.session.add(client)
    db.session.commit()
    return jsonify({'data': {'id': client.id, 'name': client.name, 'phone': client.phone, 'address': client.address}}), 201


@mobile_api.route('/expenses', methods=['GET', 'POST'])
@mobile_token_required
def mobile_expenses():
    if request.method == 'GET':
        expenses = Expense.query.filter_by(shop_id=g.mobile_shop.id).order_by(Expense.date.desc()).limit(100).all()
        return jsonify({'data': {'expenses': [
            {
                'id': item.id,
                'category_id': item.category_id,
                'category': item.category.name if item.category else 'Autre',
                'amount': item.amount,
                'description': item.description,
                'date': str(item.date),
            }
            for item in expenses
        ]}})
    data = request.get_json(silent=True) or {}
    try:
        operation_id = _client_operation_id(data)
        existing_operation = _existing_cashier_operation(
            operation_id, 'expense'
        )
    except ValueError as exc:
        return _json_error(str(exc), 400)
    if existing_operation:
        return jsonify({
            'data': existing_operation.response_payload,
            'duplicate': True,
        })
    category = _category_for_shop(data.get('category_id'), 'expense')
    if not category:
        category_name = str(data.get('category') or 'Autre').strip() or 'Autre'
        category = Category.query.filter_by(shop_id=g.mobile_shop.id, name=category_name, type='expense').first()
        if not category:
            category = Category(shop_id=g.mobile_shop.id, name=category_name, type='expense')
            db.session.add(category)
            db.session.flush()
    try:
        amount = _positive_number(data.get('amount'), 'Montant')
    except ValueError as exc:
        return _json_error(str(exc), 400)
    expense = Expense(
        shop_id=g.mobile_shop.id,
        category_id=category.id,
        amount=amount,
        date=datetime.now(),
        user_id=g.mobile_user.id,
        description=str(data.get('description') or '').strip(),
    )
    db.session.add(expense)
    db.session.flush()
    response = {
        'id': expense.id,
        'category_id': category.id,
        'category': category.name,
        'amount': expense.amount,
        'description': expense.description,
        'date': str(expense.date),
    }
    _remember_cashier_operation(operation_id, 'expense', response)
    db.session.commit()
    return jsonify({'data': response}), 201


@mobile_api.route('/loans', methods=['GET', 'POST'])
@mobile_token_required
def mobile_loans():
    if request.method == 'GET':
        loans = Loan.query.filter_by(shop_id=g.mobile_shop.id).order_by(Loan.loan_date.desc()).limit(100).all()
        return jsonify({'data': {'loans': [
            {
                'id': item.id,
                'borrower_name': item.borrower_name,
                'amount': item.amount,
                'paid_amount': item.paid_amount,
                'remaining': max(0, float(item.amount) - float(item.paid_amount or 0)),
                'loan_date': str(item.loan_date),
                'due_date': str(item.due_date) if item.due_date else None,
                'status': item.status,
            }
            for item in loans
        ]}})
    data = request.get_json(silent=True) or {}
    borrower = str(data.get('borrower_name') or '').strip()
    if not borrower:
        return _json_error('Nom du client requis.', 400)
    try:
        amount = _positive_number(data.get('amount'), 'Montant')
        paid = _positive_number(data.get('paid_amount', 0), 'Avance', allow_zero=True)
    except ValueError as exc:
        return _json_error(str(exc), 400)
    if paid > amount:
        return _json_error('L’avance dépasse le montant du crédit.', 400)
    loan = Loan(
        shop_id=g.mobile_shop.id,
        borrower_name=borrower,
        amount=amount,
        paid_amount=paid,
        loan_date=datetime.now(),
        due_date=str(data.get('due_date') or '').strip() or None,
        user_id=g.mobile_user.id,
        status='paid' if paid >= amount else 'active',
    )
    db.session.add(loan)
    db.session.commit()
    return jsonify({'data': {'id': loan.id}}), 201


@mobile_api.post('/loans/<int:loan_id>/payments')
@mobile_token_required
def mobile_loan_payment(loan_id):
    loan = Loan.query.filter_by(id=loan_id, shop_id=g.mobile_shop.id).with_for_update().first()
    if not loan:
        return _json_error('Crédit introuvable.', 404)
    data = request.get_json(silent=True) or {}
    try:
        operation_id = _client_operation_id(data)
        existing_operation = _existing_cashier_operation(
            operation_id, 'loan_payment'
        )
        amount = _positive_number(data.get('amount'), 'Montant')
    except ValueError as exc:
        return _json_error(str(exc), 400)
    if existing_operation:
        return jsonify({
            'data': existing_operation.response_payload,
            'duplicate': True,
        })
    remaining = max(0, float(loan.amount) - float(loan.paid_amount or 0))
    if amount > remaining:
        return _json_error('Le paiement dépasse le solde.', 400)
    loan.paid_amount = float(loan.paid_amount or 0) + amount
    loan.status = 'paid' if loan.paid_amount >= loan.amount else 'active'
    response = {
        'id': loan.id,
        'remaining': max(0, loan.amount - loan.paid_amount),
        'status': loan.status,
    }
    _remember_cashier_operation(operation_id, 'loan_payment', response)
    db.session.commit()
    return jsonify({'data': response})


@mobile_api.get('/sales/recent')
@mobile_token_required
def recent_sales():
    bills = SalesBill.query.filter_by(shop_id=g.mobile_shop.id).order_by(SalesBill.date.desc()).limit(100).all()
    return jsonify({'data': {'sales': [_receipt_payload(bill) for bill in bills]}})


def _next_bill_number(user_id, shop_id):
    today = datetime.now().date()
    last_bill = (
        SalesBill.query.filter(
            SalesBill.shop_id == shop_id,
            SalesBill.user_id == user_id,
            func.date(SalesBill.date) == today,
        )
        .order_by(SalesBill.bill_number.desc())
        .first()
    )
    sequence = int(str(last_bill.bill_number)[-3:]) + 1 if last_bill else 1
    if sequence > 999:
        raise ValueError('Limite quotidienne de factures atteinte.')
    return int(f"{today.strftime('%d%m%y')}{user_id:03d}{sequence:03d}")


def _receipt_payload(bill, payment_method=None):
    return {
        'sale_id': bill.id,
        'bill_number': bill.bill_number,
        'total': bill.total_amount,
        'amount_paid': bill.paid_amount,
        'remaining': bill.remaining_amount,
        'status': bill.status,
        'payment_method': payment_method or (
            bill.payments[0].payment_method if bill.payments else 'cash'
        ),
        'created_at': str(bill.date),
        'items': [
            {
                'product_id': detail.product_id,
                'name': detail.product.name,
                'quantity': detail.quantity,
                'unit_price': detail.selling_price,
                'total': detail.total_amount,
            }
            for detail in bill.sales_details
        ],
    }


@mobile_api.post('/sales')
@mobile_token_required
def create_sale():
    data = request.get_json(silent=True) or {}
    client_sale_id = str(data.get('client_sale_id') or '').strip()
    try:
        uuid.UUID(client_sale_id)
    except (ValueError, AttributeError):
        return _json_error('Identifiant local de vente invalide.', 400)

    existing = MobileSaleSubmission.query.filter_by(
        shop_id=g.mobile_shop.id, client_sale_id=client_sale_id
    ).first()
    if existing:
        bill = db.session.get(SalesBill, existing.bill_id)
        return jsonify({'data': _receipt_payload(bill), 'duplicate': True})

    items = data.get('items')
    if not isinstance(items, list) or not items:
        return _json_error('La vente ne contient aucun produit.', 400)

    quantities = {}
    requested_prices = {}
    for item in items:
        if not isinstance(item, dict):
            return _json_error('Ligne de vente invalide.', 400)
        try:
            product_id = int(item.get('product_id'))
            quantity = float(item.get('quantity'))
        except (TypeError, ValueError):
            return _json_error('Produit ou quantité invalide.', 400)
        if quantity <= 0 or not quantity.is_integer():
            return _json_error(
                'Cette version accepte uniquement des quantités entières.', 400
            )
        raw_unit_price = item.get('unit_price')
        if raw_unit_price is not None:
            try:
                unit_price = float(raw_unit_price)
            except (TypeError, ValueError):
                return _json_error('Prix de vente invalide.', 400)
            if unit_price <= 0 or not math.isfinite(unit_price):
                return _json_error('Le prix de vente doit être supérieur à zéro.', 400)
            unit_price = round(unit_price, 2)
            previous_price = requested_prices.get(product_id)
            if previous_price is not None and previous_price != unit_price:
                return _json_error(
                    'Un même produit ne peut pas avoir deux prix différents.', 400
                )
            requested_prices[product_id] = unit_price
        quantities[product_id] = quantities.get(product_id, 0) + int(quantity)

    product_ids = sorted(quantities)
    products = (
        Product.query.filter(
            Product.shop_id == g.mobile_shop.id, Product.id.in_(product_ids)
        )
        .with_for_update()
        .all()
    )
    product_by_id = {product.id: product for product in products}
    if len(product_by_id) != len(product_ids):
        return _json_error('Un produit est introuvable dans ce magasin.', 400)

    for product_id, quantity in quantities.items():
        if product_by_id[product_id].stock < quantity:
            return _json_error(
                f'Stock insuffisant pour {product_by_id[product_id].name}.', 409
            )

    client_id = data.get('client_id')
    if client_id is not None:
        try:
            client_id = int(client_id)
        except (TypeError, ValueError):
            return _json_error('Client invalide.', 400)
        client = Client.query.filter_by(
            id=client_id, shop_id=g.mobile_shop.id
        ).first()
        if not client:
            return _json_error('Client introuvable dans ce magasin.', 400)

    sale_prices = {
        product_id: requested_prices.get(
            product_id, float(product_by_id[product_id].selling_price)
        )
        for product_id in product_ids
    }
    total = round(
        sum(sale_prices[product_id] * quantity for product_id, quantity in quantities.items()),
        2,
    )
    try:
        amount_paid = max(0.0, float(data.get('amount_paid', total)))
    except (TypeError, ValueError):
        return _json_error('Montant payé invalide.', 400)
    actual_paid = min(total, amount_paid)
    remaining = round(total - actual_paid, 2)
    requested_payment_method = str(data.get('payment_method') or 'cash')
    payment_method = {
        'cash': 'cash',
        'card': 'card',
        'check': 'check',
        'transfer': 'transfer',
        'orange_money': 'transfer',
        'wave': 'transfer',
    }.get(requested_payment_method)
    if not payment_method:
        return _json_error('Mode de paiement invalide.', 400)

    now = datetime.now()
    bill = SalesBill(
        shop_id=g.mobile_shop.id,
        bill_number=_next_bill_number(g.mobile_user.id, g.mobile_shop.id),
        client_id=client_id,
        user_id=g.mobile_user.id,
        total_amount=total,
        amount_ht=total,
        discount_amount=0,
        vat_amount=0,
        vat_applied=False,
        paid_amount=actual_paid,
        remaining_amount=remaining,
        date=now,
        status='paid' if remaining == 0 else 'partially_paid',
    )
    db.session.add(bill)
    db.session.flush()

    receipt_items = []
    for product_id, quantity in quantities.items():
        product = product_by_id[product_id]
        unit_price = sale_prices[product_id]
        line_total = round(unit_price * quantity, 2)
        db.session.add(
            SalesDetail(
                bill_id=bill.id,
                product_id=product.id,
                quantity=quantity,
                selling_price=unit_price,
                buying_price=product.buying_price,
                total_amount=line_total,
            )
        )
        product.stock -= quantity
        db.session.add(
            StockMovement(
                shop_id=g.mobile_shop.id,
                product_id=product.id,
                quantity=-quantity,
                movement_type='sale',
                reference_id=bill.id,
                reference_type='mobile_sale',
                user_id=g.mobile_user.id,
                date=now,
                notes=f'Vente mobile #{bill.bill_number}',
            )
        )
        receipt_items.append(
            {
                'product_id': product.id,
                'name': product.name,
                'quantity': quantity,
                'unit_price': unit_price,
                'total': line_total,
            }
        )

    if actual_paid > 0:
        notes = 'Paiement initial depuis application mobile'
        if requested_payment_method != payment_method:
            notes += f' ({requested_payment_method})'
        db.session.add(
            PaymentTransaction(
                shop_id=g.mobile_shop.id,
                bill_id=bill.id,
                amount=actual_paid,
                payment_method=payment_method,
                user_id=g.mobile_user.id,
                date=now,
                notes=notes,
            )
        )

    if remaining > 0 and client_id is not None:
        db.session.add(
            Loan(
                shop_id=g.mobile_shop.id,
                borrower_name=client.name,
                amount=total,
                paid_amount=actual_paid,
                loan_date=now,
                user_id=g.mobile_user.id,
                status='active',
            )
        )

    db.session.add(
        MobileSaleSubmission(
            shop_id=g.mobile_shop.id,
            user_id=g.mobile_user.id,
            client_sale_id=client_sale_id,
            bill_id=bill.id,
        )
    )

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = MobileSaleSubmission.query.filter_by(
            shop_id=g.mobile_shop.id, client_sale_id=client_sale_id
        ).first()
        if existing:
            existing_bill = db.session.get(SalesBill, existing.bill_id)
            return jsonify(
                {'data': _receipt_payload(existing_bill), 'duplicate': True}
            )
        raise

    return (
        jsonify(
            {
                'data': {
                    'sale_id': bill.id,
                    'bill_number': bill.bill_number,
                    'receipt': {
                        'sale_id': bill.id,
                        'bill_number': bill.bill_number,
                        'shop_name': g.mobile_shop.name,
                        'currency_code': g.mobile_shop.currency_code,
                        'total': total,
                        'amount_paid': actual_paid,
                        'remaining': remaining,
                        'payment_method': requested_payment_method,
                        'created_at': now.isoformat(),
                        'items': receipt_items,
                    },
                }
            }
        ),
        201,
    )
