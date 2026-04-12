"""Shop-level listing mode: show all sales vs. VAT-applied bills only (e.g. audit)."""

from flask_login import current_user


def get_current_shop_row():
    from app.models import Shop

    if not current_user.is_authenticated or not current_user.current_shop_id:
        return None
    return Shop.query.get(current_user.current_shop_id)


def shop_lists_all_sales(shop=None):
    """When True (default), sales lists include every bill. When False, only `vat_applied` bills."""
    if shop is None:
        shop = get_current_shop_row()
    if shop is None:
        return True
    return bool(getattr(shop, 'show_all_sales', True))


def sales_bill_vat_only_clause():
    """Extra filter on SalesBill when in VAT-only mode; None means no extra constraint."""
    from app.models import SalesBill

    if shop_lists_all_sales():
        return None
    return SalesBill.vat_applied.is_(True)


def abort_if_bill_hidden_in_vat_mode(bill):
    """404 when shop is in VAT-only listing mode and this bill has no TVA."""
    from flask import abort

    shop = get_current_shop_row()
    if shop and not shop_lists_all_sales(shop) and bill is not None and not bill.vat_applied:
        abort(404)
