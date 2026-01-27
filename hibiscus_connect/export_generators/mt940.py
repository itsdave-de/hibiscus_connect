# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

"""
SWIFT MT940 (Customer Statement Message) Generator

This module generates MT940 text files conforming to the German banking standard
(Deutsche Kreditwirtschaft / DK specification).

MT940 Structure:
- :20: Transaction Reference Number (empty for compatibility)
- :25: Account Identification (BLZ/Kontonummer format)
- :28C: Statement Number/Sequence Number
- :60F: Opening Balance
- :61: Statement Line (one per transaction)
- :86: Information to Account Owner (structured ?XX format)
- :62F: Closing Balance
- -: Statement separator
"""

from frappe.utils import getdate


# SWIFT character set (limited to printable ASCII subset)
SWIFT_CHARS = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/-?:().,\' +')


def generate_mt940(bank_account, transactions, opening_balance, closing_balance,
                   from_date, to_date, statement_id):
    """
    Generate an MT940 text document in German banking format.

    Args:
        bank_account: Hibiscus Connect Bank Account document
        transactions: List of Hibiscus Connect Transaction documents
        opening_balance: Opening balance as float
        closing_balance: Closing balance as float
        from_date: Start date of the statement period
        to_date: End date of the statement period
        statement_id: Unique statement identifier

    Returns:
        str: MT940 content as string
    """
    lines = []

    # :20: Transaction Reference Number (empty for German format)
    lines.append(":20:")

    # :25: Account Identification (BLZ/Kontonummer format)
    account_id = _format_account_id(bank_account)
    lines.append(f":25:{account_id}")

    # :28C: Statement Number/Sequence Number (0/1 as default)
    lines.append(":28C:0/1")

    # :60F: Opening Balance
    opening_line = _format_balance_line(
        "60F",
        opening_balance,
        from_date,
        bank_account.currency or "EUR"
    )
    lines.append(opening_line)

    # Transaction entries (:61: and :86:)
    for trans in transactions:
        # :61: Statement Line
        stmt_line = _format_transaction_line(trans)
        lines.append(stmt_line)

        # :86: Information to Account Owner (structured German format)
        info_lines = _format_info_line(trans)
        lines.extend(info_lines)

    # :62F: Closing Balance
    closing_line = _format_balance_line(
        "62F",
        closing_balance,
        to_date,
        bank_account.currency or "EUR"
    )
    lines.append(closing_line)

    # Statement separator
    lines.append("-")

    # Join with LF (matching German bank format)
    # Note: SWIFT standard specifies CRLF, but German banks often use LF
    return "\n".join(lines) + "\n"


def _format_account_id(bank_account):
    """
    Format account identification as BLZ/Kontonummer.

    German format: BBBBBBBB/KKKKKKKKKK (BLZ/Kontonummer)
    """
    blz = bank_account.bank_code or ""
    account_number = bank_account.account_number or ""

    if blz and account_number:
        return f"{blz}/{account_number}"

    # Fallback: extract from IBAN if available
    iban = bank_account.iban or ""
    if iban.startswith("DE") and len(iban) >= 22:
        # German IBAN: DEpp BBBB BBBB KKKK KKKK KK
        blz = iban[4:12]
        account_number = iban[12:22].lstrip("0") or "0"
        return f"{blz}/{account_number}"

    # Last resort: use IBAN or account name
    return _sanitize_swift(iban or bank_account.name, 35)


def _format_balance_line(field_tag, amount, date_val, currency):
    """
    Format a balance line (:60F:, :62F:).

    Format: :xxF:CYYMMDDCCCNNNNNNNNNNN,NN
    - C/D: Credit or Debit indicator
    - YYMMDD: Date
    - CCC: Currency code
    - N: Amount (comma as decimal separator)
    """
    # Credit/Debit indicator
    cd_indicator = "C" if amount >= 0 else "D"

    # Format date as YYMMDD
    if isinstance(date_val, str):
        date_val = getdate(date_val)
    date_str = date_val.strftime("%y%m%d")

    # Format amount (no thousands separator, comma as decimal)
    amount_str = _format_mt940_amount(abs(amount))

    return f":{field_tag}:{cd_indicator}{date_str}{currency}{amount_str}"


