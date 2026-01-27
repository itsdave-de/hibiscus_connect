import frappe
from frappe.utils import now_datetime, add_days, getdate, fmt_money
from datetime import datetime, timedelta


# ============================================================================
# Account Status API
# ============================================================================

def hex_to_hue(hex_color):
    """Convert hex color to hue value (0-360). Green=120, Red=0/360, Yellow=60."""
    if not hex_color:
        return 180  # Default to cyan-ish for missing colors
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return 180
    try:
        r = int(hex_color[0:2], 16) / 255.0
        g = int(hex_color[2:4], 16) / 255.0
        b = int(hex_color[4:6], 16) / 255.0
    except ValueError:
        return 180

    max_c = max(r, g, b)
    min_c = min(r, g, b)
    diff = max_c - min_c

    if diff == 0:
        return 0
    elif max_c == r:
        hue = 60 * (((g - b) / diff) % 6)
    elif max_c == g:
        hue = 60 * (((b - r) / diff) + 2)
    else:
        hue = 60 * (((r - g) / diff) + 4)

    return hue


def color_sort_key(accent_color_1, sort_order):
    """
    Generate a sort key for color-based sorting (green first, red last).

    Green (hue ~120) should come first, red (hue ~0/360) last.
    We use sort_order as primary key, then color hue.
    """
    hue = hex_to_hue(accent_color_1)

    # Transform hue so that green (120) comes first and red (0/360) comes last
    # Distance from green: values closer to 120 get lower scores
    # Hue 120 (green) -> 0, Hue 0/360 (red) -> 120, Hue 240 (blue) -> 120
    distance_from_green = abs(hue - 120)
    if distance_from_green > 180:
        distance_from_green = 360 - distance_from_green

    return (sort_order or 0, distance_from_green)


@frappe.whitelist()
def get_account_status():
    """Get status of all accounts enabled for auto-fetch with balance comparison to previous day.

    Only returns accounts the current user has permission to access.
    frappe.get_list respects permission_query_conditions hooks.

    Accounts are sorted by:
    1. sort_order (manual override)
    2. Color hue (green first, red last)
    """
    # Using get_list instead of get_all to ensure permissions are respected
    accounts = frappe.get_list(
        "Hibiscus Connect Bank Account",
        filters={"auto_fetch": 1},
        fields=["name", "description", "iban", "balance", "balance_date", "currency", "accent_color_1", "accent_color_2", "text_color", "sort_order"]
    )

    # Sort by sort_order first, then by color (green to red)
    accounts = sorted(accounts, key=lambda a: color_sort_key(a.accent_color_1, a.sort_order))

    result = []
    for acc in accounts:
        current_balance = acc.balance or 0

        # Get previous day's closing balance based on the account's balance_date
        # (compare to the day before the last balance update)
        if acc.balance_date:
            previous_day = add_days(getdate(acc.balance_date), -1)
        else:
            previous_day = add_days(getdate(), -1)

        previous_balance = get_balance_for_date(acc.name, previous_day)

        # Calculate change
        change = None
        if previous_balance is not None:
            change = current_balance - previous_balance

        # Get transaction count for this account
        transaction_count = frappe.db.count("Hibiscus Connect Transaction", {"bank_account": acc.name})

        result.append({
            "name": acc.name,
            "description": acc.description or acc.iban,
            "iban": acc.iban,
            "balance": current_balance,
            "balance_formatted": fmt_money(current_balance, currency=acc.currency or "EUR"),
            "balance_date": acc.balance_date,
            "currency": acc.currency or "EUR",
            "previous_balance": previous_balance,
            "change": change,
            "change_formatted": fmt_money(abs(change) if change else 0, currency=acc.currency or "EUR") if change is not None else None,
            "transaction_count": transaction_count,
            "accent_color_1": acc.accent_color_1 or "#667eea",
            "accent_color_2": acc.accent_color_2 or "#764ba2",
            "text_color": acc.text_color or "Auto",
        })

    return result


def get_balance_for_date(account, target_date):
    """Get the closing balance for a specific date from transactions."""
    # Get the last transaction on or before the target date
    trans = frappe.db.sql("""
        SELECT balance
        FROM `tabHibiscus Connect Transaction`
        WHERE bank_account = %s
          AND COALESCE(value_date, transaction_date) <= %s
        ORDER BY COALESCE(value_date, transaction_date) DESC, name DESC
        LIMIT 1
    """, (account, target_date), as_dict=True)

    if trans:
        return trans[0].balance
    return None


