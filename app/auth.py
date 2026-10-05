# app/auth.py
import smtplib
from email.mime.text import MIMEText
import hashlib
import hmac
import os
import secrets
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_from_directory, make_response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from .models import AccountDeletionRequest, User, UserShop, Shop
from .landing_copy import get_landing_copy
from . import db
from datetime import datetime

auth = Blueprint('auth', __name__)


def _public_language():
    requested = (request.values.get('lang') or '').strip().lower()
    if requested in ('fr', 'en'):
        return requested
    saved = getattr(current_user, 'preferred_language', None)
    if current_user.is_authenticated and saved in ('fr', 'en'):
        return saved
    cookie = (request.cookies.get('vericant_language') or '').strip().lower()
    return cookie if cookie in ('fr', 'en') else 'fr'


PUBLIC_LEGAL_COPY = {
    'fr': {
        'privacy_title': 'Politique de confidentialité',
        'privacy_intro': 'Verikant aide les commerces à gérer leurs ventes, leur stock, leurs dépenses et leurs crédits clients. Cette page explique quelles informations sont utilisées et comment vous pouvez exercer vos droits.',
        'collected_title': 'Informations que nous traitons',
        'collected_body': 'Nous traitons les informations de compte et de boutique que vous fournissez, ainsi que les données opérationnelles saisies dans le service, comme les produits, ventes, clients, dépenses et crédits. Des données techniques limitées peuvent être utilisées pour sécuriser le service et diagnostiquer les erreurs.',
        'use_title': 'Pourquoi nous les utilisons',
        'use_body': 'Ces informations servent à fournir les fonctions de Verikant, synchroniser vos appareils, protéger les comptes, résoudre les incidents et améliorer la fiabilité du service. Nous ne vendons pas vos données personnelles.',
        'sharing_title': 'Partage et conservation',
        'sharing_body': 'Les données ne sont communiquées qu’aux prestataires nécessaires au fonctionnement du service ou lorsque la loi l’exige. Elles sont conservées pendant la durée nécessaire au service, à la sécurité et aux obligations légales applicables.',
        'rights_title': 'Vos choix et vos droits',
        'rights_body': 'Vous pouvez demander l’accès, la correction ou la suppression de vos informations. Une vérification d’identité peut être nécessaire afin de protéger votre compte.',
        'delete_link': 'Demander la suppression de mon compte',
        'contact_title': 'Nous contacter',
        'contact_body': 'Pour toute question relative à la confidentialité, écrivez à vericant2023@gmail.com.',
        'updated': 'Dernière mise à jour : 4 octobre 2026',
        'delete_title': 'Supprimer mon compte Verikant',
        'delete_intro': 'Envoyez cette demande pour supprimer votre compte et les données de boutique qui lui sont associées. Nous vous contacterons afin de vérifier votre identité avant toute suppression définitive.',
        'delete_scope_title': 'Ce que la suppression comprend',
        'delete_scope_body': 'Après vérification, nous supprimerons ou anonymiserons le compte et les données associées qui ne doivent pas être conservées pour des raisons légales, de sécurité ou de prévention de la fraude. Les copies de sauvegarde expirent selon leur cycle normal.',
        'username': 'Nom d’utilisateur Verikant',
        'contact': 'Téléphone ou adresse e-mail',
        'reason': 'Informations complémentaires (facultatif)',
        'submit': 'Envoyer la demande',
        'required': 'Veuillez renseigner votre nom d’utilisateur et un moyen de vous contacter.',
        'confirmation_title': 'Demande enregistrée',
        'confirmation_body': 'Votre demande a bien été enregistrée. Nous vous contacterons pour vérifier votre identité avant de procéder à la suppression.',
        'reference': 'Référence',
        'home': 'Retour à l’accueil',
        'privacy': 'Confidentialité',
    },
    'en': {
        'privacy_title': 'Privacy Policy',
        'privacy_intro': 'Verikant helps businesses manage sales, inventory, expenses, and customer credit. This page explains what information is used and how you can exercise your rights.',
        'collected_title': 'Information we process',
        'collected_body': 'We process the account and shop information you provide, together with operational data entered into the service, such as products, sales, customers, expenses, and credit. Limited technical data may be used to secure the service and diagnose errors.',
        'use_title': 'Why we use it',
        'use_body': 'We use this information to provide Verikant features, synchronize your devices, protect accounts, resolve incidents, and improve service reliability. We do not sell your personal data.',
        'sharing_title': 'Sharing and retention',
        'sharing_body': 'Data is shared only with providers needed to operate the service or when required by law. It is retained only as long as needed for the service, security, and applicable legal obligations.',
        'rights_title': 'Your choices and rights',
        'rights_body': 'You can request access to, correction of, or deletion of your information. We may need to verify your identity to protect your account.',
        'delete_link': 'Request account deletion',
        'contact_title': 'Contact us',
        'contact_body': 'For privacy questions, email vericant2023@gmail.com.',
        'updated': 'Last updated: October 4, 2026',
        'delete_title': 'Delete my Verikant account',
        'delete_intro': 'Submit this request to delete your account and its associated shop data. We will contact you to verify your identity before permanently deleting anything.',
        'delete_scope_title': 'What deletion includes',
        'delete_scope_body': 'After verification, we will delete or anonymize the account and associated data that we are not required to retain for legal, security, or fraud-prevention reasons. Backup copies expire through their normal lifecycle.',
        'username': 'Verikant username',
        'contact': 'Phone number or email address',
        'reason': 'Additional information (optional)',
        'submit': 'Submit request',
        'required': 'Enter your username and a way for us to contact you.',
        'confirmation_title': 'Request received',
        'confirmation_body': 'Your request has been recorded. We will contact you to verify your identity before proceeding with deletion.',
        'reference': 'Reference',
        'home': 'Back to home',
        'privacy': 'Privacy',
    },
}


