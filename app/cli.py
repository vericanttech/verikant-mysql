# app/cli.py
import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

import json
import os

from .models import Shop, User, UserShop

from app.models import (
    Category, Product, Client, SalesBill, SalesDetail,
    StockMovement, PaymentTransaction, Expense, Supplier,
    SupplierBill, Note, Loan, BoutiqueTransaction, Check
)
from app.extensions import db


def backup_shop_data(shop_id):
    backup_folder = os.path.join('app', 'static', 'backups')
    """Backup shop data to a JSON file."""
    os.makedirs(backup_folder, exist_ok=True)
    backup_data = {}

    related_models = {
        "sales_bills": SalesBill,
        "sales_details": SalesDetail,
        "payment_transactions": PaymentTransaction,
        "stock_movements": StockMovement,
        "products": Product,
        "categories": Category,
        "clients": Client,
        "expenses": Expense,
        "suppliers": Supplier,
        "supplier_bills": SupplierBill,
        "notes": Note,
        "loans": Loan,
        "boutique_transactions": BoutiqueTransaction,
        "checks": Check,
    }

    for name, model in related_models.items():
        if model == SalesDetail:
            # SalesDetail linked through SalesBill
            sales_bills = SalesBill.query.filter_by(shop_id=shop_id).all()
            bill_ids = [bill.id for bill in sales_bills]
            items = SalesDetail.query.filter(SalesDetail.bill_id.in_(bill_ids)).all()
        else:
            items = model.query.filter_by(shop_id=shop_id).all()

        backup_data[name] = [item.__dict__ for item in items]

    backup_file = os.path.join(backup_folder, f"shop_{shop_id}_backup.json")
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, default=str, indent=2)

    return backup_file


def delete_shop_data(shop_id):
    """Delete all data related to a shop."""
    try:
        sales_bills = SalesBill.query.filter_by(shop_id=shop_id).all()
        for bill in sales_bills:
            SalesDetail.query.filter_by(bill_id=bill.id).delete()

        models_to_delete = [
            SalesBill, PaymentTransaction, StockMovement,
            Product, Category, Client,
            Expense, Supplier, SupplierBill,
            Note, Loan, BoutiqueTransaction, Check
        ]

        for model in models_to_delete:
            db.session.query(model).filter_by(shop_id=shop_id).delete()

        db.session.commit()
        return True

    except Exception as e:
        db.session.rollback()
        print(f"Error deleting shop data: {e}")
        return False