@frappe.whitelist()
def get_fetch_health():
    """Get health status of the hourly transaction fetch.

    Account counts are filtered by user permissions.
    Uses custom Hibiscus Connect Sync Log for accurate tracking.
    """
    from frappe.utils.scheduler import is_scheduler_inactive
    now = now_datetime()

    # Check scheduler status
    scheduler_disabled = is_scheduler_inactive()

    # Get accounts enabled for auto-fetch (respects permissions via get_list)
    auto_fetch_accounts = frappe.get_all(
        "Hibiscus Connect Bank Account",
        filters={"auto_fetch": 1},
        fields=["name", "description", "iban"]
    )

    # Get last sync log entry (custom logging)
    last_sync = frappe.db.sql("""
        SELECT
            name,
            status,
            trigger_type,
            started_at,
            completed_at,
            accounts_processed,
            transactions_fetched,
            errors_count
        FROM `tabHibiscus Connect Sync Log`
        ORDER BY started_at DESC
        LIMIT 1
    """, as_dict=True)

    # Get recent sync history (last 24 hours)
    sync_history = frappe.db.sql("""
        SELECT
            name,
            status,
            trigger_type,
            started_at,
            accounts_processed,
            transactions_fetched,
            errors_count
        FROM `tabHibiscus Connect Sync Log`
        WHERE started_at >= %s
        ORDER BY started_at DESC
    """, (add_days(now, -1),), as_dict=True)

    # Calculate stats
    total_runs = len(sync_history)
    successful_runs = len([s for s in sync_history if s.status == "Complete"])
    failed_runs = len([s for s in sync_history if s.status == "Failed"])
    total_transactions = sum(s.transactions_fetched or 0 for s in sync_history)

    # Determine overall health status
    health_status = "healthy"
    health_message = "All systems operational"

    if scheduler_disabled:
        health_status = "critical"
        health_message = "Scheduler is disabled"
    elif not auto_fetch_accounts:
        health_status = "warning"
        health_message = "No accounts configured for auto-fetch"
    elif not last_sync:
        health_status = "warning"
        health_message = "No fetch jobs have run yet"
    elif last_sync[0].status == "Failed":
        health_status = "error"
        health_message = "Last fetch job failed"
    elif last_sync[0].status == "Running":
        health_status = "healthy"
        health_message = "Sync currently running"
    elif last_sync:
        # Check if last sync is too old (more than 2 hours ago)
        last_run_time = last_sync[0].started_at
        if isinstance(last_run_time, str):
            last_run_time = datetime.strptime(last_run_time, "%Y-%m-%d %H:%M:%S.%f")
        hours_since_last = (now - last_run_time).total_seconds() / 3600
        if hours_since_last > 2:
            health_status = "warning"
            health_message = f"Last fetch was {int(hours_since_last)} hours ago"

    # Get last transaction creation time
    last_transaction = frappe.db.sql("""
        SELECT creation, bank_account
        FROM `tabHibiscus Connect Transaction`
        ORDER BY creation DESC
        LIMIT 1
    """, as_dict=True)

    return {
        "health_status": health_status,
        "health_message": health_message,
        "scheduler_enabled": not scheduler_disabled,
        "auto_fetch_account_count": len(auto_fetch_accounts),
        "last_job": {
            "time": last_sync[0].started_at if last_sync else None,
            "status": last_sync[0].status if last_sync else None,
            "trigger_type": last_sync[0].trigger_type if last_sync else None,
            "accounts_processed": last_sync[0].accounts_processed if last_sync else 0,
            "transactions_fetched": last_sync[0].transactions_fetched if last_sync else 0
        } if last_sync else None,
        "stats_24h": {
            "total_runs": total_runs,
            "successful": successful_runs,
            "failed": failed_runs,
            "success_rate": round((successful_runs / total_runs * 100), 1) if total_runs > 0 else 0,
            "transactions_fetched": total_transactions
        },
        "last_transaction": {
            "time": last_transaction[0].creation if last_transaction else None,
            "account": last_transaction[0].bank_account if last_transaction else None
        } if last_transaction else None
    }


# ============================================================================
# Hibiscus Server Status API (REST)
# ============================================================================

@frappe.whitelist()
def get_hibiscus_server_status():
    """
    Get comprehensive status of the Hibiscus Payment Server.

    Returns server uptime, version, scheduler status, services, and recent logs.
    This uses the Hibiscus REST API (webadmin) to fetch real-time server information.

    Returns:
        dict: {
            "online": bool,
            "uptime": {"started": str, "uptime": str},
            "version": {"version": str, ...},
            "scheduler": {"started": bool, "service_info": dict},
            "services": {"scheduler": {...}, "execute": {...}, ...},
            "pending_jobs_count": int,
            "recent_errors": list,
            "error": str or None
        }
    """
    from hibiscus_connect.hibiscus_rest_client import get_hibiscus_rest_client, HibiscusRestError

    try:
        client = get_hibiscus_rest_client()
        return client.get_server_health()
    except HibiscusRestError as e:
        return {
            "online": False,
            "error": str(e)
        }
    except Exception as e:
        frappe.log_error(f"Error fetching Hibiscus server status: {e}", "Hibiscus Server Status")
        return {
            "online": False,
            "error": f"Unexpected error: {str(e)}"
        }


@frappe.whitelist()
def get_hibiscus_server_logs(count=100, level=None, contains=None):
    """
    Get log entries from the Hibiscus Payment Server.

    Args:
        count: Number of log entries to retrieve (default 100, max 500)
        level: Filter by log level (ERROR, WARN, INFO, DEBUG)
        contains: Filter entries containing this text

    Returns:
        dict: {
            "success": bool,
            "logs": list of log entries,
            "count": int,
            "error": str or None
        }
    """
    from hibiscus_connect.hibiscus_rest_client import get_hibiscus_rest_client, HibiscusRestError

    # Sanitize inputs
    count = min(int(count), 500)
    level = level.upper() if level else None

    try:
        client = get_hibiscus_rest_client()
        logs = client.get_logs_filtered(count=count, level=level, contains=contains)
        return {
            "success": True,
            "logs": logs,
            "count": len(logs),
            "error": None
        }
    except HibiscusRestError as e:
        return {
            "success": False,
            "logs": [],
            "count": 0,
            "error": str(e)
        }
    except Exception as e:
        frappe.log_error(f"Error fetching Hibiscus logs: {e}", "Hibiscus Server Logs")
        return {
            "success": False,
            "logs": [],
            "count": 0,
            "error": f"Unexpected error: {str(e)}"
        }


