"""Public vitrine pages and admin marketing settings."""
from __future__ import annotations

import uuid

import os

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    make_response,
    abort,
    Response,
    current_app,
)
from flask_login import login_required, current_user
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app import db
from app.auth import admin_required
from app.models import Shop, Product, VitrineVisit, VitrineProductSelection
from app.vitrine_helpers import build_vitrine_shop_url, public_base_url as vitrine_public_base_url
from app.vitrine_public_guard import (
    apply_vitrine_security_headers,
    public_vitrine_rate_limit_ok,
    should_persist_vitrine_visit,
)
from app.vitrine_share_card import get_or_create_cached_jpeg

vitrine_bp = Blueprint('vitrine', __name__)


def _current_shop_admin():
    if not current_user.current_shop_id:
        return None
    shop = Shop.query.get(current_user.current_shop_id)
    if not shop or not shop.is_active:
        return None
    return shop


def _vitrine_selection_rows(shop_id):
    return (
        VitrineProductSelection.query.filter_by(shop_id=shop_id)
        .options(joinedload(VitrineProductSelection.product))
        .order_by(VitrineProductSelection.sort_order, VitrineProductSelection.id)
        .all()
    )


@vitrine_bp.route('/v/<int:shop_id>')
def public_vitrine(shop_id):
    """Page toujours disponible pour un magasin actif (logo, infos, produits choisis)."""
    if not public_vitrine_rate_limit_ok():
        return Response(
            'Trop de requêtes. Réessayez dans une minute.',
            status=429,
            headers={'Retry-After': '60', 'Content-Type': 'text/plain; charset=utf-8'},
        )

    shop = (
        Shop.query.options(joinedload(Shop.phones))
        .filter_by(id=shop_id, is_active=True)
        .first_or_404()
    )

    visitor_key = request.cookies.get('vitrine_vid') or uuid.uuid4().hex
    if should_persist_vitrine_visit(visitor_key, shop.id):
        visit = VitrineVisit(shop_id=shop.id, visitor_key=visitor_key)
        db.session.add(visit)
        db.session.commit()

    rows = _vitrine_selection_rows(shop.id)
    vitrine_items = []
    for row in rows:
        p = row.product
        if not p or p.shop_id != shop.id:
            continue
        vitrine_items.append(
            {
                'product': p,
                'is_promo': bool(row.is_promo),
                'is_new_arrival': bool(row.is_new_arrival),
            }
        )

    vitrine_new_items = [x for x in vitrine_items if x['is_new_arrival']]
    vitrine_promo_items = [x for x in vitrine_items if x['is_promo']]
    vitrine_other_items = [
        x for x in vitrine_items if not x['is_new_arrival'] and not x['is_promo']
    ]

    resp = make_response(
        render_template(
            'vitrine/public.html',
            shop=shop,
            vitrine_items=vitrine_items,
            vitrine_new_items=vitrine_new_items,
            vitrine_promo_items=vitrine_promo_items,
            vitrine_other_items=vitrine_other_items,
            vitrine_url=build_vitrine_shop_url(shop.id),
        )
    )
    resp.set_cookie(
        'vitrine_vid',
        visitor_key,
        max_age=60 * 60 * 24 * 400,
        samesite='Lax',
        secure=request.is_secure,
    )
    apply_vitrine_security_headers(resp)
    return resp


@vitrine_bp.route('/v/<slug>')
def public_vitrine_legacy_slug(slug):
    shop = Shop.query.filter_by(vitrine_slug=slug, is_active=True).first()
    if shop:
        return redirect(url_for('vitrine.public_vitrine', shop_id=shop.id), code=301)
    abort(404)