def _username_fingerprint(username):
    """Return a stable diagnostic identifier without logging the username."""
    secret = str(current_app.config.get('SECRET_KEY') or '').encode('utf-8')
    normalized = (username or '').strip().casefold().encode('utf-8')
    return hmac.new(secret, normalized, hashlib.sha256).hexdigest()[:16]


def _auth_log(event, **fields):
    details = ' '.join(f'{key}={value}' for key, value in sorted(fields.items()))
    current_app.logger.warning('auth_event=%s %s', event, details)


def _username_candidates(username):
    """Find all legacy accounts whose names differ only by letter case."""
    return User.query.filter(
        db.func.lower(User.name) == username.lower()
    ).order_by(User.id.asc()).all()


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
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        request_id = secrets.token_hex(4)
        fingerprint = _username_fingerprint(username)
        candidates = _username_candidates(username) if username else []
        password_matches = []
        for candidate in candidates:
            try:
                if candidate.password_hash and check_password_hash(
                    candidate.password_hash, password
                ):
                    password_matches.append(candidate)
            except (TypeError, ValueError):
                _auth_log(
                    'invalid_password_hash',
                    request_id=request_id,
                    user_id=candidate.id,
                )

        user = None
        if len(password_matches) == 1:
            user = password_matches[0]
        elif len(password_matches) > 1:
            exact_matches = [u for u in password_matches if u.name == username]
            if len(exact_matches) == 1:
                user = exact_matches[0]
            else:
                _auth_log(
                    'ambiguous_credentials',
                    request_id=request_id,
                    username_fp=fingerprint,
                    candidate_count=len(password_matches),
                )

        if user:
            if user.is_active:
                login_user(user)
                _auth_log(
                    'login_success',
                    request_id=request_id,
                    user_id=user.id,
                    shop_id=user.current_shop_id,
                    role=user.role,
                )
                if getattr(user, 'superadmin', False):
                    return redirect(url_for('admin_dashboard.manage_shops'))
                elif user.role == 'admin':
                    return redirect(url_for('dashboard.index'))
                else:
                    return redirect(url_for('bills.pos'))
            _auth_log(
                'inactive_user',
                request_id=request_id,
                user_id=user.id,
                shop_id=user.current_shop_id,
            )
            flash('Ce compte a été désactivé. Veuillez contacter l\'administrateur.', 'error')
        else:
            _auth_log(
                'user_not_found' if not candidates else 'password_mismatch',
                request_id=request_id,
                username_fp=fingerprint,
                candidate_count=len(candidates),
            )
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
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password')
        role = request.form.get('role')

        if _username_candidates(username):
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
    username = (request.form.get('username') or '').strip()
    role = request.form.get('role')

    user = User.query.get_or_404(user_id)

    # Check if username is being changed and if it's already taken
    conflicts = [candidate for candidate in _username_candidates(username) if candidate.id != user.id]
    if user.name != username and conflicts:
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
    return _render_landing_page('fr')


