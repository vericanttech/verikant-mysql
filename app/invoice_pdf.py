"""
Server-side invoice PDF generation (ReportLab).
Used by the bill print/share flow; keep logic out of route files.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils import format_datetime, number_to_words


def _format_fr_num(value):
    """Match Jinja filter `fr_thousands` (integer with space thousands separator)."""
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(value)


def build_invoice_pdf_buffer(bill, shop_profile):
    """
    Build invoice PDF bytes in a BytesIO buffer (ReportLab, portrait A4).

    Parameters
    ----------
    bill : SalesBill
        Must have sales_details (with product), user, client loaded as needed.
    shop_profile : Shop | None
    """
    margin = 12 * mm
    page_w, _page_h = A4
    avail_w = page_w - 2 * margin

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=f"Facture {bill.bill_number}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvTitle",
        parent=styles["Heading1"],
        fontSize=14,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "InvMeta",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        spaceAfter=2,
        alignment=TA_LEFT,
    )
    small = ParagraphStyle(
        "InvCell",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        alignment=TA_LEFT,
    )
    normal = ParagraphStyle(
        "InvNorm",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
    )

    currency = (shop_profile.currency if shop_profile else None) or "FCFA"
    elements = []

    if shop_profile:
        elements.append(Paragraph(f"<b>{escape(shop_profile.name)}</b>", title_style))
        if shop_profile.phones:
            phones = ", ".join(p.phone for p in shop_profile.phones)
            elements.append(Paragraph(escape(f"Tel: {phones}"), meta_style))
        if shop_profile.address:
            elements.append(Paragraph(escape(str(shop_profile.address)), meta_style))
        if shop_profile.tax_id:
            elements.append(Paragraph(escape(f"NINEA / NIF: {shop_profile.tax_id}"), meta_style))
    elements.append(Spacer(1, 8))

    cashier = bill.user.name if bill.user else ""
    elements.append(
        Paragraph(
            escape(
                f"Caissière: {cashier} &nbsp;&nbsp; No Facture: {bill.bill_number} &nbsp;&nbsp; "
                f"Date: {format_datetime(bill.date)}"
            ),
            meta_style,
        )
    )
    if bill.client:
        cname = bill.client.name or ""
        cphone = bill.client.phone or ""
        line = f"Client: {cname}"
        if cphone:
            line += f" — Tél: {cphone}"
        elements.append(Paragraph(escape(line), meta_style))
    elements.append(Spacer(1, 10))

    col_w = [avail_w * 0.09, avail_w * 0.41, avail_w * 0.25, avail_w * 0.25]
    hdr = ["Qté", "Désignation", "Prix unitaire", "Prix total"]
    data = [[Paragraph(f"<b>{escape(h)}</b>", small) for h in hdr]]

    for d in bill.sales_details:
        pname = escape(d.product.name if d.product else "")
        data.append(
            [
                Paragraph(str(d.quantity), small),
                Paragraph(pname, small),
                Paragraph(_format_fr_num(d.selling_price) + " " + escape(currency), small),
                Paragraph(_format_fr_num(d.total_amount) + " " + escape(currency), small),
            ]
        )

    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    elements.append(t)
    elements.append(Spacer(1, 8))

    show_discount = bill.discount_amount is not None and float(bill.discount_amount) > 0
    show_vat = (bill.vat_amount is not None and float(bill.vat_amount) > 0) or (
        bill.vat_rate is not None and float(bill.vat_rate) > 0
    )
    if show_discount or show_vat:
        vrows = []
        if show_discount:
            vrows.append(
                (
                    "Sous-total HT",
                    _format_fr_num(bill.gross_amount_ht) + " " + currency,
                )
            )
            dr = bill.discount_rate
            pct = f" ({round(float(dr) * 100, 2)}%)" if dr else ""
            vrows.append(
                (
                    "Remise" + pct,
                    "-" + _format_fr_num(bill.discount_amount) + " " + currency,
                )
            )
        if show_vat:
            vrows.append(("Total HT", _format_fr_num(bill.amount_ht) + " " + currency))
            vr = bill.vat_rate
            vpct = f" ({round(float(vr) * 100, 2)}%)" if vr else ""
            vrows.append(("TVA" + vpct, _format_fr_num(bill.vat_amount) + " " + currency))
            vrows.append(("Total TTC", _format_fr_num(bill.total_amount) + " " + currency))
        elif show_discount:
            vrows.append(("Total", _format_fr_num(bill.total_amount) + " " + currency))
        vdata = [
            [Paragraph(escape(a), normal), Paragraph(escape(b), normal)] for a, b in vrows
        ]
        vt = Table(vdata, colWidths=[avail_w * 0.55, avail_w * 0.45])
        vt.setStyle(
            TableStyle(
                [
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONT", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        elements.append(vt)
        elements.append(Spacer(1, 6))

    ttc_label = "TOTAL TTC" if show_vat else "TOTAL"
    tot_data = [
        [
            Paragraph(f"<b>{escape(ttc_label)}</b>", normal),
            Paragraph("<b>AVANCE</b>", normal),
            Paragraph("<b>NET A PAYER</b>", normal),
        ],
        [
            Paragraph(_format_fr_num(bill.total_amount) + " " + currency, normal),
            Paragraph(_format_fr_num(bill.paid_amount) + " " + currency, normal),
            Paragraph(_format_fr_num(bill.remaining_amount) + " " + currency, normal),
        ],
    ]
    ttot = Table(tot_data, colWidths=[avail_w / 3.0] * 3)
    ttot.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    elements.append(ttot)
    elements.append(Spacer(1, 10))

    try:
        words = number_to_words(bill.total_amount, currency).upper()
        elements.append(Paragraph(f"<b>Total en lettres :</b> {escape(words)}", meta_style))
    except Exception:
        pass

    doc.build(elements)
    buffer.seek(0)
    return buffer