@vitrine_bp.route('/marketing/vitrine', methods=['GET', 'POST'])
@login_required
@admin_required
def marketing_vitrine():
    shop = _current_shop_admin()
    if not shop:
        flash("Magasin introuvable.", 'error')
        return redirect(url_for('bills.pos'))

    if request.method == 'POST':
        body = (request.form.get('vitrine_body') or '').strip() or None
        promo_end = (request.form.get('vitrine_promo_end') or '').strip() or None
        raw_pct = (request.form.get('vitrine_discount_percent') or '').strip()
        discount_pct = None
        if raw_pct:
            try:
                discount_pct = float(str(raw_pct).replace(',', '.'))
            except ValueError:
                discount_pct = None

        shop.vitrine_body = body
        shop.vitrine_promo_end = promo_end
        shop.vitrine_discount_percent = discount_pct

        db.session.commit()
        flash('Paramètres vitrine enregistrés.', 'success')
        return redirect(url_for('vitrine.marketing_vitrine'))

    from datetime import datetime, timedelta

    week_cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')

    q = VitrineVisit.query.filter(
        VitrineVisit.shop_id == shop.id,
        VitrineVisit.created_at >= week_cutoff,
    )
    visits_7d = q.count()
    unique_7d = (
        db.session.query(VitrineVisit.visitor_key)
        .filter(
            VitrineVisit.shop_id == shop.id,
            VitrineVisit.created_at >= week_cutoff,
        )
        .distinct()
        .count()
    )

    public_url = build_vitrine_shop_url(shop.id)
    has_fixed_public_host = bool((vitrine_public_base_url() or '').strip())

    selections = _vitrine_selection_rows(shop.id)
    selected_product_ids = {r.product_id for r in selections}

    catalog_products = (
        Product.query.filter_by(shop_id=shop.id)
        .order_by(Product.name)
        .limit(500)
        .all()
    )

    return render_template(
        'marketing/vitrine_settings.html',
        shop=shop,
        visits_7d=visits_7d,
        unique_visitors_7d=unique_7d,
        public_url=public_url,
        has_fixed_public_host=has_fixed_public_host,
        selections=selections,
        catalog_products=catalog_products,
        selected_product_ids=selected_product_ids,
    )


@vitrine_bp.route('/marketing/vitrine/product/add', methods=['POST'])
@login_required
@admin_required
def vitrine_add_product():
    shop = _current_shop_admin()
    if not shop:
        flash("Magasin introuvable.", 'error')
        return redirect(url_for('bills.pos'))

    try:
        product_id = int(request.form.get('product_id', 0))
    except (TypeError, ValueError):
        flash('Produit invalide.', 'error')
        return redirect(url_for('vitrine.marketing_vitrine'))

    product = Product.query.filter_by(id=product_id, shop_id=shop.id).first()
    if not product:
        flash('Produit introuvable.', 'error')
        return redirect(url_for('vitrine.marketing_vitrine'))

    exists = VitrineProductSelection.query.filter_by(
        shop_id=shop.id, product_id=product_id
    ).first()
    if exists:
        flash('Ce produit est déjà dans la vitrine.', 'error')
        return redirect(url_for('vitrine.marketing_vitrine'))

    max_order = (
        db.session.query(func.max(VitrineProductSelection.sort_order))
        .filter(VitrineProductSelection.shop_id == shop.id)
        .scalar()
    )
    next_order = (max_order or 0) + 10

    row = VitrineProductSelection(
        shop_id=shop.id,
        product_id=product_id,
        sort_order=next_order,
        is_promo=False,
        is_new_arrival=False,
    )
    db.session.add(row)
    db.session.commit()
    flash('Produit ajouté à la vitrine.', 'success')
    return redirect(url_for('vitrine.marketing_vitrine'))


