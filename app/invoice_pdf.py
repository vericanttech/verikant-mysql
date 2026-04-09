"""
Server-side invoice PDF generation (ReportLab) — Premium design.
Compact header, space-efficient layout, auto multi-page support.
"""
import os
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics.barcode.qr import QrCode
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.platypus.flowables import Flowable

from app.utils import format_datetime, number_to_words
from app.vitrine_helpers import build_vitrine_shop_url


# ── Brand palette ─────────────────────────────────────────────────────────────
INK        = colors.HexColor("#0F172A")   # near-black text
ACCENT     = colors.HexColor("#2563EB")   # vivid blue
ACCENT_LT  = colors.HexColor("#EFF6FF")   # pale blue fill
MUTED      = colors.HexColor("#64748B")   # secondary text
RULE       = colors.HexColor("#CBD5E1")   # thin hairlines
WHITE      = colors.white
GOLD       = colors.HexColor("#F59E0B")   # "paid" badge accent


class _HLine(Flowable):
    """Full-width hairline rule."""
    def __init__(self, width, color=RULE, thickness=0.4):
        super().__init__()
        self.line_width = width
        self.color = color
        self.thickness = thickness
        self.height = self.thickness
        self.width = width

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 0, self.line_width, 0)


def _logo_flowable(logo_fs_path, max_width, max_height):
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
    try:
        return f"{int(round(float(value))):,}".replace(",", "\u202f")  # narrow no-break space
    except (ValueError, TypeError):
        return str(value)


def _p(text, style):
    return Paragraph(text, style)


