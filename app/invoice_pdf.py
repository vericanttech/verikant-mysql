"""
Server-side invoice PDF generation (ReportLab).
Used by the bill print/share flow; keep logic out of route files.
"""
import os
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics.barcode.qr import QrCode
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils import format_datetime, number_to_words
from app.vitrine_helpers import build_vitrine_shop_url


def _logo_flowable(logo_fs_path, max_width, max_height):
    """Centered raster logo scaled to fit, or None if unreadable."""
    if not logo_fs_path or not os.path.isfile(logo_fs_path):
        return None
    try:
        ir = ImageReader(logo_fs_path)
        iw, ih = ir.getSize()
        if iw <= 0 or ih <= 0:
            return None
        w = float(max_width)
        h = w * ih / iw
        if h > max_height:
            h = float(max_height)
            w = h * iw / ih
        return Image(logo_fs_path, width=w, height=h, mask="auto")
    except Exception:
        return None


def _format_fr_num(value):
    """Match Jinja filter `fr_thousands` (integer with space thousands separator)."""
    try:
        return f"{int(round(float(value))):,}".replace(",", " ")
    except (ValueError, TypeError):
        return str(value)


def build_invoice_pdf_buffer(bill, shop_profile, vitrine_public_url=None, logo_fs_path=None):
    """
    Build invoice PDF bytes in a BytesIO buffer (ReportLab, portrait A4).

    Parameters
    ----------
    bill : SalesBill
        Must have sales_details (with product), user, client loaded as needed.
    shop_profile : Shop | None
    vitrine_public_url : str | None
        Absolute vitrine URL for the QR (from ``url_for(..., _external=True)`` in the route).
        If omitted, uses :func:`build_vitrine_shop_url` (may be host-relative without env/request).
    logo_fs_path : str | None
        Absolute filesystem path to the shop logo (under the Flask static folder).
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
        logo = _logo_flowable(logo_fs_path, max_width=avail_w * 0.55, max_height=22 * mm)
        if logo:
            logo_table = Table([[logo]], colWidths=[avail_w])
            logo_table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            elements.append(logo_table)
        elements.append(Paragraph(f"<b>{escape(shop_profile.name)}</b>", title_style))

    # Line-item column widths (Qté | Désignation | Prix unitaire | Prix total)
    col_w = [avail_w * 0.09, avail_w * 0.41, avail_w * 0.25, avail_w * 0.25]

    # Shop contact (left) and bill meta (right): right cell matches « Prix total » column start
    cashier = bill.user.name if bill.user else ""
    meta_lines = [
        f"Caissière: {cashier}",
        f"No Facture: {bill.bill_number}",
        f"Date: {format_datetime(bill.date)}",
    ]
    right_html = "<br/>".join(escape(line) for line in meta_lines)

    left_parts = []
    if shop_profile:
        if shop_profile.phones:
            phones = ", ".join(p.phone for p in shop_profile.phones)
            left_parts.append(f"Tel: {phones}")
        if shop_profile.address:
            left_parts.append(str(shop_profile.address))
        if shop_profile.tax_id:
            left_parts.append(f"NINEA / NIF: {shop_profile.tax_id}")
    left_html = "<br/>".join(escape(p) for p in left_parts) if left_parts else ""
    left_cell = Paragraph(left_html if left_html.strip() else " ", meta_style)
    right_cell = Paragraph(right_html, meta_style)
    meta_row = Table(
        [[left_cell, right_cell]],
        colWidths=[col_w[0] + col_w[1] + col_w[2], col_w[3]],
    )
    meta_row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(meta_row)
    elements.append(Spacer(1, 6))
    if bill.client:
        cname = bill.client.name or ""
        cphone = bill.client.phone or ""
        line = f"Client: {cname}"
        if cphone:
            line += f" - Tél: {cphone}"
        elements.append(Paragraph(escape(line), meta_style))
    elements.append(Spacer(1, 10))

    hdr = ["Qté", "Désignation", "Prix unitaire", "Prix total"]
    data = [[Paragraph(f"<b>{escape(h)}</b>", small) for h in hdr]]

    for d in bill.sales_details:
        pname = escape(d.product.name if d.product else "")
        data.append(
            [
                Paragraph(str(d.quantity), small),
                Paragraph(pname, small),
                Paragraph(
                    escape(_format_fr_num(d.selling_price) + " " + str(currency)),
                    small,
                ),
                Paragraph(
                    escape(_format_fr_num(d.total_amount) + " " + str(currency)),
                    small,
                ),
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
            Paragraph(escape(_format_fr_num(bill.total_amount) + " " + str(currency)), normal),
            Paragraph(escape(_format_fr_num(bill.paid_amount) + " " + str(currency)), normal),
            Paragraph(escape(_format_fr_num(bill.remaining_amount) + " " + str(currency)), normal),
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

    # Vitrine QR + public URL (same idea as bills/print.html)
    if shop_profile and getattr(shop_profile, "is_active", True):
        vitrine_url = (vitrine_public_url or "").strip() or build_vitrine_shop_url(
            shop_profile.id
        )
        if vitrine_url:
            try:
                # Vector QR (no Pillow/raster) — reliable in all PDF viewers
                qr_flow = QrCode(value=vitrine_url, width=32 * mm, height=32 * mm)
                vitrine_title = ParagraphStyle(
                    "InvVitrineTitle",
                    parent=styles["Normal"],
                    fontSize=10,
                    leading=12,
                    alignment=TA_CENTER,
                    spaceAfter=4,
                )
                elements.append(Spacer(1, 10))
                href_xml = escape(vitrine_url)
                vitrine_heading = (
                    f'<a href="{href_xml}" color="#2563eb">'
                    f"<b>Promos &amp; vitrine</b></a>"
                )
                elements.append(Paragraph(vitrine_heading, vitrine_title))
                qr_wrap = Table([[qr_flow]], colWidths=[avail_w])
                qr_wrap.setStyle(
                    TableStyle(
                        [
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                elements.append(qr_wrap)
            except Exception:
                pass

    doc.build(elements)
    buffer.seek(0)
    return buffer