def _format_transaction_line(transaction):
    """
    Format a transaction line (:61:).

    German format: :61:VVMMDDMMDDCRNNNNNNNN,NNNTRFNONREF//XXXXXXXXXXXXXXXX
    - VVMMDD: Value date (YYMMDD)
    - MMDD: Entry/Booking date
    - C/D + R: Credit/Debit with Funds Code R
    - N: Amount
    - TRF: Transaction type (Transfer as default)
    - NONREF: Reference placeholder
    - //: Bank reference
    """
    # Value date (YYMMDD)
    value_date = transaction.value_date or transaction.transaction_date
    if isinstance(value_date, str):
        value_date = getdate(value_date)
    value_date_str = value_date.strftime("%y%m%d")

    # Entry/Booking date (MMDD) - always include for German format
    booking_date = transaction.transaction_date
    if isinstance(booking_date, str):
        booking_date = getdate(booking_date)
    entry_date_str = booking_date.strftime("%m%d")

    # Credit/Debit indicator with Funds Code R
    amount = float(transaction.amount)
    if amount >= 0:
        cd_indicator = "CR"
    else:
        cd_indicator = "DR"

    # Amount (no currency, comma as decimal)
    amount_str = _format_mt940_amount(abs(amount))

    # Transaction type code - default to TRF (Transfer)
    tx_type = "NTRF"

    # Reference - use NONREF as placeholder
    ref_part = "NONREF"

    # Bank reference (after //) - use customer_ref if available
    bank_ref = ""
    customer_ref = transaction.get('customer_ref') or ""
    if customer_ref:
        # Truncate to 16 chars (MT940 limit for this field)
        bank_ref = f"//{_sanitize_swift(customer_ref[:16], 16)}"
    elif transaction.get('hibiscus_id'):
        bank_ref = f"//{_sanitize_swift(str(transaction.hibiscus_id), 16)}"

    return f":61:{value_date_str}{entry_date_str}{cd_indicator}{amount_str}{tx_type}{ref_part}{bank_ref}"


def _format_info_line(transaction):
    """
    Format information lines (:86:) in structured German format.

    German DK format with ?XX subfields:
    - GV-Code directly after :86: (before ?00)
    - ?00: Buchungstext (transaction type)
    - ?10: Primanota
    - ?20-?29: Verwendungszweck (purpose)
    - ?30: BIC Gegenkonto
    - ?31: IBAN Gegenkonto
    - ?32-?33: Name Gegenkonto

    Each subfield on a new line.
    """
    lines = []

    # Get GV-Code (stored in primanota field in our system)
    gv_code = transaction.get('primanota') or ""

    # Start :86: line with GV-Code
    first_line = f":86:{gv_code}"

    # ?00: Buchungstext (transaction type)
    tx_type = transaction.get('transaction_type') or ""
    if tx_type:
        first_line += f"?00{_sanitize_swift(tx_type, 27)}"

    lines.append(first_line)

    # ?10: Primanota - we don't have the real primanota value
    # (our primanota field contains the GV-code, which is already used above)
    # Skipping ?10 as it's not critical for most import software

    # ?20-?29: Verwendungszweck (purpose) - split into 27-char chunks
    purpose = transaction.get('purpose') or ""
    purpose = _sanitize_swift(purpose, 270)  # Max 10 x 27 chars

    purpose_parts = [purpose[i:i+27] for i in range(0, len(purpose), 27)]
    for i, part in enumerate(purpose_parts[:10]):
        if part:
            lines.append(f"?{20+i:02d}{part}")

    # ?30: BIC Gegenkonto
    counterparty_bic = transaction.get('counterparty_bic') or ""
    if counterparty_bic:
        lines.append(f"?30{_sanitize_swift(counterparty_bic, 11)}")

    # ?31: IBAN Gegenkonto
    counterparty_iban = transaction.get('counterparty_iban') or ""
    if counterparty_iban:
        lines.append(f"?31{_sanitize_swift(counterparty_iban, 34)}")

    # ?32-?33: Name Gegenkonto (max 2 x 27 chars)
    counterparty_name = transaction.get('counterparty_name') or ""
    counterparty_name = _sanitize_swift(counterparty_name, 54)

    if counterparty_name:
        lines.append(f"?32{counterparty_name[:27]}")
        if len(counterparty_name) > 27:
            lines.append(f"?33{counterparty_name[27:54]}")

    return lines


def _format_mt940_amount(amount):
    """
    Format amount for MT940.

    Format: digits with comma as decimal separator, no thousands separator
    Example: 75000,00
    """
    # Format with 2 decimal places
    formatted = f"{abs(float(amount)):.2f}"

    # Replace decimal point with comma (German/SWIFT format)
    formatted = formatted.replace(".", ",")

    return formatted


def _sanitize_swift(text, max_length=None):
    """
    Sanitize text for SWIFT MT940 format.

    - Replace German umlauts with ASCII equivalents
    - Keep only SWIFT-allowed characters
    - Truncate to max_length if specified
    """
    if not text:
        return ""

    text = str(text)

    # Replace German umlauts and special characters
    replacements = {
        'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
        'Ä': 'AE', 'Ö': 'OE', 'Ü': 'UE',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u',
        'ñ': 'n', 'ç': 'c',
        '€': 'EUR',
        '&': '+',
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Keep only SWIFT-allowed characters
    sanitized = ''.join(c if c in SWIFT_CHARS else ' ' for c in text)

    # Normalize whitespace (but preserve single spaces)
    sanitized = ' '.join(sanitized.split())

    # Truncate if needed
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized
