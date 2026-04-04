# app/__init__.py
from flask import Flask, flash, redirect, url_for, request
from flask_login import logout_user, current_user
from app.cli import init_cli
from app.extensions import db, migrate, login_manager
from app.utils import format_date, number_to_words
import os
from pathlib import Path
from dotenv import load_dotenv
from flask import current_app, jsonify #import jsonify
from app.ssh_tunnel_db import maybe_start_ssh_tunnel as _maybe_start_ssh_tunnel


def _resolve_database_url(default_sqlite: str) -> str:
    """
    Prefer PA_MYSQL_BUILD_URL=1 + PA_MYSQL_PASSWORD etc. so the MySQL password is not
    embedded in a URI string (avoids dotenv / special-character / parsing issues).
    """
    flag = os.environ.get('PA_MYSQL_BUILD_URL', '').strip().lower()
    if flag not in ('1', 'true', 'yes'):
        return (
            os.environ.get('DATABASE_URL')
            or os.environ.get('SQLALCHEMY_DATABASE_URI')
            or default_sqlite
        )

    password = os.environ.get('PA_MYSQL_PASSWORD')
    if not password:
        raise RuntimeError(
            'PA_MYSQL_BUILD_URL=1 requires PA_MYSQL_PASSWORD (plain text, no URL encoding).'
        )

    from sqlalchemy.engine.url import URL

    user = os.environ.get('PA_MYSQL_USER', 'vericant').strip()
    host = os.environ.get(
        'PA_MYSQL_HOST', 'vericant.mysql.pythonanywhere-services.com'
    ).strip()
    port = int(os.environ.get('PA_MYSQL_PORT', '3306'))
    database = os.environ.get('PA_MYSQL_DATABASE', 'vericant$shop').strip()
    if '%24' in database:
        from urllib.parse import unquote

        database = unquote(database)

    return URL.create(
        'mysql+pymysql',
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
        query={'charset': 'utf8mb4'},
    ).render_as_string(hide_password=False)


def create_app():
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'your-secret-key'
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(os.path.dirname(basedir), 'instance', 'shop.db')
    default_sqlite = f'sqlite:///{db_path}'
    database_url = _resolve_database_url(default_sqlite)
    # Heroku / some hosts still use postgres://
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    database_url, ssh_tunnel = _maybe_start_ssh_tunnel(database_url)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    if ssh_tunnel is not None:
        app.config['PA_SSH_TUNNEL_ACTIVE'] = True
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # MySQL (e.g. PythonAnywhere) often closes idle connections; pooled sockets
    # then fail with OperationalError 2013 "Lost connection ... during query".
    if database_url.startswith('mysql'):
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 280,
        }

    # Behind HTTPS reverse proxy (Google Cloud Run, etc.)
    if os.environ.get('K_SERVICE'):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
        )

    # Register Jinja filters
    app.jinja_env.filters['format_date'] = format_date
    app.jinja_env.filters['number_to_words'] = number_to_words

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @app.before_request
    def redirect_to_www():
        if request.host == 'vericant.online':
            return redirect(f"https://www.vericant.online{request.full_path}", code=301)

    from .models import User, Shop, UserShop
    @app.context_processor
    def inject_shop_data():
        """Make current shop data available to all templates"""
        if current_user.is_authenticated and current_user.current_shop_id:
            current_shop = Shop.query.get(current_user.current_shop_id)
            user_shop = UserShop.query.filter_by(
                user_id=current_user.id,
                shop_id=current_user.current_shop_id
            ).first()

            # Get all shops the user has access to
            available_shops = Shop.query.join(UserShop).filter(
                UserShop.user_id == current_user.id,
                UserShop.is_active == True,
                Shop.is_active == True
            ).all()

            shop_phones_dicts = []
            if current_shop and current_shop.phones: # Check if current_shop and phones exist.
                for phone in current_shop.phones:
                    shop_phones_dicts.append({
                        'phone': phone.phone, # Access the 'phone' attribute from ShopPhone.
                    })
            else:
              shop_phones_dicts = []

            return dict(
                current_shop=current_shop,
                shop_profile=current_shop,
                shop_phones=shop_phones_dicts,
                user_shop_role=user_shop.role if user_shop else None,
                available_shops=available_shops
            )
        return dict(
            current_shop=None,
            shop_profile=None,
            shop_phones=[],
            user_shop_role=None,
            available_shops=[]
        )

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.template_filter('fr_thousands')
    def fr_thousands(value):
        try:
            # Convert to int first to drop decimals, then format with space as thousands separator
            formatted = f"{int(value):,}".replace(",", " ")
            return formatted
        except (ValueError, TypeError):
            return value


    @app.before_request
    def check_user_status():
        if current_user.is_authenticated:
            # Allow superadmin to bypass shop checks
            if getattr(current_user, 'superadmin', False):
                return
            # Skip check for auth routes and static files
            if request.endpoint and \
                    not request.endpoint.startswith('static') and \
                    not request.endpoint.startswith('auth.'):

                # Verify user status and shop access in one query
                user_shop = db.session.query(User, UserShop).join(
                    UserShop, User.id == UserShop.user_id
                ).filter(
                    User.id == current_user.id,
                    User.is_active == True,
                    UserShop.shop_id == User.current_shop_id,
                    UserShop.is_active == True
                ).first()

                if not user_shop:
                    logout_user()
                    flash(
                        'Votre compte a été désactivé ou vous n\'avez plus accès au magasin. Veuillez contacter l\'administrateur.',
                        'error')
                    return redirect(url_for('auth.login'))

    # Register CLI commands
    init_cli(app, db, User)

    # Register blueprints
    from .auth import auth
    app.register_blueprint(auth)

    from .routes.dashboard import dashboard
    app.register_blueprint(dashboard)

    from .routes.bills import bills
    app.register_blueprint(bills)

    from .routes.inventory import inventory
    app.register_blueprint(inventory)

    from .routes.expenses import expenses
    app.register_blueprint(expenses)

    from .routes.clients import clients
    app.register_blueprint(clients)

    from .routes.boutique import boutique
    app.register_blueprint(boutique)

    from .routes.loans import loans
    app.register_blueprint(loans)

    from .routes.notes import notes
    app.register_blueprint(notes)

    from .routes.employee_salaries import employee_salaries
    app.register_blueprint(employee_salaries)

    from .routes.employee_loans import employee_loans
    app.register_blueprint(employee_loans)

    # Initialize profile routes with new shop management
    from .routes.profile import profile as profile_blueprint
    app.register_blueprint(profile_blueprint)

    from .routes.bill_editor import bill_editor
    app.register_blueprint(bill_editor, url_prefix='/bill-edit')

    from .routes.admin_dashboard import admin_dashboard
    app.register_blueprint(admin_dashboard)

    return app