def init_cli(app, db, User):
    # Helper functions
    @app.cli.command('init-db')
    def init_db():
        """Initialize the database by creating all tables."""
        try:
            click.echo('Creating database tables...')
            db.create_all()
            click.echo('Database tables created successfully!')
            click.echo('\nUse these commands to setup your shop:')
            click.echo('1. flask shop create "Your Shop Name"')
            click.echo('2. flask user create admin your_password')
            click.echo('3. flask assign user-to-shop 1 1 --role admin')
        except Exception as e:
            click.echo(f'Error initializing database: {str(e)}')

    def create_shop(name, business_type=None):
        """Create a new shop."""
        try:
            shop = Shop(
                name=name,
                business_type=business_type,
                is_active=True
            )
            db.session.add(shop)
            db.session.flush()
            return shop
        except Exception as e:
            db.session.rollback()
            click.echo(f'Error creating shop: {str(e)}')
            return None

    def create_user(username, password, role='admin'):
        """Create a new user."""
        try:
            user = User(
                name=username,
                password_hash=generate_password_hash(password),
                role=role,
                is_active=True
            )
            db.session.add(user)
            db.session.flush()
            return user
        except Exception as e:
            db.session.rollback()
            click.echo(f'Error creating user: {str(e)}')
            return None

    def assign_user_to_shop(user_id, shop_id, role='admin'):
        """Assign a user to a shop with specified role."""
        try:
            user_shop = UserShop(
                user_id=user_id,
                shop_id=shop_id,
                role=role,
                is_active=True
            )
            db.session.add(user_shop)
            db.session.flush()
            return user_shop
        except Exception as e:
            db.session.rollback()
            click.echo(f'Error assigning user to shop: {str(e)}')
            return None

    # CLI Commands
    @app.cli.group()
    def shop():
        """Shop management commands."""
        pass

    @app.cli.group()
    def user():
        """User management commands."""
        pass

    @user.command('create')
    @click.argument('username')
    @click.argument('password')
    @click.option('--role', default='admin', help='User role (admin/staff)')
    def create_user_command(username, password, role):
        """Create a new user."""
        user = create_user(username, password, role)
        if user:
            db.session.commit()
            click.echo(f'User {username} created successfully with ID: {user.id}')
        else:
            click.echo('Failed to create user')

    @app.cli.group()
    def assign():
        """Assignment management commands."""
        pass

    @assign.command('user-to-shop')
    @click.argument('user_id')
    @click.argument('shop_id')
    @click.option('--role', default='admin', help='Role in shop (admin/staff)')
    def assign_user_shop_command(user_id, shop_id, role):
        """Assign a user to a shop with a role."""
        user_shop = assign_user_to_shop(int(user_id), int(shop_id), role)
        if user_shop:
            # Set as current shop if user doesn't have one
            user = User.query.get(int(user_id))
            if not user.current_shop_id:
                user.current_shop_id = int(shop_id)
            db.session.commit()
            click.echo(f'User {user_id} assigned to shop {shop_id} as {role}')
        else:
            click.echo('Failed to assign user to shop')

    @assign.command('update-user-role-in-shop')
    @click.argument('user_id', type=int)
    @click.argument('shop_id', type=int)
    @click.argument('role', type=str)
    def update_user_role_in_shop(user_id, shop_id, role):
        """Update the role of a user in a specific shop."""
        user_shop = UserShop.query.filter_by(user_id=user_id, shop_id=shop_id).first()
        if not user_shop:
            click.echo(f'No UserShop record found for user_id={user_id} and shop_id={shop_id}.')
            return
        user_shop.role = role
        db.session.commit()
        click.echo(f'Updated user_id={user_id} in shop_id={shop_id} to role={role}.')

    @app.cli.command('init-shop')
    @click.argument('shop_name')
    @click.argument('admin_username')
    @click.argument('admin_password')
    @click.option('--type', 'business_type', help='Type of business')
    def init_shop(shop_name, admin_username, admin_password, business_type=None):
        """Initialize a new shop with an admin user (convenience command)."""
        try:
            # Create shop
            shop = create_shop(shop_name, business_type)
            if not shop:
                return

            # Create admin user
            admin = create_user(admin_username, admin_password, 'admin')
            if not admin:
                return

            # Assign admin to shop
            user_shop = assign_user_to_shop(admin.id, shop.id, 'admin')
            if not user_shop:
                return

            # Set as current shop
            admin.current_shop_id = shop.id

            db.session.commit()
            click.echo(f'''
Shop initialization successful:
- Shop: {shop_name} (ID: {shop.id})
- Admin: {admin_username} (ID: {admin.id})
''')
        except Exception as e:
            db.session.rollback()
            click.echo(f'Error during initialization: {str(e)}')

    # Additional utility commands
    @app.cli.group()
    def list():
        """List entities."""
        pass

    @shop.command('create')
    @click.argument('name')
    @click.option('--type', 'business_type', help='Type of business')
    def create_shop_command(name, business_type=None):
        """Create a new shop."""
        shop = create_shop(name, business_type)
        if shop:
            db.session.commit()
            click.echo(f'Shop {name} created successfully with ID: {shop.id}')
        else:
            click.echo('Failed to create shop')

    @list.command('shops')
    def list_shops():
        """List all shops."""
        shops = Shop.query.all()
        if shops:
            click.echo('\nExisting shops:')
            for shop in shops:
                click.echo(f'ID: {shop.id}, Name: {shop.name}, Type: {shop.business_type}')
        else:
            click.echo('No shops found')

    @list.command('users')
    def list_users():
        """List all users."""
        users = User.query.all()
        if users:
            click.echo('\nExisting users:')
            for user in users:
                # Join with Shop table to get shop names
                user_shops = db.session.query(UserShop, Shop).join(
                    Shop, UserShop.shop_id == Shop.id
                ).filter(UserShop.user_id == user.id).all()

                shop_names = [shop.name for _, shop in user_shops]
                click.echo(f'ID: {user.id}, Name: {user.name}, Role: {user.role}')
                click.echo(f'Shops: {", ".join(shop_names)}')
        else:
            click.echo('No users found')

    @shop.command('delete')
    @click.argument('shop_id')
    @click.confirmation_option(prompt='This will delete the shop and all its data. Are you sure?')
    def delete_shop_command(shop_id):
        """Delete a shop and all its associated data."""
        try:
            shop = Shop.query.get(shop_id)
            if not shop:
                click.echo('Shop not found.')
                return

            # Save name for confirmation message
            shop_name = shop.name

            # Delete all related records
            UserShop.query.filter_by(shop_id=shop_id).delete()
            shop.is_active = False  # Soft delete
            db.session.commit()

            click.echo(f'Shop {shop_name} (ID: {shop_id}) has been deactivated.')
            click.echo('All user associations have been removed.')

        except Exception as e:
            db.session.rollback()
            click.echo(f'Error deleting shop: {str(e)}')

    @shop.command('activate')
    @click.argument('shop_id', type=int)
    def activate_shop(shop_id):
        """Activate a shop by ID."""
        shop = Shop.query.get(shop_id)
        if not shop:
            click.echo(f'Shop with ID {shop_id} not found.')
            return
        shop.is_active = True
        db.session.commit()
        click.echo(f'Shop {shop.name} (ID: {shop_id}) has been activated.')

    @shop.command('deactivate')
    @click.argument('shop_id', type=int)
    def deactivate_shop(shop_id):
        """Deactivate a shop by ID."""
        shop = Shop.query.get(shop_id)
        if not shop:
            click.echo(f'Shop with ID {shop_id} not found.')
            return
        shop.is_active = False
        db.session.commit()
        click.echo(f'Shop {shop.name} (ID: {shop_id}) has been deactivated.')

    @user.command('delete')
    @click.argument('user_id')
    @click.confirmation_option(prompt='Are you sure you want to delete this user?')
    def delete_user_command(user_id):
        """Delete a user and their shop associations."""
        try:
            user = User.query.get(user_id)
            if not user:
                click.echo('User not found.')
                return

            # Save name for confirmation message
            user_name = user.name

            # Remove shop associations
            UserShop.query.filter_by(user_id=user_id).delete()
            user.is_active = False  # Soft delete
            db.session.commit()

            click.echo(f'User {user_name} (ID: {user_id}) has been deactivated.')
            click.echo('All shop associations have been removed.')

        except Exception as e:
            db.session.rollback()
            click.echo(f'Error deleting user: {str(e)}')

    @app.cli.command('delete-shop-data')
    @click.argument('shop_id', type=int)
    @click.option('--backup', is_flag=True, help='Backup data before deleting.')
    def delete_shop_data_command(shop_id, backup):
        """Delete all records related to a specific shop, with optional backup."""

        click.confirm(f'⚠️  Are you sure you want to delete all data for shop_id={shop_id}?', abort=True)

        if backup:
            print(f"📦 Backing up data for shop_id {shop_id}...")
            backup_file = backup_shop_data(shop_id)
            print(f"✅ Backup completed: {backup_file}")

        print(f"🧹 Deleting all related data for shop_id {shop_id}...")
        success = delete_shop_data(shop_id)

        if success:
            print(f"✅ Successfully deleted all related records for shop_id {shop_id}.")
        else:
            print(f"❌ Failed to delete records for shop_id {shop_id}.")
