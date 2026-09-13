"""Country and currency rules for Vericant shops.

Each shop has one base currency.  Currency conversion is intentionally outside
this module: amounts entered for a shop always remain in that shop's currency.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


COUNTRIES = {
    "SN": {
        "name_fr": "Sénégal",
        "name_en": "Senegal",
        "currency_code": "XOF",
    },
    "GN": {
        "name_fr": "Guinée-Conakry",
        "name_en": "Guinea-Conakry",
        "currency_code": "GNF",
    },
    "SL": {
        "name_fr": "Sierra Leone",
        "name_en": "Sierra Leone",
        "currency_code": "SLE",
    },
}

CURRENCIES = {
    "XOF": {"label": "FCFA", "decimals": 0},
    "GNF": {"label": "GNF", "decimals": 0},
    "SLE": {"label": "Le", "decimals": 2},
}


def normalize_country_code(value: str | None) -> str:
    code = (value or "SN").strip().upper()
    return code if code in COUNTRIES else "SN"


def currency_for_country(country_code: str | None) -> str:
    return COUNTRIES[normalize_country_code(country_code)]["currency_code"]


def normalize_currency_code(value: str | None) -> str:
    raw = (value or "XOF").strip().upper()
    aliases = {"FCFA": "XOF", "F.CFA": "XOF", "LE": "SLE", "SLL": "SLE"}
    code = aliases.get(raw, raw)
    return code if code in CURRENCIES else "XOF"


def currency_label(currency_code: str | None) -> str:
    return CURRENCIES[normalize_currency_code(currency_code)]["label"]


def currency_decimals(currency_code: str | None) -> int:
    return int(CURRENCIES[normalize_currency_code(currency_code)]["decimals"])


def shop_currency_code(shop) -> str:
    if shop is None:
        return "XOF"
    explicit = getattr(shop, "currency_code", None)
    if explicit:
        return normalize_currency_code(explicit)
    return normalize_currency_code(getattr(shop, "currency", None))


def format_amount(value, currency_code: str | None = "XOF", language: str = "fr") -> str:
    """Format the numeric part of a monetary amount without its currency label."""
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)

    decimals = currency_decimals(currency_code)
    quantum = Decimal("1") if decimals == 0 else Decimal("1." + ("0" * decimals))
    amount = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    rendered = f"{amount:,.{decimals}f}"
    if language == "fr":
        rendered = rendered.replace(",", "\u202f").replace(".", ",")
    return rendered


def format_money(value, currency_code: str | None = "XOF", language: str = "fr") -> str:
    code = normalize_currency_code(currency_code)
    amount = format_amount(value, code, language)
    label = currency_label(code)
    return f"{label} {amount}" if code == "SLE" else f"{amount} {label}"


def country_options(language: str = "fr") -> list[dict]:
    name_key = "name_en" if language == "en" else "name_fr"
    return [
        {
            "country_code": country_code,
            "country_name": data[name_key],
            "currency_code": data["currency_code"],
            "currency_label": currency_label(data["currency_code"]),
        }
        for country_code, data in COUNTRIES.items()
    ]
