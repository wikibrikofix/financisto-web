"""Email worker: polls Gmail IMAP for bank emails and creates transactions."""
import imaplib
import email
import email.header
import re
import os
import time
import json
import socket
import requests
from datetime import datetime

# Global socket timeout to prevent hanging on DNS/connection
socket.setdefaulttimeout(30)

API_URL = os.environ.get("API_URL", "http://backend:5000/api")
IMAP_HOST = os.environ.get("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.environ.get("IMAP_USER")
IMAP_PASS = os.environ.get("IMAP_PASS")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "300"))  # 5 min
ACCOUNT_MAP = json.loads(os.environ.get("ACCOUNT_MAP", "{}"))  # {"bank": 1, "card": 2}

# Track processed emails to avoid duplicates
PROCESSED_FILE = "/data/processed_emails.json"


def load_processed():
    try:
        with open(PROCESSED_FILE) as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_processed(ids):
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "w") as f:
        json.dump(list(ids), f)


def get_text_from_html(html):
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    html = re.sub(r'</tr>', '\n', html)
    html = re.sub(r'<td[^>]*>', '|', html)
    html = re.sub(r'<[^>]+>', '', html)
    html = re.sub(r'&nbsp;', ' ', html)
    html = re.sub(r'[ \t]+', ' ', html)
    return html