@auth.route('/en/')
def landing_page_en():
    return _render_landing_page('en')


@auth.route('/privacy')
def privacy():
    language = _public_language()
    return render_template(
        'privacy.html',
        language=language,
        copy=PUBLIC_LEGAL_COPY[language],
    )


@auth.route('/account/delete', methods=['GET', 'POST'])
def request_account_deletion():
    language = _public_language()
    copy = PUBLIC_LEGAL_COPY[language]
    username = ''
    contact = ''
    reason = ''
    error = None
    deletion_request = None

    if request.method == 'POST':
        # A filled website field is a bot signal; render the same confirmation
        # without adding junk to the deletion queue.
        if (request.form.get('website') or '').strip():
            return render_template(
                'account_delete.html',
                language=language,
                copy=copy,
                deletion_request=True,
                reference='DEL-RECEIVED',
                username='',
                contact='',
                reason='',
                error=None,
            )

        username = (request.form.get('username') or '').strip()[:255]
        contact = (request.form.get('contact') or '').strip()[:255]
        reason = (request.form.get('reason') or '').strip()[:2000]
        if not username or not contact:
            error = copy['required']
        else:
            deletion_request = AccountDeletionRequest.query.filter(
                db.func.lower(AccountDeletionRequest.username) == username.casefold(),
                AccountDeletionRequest.contact == contact,
                AccountDeletionRequest.status == 'pending',
            ).first()
            if deletion_request is None:
                deletion_request = AccountDeletionRequest(
                    user_id=current_user.id if current_user.is_authenticated else None,
                    shop_id=(
                        current_user.current_shop_id
                        if current_user.is_authenticated
                        else None
                    ),
                    username=username,
                    contact=contact,
                    reason=reason or None,
                    language_code=language,
                    status='pending',
                )
                db.session.add(deletion_request)
                db.session.commit()
                current_app.logger.warning(
                    'account_deletion_request_created id=%s authenticated=%s',
                    deletion_request.id,
                    current_user.is_authenticated,
                )

    return render_template(
        'account_delete.html',
        language=language,
        copy=copy,
        deletion_request=deletion_request,
        reference=(
            f'DEL-{deletion_request.id:06d}' if deletion_request else None
        ),
        username=username,
        contact=contact,
        reason=reason,
        error=error,
    ), (400 if error else 200)


def _render_landing_page(language):
    response = make_response(render_template(
        'landing_page.html',
        year=datetime.now().year,
        landing_lang=language,
        copy=get_landing_copy(language),
    ))
    response.set_cookie('vericant_language', language, max_age=31536000, samesite='Lax', secure=request.is_secure)
    return response


@auth.route('/language/<language>')
def set_language(language):
    if language not in ('fr', 'en'):
        language = 'fr'
    if current_user.is_authenticated:
        current_user.preferred_language = language
        db.session.commit()
    target = request.args.get('next') or url_for('dashboard.index')
    if not target.startswith('/') or target.startswith('//'):
        target = url_for('dashboard.index')
    response = make_response(redirect(target))
    response.set_cookie('vericant_language', language, max_age=31536000, samesite='Lax', secure=request.is_secure)
    return response

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

    sender_email = (os.environ.get('SMTP_SENDER_EMAIL') or '').strip()
    sender_password = os.environ.get('SMTP_APP_PASSWORD') or ''
    recipient_email = (os.environ.get('CONTACT_RECIPIENT_EMAIL') or '').strip()

    if not sender_email or not sender_password or not recipient_email:
        current_app.logger.error('contact_email_event=configuration_missing')
        return jsonify({"error": "Service de messagerie temporairement indisponible"}), 503

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
    except Exception:
        current_app.logger.exception('contact_email_event=send_failed')
        return jsonify({"error": "Impossible d'envoyer le message pour le moment"}), 500