@frappe.whitelist()
def get_hibiscus_scheduler_status():
    """
    Get the Hibiscus server scheduler status.

    Returns:
        dict: {
            "online": bool,
            "scheduler_running": bool,
            "services": dict,
            "pending_jobs": int,
            "error": str or None
        }
    """
    from hibiscus_connect.hibiscus_rest_client import get_hibiscus_rest_client, HibiscusRestError

    try:
        client = get_hibiscus_rest_client()

        scheduler = client.get_scheduler_status()
        services = client.get_all_services_status()
        jobs = client.get_pending_jobs()

        return {
            "online": True,
            "scheduler_running": scheduler.get("started", False),
            "services": services,
            "pending_jobs": len(jobs) if jobs else 0,
            "error": None
        }
    except HibiscusRestError as e:
        return {
            "online": False,
            "scheduler_running": False,
            "services": {},
            "pending_jobs": 0,
            "error": str(e)
        }


@frappe.whitelist()
def get_hibiscus_sync_logs(count=50):
    """
    Get synchronization-related log entries from the Hibiscus server.

    Filters logs for HBCI/FinTS synchronization activity.

    Args:
        count: Number of entries to scan (default 50)

    Returns:
        dict: {
            "success": bool,
            "logs": list of sync-related log entries,
            "error": str or None
        }
    """
    from hibiscus_connect.hibiscus_rest_client import get_hibiscus_rest_client, HibiscusRestError

    count = min(int(count), 200)

    try:
        client = get_hibiscus_rest_client()
        logs = client.get_sync_logs(count)
        return {
            "success": True,
            "logs": logs,
            "count": len(logs),
            "error": None
        }
    except HibiscusRestError as e:
        return {
            "success": False,
            "logs": [],
            "count": 0,
            "error": str(e)
        }


# ============================================================================
# Enhanced Health Check (combines Frappe scheduler + Hibiscus server status)
# ============================================================================

@frappe.whitelist()
def get_comprehensive_health():
    """
    Get comprehensive health status combining Frappe and Hibiscus server information.

    This provides a unified view of:
    - Frappe scheduler status
    - Hibiscus server online status
    - Hibiscus scheduler status
    - Recent sync activity
    - Error indicators

    Returns:
        dict: Complete health information for dashboard display
    """
    from frappe.utils.scheduler import is_scheduler_inactive
    from hibiscus_connect.hibiscus_rest_client import get_hibiscus_rest_client, HibiscusRestError

    now = now_datetime()
    result = {
        "overall_status": "healthy",
        "overall_message": "All systems operational",
        "frappe": {
            "scheduler_enabled": not is_scheduler_inactive()
        },
        "hibiscus_server": {
            "online": False,
            "scheduler_running": False,
            "uptime": None,
            "version": None,
            "pending_jobs": 0,
            "recent_errors_count": 0,
            "error": None
        },
        "sync": {
            "last_sync_time": None,
            "last_sync_status": None,
            "runs_24h": 0,
            "success_rate_24h": 0,
            "transactions_24h": 0
        },
        "accounts": {
            "auto_fetch_count": 0
        }
    }

    # Get Frappe-side information
    auto_fetch_accounts = frappe.get_all(
        "Hibiscus Connect Bank Account",
        filters={"auto_fetch": 1},
        fields=["name"]
    )
    result["accounts"]["auto_fetch_count"] = len(auto_fetch_accounts)

    # Get sync history
    last_sync = frappe.db.sql("""
        SELECT name, status, started_at, transactions_fetched
        FROM `tabHibiscus Connect Sync Log`
        ORDER BY started_at DESC
        LIMIT 1
    """, as_dict=True)

    sync_history = frappe.db.sql("""
        SELECT status, transactions_fetched
        FROM `tabHibiscus Connect Sync Log`
        WHERE started_at >= %s
    """, (add_days(now, -1),), as_dict=True)

    if last_sync:
        result["sync"]["last_sync_time"] = last_sync[0].started_at
        result["sync"]["last_sync_status"] = last_sync[0].status

    if sync_history:
        total = len(sync_history)
        successful = len([s for s in sync_history if s.status == "Complete"])
        result["sync"]["runs_24h"] = total
        result["sync"]["success_rate_24h"] = round((successful / total * 100), 1) if total > 0 else 0
        result["sync"]["transactions_24h"] = sum(s.transactions_fetched or 0 for s in sync_history)

    # Get Hibiscus server status
    try:
        client = get_hibiscus_rest_client()
        server_health = client.get_server_health()

        result["hibiscus_server"]["online"] = server_health.get("online", False)
        result["hibiscus_server"]["uptime"] = server_health.get("uptime")
        result["hibiscus_server"]["version"] = server_health.get("version")
        result["hibiscus_server"]["pending_jobs"] = server_health.get("pending_jobs_count", 0)
        result["hibiscus_server"]["recent_errors_count"] = len(server_health.get("recent_errors", []))

        scheduler_info = server_health.get("scheduler", {})
        result["hibiscus_server"]["scheduler_running"] = scheduler_info.get("started", False)

    except HibiscusRestError as e:
        result["hibiscus_server"]["error"] = str(e)
    except Exception as e:
        result["hibiscus_server"]["error"] = f"Unexpected error: {str(e)}"

    # Determine overall health status
    issues = []

    if not result["frappe"]["scheduler_enabled"]:
        issues.append("Frappe scheduler disabled")

    if not result["hibiscus_server"]["online"]:
        issues.append("Hibiscus server offline")
    elif not result["hibiscus_server"]["scheduler_running"]:
        issues.append("Hibiscus scheduler stopped")

    if result["hibiscus_server"]["recent_errors_count"] > 5:
        issues.append(f"{result['hibiscus_server']['recent_errors_count']} recent errors on server")

    if result["sync"]["last_sync_status"] == "Failed":
        issues.append("Last sync failed")

    if result["accounts"]["auto_fetch_count"] == 0:
        issues.append("No accounts configured")

    # Set overall status
    if not result["frappe"]["scheduler_enabled"] or not result["hibiscus_server"]["online"]:
        result["overall_status"] = "critical"
    elif issues:
        result["overall_status"] = "warning"

    if issues:
        result["overall_message"] = "; ".join(issues)

    return result

