# In your utils.py
from datetime import date, datetime
from num2words import num2words

from functools import wraps
from flask import flash, redirect, request
from flask_login import current_user


def parse_datetime(value):
    """
    Parse DB / API datetimes (strings with optional microseconds, ISO, or datetime/date).
    Used for display only — does not change stored values or SQL filters.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # Plain date (not datetime) — isinstance(datetime_obj, date) is True for datetime too
    if type(value) is date:
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # ISO with space (MySQL / Python str): 2026-04-04 17:25:35.007435
        if len(s) > 10 and s[10] == ' ':
            s_iso = s[:10] + 'T' + s[11:]
        else:
            s_iso = s
        try:
            return datetime.fromisoformat(s_iso)
        except ValueError:
            pass
        for fmt, maxlen in (
            ('%Y-%m-%d %H:%M:%S.%f', 26),
            ('%Y-%m-%d %H:%M:%S', 19),
            ('%Y-%m-%d', 10),
        ):
            try:
                chunk = s[:maxlen] if len(s) >= maxlen else s
                return datetime.strptime(chunk, fmt)
            except ValueError:
                continue
    return None


def format_date(value):
    """
    HTML <input type="date"> values: always YYYY-MM-DD.
    Parses strings with or without fractional seconds.
    """
    dt = parse_datetime(value)
    if dt is not None:
        return dt.strftime('%Y-%m-%d')
    if isinstance(value, str) and len(value) >= 10 and value[4] == '-' and value[7] == '-':
        return value[:10]
    if hasattr(value, 'strftime') and not isinstance(value, str):
        try:
            return value.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    return value if value is not None else ''


def format_datetime(value):
    """
    Human-readable display: DD/MM/YYYY, or DD/MM/YYYY HH:MM when time is not midnight.
    Strips microseconds. Does not affect date range filters (those use raw columns / request args).
    """
    dt = parse_datetime(value)
    if dt is None:
        return value if value is not None else ''
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.strftime('%d/%m/%Y')
    return dt.strftime('%d/%m/%Y %H:%M')


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


def recalculate_sales_bill_totals(bill):
    """
    Set amount_ht from line items (after global discount), vat_amount from vat_rate,
    total_amount (TTC), remaining_amount and status.
    """
    from app.models import SalesDetail

    details = SalesDetail.query.filter_by(bill_id=bill.id).all()
    gross_ht = sum(float(d.total_amount) for d in details)
    dr = bill.discount_rate
    if dr is not None and float(dr) > 0:
        bill.discount_amount = round(gross_ht * float(dr), 2)
        bill.amount_ht = round(gross_ht - float(bill.discount_amount), 2)
    else:
        bill.discount_amount = 0
        bill.discount_rate = None
        bill.amount_ht = gross_ht
    if bill.vat_rate is not None and float(bill.vat_rate) > 0:
        bill.vat_amount = round(float(bill.amount_ht) * float(bill.vat_rate), 2)
    else:
        bill.vat_amount = 0
    bill.total_amount = float(bill.amount_ht) + float(bill.vat_amount)
    paid = float(bill.paid_amount or 0)
    bill.remaining_amount = max(0, float(bill.total_amount) - paid)
    if bill.remaining_amount == 0:
        bill.status = 'paid'
    else:
        bill.status = 'partially_paid'
