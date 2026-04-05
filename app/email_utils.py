import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app
from app.models import SalesBill, Client, Shop
from app.utils import format_datetime
from sqlalchemy.orm import joinedload
import logging

logger = logging.getLogger(__name__)

def send_balance_notifications(shop_id, email_password):
    """
    Send balance notifications to all clients with unpaid bills
    """
    try:
        # Get shop information
        shop = Shop.query.get(shop_id)
        if not shop or not shop.email:
            return False, "Shop email not configured"
        
        # Get all bills with remaining amounts > 0
        unpaid_bills = SalesBill.query.filter_by(
            shop_id=shop_id
        ).filter(
            SalesBill.remaining_amount > 0
        ).options(
            joinedload(SalesBill.client)
        ).all()
        
        if not unpaid_bills:
            return True, "No unpaid bills found"
        
        # Group bills by client
        client_bills = {}
        for bill in unpaid_bills:
            if bill.client and bill.client.email:
                client_id = bill.client.id
                if client_id not in client_bills:
                    client_bills[client_id] = {
                        'client': bill.client,
                        'bills': [],
                        'total_remaining': 0
                    }
                client_bills[client_id]['bills'].append(bill)
                client_bills[client_id]['total_remaining'] += bill.remaining_amount
        
        # Send emails to each client
        sent_count = 0
        failed_count = 0
        
        for client_data in client_bills.values():
            client = client_data['client']
            bills = client_data['bills']
            total_remaining = client_data['total_remaining']
            
            success, message = send_client_balance_email(
                shop, client, bills, total_remaining, email_password
            )
            
            if success:
                sent_count += 1
            else:
                failed_count += 1
        
        return True, f"Sent {sent_count} emails successfully. {failed_count} failed."
        
    except Exception as e:
        logger.error(f"Error sending balance notifications: {str(e)}")
        return False, f"Error: {str(e)}"

def create_balance_email_html(shop, client, bills, total_remaining):
    """
    Create the HTML email body for balance notifications
    """
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rappel de solde impayé</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        .container {{
            background-color: #ffffff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #e3f2fd;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .shop-name {{
            color: #1976d2;
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .greeting {{
            font-size: 18px;
            color: #333;
            margin-bottom: 20px;
        }}
        .alert-box {{
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 5px;
            padding: 15px;
            margin: 20px 0;
        }}
        .bills-section {{
            margin: 25px 0;
        }}
        .bill-item {{
            background-color: #f8f9fa;
            border-left: 4px solid #dc3545;
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
        }}
        .bill-number {{
            font-weight: bold;
            color: #dc3545;
            font-size: 16px;
        }}
        .bill-amount {{
            font-size: 18px;
            font-weight: bold;
            color: #dc3545;
        }}
        .bill-date {{
            color: #6c757d;
            font-size: 14px;
        }}
        .total-section {{
            background-color: #e3f2fd;
            border: 2px solid #1976d2;
            border-radius: 8px;
            padding: 20px;
            margin: 25px 0;
            text-align: center;
        }}
        .total-label {{
            font-size: 16px;
            color: #1976d2;
            font-weight: bold;
        }}
        .total-amount {{
            font-size: 24px;
            font-weight: bold;
            color: #dc3545;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e9ecef;
            text-align: center;
            color: #6c757d;
            font-size: 14px;
        }}
        .signature {{
            margin: 20px 0;
            font-style: italic;
        }}
        .auto-message {{
            background-color: #f8f9fa;
            border-radius: 5px;
            padding: 10px;
            font-size: 12px;
            color: #6c757d;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="shop-name">{shop.name}</div>
        </div>
        
        <div class="greeting">
            Bonjour <strong>{client.name}</strong>,
        </div>
        
        <div class="alert-box">
            <strong>⚠️ Rappel Important :</strong> Nous vous rappelons que vous avez des soldes impayés dans notre système.
        </div>
        
        <div class="bills-section">
            <h3 style="color: #dc3545; margin-bottom: 15px;">📋 Détails des factures impayées :</h3>
"""
    
    for bill in bills:
        html += f"""
            <div class="bill-item">
                <div class="bill-number">Facture #{bill.bill_number}</div>
                <div class="bill-amount">{bill.remaining_amount:,.0f} {shop.currency}</div>
                <div class="bill-date">Date : {format_datetime(bill.date)}</div>
            </div>
"""
    
    html += f"""
        </div>
        
        <div class="total-section">
            <div class="total-label">Montant total impayé :</div>
            <div class="total-amount">{total_remaining:,.0f} {shop.currency}</div>
        </div>
        
        <div class="signature">
            Merci de régulariser votre situation dans les plus brefs délais.
            <br><br>
            Cordialement,<br>
            <strong>{shop.name}</strong>
        </div>
        
        <div class="footer">
            <div class="auto-message">
                Ce message est envoyé automatiquement par le système de gestion de {shop.name}.
            </div>
        </div>
    </div>
</body>
</html>
"""
    
    return html

def create_balance_email_text(shop, client, bills, total_remaining):
    """
    Create the plain text email body for balance notifications
    """
    body = f"""Bonjour {client.name},

Nous vous rappelons que vous avez des soldes impayés dans notre système.

Détails des factures impayées :
"""
    
    for bill in bills:
        body += f"""
- Facture #{bill.bill_number} : {bill.remaining_amount:,.0f} {shop.currency}
  Date : {format_datetime(bill.date)}
"""
    
    body += f"""

Montant total impayé : {total_remaining:,.0f} {shop.currency}

Merci de régulariser votre situation dans les plus brefs délais.

Cordialement,
{shop.name}

---
Ce message est envoyé automatiquement par le système de gestion de {shop.name}.
"""
    
    return body 

def _send_email(shop, recipient_email, subject, html_body, text_body, email_password):
    """
    Helper to send an email with both HTML and plain text bodies.
    """
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = shop.email
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(shop.email, email_password)
        server.sendmail(shop.email, recipient_email, msg.as_string())
        server.quit()
        logger.info(f"Email sent to {recipient_email}")
        return True, f"Rappel envoyé à {recipient_email}."
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {str(e)}")
        return False, f"Erreur lors de l'envoi de l'email: {str(e)}"


def send_client_balance_email(shop, client, bills, total_remaining, email_password):
    """
    Send balance notification email to a specific client
    """
    subject = f"Rappel de solde impayé - {shop.name}"
    html_body = create_balance_email_html(shop, client, bills, total_remaining)
    text_body = create_balance_email_text(shop, client, bills, total_remaining)
    return _send_email(shop, client.email, subject, html_body, text_body, email_password)


def send_single_bill_reminder(bill_id, shop_id, email_password):
    """
    Send a reminder for a single bill to its client (if possible)
    """
    from app.models import SalesBill, Shop
    bill = SalesBill.query.filter_by(id=bill_id, shop_id=shop_id).first()
    if not bill:
        return False, "Facture introuvable."
    if not bill.client or not bill.client.email:
        return False, "Ce client n'a pas d'adresse email enregistrée."
    if bill.remaining_amount <= 0:
        return False, "Cette facture est déjà réglée."
    shop = Shop.query.get(shop_id)
    if not shop or not shop.email or not email_password:
        return False, "Configuration email du magasin incomplète."
    subject = f"Rappel de solde impayé - {shop.name}"
    html_body = create_balance_email_html(shop, bill.client, [bill], bill.remaining_amount)
    text_body = create_balance_email_text(shop, bill.client, [bill], bill.remaining_amount)
    return _send_email(shop, bill.client.email, subject, html_body, text_body, email_password) 