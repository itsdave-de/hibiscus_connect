import frappe
from frappe.utils import now_datetime
from datetime import date, timedelta
from hibiscus_connect.tools import get_transactions_for_account
import json

# Default: fetch last 30 days for scheduled task
DEFAULT_DAYS_BACK = 30
# For manual "fetch all": go back far enough to get everything
FETCH_ALL_START_DATE = "2000-01-01"


def fetch_transactions_from_active_accounts():
    """Scheduled task to fetch transactions from accounts with auto_fetch enabled (last 30 days)."""
    result = _fetch_from_auto_fetch_accounts(days_back=DEFAULT_DAYS_BACK, trigger_type="Scheduled")
    if result["accounts_processed"] == 0:
        print("No accounts configured for auto-fetch")
    else:
        print(f"Fetched transactions from {result['accounts_processed']} account(s)")


@frappe.whitelist()
def fetch_transactions_now(fetch_all=True):
    """Manual trigger to fetch transactions from all auto_fetch accounts.

    Args:
        fetch_all: If True, fetches all available transactions. If False, only last 30 days.
    """
    if fetch_all:
        result = _fetch_from_auto_fetch_accounts(from_date=FETCH_ALL_START_DATE, trigger_type="Manual")
    else:
        result = _fetch_from_auto_fetch_accounts(days_back=DEFAULT_DAYS_BACK, trigger_type="Manual")
    return result


def _create_sync_log(trigger_type="Manual"):
    """Create a new sync log entry and return it."""
    sync_log = frappe.get_doc({
        "doctype": "Hibiscus Connect Sync Log",
        "status": "Running",
        "trigger_type": trigger_type,
        "started_at": now_datetime(),
        "accounts_processed": 0,
        "transactions_fetched": 0,
        "errors_count": 0
    })
    sync_log.insert(ignore_permissions=True)
    frappe.db.commit()
    return sync_log


def _update_sync_log(sync_log, result, error_log=None):
    """Update sync log with final results."""
    sync_log.reload()
    sync_log.completed_at = now_datetime()
    sync_log.accounts_processed = result.get("accounts_processed", 0)
    sync_log.transactions_fetched = result.get("transactions_fetched", 0)
    sync_log.errors_count = len(result.get("errors", []))
    sync_log.details = json.dumps(result, default=str, indent=2)

    if result.get("errors"):
        sync_log.status = "Failed" if sync_log.accounts_processed == 0 else "Complete"
        sync_log.error_log = "\n".join([
            f"{e.get('name', 'Unknown')}: {e.get('error', 'Unknown error')}"
            for e in result.get("errors", [])
        ])
    else:
        sync_log.status = "Complete"

    if error_log:
        sync_log.status = "Failed"
        sync_log.error_log = error_log

    sync_log.save(ignore_permissions=True)
    frappe.db.commit()


def _fetch_from_auto_fetch_accounts(days_back=None, from_date=None, trigger_type="Manual"):
    """Internal function to fetch transactions from all accounts with auto_fetch=1.

    Args:
        days_back: Number of days back from today to fetch (e.g., 30)
        from_date: Specific start date as string "YYYY-MM-DD" (overrides days_back)
        trigger_type: "Scheduled" or "Manual"
    """
    # Create sync log entry
    sync_log = _create_sync_log(trigger_type)

    try:
        accounts = frappe.get_all("Hibiscus Connect Bank Account",
            filters={"auto_fetch": 1},
            fields=["name", "description", "iban"]
        )

        # Determine date range
        bis = str(date.today())
        if from_date:
            von = from_date
        elif days_back:
            von = str(date.today() - timedelta(days=days_back))
        else:
            von = str(date.today() - timedelta(days=DEFAULT_DAYS_BACK))

        result = {
            "accounts_processed": 0,
            "transactions_fetched": 0,
            "accounts": [],
            "errors": [],
            "date_range": {"from": von, "to": bis}
        }

        for account in accounts:
            # Count transactions before fetch
            trans_before = frappe.db.count("Hibiscus Connect Transaction", {"bank_account": account["name"]})

            try:
                get_transactions_for_account(account["name"], von=von, bis=bis)

                # Count transactions after fetch
                trans_after = frappe.db.count("Hibiscus Connect Transaction", {"bank_account": account["name"]})
                new_trans = trans_after - trans_before

                result["accounts_processed"] += 1
                result["transactions_fetched"] += new_trans
                result["accounts"].append({
                    "name": account["name"],
                    "description": account.get("description") or account["iban"],
                    "status": "success",
                    "transactions_fetched": new_trans
                })
            except Exception as e:
                result["errors"].append({
                    "name": account["name"],
                    "description": account.get("description") or account["iban"],
                    "error": str(e)
                })

        # Update sync log with results
        _update_sync_log(sync_log, result)
        return result

    except Exception as e:
        # Log unexpected errors
        _update_sync_log(sync_log, {"accounts_processed": 0, "errors": []}, error_log=str(e))
        raise