def build_invoice_pdf_buffer(bill, shop_profile, vitrine_public_url=None, logo_fs_path=None):
    """
    Build a premium invoice PDF in a BytesIO buffer (ReportLab, portrait A4).
    Auto-paginates; maximises rows per page with a compact header.
    """
    margin_h = 10 * mm
    margin_v = 8 * mm
    page_w, page_h = A4
    avail_w = page_w - 2 * margin_h

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin_h,
        rightMargin=margin_h,
        topMargin=margin_v,
        bottomMargin=margin_v,
        title=f"Facture {bill.bill_number}",
    )

    # ── Styles ────────────────────────────────────────────────────────────────
    base = getSampleStyleSheet()

    def ps(name, **kw):
        parent = kw.pop("parent", base["Normal"])
        s = ParagraphStyle(name, parent=parent, **kw)
        return s

    shop_name_st = ps("ShopName",   fontSize=13, textColor=INK,   fontName="Helvetica-Bold",   leading=15, alignment=TA_LEFT)
    shop_sub_st  = ps("ShopSub",    fontSize=7,  textColor=MUTED,  fontName="Helvetica",        leading=9,  alignment=TA_LEFT)
    badge_st     = ps("Badge",      fontSize=8,  textColor=WHITE,  fontName="Helvetica-Bold",   leading=10, alignment=TA_CENTER)
    meta_lbl_st  = ps("MetaLbl",    fontSize=6.5,textColor=MUTED,  fontName="Helvetica",        leading=8,  alignment=TA_LEFT, spaceAfter=0)
    meta_val_st  = ps("MetaVal",    fontSize=8,  textColor=INK,    fontName="Helvetica-Bold",   leading=10, alignment=TA_LEFT, spaceAfter=0)
    meta_r_lbl   = ps("MetaRLbl",   fontSize=6.5,textColor=MUTED,  fontName="Helvetica",        leading=8,  alignment=TA_RIGHT,spaceAfter=0)
    meta_r_val   = ps("MetaRVal",   fontSize=8,  textColor=INK,    fontName="Helvetica-Bold",   leading=10, alignment=TA_RIGHT,spaceAfter=0)
    col_hdr_st   = ps("ColHdr",     fontSize=7,  textColor=WHITE,  fontName="Helvetica-Bold",   leading=9,  alignment=TA_CENTER)
    col_hdr_r_st = ps("ColHdrR",    fontSize=7,  textColor=WHITE,  fontName="Helvetica-Bold",   leading=9,  alignment=TA_RIGHT)
    cell_st      = ps("Cell",       fontSize=7.5,textColor=INK,    fontName="Helvetica",        leading=9,  alignment=TA_LEFT)
    cell_r_st    = ps("CellR",      fontSize=7.5,textColor=INK,    fontName="Helvetica",        leading=9,  alignment=TA_RIGHT)
    cell_c_st    = ps("CellC",      fontSize=7.5,textColor=INK,    fontName="Helvetica",        leading=9,  alignment=TA_CENTER)
    subtot_lbl   = ps("SubtotLbl",  fontSize=8,  textColor=MUTED,  fontName="Helvetica",        leading=10, alignment=TA_RIGHT)
    subtot_val   = ps("SubtotVal",  fontSize=8,  textColor=INK,    fontName="Helvetica",        leading=10, alignment=TA_RIGHT)
    grand_lbl    = ps("GrandLbl",   fontSize=9,  textColor=WHITE,  fontName="Helvetica-Bold",   leading=11, alignment=TA_RIGHT)
    grand_val    = ps("GrandVal",   fontSize=9,  textColor=WHITE,  fontName="Helvetica-Bold",   leading=11, alignment=TA_RIGHT)
    footer_st    = ps("Footer",     fontSize=6.5,textColor=MUTED,  fontName="Helvetica-Oblique",leading=8,  alignment=TA_CENTER)
    words_st     = ps("Words",      fontSize=7.5,textColor=MUTED,  fontName="Helvetica-Oblique",leading=9,  alignment=TA_LEFT)
    client_st    = ps("Client",     fontSize=8,  textColor=INK,    fontName="Helvetica",        leading=10, alignment=TA_LEFT)

    currency = (shop_profile.currency if shop_profile else None) or "FCFA"
    elements  = []

    # ── HEADER ────────────────────────────────────────────────────────────────
    # Left: logo + shop name / contact  |  Right: FACTURE badge + meta fields
    # Everything packed into a single compact table row.

    logo_flow = _logo_flowable(logo_fs_path, max_width=28 * mm, max_height=14 * mm) if shop_profile else None

    # -- Build left info block
    left_lines = []
    if shop_profile:
        left_lines.append(_p(escape(shop_profile.name), shop_name_st))
        sub_parts = []
        if shop_profile.phones:
            sub_parts.append("Tél: " + ", ".join(p.phone for p in shop_profile.phones))
        if shop_profile.address:
            sub_parts.append(str(shop_profile.address))
        if shop_profile.tax_id:
            sub_parts.append("NINEA: " + str(shop_profile.tax_id))
        if sub_parts:
            left_lines.append(_p(" · ".join(escape(s) for s in sub_parts), shop_sub_st))

    # -- Bill meta (right column)
    cashier = bill.user.name if bill.user else "—"
    meta_pairs = [
        ("FACTURE N°",  bill.bill_number),
        ("DATE",        format_datetime(bill.date)),
        ("CAISSIER(E)", cashier),
    ]

    # Badge "FACTURE" label
    badge_data  = [[_p("F A C T U R E", badge_st)]]
    badge_table = Table(badge_data, colWidths=[avail_w * 0.38])
    badge_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), ACCENT),
        ("ROUNDEDCORNERS",(0,0),(-1,-1), [3,3,3,3]),
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
    ]))

    meta_rows = [[_p(lbl, meta_r_lbl), _p(escape(str(val)), meta_r_val)]
                 for lbl, val in meta_pairs]
    meta_inner = Table(meta_rows, colWidths=[avail_w * 0.14, avail_w * 0.24])
    meta_inner.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 1),
        ("BOTTOMPADDING", (0,0),(-1,-1), 1),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("LINEBELOW", (0,-1),(-1,-1), 0, colors.transparent),
    ]))

    right_cell_content = [badge_table, Spacer(1, 4), meta_inner]

    # Assemble logo + shop name
    if logo_flow:
        left_top = Table(
            [[logo_flow, Table([[_p(e.text if hasattr(e,'text') else '', shop_name_st)] for e in left_lines[:1]],
                               colWidths=[avail_w * 0.38])]],
            colWidths=[30*mm, avail_w * 0.38],
        ) if False else None  # simplified: just stack
        left_cell_items = [logo_flow] + left_lines
    else:
        left_cell_items = left_lines

    left_col  = Table([[item] for item in left_cell_items], colWidths=[avail_w * 0.58])
    left_col.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 1),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
    ]))

    right_col = Table([[item] for item in right_cell_content], colWidths=[avail_w * 0.38])
    right_col.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 1),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("ALIGN",         (0,0),(-1,-1), "RIGHT"),
    ]))

    header_table = Table(
        [[left_col, right_col]],
        colWidths=[avail_w * 0.60, avail_w * 0.40],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("TOPPADDING",    (0,0),(-1,-1), 0),
        ("BOTTOMPADDING", (0,0),(-1,-1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 3))
    elements.append(_HLine(avail_w, ACCENT, 1.2))
    elements.append(Spacer(1, 3))

    # ── CLIENT ROW ────────────────────────────────────────────────────────────
    if bill.client:
        cname  = bill.client.name  or ""
        cphone = bill.client.phone or ""
        line   = f"<b>Client :</b>  {escape(cname)}"
        if cphone:
            line += f"   <font color='#{MUTED.hexval()[2:]}'>·  {escape(cphone)}</font>"
        elements.append(_p(line, client_st))
        elements.append(Spacer(1, 3))

    # ── LINE-ITEMS TABLE ──────────────────────────────────────────────────────
    # Columns: Qté | Désignation | P.U. | Total
    col_w = [
        avail_w * 0.08,   # qty
        avail_w * 0.44,   # name
        avail_w * 0.24,   # unit price
        avail_w * 0.24,   # total
    ]

    hdr_row = [
        _p("QTÉ",          col_hdr_st),
        _p("DÉSIGNATION",  col_hdr_st),
        _p("PRIX UNITAIRE",col_hdr_r_st),
        _p("TOTAL",        col_hdr_r_st),
    ]
    data = [hdr_row]

    for idx, d in enumerate(bill.sales_details):
        pname    = escape(d.product.name if d.product else "")
        row_bg   = ACCENT_LT if idx % 2 == 0 else WHITE
        data.append([
            _p(str(d.quantity),                                                   cell_c_st),
            _p(pname,                                                              cell_st),
            _p(escape(_format_fr_num(d.selling_price) + " " + str(currency)),    cell_r_st),
            _p(escape(_format_fr_num(d.total_amount)  + " " + str(currency)),    cell_r_st),
        ])

    t = Table(data, colWidths=col_w, repeatRows=1)

    # Build per-row background commands
    row_cmds = [
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0),  ACCENT),
        ("TOPPADDING",    (0, 0), (-1, 0),  4),
        ("BOTTOMPADDING", (0, 0), (-1, 0),  4),
        # All cells
        ("FONT",          (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        # Subtle horizontal grid only
        ("LINEBELOW",     (0, 0), (-1, -2), 0.3, RULE),
        ("LINEBELOW",     (0, -1),(-1, -1), 0.8, ACCENT),
        # Alternate row tint
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            row_cmds.append(("BACKGROUND", (0, i), (-1, i), ACCENT_LT))

    t.setStyle(TableStyle(row_cmds))
    elements.append(t)
    elements.append(Spacer(1, 4))

    # ── SUBTOTALS BLOCK ───────────────────────────────────────────────────────
    show_discount = bill.discount_amount is not None and float(bill.discount_amount) > 0
    show_vat = (bill.vat_amount is not None and float(bill.vat_amount) > 0) or (
        bill.vat_rate is not None and float(bill.vat_rate) > 0
    )

    if show_discount or show_vat:
        vrows = []
        if show_discount:
            vrows.append(("Sous-total HT", _format_fr_num(bill.gross_amount_ht) + " " + currency))
            dr  = bill.discount_rate
            pct = f" ({round(float(dr)*100,2)}%)" if dr else ""
            vrows.append(("Remise" + pct, "−" + _format_fr_num(bill.discount_amount) + " " + currency))
        if show_vat:
            vrows.append(("Total HT",  _format_fr_num(bill.amount_ht)  + " " + currency))
            vr   = bill.vat_rate
            vpct = f" ({round(float(vr)*100,2)}%)" if vr else ""
            vrows.append(("TVA" + vpct, _format_fr_num(bill.vat_amount) + " " + currency))

        vdata = [[_p(escape(a), subtot_lbl), _p(escape(b), subtot_val)] for a, b in vrows]
        vt = Table(vdata, colWidths=[avail_w * 0.80, avail_w * 0.20])
        vt.setStyle(TableStyle([
            ("TOPPADDING",    (0,0),(-1,-1), 2),
            ("BOTTOMPADDING", (0,0),(-1,-1), 2),
            ("LEFTPADDING",   (0,0),(-1,-1), 0),
            ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ]))
        elements.append(vt)
        elements.append(Spacer(1, 3))

    # ── TOTALS BANNER (3-column) ──────────────────────────────────────────────
    ttc_label = "TOTAL TTC" if show_vat else "TOTAL"
    tot_cells = [
        (_p(ttc_label, grand_lbl),         _p(escape(_format_fr_num(bill.total_amount)     + " " + str(currency)), grand_val)),
        (_p("AVANCE",  grand_lbl),         _p(escape(_format_fr_num(bill.paid_amount)       + " " + str(currency)), grand_val)),
        (_p("NET À PAYER", grand_lbl),     _p(escape(_format_fr_num(bill.remaining_amount)  + " " + str(currency)), grand_val)),
    ]
    col_w3 = avail_w / 3.0

    inner_cols = []
    for lbl_p, val_p in tot_cells:
        inner_cols.append(Table([[lbl_p], [val_p]], colWidths=[col_w3 - 4]))

    tot_banner = Table([inner_cols], colWidths=[col_w3] * 3)
    tot_banner.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), ACCENT),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ("LINEBEFORE",    (1,0),(2,-1),  0.5, colors.HexColor("#93C5FD")),
    ]))

    elements.append(KeepTogether([tot_banner]))
    elements.append(Spacer(1, 4))

    # Amount in words
    try:
        words = number_to_words(bill.total_amount, currency).upper()
        elements.append(_p(f"<i>Arrêté à la somme de : </i><b>{escape(words)}</b>", words_st))
    except Exception:
        pass

    # ── FOOTER: QR + thank-you note ───────────────────────────────────────────
    if shop_profile and getattr(shop_profile, "is_active", True):
        vitrine_url = (vitrine_public_url or "").strip() or build_vitrine_shop_url(shop_profile.id)
        if vitrine_url:
            try:
                qr_size   = 20 * mm
                qr_flow   = QrCode(value=vitrine_url, width=qr_size, height=qr_size)
                href_xml  = escape(vitrine_url)
                link_text = (f'<a href="{href_xml}" color="#2563EB"><u>Découvrez nos promos &amp; vitrine</u></a>')
                link_p    = _p(link_text, footer_st)
                ty_p      = _p("Merci pour votre confiance !", footer_st)

                footer_table = Table(
                    [[qr_flow, Table([[ty_p], [link_p]], colWidths=[avail_w - qr_size - 6*mm])]],
                    colWidths=[qr_size + 4*mm, avail_w - qr_size - 4*mm],
                )
                footer_table.setStyle(TableStyle([
                    ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
                    ("LEFTPADDING",   (0,0),(-1,-1), 0),
                    ("RIGHTPADDING",  (0,0),(-1,-1), 0),
                    ("TOPPADDING",    (0,0),(-1,-1), 0),
                    ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                ]))

                elements.append(Spacer(1, 6))
                elements.append(_HLine(avail_w, RULE, 0.4))
                elements.append(Spacer(1, 4))
                elements.append(footer_table)
            except Exception:
                pass

    doc.build(elements)
    buffer.seek(0)
    return buffer