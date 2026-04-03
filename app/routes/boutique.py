from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.utils import admin_only_action
from app.models import BoutiqueTransaction, Category
from datetime import datetime, timedelta
from sqlalchemy import desc, func

boutique = Blueprint('boutique', __name__)

def get_available_shops():
    """Get list of available shops for current user"""
    # Get distinct shop names from existing transactions for current user's shop
    shops = db.session.query(BoutiqueTransaction.name).filter_by(
        shop_id=current_user.current_shop_id
    ).distinct().order_by(BoutiqueTransaction.name).all()

    # Return list of shop names, filtering out None/empty values
    return [shop[0] for shop in shops if shop[0] and shop[0].strip()]

@boutique.route('/boutique', methods=['GET', 'POST'])
@login_required
@admin_only_action('delete_transaction')
def transaction_list():
    if request.method == 'POST':
        if 'add_transaction' in request.form:
            try:
                # Handle shop name - prioritize custom input over dropdown
                shop_name = request.form.get('custom_shop_name', '').strip()
                if not shop_name:
                    shop_name = request.form.get('shop_name', '').strip()

                # Validate that we have a shop name
                if not shop_name:
                    flash('Veuillez sélectionner ou saisir une source de versement', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                # Validate and convert paid amount
                paid_amount_str = request.form.get('paid_amount', '').strip()
                if not paid_amount_str:
                    flash('Veuillez saisir un montant', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                try:
                    # Handle formatted numbers (remove spaces and convert comma to dot)
                    paid_amount_str = paid_amount_str.replace(' ', '').replace(',', '.')
                    paid_amount = float(paid_amount_str)

                    if paid_amount <= 0:
                        flash('Le montant doit être supérieur à zéro', 'error')
                        return redirect(url_for('boutique.transaction_list'))

                except (ValueError, TypeError):
                    flash('Montant invalide. Veuillez saisir un nombre valide', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                # Get category_id if provided
                category_id = request.form.get('category_id')
                if category_id and category_id.strip():
                    try:
                        category_id = int(category_id)
                    except (ValueError, TypeError):
                        category_id = None
                else:
                    category_id = None

                # Create the transaction
                transaction = BoutiqueTransaction(
                    shop_id=current_user.current_shop_id,
                    name=shop_name,
                    amount=paid_amount,
                    paid_amount=paid_amount,
                    date=datetime.now().strftime('%Y-%m-%d'),
                    user_id=current_user.current_shop_id,
                    category_id=category_id
                )

                db.session.add(transaction)
                db.session.commit()
                flash(f'Transaction ajoutée avec succès pour {shop_name}!', 'success')

            except Exception as e:
                db.session.rollback()
                flash(f'Erreur lors de l\'ajout de la transaction: {str(e)}', 'error')

        elif 'edit_transaction' in request.form:
            try:
                # Get and validate boutique_id
                boutique_id = request.form.get('boutique_id')
                if not boutique_id:
                    flash('ID de transaction manquant', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                try:
                    boutique_id = int(boutique_id)
                except (ValueError, TypeError):
                    flash('ID de transaction invalide', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                # Get the transaction
                transaction = BoutiqueTransaction.query.get_or_404(boutique_id)

                # Verify shop ownership
                if transaction.shop_id != current_user.current_shop_id:
                    flash('Accès non autorisé à cette transaction', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                # Get and validate shop name
                shop_name = request.form.get('shop_name', '').strip()
                if not shop_name:
                    flash('Nom de source requis', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                # Validate and convert paid amount
                paid_amount_str = request.form.get('paid_amount', '').strip()
                if not paid_amount_str:
                    flash('Montant requis', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                try:
                    # Handle formatted numbers
                    paid_amount_str = paid_amount_str.replace(' ', '').replace(',', '.')
                    paid_amount = float(paid_amount_str)

                    if paid_amount <= 0:
                        flash('Le montant doit être supérieur à zéro', 'error')
                        return redirect(url_for('boutique.transaction_list'))

                except (ValueError, TypeError):
                    flash('Montant invalide', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                # Get category_id if provided
                category_id = request.form.get('category_id')
                if category_id and category_id.strip():
                    try:
                        category_id = int(category_id)
                    except (ValueError, TypeError):
                        category_id = None
                else:
                    category_id = None

                # Update the transaction
                old_name = transaction.name
                transaction.name = shop_name
                transaction.amount = paid_amount
                transaction.paid_amount = paid_amount
                transaction.category_id = category_id

                db.session.commit()
                flash(f'Transaction mise à jour avec succès (de {old_name} vers {shop_name})!', 'success')

            except Exception as e:
                db.session.rollback()
                flash(f'Erreur lors de la mise à jour: {str(e)}', 'error')

        elif 'delete_transaction' in request.form and current_user.role == 'admin':
            try:
                # Get and validate boutique_id
                boutique_id = request.form.get('boutique_id')
                if not boutique_id:
                    flash('ID de transaction manquant', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                try:
                    boutique_id = int(boutique_id)
                except (ValueError, TypeError):
                    flash('ID de transaction invalide', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                # Get the transaction
                transaction = BoutiqueTransaction.query.get_or_404(boutique_id)

                # Verify shop ownership
                if transaction.shop_id != current_user.current_shop_id:
                    flash('Accès non autorisé à cette transaction', 'error')
                    return redirect(url_for('boutique.transaction_list'))

                # Store name for confirmation message
                transaction_name = transaction.name

                # Delete the transaction
                db.session.delete(transaction)
                db.session.commit()
                flash(f'Transaction de {transaction_name} supprimée avec succès!', 'success')

            except Exception as e:
                db.session.rollback()
                flash(f'Erreur lors de la suppression: {str(e)}', 'error')

        else:
            flash('Action non reconnue', 'error')

        return redirect(url_for('boutique.transaction_list'))

    # GET request - Display transactions
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 10

        # Get filter parameters
        selected_shop = request.args.get('shop_filter', '').strip()
        start_date = request.args.get('start', '').strip()
        end_date = request.args.get('end', '').strip()

        # Base query with shop_id filter
        query = BoutiqueTransaction.query.filter_by(shop_id=current_user.current_shop_id)

        # Apply shop name filter if selected
        if selected_shop:
            query = query.filter(BoutiqueTransaction.name == selected_shop)

        # Apply date filter if provided
        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(BoutiqueTransaction.date.between(start, end))
            except ValueError:
                flash('Format de date invalide', 'error')
                start_date = end_date = None

        # Get paginated results ordered by date (most recent first)
        transactions = query.order_by(desc(BoutiqueTransaction.date), desc(BoutiqueTransaction.id)).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # Calculate total for filtered results
        total_amount = query.with_entities(func.sum(BoutiqueTransaction.amount)).scalar() or 0

        # Get available data for dropdowns
        available_shops = get_available_shops()

        # Get categories for current shop (assuming you have categories)
        categories = Category.query.filter_by(
            type='income',
            shop_id=current_user.current_shop_id
        ).order_by(Category.name).all() if Category else []

        # Get shop totals for summary (for current filters if any)
        shop_totals_query = db.session.query(
            BoutiqueTransaction.name,
            func.sum(BoutiqueTransaction.amount).label('total')
        ).filter_by(shop_id=current_user.current_shop_id)

        # Apply same filters to shop totals
        if selected_shop:
            shop_totals_query = shop_totals_query.filter(BoutiqueTransaction.name == selected_shop)

        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                shop_totals_query = shop_totals_query.filter(BoutiqueTransaction.date.between(start, end))
            except ValueError:
                pass  # Already handled above

        shop_totals = shop_totals_query.group_by(BoutiqueTransaction.name).order_by(
            func.sum(BoutiqueTransaction.amount).desc()
        ).all()

        # Get current user's shop profile for currency display
        # Assuming you have a shop_profile attribute or method
        shop_profile = getattr(current_user, 'shop_profile', None) or type('obj', (object,), {'currency': 'FCFA'})()

        return render_template('boutique/boutique.html',
                             boutique_items=transactions,
                             categories=categories,
                             total_amount=total_amount,
                             available_shops=available_shops,
                             selected_shop=selected_shop,
                             shop_totals=shop_totals,
                             start_date=start_date,
                             end_date=end_date,
                             shop_profile=shop_profile)

    except Exception as e:
        flash(f'Erreur lors du chargement des données: {str(e)}', 'error')
        return render_template('boutique/boutique.html',
                             boutique_items=None,
                             categories=[],
                             total_amount=0,
                             available_shops=[],
                             selected_shop='',
                             shop_totals=[],
                             start_date='',
                             end_date='',
                             shop_profile=type('obj', (object,), {'currency': 'FCFA'})())

# Additional utility functions for the boutique module

@boutique.route('/boutique/export')
@login_required
def export_transactions():
    """Export transactions to CSV"""
    try:
        import csv
        from io import StringIO
        from flask import make_response

        # Get filter parameters
        selected_shop = request.args.get('shop_filter', '').strip()
        start_date = request.args.get('start', '').strip()
        end_date = request.args.get('end', '').strip()

        # Build query with same filters as main view
        query = BoutiqueTransaction.query.filter_by(shop_id=current_user.current_shop_id)

        if selected_shop:
            query = query.filter(BoutiqueTransaction.name == selected_shop)

        if start_date and end_date:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(BoutiqueTransaction.date.between(start, end))

        transactions = query.order_by(desc(BoutiqueTransaction.date)).all()

        # Create CSV
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Source', 'Montant', 'Date', 'ID'])

        # Write data
        for transaction in transactions:
            writer.writerow([
                transaction.name,
                transaction.amount,
                transaction.date,
                transaction.id
            ])

        # Create response
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=transactions_boutique.csv"
        response.headers["Content-type"] = "text/csv"

        return response

    except Exception as e:
        flash(f'Erreur lors de l\'export: {str(e)}', 'error')
        return redirect(url_for('boutique.transaction_list'))

@boutique.route('/boutique/stats')
@login_required
def transaction_stats():
    """Get transaction statistics for current shop"""
    try:
        # Get date range (default to current month)
        end_date = datetime.now()
        start_date = end_date.replace(day=1)  # First day of current month

        # Override with request params if provided
        if request.args.get('start'):
            start_date = datetime.strptime(request.args.get('start'), '%Y-%m-%d')
        if request.args.get('end'):
            end_date = datetime.strptime(request.args.get('end'), '%Y-%m-%d')

        # Get transactions in date range
        transactions = BoutiqueTransaction.query.filter_by(
            shop_id=current_user.current_shop_id
        ).filter(
            BoutiqueTransaction.date.between(start_date, end_date + timedelta(days=1))
        ).all()

        # Calculate stats
        stats = {
            'total_amount': sum(t.amount for t in transactions),
            'total_transactions': len(transactions),
            'average_transaction': sum(t.amount for t in transactions) / len(transactions) if transactions else 0,
            'unique_sources': len(set(t.name for t in transactions)),
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            }
        }

        # Top sources
        from collections import Counter
        source_amounts = Counter()
        for t in transactions:
            source_amounts[t.name] += t.amount

        stats['top_sources'] = source_amounts.most_common(5)

        return render_template('boutique/stats.html', stats=stats)

    except Exception as e:
        flash(f'Erreur lors du calcul des statistiques: {str(e)}', 'error')
        return redirect(url_for('boutique.transaction_list'))