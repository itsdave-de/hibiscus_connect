# Copyright (c) 2026, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _


# Statuses that represent a fully-booked transaction. When "Verbuchte ausblenden"
# is active, rows in any of these statuses are excluded from the list.
FULLY_BOOKED_STATUSES = ("auto booked", "legacy booked", "manually booked")


@frappe.whitelist()
def get_unbooked_transactions(
    direction="All",
    bank_account=None,
    search=None,
    hide_booked=1,
    page=1,
    page_size=50,
):
    """Fetch bank transactions with filters and pagination."""

    page = int(page)
    page_size = int(page_size)
    hide_booked = int(hide_booked)
    offset = (page - 1) * page_size

    conditions = []
    values = {}

    if hide_booked:
        conditions.append("t.status NOT IN %(booked_statuses)s")
        values["booked_statuses"] = FULLY_BOOKED_STATUSES

    if direction == "Outgoing":
        conditions.append("t.amount < 0")
    elif direction == "Incoming":
        conditions.append("t.amount > 0")

    if bank_account:
        conditions.append("t.bank_account = %(bank_account)s")
        values["bank_account"] = bank_account

    if search:
        # Full-text search across all user-visible fields.
        # Amount matching accepts both German (33,70) and SQL/dot (33.70) formats
        # by comparing against a German-formatted version AND the raw string.
        conditions.append(
            "(t.counterparty_name LIKE %(search)s "
            "OR t.purpose LIKE %(search)s "
            "OR t.counterparty_iban LIKE %(search)s "
            "OR t.counterparty_bic LIKE %(search)s "
            "OR t.transaction_type LIKE %(search)s "
            "OR t.gvcode LIKE %(search)s "
            "OR t.name LIKE %(search)s "
            "OR CAST(t.amount AS CHAR) LIKE %(search)s "
            "OR REPLACE(CAST(t.amount AS CHAR), '.', ',') LIKE %(search)s "
            "OR DATE_FORMAT(t.transaction_date, '%%d.%%m.%%Y') LIKE %(search)s)"
        )
        values["search"] = f"%{search}%"

    where = " AND ".join(conditions) if conditions else "1 = 1"

    # Paginate directly in SQL now that we filter on a database column (status).
    total = frappe.db.sql(
        f"SELECT COUNT(*) FROM `tabHibiscus Connect Transaction` t WHERE {where}",
        values,
    )[0][0]

    transactions = frappe.db.sql(
        f"""
        SELECT
            t.name, t.amount, t.transaction_date, t.counterparty_name,
            t.counterparty_iban, t.counterparty_bic, t.purpose,
            t.transaction_type, t.gvcode, t.bank_account, t.status
        FROM `tabHibiscus Connect Transaction` t
        WHERE {where}
        ORDER BY t.transaction_date DESC, t.name DESC
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        {**values, "limit": page_size, "offset": offset},
        as_dict=True,
    )

    # Auto-classify each transaction using Booking Category keywords
    categories = frappe.get_all(
        "Booking Category",
        filters={"enabled": 1},
        fields=["category_name", "purpose_keywords", "direction", "booking_type"],
        order_by="sort_order asc",
    )

    # Build a direction lookup for all categories (used to validate rules)
    all_categories = frappe.get_all("Booking Category",
        fields=["category_name", "direction"])
    category_direction = {c["category_name"]: c["direction"] for c in all_categories}

    # Load all Booking Rules indexed by IBAN for fast lookup
    booking_rules = {}
    rules = frappe.get_all("Booking Rule",
        filters={"enabled": 1},
        fields=["counterparty_iban", "booking_category", "match_count", "logo"])
    for r in rules:
        r["category_direction"] = category_direction.get(r.booking_category)
        booking_rules[r.counterparty_iban] = r

    for tx in transactions:
        tx["suggestion"] = _auto_classify(tx, categories, booking_rules)

    # Stats — always reflect the count of transactions that still need attention
    # (i.e. not fully booked), independent of the current filter state.
    stats = frappe.db.sql(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN amount < 0 THEN 1 ELSE 0 END) as outgoing_count,
            SUM(CASE WHEN amount > 0 THEN 1 ELSE 0 END) as incoming_count,
            COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as outgoing_sum,
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as incoming_sum
        FROM `tabHibiscus Connect Transaction`
        WHERE status NOT IN %(booked_statuses)s
        """,
        {"booked_statuses": FULLY_BOOKED_STATUSES},
        as_dict=True,
    )[0]

    return {
        "transactions": transactions,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "stats": stats,
    }


def _auto_classify(tx, categories, booking_rules=None):
    """Auto-classification: Booking Rule (learned) > Keyword (rule-based)."""

    direction = "Incoming" if tx.get("amount", 0) > 0 else "Outgoing"

    # 1. Check Booking Rule (learned from previous bookings, direction-aware)
    iban = tx.get("counterparty_iban") or ""
    if booking_rules and iban in booking_rules:
        rule = booking_rules[iban]
        cat_direction = rule.get("category_direction")
        # Skip the learned rule if its category direction doesn't match
        # (e.g. "Sonstige Ausgabe" should not apply to an incoming transaction)
        if not cat_direction or cat_direction in (direction, "Both"):
            result = {
                "category": rule["booking_category"],
                "source": "learned",
                "match_count": rule.get("match_count", 0),
            }
            if rule.get("logo"):
                result["logo"] = rule["logo"]
            return result

    # 2. Fallback: keyword matching
    purpose_lower = (tx.get("purpose") or "").lower()
    tx_type_lower = (tx.get("transaction_type") or "").lower()
    combined = purpose_lower + " " + tx_type_lower

    for cat in categories:
        if cat["direction"] not in (direction, "Both"):
            continue
        keywords = cat.get("purpose_keywords") or ""
        if not keywords:
            continue
        for kw in keywords.split(","):
            kw = kw.strip().lower()
            if kw and kw in combined:
                return {
                    "category": cat["category_name"],
                    "source": "keyword",
                    "keyword": kw,
                }
    return None
