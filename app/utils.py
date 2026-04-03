# In your utils.py
from datetime import datetime
from num2words import num2words

from functools import wraps
from flask import flash, redirect, request
from flask_login import current_user


def format_date(value):
    if isinstance(value, str):
        try:
            return datetime.strptime(value, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            return value
    elif hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    return value


# Register the filter in your app
def admin_only_action(*form_keys):
    """
    Decorator to restrict POST actions (triggered via modal forms) to admins only.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if request.method == 'POST' and any(key in request.form for key in form_keys):
                if current_user.role.lower() != 'admin':
                    flash("Action non autorisée. Seuls les administrateurs peuvent effectuer cette opération.", 'error')
                    return redirect(request.referrer or '/')
            return view_func(*args, **kwargs)
        return wrapper
    return decorator



def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Veuillez vous connecter pour effectuer cette action.", "error")
            return redirect(request.referrer or "/")

        if current_user.role != 'admin':
            flash("Action non autorisée : seuls les administrateurs peuvent effectuer cette opération. Vous pouvez "
                  "prendre note de cette modification et en informer un administrateur.", "error")
            return redirect(request.referrer or "/")

        return f(*args, **kwargs)
    return decorated_function


def number_to_words(number, currency='FCFA'):
    try:
        amount = float(str(number).rstrip('0').rstrip('.') if '.' in str(number) else number)
        words = num2words(amount, lang='fr')
        return f"{words.upper()} {currency}"
    except Exception as e:
        print(f"Error converting number to words: {e}")
        return str(number)
