# app/middleware.py
from functools import wraps
from flask import g, session, redirect, url_for

from app import db


def shop_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        shop_id = session.get('shop_id')
        if not shop_id:
            return redirect(url_for('auth.select_shop'))
        with db.shop_session(shop_id):
            return f(*args, **kwargs)

    return decorated_function
