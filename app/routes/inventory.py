import os
import uuid
from typing import Optional

from werkzeug.utils import secure_filename

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app, make_response
from flask_login import login_required, current_user
from app import db
from app.models import Product, Category, StockMovement, UserShop
from datetime import datetime
from app.utils import admin_only_action
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from io import BytesIO


inventory = Blueprint('inventory', __name__)

_PRODUCT_IMAGE_MAX_BYTES = 900 * 1024  # after client resize; still guard on server
_ALLOWED_IMAGE_EXT = {'jpg', 'jpeg', 'png', 'webp'}


def _allowed_product_image(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in _ALLOWED_IMAGE_EXT


def _delete_product_image_file(relative_path: Optional[str]) -> None:
    if not relative_path:
        return
    base = os.path.abspath(current_app.static_folder)
    full = os.path.abspath(os.path.join(base, relative_path))
    if not full.startswith(base + os.sep) and full != base:
        return
    if os.path.isfile(full):
        try:
            os.remove(full)
        except OSError:
            current_app.logger.exception('Could not remove product image %s', full)


def _save_product_image(product: Product, file_storage) -> Optional[str]:
    """Save uploaded file; return relative static path like uploads/products/shop_1/xxx.jpg"""
    if not file_storage or not file_storage.filename:
        return None
    if not _allowed_product_image(file_storage.filename):
        return None
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > _PRODUCT_IMAGE_MAX_BYTES:
        return None

    shop_id = product.shop_id
    folder = os.path.join(current_app.static_folder, 'uploads', 'products', f'shop_{shop_id}')
    os.makedirs(folder, exist_ok=True)

    ext = secure_filename(file_storage.filename).rsplit('.', 1)[-1].lower()
    if ext == 'jpeg':
        ext = 'jpg'
    if ext not in _ALLOWED_IMAGE_EXT:
        ext = 'jpg'
    fname = f'{uuid.uuid4().hex}.{ext}'
    full_path = os.path.join(folder, fname)
    file_storage.save(full_path)
    return f'uploads/products/shop_{shop_id}/{fname}'


@inventory.route('/inventory', methods=['GET', 'POST'])
@login_required
@admin_only_action('delete_product')
def product_list():
    shop_id = current_user.current_shop_id

    if request.method == 'POST':
        if 'add_product' in request.form:
            try:
                # Start a transaction
                product = Product(
                    shop_id=shop_id,
                    name=request.form.get('name'),
                    selling_price=float(request.form.get('selling_price')),
                    buying_price=float(request.form.get('buying_price')),
                    stock=int(request.form.get('stock')),
                    min_stock=int(request.form.get('min_stock', 0)),
                    category_id=request.form.get('category_id')
                )
                db.session.add(product)
                db.session.flush()  # This gets us the product.id

                img = request.files.get('product_image')
                if img and img.filename:
                    rel = _save_product_image(product, img)
                    if rel:
                        product.image_path = rel
                    else:
                        flash("L'image n'a pas été enregistrée (type ou taille non accepté).", 'warning')

                # Create initial stock movement
                initial_stock = int(request.form.get('stock'))
                if initial_stock > 0:
                    movement = StockMovement(
                        shop_id=shop_id,
                        product_id=product.id,  # Now we have the product.id
                        quantity=initial_stock,
                        movement_type='adjustment',
                        user_id=current_user.id,
                        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        notes='Stock initial'
                    )
                    db.session.add(movement)

                db.session.commit()
                # flash('Product added successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error adding product: {str(e)}', 'error')
                return redirect(url_for('inventory.product_list'))

        elif 'edit_product' in request.form:
            try:
                product = Product.query.get_or_404(request.form.get('product_id'))
                if product.shop_id != shop_id:
                    flash('Produit introuvable pour cette boutique.', 'error')
                    return redirect(url_for('inventory.product_list'))
                old_stock = product.stock
                new_stock = int(request.form.get('stock'))

                product.name = request.form.get('name')
                product.selling_price = float(request.form.get('selling_price'))
                product.buying_price = float(request.form.get('buying_price'))
                product.stock = new_stock
                product.min_stock = int(request.form.get('min_stock', 0))
                product.category_id = request.form.get('category_id')

                if request.form.get('remove_product_image'):
                    _delete_product_image_file(product.image_path)
                    product.image_path = None
                else:
                    img = request.files.get('product_image')
                    if img and img.filename:
                        _delete_product_image_file(product.image_path)
                        rel = _save_product_image(product, img)
                        if rel:
                            product.image_path = rel
                        else:
                            flash("L'image n'a pas été enregistrée (type ou taille non accepté).", 'warning')

                # Create stock movement if stock changed
                if new_stock != old_stock:
                    movement = StockMovement(
                        shop_id=shop_id,
                        product_id=product.id,
                        quantity=new_stock - old_stock,  # Can be negative for stock reduction
                        movement_type='adjustment',
                        user_id=current_user.id,
                        date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        notes='Stock ajustment'
                    )
                    db.session.add(movement)

                db.session.commit()
                flash('Product updated successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating product: {str(e)}', 'error')
                return redirect(url_for('inventory.product_list'))

        elif 'delete_product' in request.form:
            try:
                product_id = request.form.get('product_id')
                product = Product.query.get_or_404(product_id)
                if product.shop_id != shop_id:
                    flash('Produit introuvable pour cette boutique.', 'error')
                    return redirect(url_for('inventory.product_list'))

                old_image = product.image_path
                # Delete related stock movements first
                StockMovement.query.filter_by(product_id=product.id).delete()

                db.session.delete(product)
                db.session.commit()
                _delete_product_image_file(old_image)
                flash('Product deleted successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f'Error deleting product: {e}')
                flash("Impossible de supprimer ce produit car il est lié à des ventes existantes.", 'error')
                return redirect(url_for('inventory.product_list'))

        return redirect(url_for('inventory.product_list'))

    # GET request
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search = request.args.get('search', '').strip()
    category_id = request.args.get('category')
    stock_filter = request.args.get('stock_filter')

    query = Product.query.filter_by(shop_id=shop_id)

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if stock_filter == 'low':
        query = query.filter(Product.stock <= Product.min_stock)

    products = query.paginate(page=page, per_page=per_page, error_out=False)
    categories = Category.query.filter_by(shop_id=shop_id).all()
    shop_totals = None
    # Check if current user is admin for the current shop
    user_shop = UserShop.query.filter_by(
        user_id=current_user.id,
        shop_id=shop_id,
        is_active=True
    ).first()

    if user_shop and user_shop.role == 'admin':
        # Calculate totals for all products in the shop (not just the paginated ones)
        all_products = Product.query.filter_by(shop_id=shop_id).all()

        total_buying_value = sum(product.buying_price * product.stock for product in all_products)
        total_selling_value = sum(product.selling_price * product.stock for product in all_products)
        total_profit = total_selling_value - total_buying_value
        total_products_count = len(all_products)
        low_stock_count = sum(1 for product in all_products if product.stock < (product.min_stock or 10))

        shop_totals = {
            'total_buying_value': total_buying_value,
            'total_selling_value': total_selling_value,
            'total_profit': total_profit,
            'total_products_count': total_products_count,
            'low_stock_count': low_stock_count
        }

    # Then modify your return statement to include shop_totals:
    return render_template('inventory/inventory.html',
                           products=products,
                           categories=categories,
                           shop_totals=shop_totals)


@inventory.route('/inventory/<int:product_id>/movements')
@login_required
def stock_movements(product_id):
    product = Product.query.get_or_404(product_id)
    movements = StockMovement.query.filter_by(product_id=product_id) \
        .order_by(StockMovement.date.desc()) \
        .all()
    return render_template('inventory/movements.html',
                           product=product,
                           movements=movements)



# Add this route to your inventory blueprint
@inventory.route('/inventory/export-pdf')
@login_required
def export_products_pdf():
    shop_id = current_user.current_shop_id

    # Get the same filtered products as in the main view
    search = request.args.get('search', '').strip()
    stock_filter = request.args.get('stock_filter')

    query = Product.query.filter_by(shop_id=shop_id)

    if search:
        query = query.filter(Product.name.ilike(f"%{search}%"))
    if stock_filter == 'low':
        query = query.filter(Product.stock <= Product.min_stock)

    products = query.all()

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=18)

    # Container for the 'Flowable' objects
    elements = []

    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor=colors.HexColor('#1f2937')
    )

    # Add title
    title = Paragraph("Liste des Produits - Gestion des Stocks", title_style)
    elements.append(title)
    elements.append(Spacer(1, 20))

    # Add date
    from datetime import datetime
    date_text = f"Généré le: {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    date_para = Paragraph(date_text, styles['Normal'])
    elements.append(date_para)
    elements.append(Spacer(1, 20))

    # Create table data
    data = [['Nom du Produit', 'Prix de Vente', 'Prix d\'Achat', 'Stock', 'Stock Min.']]

    # Get currency from shop_profile (you might need to adjust this)
    currency = "FCFA"  # Default, you can get this from your shop_profile

    for product in products:
        # Format prices with thousands separator
        selling_price = f"{product.selling_price:,.0f}".replace(',', ' ') + f" {currency}"
        buying_price = f"{product.buying_price:,.0f}".replace(',', ' ') + f" {currency}"

        data.append([
            product.name,
            selling_price,
            buying_price,
            str(product.stock),
            str(product.min_stock or 0)
        ])

    # Create table
    table = Table(data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch, 0.8*inch, 0.8*inch])

    # Table style
    table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b4c6b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

        # Data rows
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),  # Right align prices and stock
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),    # Left align product names

        # Borders
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]))

    # Highlight low stock items
    for i, product in enumerate(products, 1):
        if product.stock < (product.min_stock or 10):
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, i), (-1, i), colors.HexColor('#fee2e2')),
                ('TEXTCOLOR', (3, i), (3, i), colors.red),
            ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

    # Add summary
    total_products = len(products)
    low_stock_products = sum(1 for p in products if p.stock < (p.min_stock or 10))

    summary_text = f"<b>Résumé:</b><br/>Total des produits: {total_products}<br/>Produits en stock bas: {low_stock_products}"
    summary = Paragraph(summary_text, styles['Normal'])
    elements.append(summary)

    # Build PDF
    doc.build(elements)

    # Get the value of the BytesIO buffer and write it to the response
    pdf_data = buffer.getvalue()
    buffer.close()

    response = make_response(pdf_data)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=produits_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf'

    return response


@inventory.route('/api/products')
@login_required
def get_products():
    products = Product.query.all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'price': p.selling_price,
        'stock': p.stock,
        'category': p.category.name if p.category else None
    } for p in products])