# ============================================================================
# Compusoft Matching API
# ============================================================================

import re
from datetime import datetime, timedelta

@frappe.whitelist()
def match_hibiscus_transaction(transaction_id):
    """
    Matche eine einzelne Hibiscus-Transaktion mit Compusoft PAYINFO
    
    Args:
        transaction_id: Name des Hibiscus Connect Transaction DocTypes
        
    Returns:
        dict mit Match-Ergebnis
    """
    from ssc_camp_management.tools import get_cursor, get_all_from_query
    
    try:
        # Lade Transaction
        tx = frappe.get_doc("Hibiscus Connect Transaction", transaction_id)
        
        # Parse Purpose
        pattern = r'(\d{7})-([A-Z]{4})-(\d{6,7})'
        match = re.search(pattern, tx.purpose or '')
        
        if not match:
            # Kein strukturiertes Format
            tx.compusoft_match_status = "No Match"
            tx.compusoft_match_data = {
                "error": "Kein strukturiertes Format im Purpose-Feld gefunden",
                "timestamp": datetime.now().isoformat()
            }
            tx.compusoft_last_matched = datetime.now()
            tx.save()
            return {"status": "error", "message": "Kein strukturiertes Format"}
        
        kunde_lbnr = int(match.group(1))
        code = match.group(2)
        booking_nr = int(match.group(3))
        
        # Speichere geparste Daten
        tx.compusoft_kunde_lbnr = kunde_lbnr
        tx.compusoft_booking_nr = booking_nr
        
        # Suche PAYINFO
        cur = get_cursor()
        
        payinfo_query = f'''
        SELECT "ID", "Belob", "PosterID", "TimeStamp", "VareNr", "Ordre", "TransID"
        FROM "PAYINFO"
        WHERE "KundLbnr" = {kunde_lbnr}
          AND "BookingNr" = {booking_nr}
        ORDER BY "TimeStamp" DESC
        '''
        
        payinfo_entries = get_all_from_query(payinfo_query, cur)
        
        # Hole Kundeninformationen
        kunde_query = f'''
        SELECT "KundLbNr", "Fornavn", "Efternavn", "Email1", "Tlf", "Nation"
        FROM "CAMPKUND"
        WHERE "KundLbNr" = {kunde_lbnr}
        '''
        
        kunde_info = get_all_from_query(kunde_query, cur)
        
        # Hole Reservierungsinformationen
        reser_query = f'''
        SELECT "BookingNr", "Fra", "Til", "Nr" as PladsNr, "Status"
        FROM "RESER"
        WHERE "BookingNr" = {booking_nr}
        '''
        
        reser_info = get_all_from_query(reser_query, cur)
        
        # Hole Rechnungspositionen
        poster_query = f'''
        SELECT "Id", "Nr" as VareNr, "Beskr", "Antal", "Pris", "UdlignerID"
        FROM "POSTER"
        WHERE "KeyType" = 'R' AND "KeyVal" = {booking_nr}
        ORDER BY "OprettetDen"
        '''
        
        poster_positionen = get_all_from_query(poster_query, cur)
        
        cur.close()
        
        # Berechne Beträge
        compusoft_total = sum(p.get('Belob', 0) or 0 for p in payinfo_entries) if payinfo_entries else 0
        hibiscus_amount = tx.amount
        difference = abs(hibiscus_amount - compusoft_total)
        
        # Bestimme Status und Qualität
        is_anzahlung = False
        
        if not payinfo_entries:
            # NEUE LOGIK: Prüfe ob Kunde + Reservierung existieren
            if kunde_info and reser_info:
                status = "Pending - Awaiting PAYINFO"
                quality_score = 0
            else:
                status = "No Match"
                quality_score = 0
        elif difference < 0.01:
            status = "Matched (Perfect)"
            quality_score = 100
        elif difference < 1.0:
            status = "Matched (Perfect)"
            quality_score = 95
        else:
            # Prüfe auf Anzahlung (typisch 20-30% des Gesamtbetrags)
            if compusoft_total > 0 and hibiscus_amount > 0:
                percentage = (compusoft_total / hibiscus_amount) * 100
                
                if 15 <= percentage <= 35:
                    status = "Matched (Partial)"
                    quality_score = 60
                    is_anzahlung = True
                else:
                    status = "Matched (Mismatch)"
                    quality_score = 40
            else:
                status = "Matched (Mismatch)"
                quality_score = 30
        
        # Baue JSON-Daten
        def excel_to_datetime(excel_date):
            if not excel_date:
                return None
            try:
                base_date = datetime(1899, 12, 30)
                return (base_date + timedelta(days=excel_date)).strftime('%Y-%m-%d %H:%M:%S')
            except:
                return None
        
        match_data = {
            "parsed_data": {
                "kunde_lbnr": kunde_lbnr,
                "booking_nr": booking_nr,
                "code": code,
                "raw_purpose": tx.purpose
            },
            "payinfo_entries": [
                {
                    "id": p.get('ID'),
                    "belob": p.get('Belob'),
                    "poster_id": p.get('PosterID'),
                    "timestamp": p.get('TimeStamp'),
                    "timestamp_formatted": excel_to_datetime(p.get('TimeStamp')),
                    "vare_nr": p.get('VareNr'),
                    "ordre": p.get('Ordre'),
                    "trans_id": p.get('TransID')
                }
                for p in payinfo_entries
            ] if payinfo_entries else [],
            "kunde_info": {
                "lbnr": kunde_info[0].get('KundLbNr'),
                "fornavn": kunde_info[0].get('Fornavn'),
                "efternavn": kunde_info[0].get('Efternavn'),
                "email": kunde_info[0].get('Email1'),
                "tlf": kunde_info[0].get('Tlf'),
                "nation": kunde_info[0].get('Nation')
            } if kunde_info else None,
            "reservierung_info": {
                "booking_nr": reser_info[0].get('BookingNr'),
                "fra": reser_info[0].get('Fra'),
                "til": reser_info[0].get('Til'),
                "fra_formatted": excel_to_datetime(reser_info[0].get('Fra')),
                "til_formatted": excel_to_datetime(reser_info[0].get('Til')),
                "plads_nr": reser_info[0].get('PladsNr'),
                "status": reser_info[0].get('Status')
            } if reser_info else None,
            "poster_positionen": [
                {
                    "id": p.get('Id'),
                    "vare_nr": p.get('VareNr'),
                    "beschr": p.get('Beskr'),
                    "antal": p.get('Antal'),
                    "pris": p.get('Pris'),
                    "gesamt": (p.get('Antal', 0) or 0) * (p.get('Pris', 0) or 0),
                    "udligner_id": p.get('UdlignerID')
                }
                for p in poster_positionen
            ] if poster_positionen else [],
            "amounts": {
                "hibiscus": hibiscus_amount,
                "compusoft_total": compusoft_total,
                "difference": difference,
                "percentage_match": (min(hibiscus_amount, compusoft_total) / max(hibiscus_amount, compusoft_total) * 100) if max(hibiscus_amount, compusoft_total) > 0 else 0
            },
            "match_result": {
                "status": status,
                "quality_score": quality_score / 100,
                "is_anzahlung": is_anzahlung,
                "anzahlung_percentage": (compusoft_total / hibiscus_amount * 100) if hibiscus_amount > 0 and compusoft_total > 0 else 0,
                "notes": f"Anzahlung erkannt - ca. {int((compusoft_total / hibiscus_amount * 100))}% des Gesamtbetrags" if is_anzahlung else ""
            },
            "timestamp": datetime.now().isoformat(),
            "version": "1.0"
        }
        
        # Speichere Ergebnis
        tx.compusoft_match_status = status
        tx.compusoft_match_data = match_data
        tx.compusoft_match_score = quality_score
        tx.compusoft_total_amount = compusoft_total
        tx.compusoft_last_matched = datetime.now()
        tx.save()
        
        return {
            "status": "success",
            "transaction_id": transaction_id,
            "match_status": status,
            "quality_score": quality_score,
            "match_data": match_data
        }
        
    except Exception as e:
        frappe.log_error(f"Matching error for {transaction_id}: {str(e)}", "Hibiscus Matching Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def bulk_match_transactions(filters=None, limit=100):
    """
    Matche mehrere Transaktionen auf einmal
    
    Args:
        filters: Optional - Filter für Transaktionen (JSON string)
        limit: Maximale Anzahl zu matchender Transaktionen
        
    Returns:
        dict mit Statistiken
    """
    import json
    
    # Parse filters wenn als String übergeben
    if filters and isinstance(filters, str):
        filters = json.loads(filters)
    
    # Default-Filter: Nur positive Beträge, älter als 24h, Status = Pending
    if not filters:
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        filters = [
            ["amount", ">", 0],
            ["transaction_date", "<=", yesterday],
            ["compusoft_match_status", "in", ["Pending", ""]]
        ]
    
    transactions = frappe.get_all(
        "Hibiscus Connect Transaction",
        fields=["name"],
        filters=filters,
        limit=limit
    )
    
    results = {
        "total": len(transactions),
        "matched_perfect": 0,
        "matched_partial": 0,
        "matched_mismatch": 0,
        "no_match": 0,
        "errors": 0
    }
    
    for tx in transactions:
        try:
            result = match_hibiscus_transaction(tx.name)
            
            if result["status"] == "success":
                status = result["match_status"]
                
                if status == "Matched (Perfect)":
                    results["matched_perfect"] += 1
                elif status == "Matched (Partial)":
                    results["matched_partial"] += 1
                elif status == "Matched (Mismatch)":
                    results["matched_mismatch"] += 1
                elif status == "No Match":
                    results["no_match"] += 1
            else:
                # Kein strukturiertes Format - als No Match behandeln statt Error
                results["no_match"] += 1
                
        except Exception as e:
            frappe.log_error(f"Bulk matching error for {tx.name}: {str(e)}")
            results["errors"] += 1
    
    return results


@frappe.whitelist()
def rematch_transaction(transaction_id):
    """
    Force Re-Match einer Transaktion
    
    Args:
        transaction_id: Name des Hibiscus Connect Transaction DocTypes
        
    Returns:
        dict mit Match-Ergebnis
    """
    return match_hibiscus_transaction(transaction_id)


@frappe.whitelist()
def test_matching_analysis():
    """Analysiere ältere Transaktionen für Testing"""
    import re
    from datetime import datetime, timedelta
    
    # Suche parsbare Transaktionen
    drei_tage_alt = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    dreissig_tage_alt = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    transactions = frappe.get_all(
        "Hibiscus Connect Transaction",
        fields=["name", "transaction_date", "amount", "purpose"],
        filters=[
            ["amount", ">", 0],
            ["transaction_date", ">=", dreissig_tage_alt],
            ["transaction_date", "<=", drei_tage_alt]
        ],
        order_by="transaction_date desc",
        limit=20
    )
    
    pattern = r'(\d{7})-([A-Z]{4})-(\d{6,7})'
    parseable = [tx for tx in transactions if re.search(pattern, tx.purpose or '')]
    
    results = {"perfect": [], "partial": [], "mismatch": [], "no_match": [], "details": []}
    
    for tx in parseable[:12]:
        result = match_hibiscus_transaction(tx.name)
        
        if result.get("status") == "success":
            status = result.get("match_status")
            match_data = result.get("match_data", {})
            
            detail = {
                "transaction_id": tx.name,
                "date": str(tx.transaction_date),
                "amount": tx.amount,
                "status": status,
                "quality_score": result.get("quality_score"),
                "kunde": None,
                "compusoft_total": None,
                "difference": None,
                "is_anzahlung": False
            }
            
            if match_data.get("kunde_info"):
                k = match_data["kunde_info"]
                detail["kunde"] = f"{k.get('fornavn', '')} {k.get('efternavn', '')}"
            
            if match_data.get("amounts"):
                a = match_data["amounts"]
                detail["compusoft_total"] = a.get("compusoft_total")
                detail["difference"] = a.get("difference")
            
            if match_data.get("match_result"):
                detail["is_anzahlung"] = match_data["match_result"].get("is_anzahlung", False)
                detail["anzahlung_pct"] = match_data["match_result"].get("anzahlung_percentage", 0)
            
            results["details"].append(detail)
            
            if status == "Matched (Perfect)":
                results["perfect"].append(detail)
            elif status == "Matched (Partial)":
                results["partial"].append(detail)
            elif status == "Matched (Mismatch)":
                results["mismatch"].append(detail)
            elif status == "No Match":
                results["no_match"].append(detail)
    
    frappe.db.commit()
    
    return {
        "summary": {
            "total": len(parseable[:12]),
            "perfect": len(results["perfect"]),
            "partial": len(results["partial"]),
            "mismatch": len(results["mismatch"]),
            "no_match": len(results["no_match"])
        },
        "details": results["details"]
    }


@frappe.whitelist()
def rematch_pending_transactions():
    """
    Re-Matching für alle 'Pending - Awaiting PAYINFO' Transaktionen
    die älter als 3 Tage sind
    
    Wird täglich durch Scheduled Job ausgeführt
    """
    from datetime import datetime, timedelta
    
    # Finde alle Pending Transaktionen älter als 3 Tage
    drei_tage_alt = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    
    transactions = frappe.get_all(
        "Hibiscus Connect Transaction",
        fields=["name", "transaction_date", "compusoft_kunde_lbnr", "compusoft_booking_nr"],
        filters=[
            ["compusoft_match_status", "=", "Pending - Awaiting PAYINFO"],
            ["transaction_date", "<=", drei_tage_alt]
        ],
        limit=100
    )
    
    results = {
        "total": len(transactions),
        "rematched": 0,
        "now_matched": 0,
        "still_pending": 0,
        "errors": 0
    }
    
    for tx in transactions:
        try:
            result = match_hibiscus_transaction(tx.name)
            results["rematched"] += 1
            
            if result.get("status") == "success":
                new_status = result.get("match_status")
                
                if new_status in ["Matched (Perfect)", "Matched (Partial)", "Matched (Mismatch)"]:
                    results["now_matched"] += 1
                elif new_status == "Pending - Awaiting PAYINFO":
                    results["still_pending"] += 1
        except Exception as e:
            frappe.log_error(f"Re-matching error for {tx.name}: {str(e)}", "Rematch Job Error")
            results["errors"] += 1
    
    frappe.db.commit()
    
    # Log Ergebnis
    frappe.log_error(
        f"Re-Matching Job completed: {results}",
        "Rematch Job Summary"
    )
    
    return results


# ============================================================================
# Matching Dashboard API
# ============================================================================


# ============================================================================
# Matching Dashboard API
# ============================================================================

@frappe.whitelist()
def get_matching_statistics():
    """
    Liefert Statistiken über alle Matching-Ergebnisse

    Returns:
        dict mit Status-Verteilung, Trends, etc.
    """
    from datetime import datetime, timedelta

    # Status-Verteilung
    status_distribution = frappe.db.sql('''
        SELECT
            compusoft_match_status,
            COUNT(*) as count,
            SUM(amount) as total_amount
        FROM `tabHibiscus Connect Transaction`
        WHERE amount > 0
        GROUP BY compusoft_match_status
        ORDER BY count DESC
    ''', as_dict=True)

    # Gesamt-Statistik
    total_transactions = frappe.db.count(
        "Hibiscus Connect Transaction",
        filters={"amount": [">", 0]}
    )

    # Matched Transaktionen (Perfect + Partial)
    matched_count = frappe.db.count(
        "Hibiscus Connect Transaction",
        filters={
            "amount": [">", 0],
            "compusoft_match_status": ["in", ["Matched (Perfect)", "Matched (Partial)"]]
        }
    )

    # Pending - Awaiting PAYINFO
    pending_payinfo_count = frappe.db.count(
        "Hibiscus Connect Transaction",
        filters={
            "amount": [">", 0],
            "compusoft_match_status": "Pending - Awaiting PAYINFO"
        }
    )

    # No Match
    no_match_count = frappe.db.count(
        "Hibiscus Connect Transaction",
        filters={
            "amount": [">", 0],
            "compusoft_match_status": "No Match"
        }
    )

    # Durchschnittliche Match Quality
    avg_quality = frappe.db.sql('''
        SELECT AVG(compusoft_match_score) as avg_quality
        FROM `tabHibiscus Connect Transaction`
        WHERE amount > 0
          AND compusoft_match_status IN ('Matched (Perfect)', 'Matched (Partial)', 'Matched (Mismatch)')
          AND compusoft_match_score IS NOT NULL
    ''', as_dict=True)

    # Match-Rate berechnen
    match_rate = (matched_count / total_transactions * 100) if total_transactions > 0 else 0

    # Trend der letzten 7 Tage
    sieben_tage_alt = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    recent_matches = frappe.db.sql('''
        SELECT
            DATE(compusoft_last_matched) as date,
            COUNT(*) as count
        FROM `tabHibiscus Connect Transaction`
        WHERE amount > 0
          AND compusoft_last_matched >= %s
          AND compusoft_match_status IN ('Matched (Perfect)', 'Matched (Partial)', 'Matched (Mismatch)')
        GROUP BY DATE(compusoft_last_matched)
        ORDER BY date DESC
    ''', (sieben_tage_alt,), as_dict=True)

    return {
        "status_distribution": status_distribution,
        "total_transactions": total_transactions,
        "matched_count": matched_count,
        "pending_payinfo_count": pending_payinfo_count,
        "no_match_count": no_match_count,
        "match_rate": round(match_rate, 2),
        "avg_quality": round((avg_quality[0].avg_quality or 0), 2) if avg_quality else 0,
        "recent_trend": recent_matches
    }


@frappe.whitelist()
def get_recent_matches(limit=20):
    """
    Liefert die letzten Matching-Ergebnisse

    Args:
        limit: Anzahl der Ergebnisse

    Returns:
        list von Transaktionen mit Match-Daten
    """
    transactions = frappe.get_all(
        "Hibiscus Connect Transaction",
        fields=[
            "name",
            "transaction_date",
            "amount",
            "counterparty_name",
            "purpose",
            "compusoft_match_status",
            "compusoft_match_score",
            "compusoft_total_amount",
            "compusoft_kunde_lbnr",
            "compusoft_booking_nr",
            "compusoft_last_matched"
        ],
        filters=[
            ["amount", ">", 0],
            ["compusoft_last_matched", "is", "set"],
            ["compusoft_match_status", "in", ["Matched (Perfect)", "Matched (Partial)", "Matched (Mismatch)"]]
        ],
        order_by="compusoft_last_matched desc",
        limit=limit
    )

    # Lade zusätzliche Details für jeden Match
    for tx in transactions:
        if tx.compusoft_kunde_lbnr:
            # Hole Kunde-Daten aus match_data
            tx_doc = frappe.get_doc("Hibiscus Connect Transaction", tx.name)

            if tx_doc.compusoft_match_data and isinstance(tx_doc.compusoft_match_data, dict):
                match_data = tx_doc.compusoft_match_data

                # Kunde-Info
                if match_data.get("kunde_info"):
                    kunde = match_data["kunde_info"]
                    tx["kunde_name"] = f"{kunde.get('fornavn', '')} {kunde.get('efternavn', '')}".strip()
                    tx["kunde_email"] = kunde.get("email")

                # Anzahlung-Info
                if match_data.get("match_result"):
                    match_result = match_data["match_result"]
                    tx["is_anzahlung"] = match_result.get("is_anzahlung", False)
                    tx["anzahlung_percentage"] = match_result.get("anzahlung_percentage", 0)

    return transactions


@frappe.whitelist()
def get_pending_payinfo_list(limit=50):
    """
    Liefert Liste aller Transaktionen mit Status "Pending - Awaiting PAYINFO"

    Args:
        limit: Anzahl der Ergebnisse

    Returns:
        list von Transaktionen
    """
    from datetime import datetime, timedelta

    transactions = frappe.get_all(
        "Hibiscus Connect Transaction",
        fields=[
            "name",
            "transaction_date",
            "amount",
            "counterparty_name",
            "purpose",
            "compusoft_kunde_lbnr",
            "compusoft_booking_nr",
            "compusoft_last_matched"
        ],
        filters=[
            ["amount", ">", 0],
            ["compusoft_match_status", "=", "Pending - Awaiting PAYINFO"]
        ],
        order_by="transaction_date desc",
        limit=limit
    )

    # Berechne Wartezeit
    now = datetime.now()

    for tx in transactions:
        if tx.transaction_date:
            tx_date = datetime.combine(tx.transaction_date, datetime.min.time())
            waiting_days = (now - tx_date).days
            tx["waiting_days"] = waiting_days
            tx["can_rematch"] = waiting_days >= 3

        # Hole Kunde-Name
        if tx.compusoft_kunde_lbnr:
            tx_doc = frappe.get_doc("Hibiscus Connect Transaction", tx.name)

            if tx_doc.compusoft_match_data and isinstance(tx_doc.compusoft_match_data, dict):
                match_data = tx_doc.compusoft_match_data

                if match_data.get("kunde_info"):
                    kunde = match_data["kunde_info"]
                    tx["kunde_name"] = f"{kunde.get('fornavn', '')} {kunde.get('efternavn', '')}".strip()

    return transactions


# ============================================================================
# Background Job für Bulk-Matching
# ============================================================================

@frappe.whitelist()
def start_bulk_matching_job(limit=1000):
    """
    Startet Bulk-Matching als Background Job

    Args:
        limit: Maximale Anzahl zu matchender Transaktionen

    Returns:
        dict mit Job-ID und Status
    """
    import json

    # Prüfe ob bereits ein Job läuft
    running_job = get_matching_job_status()

    if running_job.get("is_running"):
        return {
            "status": "error",
            "message": "Es läuft bereits ein Matching-Job",
            "job_status": running_job
        }

    # Starte neuen Background Job
    job = frappe.enqueue(
        method="hibiscus_connect.api.bulk_match_transactions_job",
        queue="long",
        timeout=3600,  # 1 Stunde
        is_async=True,
        job_name=f"bulk_matching_{frappe.session.user}",
        limit=int(limit),
        user=frappe.session.user,
        now=False
    )

    # Speichere Job-Info in Cache
    frappe.cache().set_value(
        "matching_job_info",
        json.dumps({
            "job_id": job.id if hasattr(job, 'id') else str(job),
            "started_by": frappe.session.user,
            "started_at": frappe.utils.now(),
            "limit": int(limit),
            "status": "queued"
        }),
        expires_in_sec=7200  # 2 Stunden
    )

    return {
        "status": "success",
        "message": "Matching-Job wurde gestartet",
        "job_id": job.id if hasattr(job, 'id') else str(job)
    }


@frappe.whitelist()
def bulk_match_transactions_job(limit=1000, user=None):
    """
    Die eigentliche Matching-Funktion für Background Job

    Args:
        limit: Maximale Anzahl zu matchender Transaktionen
        user: User der den Job gestartet hat
    """
    import json
    from datetime import datetime, timedelta

    # Update Job-Info: Running
    job_info = {
        "status": "running",
        "started_at": frappe.utils.now(),
        "limit": int(limit),
        "started_by": user or frappe.session.user,
        "progress": 0,
        "matched_count": 0,
        "error_count": 0
    }

    frappe.cache().set_value(
        "matching_job_info",
        json.dumps(job_info),
        expires_in_sec=7200
    )

    try:
        # Filter für Transaktionen
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        filters = [
            ["amount", ">", 0],
            ["transaction_date", "<=", yesterday],
            ["compusoft_match_status", "in", ["Pending", ""]]
        ]

        transactions = frappe.get_all(
            "Hibiscus Connect Transaction",
            fields=["name"],
            filters=filters,
            limit=int(limit)
        )

        total = len(transactions)
        job_info["total"] = total

        results = {
            "total": total,
            "matched_perfect": 0,
            "matched_partial": 0,
            "matched_mismatch": 0,
            "pending_payinfo": 0,
            "no_match": 0,
            "errors": 0
        }

        for i, tx in enumerate(transactions, 1):
            try:
                result = match_hibiscus_transaction(tx.name)

                if result["status"] == "success":
                    status = result["match_status"]

                    if status == "Matched (Perfect)":
                        results["matched_perfect"] += 1
                    elif status == "Matched (Partial)":
                        results["matched_partial"] += 1
                    elif status == "Matched (Mismatch)":
                        results["matched_mismatch"] += 1
                    elif status == "Pending - Awaiting PAYINFO":
                        results["pending_payinfo"] += 1
                    elif status == "No Match":
                        results["no_match"] += 1
                else:
                    # Kein strukturiertes Format - als No Match behandeln statt Error
                    results["no_match"] += 1

            except Exception as e:
                frappe.log_error(f"Bulk matching error for {tx.name}: {str(e)}")
                results["errors"] += 1

            # Update Progress alle 10 Transaktionen
            if i % 10 == 0 or i == total:
                progress = int((i / total) * 100)
                job_info["progress"] = progress
                job_info["processed"] = i
                job_info["matched_count"] = results["matched_perfect"] + results["matched_partial"]
                job_info["error_count"] = results["errors"]
                job_info["status"] = "running"

                frappe.cache().set_value(
                    "matching_job_info",
                    json.dumps(job_info),
                    expires_in_sec=7200
                )

                # Commit alle 50 Transaktionen
                if i % 50 == 0:
                    frappe.db.commit()

        # Final Commit
        frappe.db.commit()

        # Update Job-Info: Completed
        job_info["status"] = "completed"
        job_info["completed_at"] = frappe.utils.now()
        job_info["progress"] = 100
        job_info["results"] = results

        frappe.cache().set_value(
            "matching_job_info",
            json.dumps(job_info),
            expires_in_sec=7200
        )

        # Log Erfolg (gekürzt um Truncation zu vermeiden)
        frappe.log_error(
            f"Bulk Match: {results['total']} tx, {results['matched_perfect'] + results['matched_partial']} matched",
            "Bulk Matching Success"
        )

        return results

    except Exception as e:
        # Update Job-Info: Failed
        job_info["status"] = "failed"
        job_info["error"] = str(e)
        job_info["failed_at"] = frappe.utils.now()

        frappe.cache().set_value(
            "matching_job_info",
            json.dumps(job_info),
            expires_in_sec=7200
        )

        frappe.log_error(f"Bulk Matching failed", "Bulk Matching Error")
        raise


@frappe.whitelist()
def get_matching_job_status():
    """
    Liefert den Status des aktuellen Matching-Jobs

    Returns:
        dict mit Job-Status und Progress
    """
    import json

    # Hole Job-Info aus Cache
    job_info_str = frappe.cache().get_value("matching_job_info")

    if not job_info_str:
        return {
            "is_running": False,
            "status": "none",
            "message": "Kein Job läuft aktuell"
        }

    try:
        job_info = json.loads(job_info_str)

        status = job_info.get("status", "unknown")
        is_running = status in ["queued", "running"]

        return {
            "is_running": is_running,
            "status": status,
            "progress": job_info.get("progress", 0),
            "total": job_info.get("total", 0),
            "processed": job_info.get("processed", 0),
            "matched_count": job_info.get("matched_count", 0),
            "error_count": job_info.get("error_count", 0),
            "started_by": job_info.get("started_by"),
            "started_at": job_info.get("started_at"),
            "completed_at": job_info.get("completed_at"),
            "failed_at": job_info.get("failed_at"),
            "error": job_info.get("error"),
            "results": job_info.get("results")
        }

    except json.JSONDecodeError:
        return {
            "is_running": False,
            "status": "error",
            "message": "Fehler beim Lesen des Job-Status"
        }


@frappe.whitelist()
def clear_matching_job_status():
    """
    Löscht den Job-Status aus dem Cache

    Returns:
        dict mit Erfolgsmeldung
    """
    frappe.cache().delete_value("matching_job_info")

    return {
        "status": "success",
        "message": "Job-Status wurde gelöscht"
    }