def get_email_body(msg):
    """Extract text content from email."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == 'text/plain':
                return part.get_payload(decode=True).decode('utf-8', errors='ignore')
            elif ct == 'text/html':
                html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                return get_text_from_html(html)
    else:
        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        if msg.get_content_type() == 'text/html':
            return get_text_from_html(body)
        return body
    return ""


def parse_bank_statement(body, date_str):
    """Parse bank 'operation executed' email. Expects table with Importo, Descrizione movimento, Data contabile."""
    lines = body.split('\n')
    data = {}
    for line in lines:
        if '|' not in line:
            continue
        parts = line.split('|')
        for i, p in enumerate(parts):
            p = p.strip()
            if 'Importo' in p and i + 1 < len(parts):
                data['amount_str'] = parts[i + 1].strip()
            elif 'Descrizione movimento' in p and i + 1 < len(parts):
                data['description'] = parts[i + 1].strip()
            elif 'Data contabile' in p and i + 1 < len(parts):
                data['date'] = parts[i + 1].strip()
            elif 'Tipo operazione' in p and i + 1 < len(parts):
                data['type'] = parts[i + 1].strip()

    if 'amount_str' not in data:
        return None

    # Parse amount: "+700,00 euro" or "-38,50 euro"
    m = re.search(r'([+-]?[\d.,]+)\s*euro', data['amount_str'])
    if not m:
        return None
    amount_str = m.group(1).replace('.', '').replace(',', '.')
    amount_cents = int(float(amount_str) * 100)

    # Parse date
    dt = None
    if 'date' in data:
        try:
            dt = datetime.strptime(data['date'], '%d/%m/%Y')
        except ValueError:
            pass
    if not dt:
        dt = datetime.now()

    # Extract payee from description
    desc = data.get('description', '')
    payee = desc[:60].strip()

    return {
        'from_amount': amount_cents,
        'datetime': int(dt.timestamp() * 1000),
        'note': desc,
        'payee_name': payee,
        'source': 'bank',
        'account_key': 'bank',
    }


def parse_card_notification(body, date_str):
    """Parse real-time card payment notification."""
    # Pattern 1: "autorizzato il pagamento di 16,40 EUR il 18/05 alle 19:24 ... presso NOME"
    m = re.search(r'pagamento di ([\d.,]+) EUR il (\d{2}/\d{2}) .+?presso (.+?)\.', body)
    if m:
        amount_str = m.group(1).replace('.', '').replace(',', '.')
        date_part = m.group(2)
        payee = m.group(3).strip()
        dt = datetime.strptime(f"{date_part}/{datetime.now().year}", '%d/%m/%Y')
        return {
            'from_amount': -int(float(amount_str) * 100),
            'datetime': int(dt.timestamp() * 1000),
            'note': f'Card: {payee}',
            'payee_name': payee,
            'source': 'card',
            'account_key': 'bank',
        }

    # Pattern 2: "spesa di EUR 94,60 alle ore 08:00 del giorno 22/05 ... presso NOME"
    m = re.search(r'spesa di EUR ([\d.,]+) .+?del giorno (\d{2}/\d{2}) .+?presso (.+?)\.', body)
    if m:
        amount_str = m.group(1).replace('.', '').replace(',', '.')
        date_part = m.group(2)
        payee = m.group(3).strip()
        dt = datetime.strptime(f"{date_part}/{datetime.now().year}", '%d/%m/%Y')
        return {
            'from_amount': -int(float(amount_str) * 100),
            'datetime': int(dt.timestamp() * 1000),
            'note': f'Card: {payee}',
            'payee_name': payee,
            'source': 'card',
            'account_key': 'bank',
        }

    return None




# Sender configuration via env vars
BANK_SENDER = os.environ.get("BANK_SENDER", "")
BANK_SUBJECT = os.environ.get("BANK_SUBJECT", "")
CARD_SENDER = os.environ.get("CARD_SENDER", "")

PARSERS = {}
if BANK_SENDER:
    PARSERS[BANK_SENDER] = (BANK_SUBJECT or None, parse_bank_statement)
if CARD_SENDER:
    PARSERS[CARD_SENDER] = (None, parse_card_notification)


def is_duplicate(tx, existing_txs):
    """Check if a similar transaction already exists (same amount, same day ±1 day)."""
    tx_date = tx['datetime']
    for e in existing_txs:
        if e['from_amount'] == tx['from_amount'] and abs(e['datetime'] - tx_date) < 86400000 * 2:
            return True
    return False


def create_transaction(tx):
    """Create transaction via API."""
    # Resolve or create payee
    payee_id = 0
    if tx.get('payee_name'):
        payees = requests.get(f"{API_URL}/payees").json()
        existing = next((p for p in payees if p['title'].lower() == tx['payee_name'].lower()), None)
        if existing:
            payee_id = existing['id']
        else:
            resp = requests.post(f"{API_URL}/payees", json={"title": tx['payee_name']})
            if resp.ok:
                payee_id = resp.json()['id']

    account_id = ACCOUNT_MAP.get(tx.get('account_key'), list(ACCOUNT_MAP.values())[0] if ACCOUNT_MAP else 1)

    data = {
        'from_account_id': account_id,
        'from_amount': tx['from_amount'],
        'to_account_id': 0,
        'to_amount': 0,
        'category_id': 0,
        'payee_id': payee_id,
        'datetime': tx['datetime'],
        'note': tx.get('note', ''),
        'status': 'UR',
    }
    resp = requests.post(f"{API_URL}/transactions", json=data)
    return resp.ok


def check_duplicates(tx, account_id):
    """Check recent transactions for duplicates."""
    resp = requests.get(f"{API_URL}/accounts/{account_id}/transactions?limit=20")
    if not resp.ok:
        return False
    return is_duplicate(tx, resp.json())


def poll():
    """Poll Gmail for new bank emails."""
    processed = load_processed()
    print("[*] Connecting to IMAP...", flush=True)
    mail = imaplib.IMAP4_SSL(IMAP_HOST, 993, timeout=30)
    mail.login(IMAP_USER, IMAP_PASS)
    mail.select('INBOX')

    new_count = 0
    for sender, (subject_filter, parser) in PARSERS.items():
        # Search last 2 days instead of UNSEEN - we track processed IDs ourselves
        from datetime import timedelta
        since = (datetime.now() - timedelta(days=2)).strftime('%d-%b-%Y')
        query = f'(FROM "{sender}" SINCE {since})'
        status, messages = mail.search(None, query)
        if status != 'OK':
            continue

        nums = messages[0].split()
        for num in nums:
            msg_id = num.decode()
            if msg_id in processed:
                continue

            status, data = mail.fetch(num, '(BODY.PEEK[])')
            msg = email.message_from_bytes(data[0][1])

            # Check subject filter
            if subject_filter:
                subj = email.header.decode_header(msg['Subject'])[0]
                subj_text = subj[0].decode(subj[1] or 'utf-8') if isinstance(subj[0], bytes) else subj[0]
                if subject_filter.lower() not in subj_text.lower():
                    processed.add(msg_id)
                    continue

            body = get_email_body(msg)
            date_str = msg.get('Date', '')

            tx = parser(body, date_str)
            if tx:
                account_id = ACCOUNT_MAP.get(tx.get('account_key'), 1)
                if not check_duplicates(tx, account_id):
                    if create_transaction(tx):
                        new_count += 1
                        print(f"[+] {tx['source']}: {tx['payee_name']} {tx['from_amount']/100:.2f}€")
                    else:
                        print(f"[!] Failed to create tx: {tx}")
                else:
                    print(f"[=] Duplicate skipped: {tx['payee_name']} {tx['from_amount']/100:.2f}€")

            processed.add(msg_id)

    mail.logout()
    save_processed(processed)
    if new_count:
        print(f"[*] Created {new_count} new transactions")


def main():
    print(f"[*] Email worker started. Polling every {POLL_INTERVAL}s", flush=True)
    print(f"[*] Monitoring: {', '.join(PARSERS.keys())}", flush=True)
    print(f"[*] Account map: {ACCOUNT_MAP}", flush=True)

    while True:
        try:
            poll()
        except Exception as e:
            print(f"[!] Error: {e}", flush=True)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
