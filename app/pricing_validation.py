"""Enforce unit selling price >= buying price (cost) where applicable."""


def validate_unit_selling_not_below_buying(
    unit_selling,
    buying_price,
    product_name=None,
):
    """
    Raise ValueError if unit selling price is strictly below buying price.

    Used for products, POS lines, and bill line edits. Float comparison is
    sufficient for typical currency amounts; both values should be non-negative.
    """
    try:
        us = float(unit_selling)
        bp = float(buying_price)
    except (TypeError, ValueError) as e:
        raise ValueError("Prix invalide.") from e
    if us < bp:
        label = (product_name or "Produit").strip() or "Produit"
        raise ValueError(
            f"{label} : le prix de vente unitaire doit être supérieur ou égal au prix d'achat "
            f"(minimum {bp:g})."
        )