@vitrine_bp.route('/marketing/vitrine/product/toggle', methods=['POST'])
@login_required
@admin_required
def vitrine_toggle_product():
    """Add or remove a product from the vitrine (same action toggles)."""
    shop = _current_shop_admin()
    if not shop:
        flash("Magasin introuvable.", 'error')
        return redirect(url_for('bills.pos'))

    try:
        product_id = int(request.form.get('product_id', 0))
    except (TypeError, ValueError):
        flash('Produit invalide.', 'error')
        return redirect(url_for('vitrine.marketing_vitrine'))

    product = Product.query.filter_by(id=product_id, shop_id=shop.id).first()
    if not product:
        flash('Produit introuvable.', 'error')
        return redirect(url_for('vitrine.marketing_vitrine'))

    existing = VitrineProductSelection.query.filter_by(
        shop_id=shop.id, product_id=product_id
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
    else:
        max_order = (
            db.session.query(func.max(VitrineProductSelection.sort_order))
            .filter(VitrineProductSelection.shop_id == shop.id)
            .scalar()
        )
        next_order = (max_order or 0) + 10
        row = VitrineProductSelection(
            shop_id=shop.id,
            product_id=product_id,
            sort_order=next_order,
            is_promo=False,
            is_new_arrival=False,
        )
        db.session.add(row)
        db.session.commit()

    return redirect(url_for('vitrine.marketing_vitrine'))


@vitrine_bp.route('/marketing/vitrine/product/<int:row_id>/remove', methods=['POST'])
@login_required
@admin_required
def vitrine_remove_product(row_id):
    shop = _current_shop_admin()
    if not shop:
        flash("Magasin introuvable.", 'error')
        return redirect(url_for('bills.pos'))

    row = VitrineProductSelection.query.filter_by(id=row_id, shop_id=shop.id).first()
    if row:
        db.session.delete(row)
        db.session.commit()
        flash('Produit retiré de la vitrine.', 'success')
    return redirect(url_for('vitrine.marketing_vitrine'))


@vitrine_bp.route('/marketing/vitrine/product/<int:row_id>/promo', methods=['POST'])
@login_required
@admin_required
def vitrine_toggle_promo(row_id):
    shop = _current_shop_admin()
    if not shop:
        flash("Magasin introuvable.", 'error')
        return redirect(url_for('bills.pos'))

    row = VitrineProductSelection.query.filter_by(id=row_id, shop_id=shop.id).first()
    if row:
        row.is_promo = not bool(row.is_promo)
        db.session.commit()
        flash('Mise en avant mise à jour.', 'success')
    return redirect(url_for('vitrine.marketing_vitrine'))


@vitrine_bp.route('/marketing/vitrine/product/<int:row_id>/new_arrival', methods=['POST'])
@login_required
@admin_required
def vitrine_toggle_new_arrival(row_id):
    shop = _current_shop_admin()
    if not shop:
        flash("Magasin introuvable.", 'error')
        return redirect(url_for('bills.pos'))

    row = VitrineProductSelection.query.filter_by(id=row_id, shop_id=shop.id).first()
    if row:
        row.is_new_arrival = not bool(row.is_new_arrival)
        db.session.commit()
        flash('Badge nouveauté mis à jour.', 'success')
    return redirect(url_for('vitrine.marketing_vitrine'))


@vitrine_bp.route('/marketing/vitrine/product/<int:row_id>/move', methods=['POST'])
@login_required
@admin_required
def vitrine_move_product(row_id):
    shop = _current_shop_admin()
    if not shop:
        flash("Magasin introuvable.", 'error')
        return redirect(url_for('bills.pos'))

    direction = (request.form.get('direction') or '').strip().lower()
    rows = _vitrine_selection_rows(shop.id)
    ids_order = [r.id for r in rows]
    try:
        idx = ids_order.index(row_id)
    except ValueError:
        return redirect(url_for('vitrine.marketing_vitrine'))

    if direction == 'up' and idx > 0:
        ids_order[idx], ids_order[idx - 1] = ids_order[idx - 1], ids_order[idx]
    elif direction == 'down' and idx < len(ids_order) - 1:
        ids_order[idx], ids_order[idx + 1] = ids_order[idx + 1], ids_order[idx]
    else:
        return redirect(url_for('vitrine.marketing_vitrine'))

    for i, rid in enumerate(ids_order):
        row = VitrineProductSelection.query.filter_by(id=rid, shop_id=shop.id).first()
        if row:
            row.sort_order = (i + 1) * 10
    db.session.commit()
    return redirect(url_for('vitrine.marketing_vitrine'))


@vitrine_bp.route('/marketing/vitrine/product/<int:row_id>/share-card.jpg')
@login_required
@admin_required
def vitrine_share_card_jpeg(row_id):
    """JPEG partage WhatsApp (cache disque 24h, admin uniquement)."""
    shop = _current_shop_admin()
    if not shop:
        abort(404)

    row = VitrineProductSelection.query.filter_by(id=row_id, shop_id=shop.id).first()
    if not row:
        abort(404)

    product = Product.query.filter_by(id=row.product_id, shop_id=shop.id).first()
    if not product:
        abort(404)

    shop_full = Shop.query.options(joinedload(Shop.phones)).filter_by(id=shop.id).first()
    if not shop_full:
        abort(404)

    vitrine_url = build_vitrine_shop_url(shop.id)
    static_root = os.path.join(current_app.root_path, 'static')

    data = get_or_create_cached_jpeg(
        current_app.instance_path,
        shop_full,
        product,
        row,
        vitrine_url,
        static_root,
    )

    safe_name = ''.join(c if c.isalnum() or c in '-_' else '_' for c in (product.name or 'produit'))[:40]
    fn = f'vitrine-{shop.id}-{product.id}-{safe_name}.jpg'

    return Response(
        data,
        mimetype='image/jpeg',
        headers={
            'Content-Disposition': f'inline; filename="{fn}"',
            'Cache-Control': 'private, max-age=3600',
        },
    )
