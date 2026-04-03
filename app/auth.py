# app/auth.py
import smtplib
from email.mime.text import MIMEText
import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from .models import User, UserShop, Shop
from . import db
from datetime import datetime

auth = Blueprint('auth', __name__)


# Define the admin_required decorator first
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            # flash('Cette section est réservée aux administrateurs.', 'error')
            return redirect(url_for('bills.pos'))
        return f(*args, **kwargs)

    return decorated_function


# Then define your routes
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(name=username).first()

        if user and check_password_hash(user.password_hash, password):
            if user.is_active:
                login_user(user)
                # Redirect based on user type
                if getattr(user, 'superadmin', False):
                    return redirect(url_for('admin_dashboard.manage_shops'))
                elif user.role == 'admin':
                    return redirect(url_for('dashboard.index'))
                else:
                    return redirect(url_for('bills.pos'))
            else:
                flash('Ce compte a été désactivé. Veuillez contacter l\'administrateur.', 'error')
        else:
            flash('Veuillez vérifier vos identifiants et réessayer.')

    return render_template('./auth/login.html', year=datetime.now().year)


@auth.route('/toggle-user-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status():
    user_id = request.form.get('user_id')
    current_status = request.form.get('current_status') == 'true'

    # Verify user belongs to current shop
    user_shop = UserShop.query.filter_by(
        user_id=user_id,
        shop_id=current_user.current_shop_id
    ).first()

    if not user_shop:
        flash('Utilisateur non trouvé.', 'error')
        return redirect(url_for('auth.create_user'))

    user = User.query.get_or_404(user_id)

    # Prevent self-deactivation
    if user.id == current_user.id:
        flash('Vous ne pouvez pas désactiver votre propre compte.', 'error')
        return redirect(url_for('auth.create_user'))

    # Check if this is the last active admin
    if user.role == 'admin' and user.is_active and not current_status:
        active_admins = User.query.filter_by(role='admin', is_active=True).count()
        if active_admins <= 1:
            flash('Impossible de désactiver le dernier administrateur actif.', 'error')
            return redirect(url_for('auth.create_user'))

    try:
        user.is_active = not current_status
        db.session.commit()
        status_text = 'activé' if user.is_active else 'désactivé'
        flash(f'Le compte de {user.name} a été {status_text} avec succès.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Une erreur est survenue lors de la modification du statut.', 'error')

    return redirect(url_for('auth.create_user'))


@auth.route('/create-user', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    # Get users for the current shop only
    users = User.query.join(UserShop).filter(
        UserShop.shop_id == current_user.current_shop_id
    ).order_by(User.created_at.desc()).all()

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')

        if User.query.filter_by(name=username).first():
            flash('Un utilisateur avec ce nom existe déjà.', 'error')
            return redirect(url_for('auth.create_user'))

        try:
            # Create new user
            new_user = User(
                name=username,
                password_hash=generate_password_hash(password),
                role=role,
                is_active=True,
                current_shop_id=current_user.current_shop_id
            )
            db.session.add(new_user)
            db.session.flush()

            # Create shop association
            user_shop = UserShop(
                user_id=new_user.id,
                shop_id=current_user.current_shop_id,
                role='staff',
                is_active=True
            )
            db.session.add(user_shop)

            db.session.commit()
            flash(f'Utilisateur {username} créé avec succès.', 'success')
            return redirect(url_for('auth.create_user'))
        except Exception as e:
            db.session.rollback()
            flash('Une erreur est survenue lors de la création de l\'utilisateur.', 'error')

    return render_template('auth/create_user.html', users=users)


@auth.route('/edit-user', methods=['POST'])
@login_required
@admin_required
def edit_user():
    user_id = request.form.get('user_id')
    username = request.form.get('username')
    role = request.form.get('role')

    user = User.query.get_or_404(user_id)

    # Check if username is being changed and if it's already taken
    if user.name != username and User.query.filter_by(name=username).first():
        flash('Ce nom d\'utilisateur est déjà pris.', 'error')
        return redirect(url_for('auth.create_user'))

    try:
        user.name = username
        user.role = role
        db.session.commit()
        flash('Utilisateur modifié avec succès.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erreur lors de la modification de l\'utilisateur.', 'error')

    return redirect(url_for('auth.create_user'))


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.landing_page'))

@auth.route('/')
def landing_page():
    return render_template('landing_page.html', year=datetime.now().year)

@auth.route('/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_password():
    user_id = request.form.get('user_id')
    new_password = request.form.get('new_password')

    user = User.query.get_or_404(user_id)
    user.password_hash = generate_password_hash(new_password)

    try:
        db.session.commit()
        flash('Mot de passe réinitialisé avec succès.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erreur lors de la réinitialisation du mot de passe.', 'error')

    return redirect(url_for('auth.create_user'))


@auth.route('/manage-shops')
@login_required
@admin_required
def manage_shops():
    # Get shops where the current user is an admin
    shops = Shop.query.join(UserShop).filter(
        UserShop.user_id == current_user.id,
        UserShop.role == 'admin',
        Shop.is_active == True
    ).all()

    return render_template('auth/manage_shops.html', shops=shops)


@auth.route('/select-shop/<int:shop_id>')
@login_required
def select_shop(shop_id):
    # Verify user has access to this shop with shop details
    user_shop = db.session.query(UserShop, Shop).join(
        Shop, UserShop.shop_id == Shop.id
    ).filter(
        UserShop.user_id == current_user.id,
        UserShop.shop_id == shop_id,
        UserShop.is_active == True
    ).first()

    if not user_shop:
        flash('Vous n\'avez pas accès à ce magasin.', 'error')
        return redirect(url_for('dashboard.index'))

    # Update current shop
    current_user.current_shop_id = shop_id
    db.session.commit()

    # Use user_shop[1] to access the Shop object from the tuple
    flash(f'Vous êtes maintenant connecté à {user_shop[1].name}', 'success')
    return redirect(url_for('dashboard.index'))

@auth.route('/download/android')
def download_android():
    """Serve Android APK file with proper download headers"""
    apk_filename = 'vericant.apk'  # Change this to your actual APK filename
    # Store outside static folder so it can ONLY be accessed through this route
    # This prevents direct URL access and ensures proper download headers
    apk_directory = os.path.join(current_app.root_path, 'downloads')

    # Ensure directory exists
    if not os.path.exists(apk_directory):
        os.makedirs(apk_directory, exist_ok=True)

    apk_path = os.path.join(apk_directory, apk_filename)

    if not os.path.exists(apk_path):
        flash('Application Android non disponible pour le moment.', 'error')
        return redirect(url_for('auth.landing_page'))

    return send_from_directory(
        apk_directory,
        apk_filename,
        as_attachment=True,
        mimetype='application/vnd.android.package-archive',
        download_name=apk_filename
    )

@auth.route('/send-email', methods=['POST'])
def send_email():
    name = request.form.get('name')
    email = request.form.get('email')
    message = request.form.get('message')

    if not name or not email or not message:
        return jsonify({"error": "Tous les champs sont requis"}), 400

    sender_email = "zilbalde123@gmail.com"  # Replace with your email
    sender_password = "lzhj owxw mtsl lfpg"  # Use an app password if using Gmail
    recipient_email = "vericant2023@gmail.com"

    subject = f"Nouveau message de {name}"
    body = f"Nom: {name}\nEmail: {email}\n\nMessage:\n{message}"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient_email

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())

        return jsonify({"success": "Message envoyé avec succès"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500