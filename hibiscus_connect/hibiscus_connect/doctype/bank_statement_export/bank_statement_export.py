# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, getdate
from frappe.utils.file_manager import save_file
import os


class BankStatementExport(Document):
    def before_save(self):
        """Calculate balances and transaction count before saving."""
        # Check protection permission if document is protected
        # Skip check if generating export (only status/error_log change)
        if self.is_protected and not self.is_new() and not self.flags.get('generating_export'):
            self._check_protected_edit_permission()

        if self.bank_account and self.from_date and self.to_date:
            self.calculate_balances()
            self.calculate_transaction_count()

    def before_delete(self):
        """Check permission before deleting protected exports."""
        if self.is_protected:
            self._check_protected_edit_permission()

    def _check_protected_edit_permission(self):
        """Check if current user has permission to edit/delete this protected export."""
        if not has_protected_export_permission():
            frappe.throw(
                _("You do not have permission to modify this protected export. Required role: {0}").format(
                    get_protected_export_role() or _("Not configured")
                ),
                frappe.PermissionError
            )

    def calculate_balances(self):
        """Calculate opening and closing balances from transactions.

        Note: We use customer_ref for ordering within the same date because:
        - customer_ref is a timestamp-based reference from the bank (e.g., 2025120915030704000)
        - The Frappe 'name' field order doesn't match chronological order
        - customer_ref correctly represents the sequence of transactions
        """
        # Opening balance: balance from the last transaction before from_date
        opening = frappe.db.sql("""
            SELECT balance
            FROM `tabHibiscus Connect Transaction`
            WHERE bank_account = %s
              AND COALESCE(value_date, transaction_date) < %s
            ORDER BY COALESCE(value_date, transaction_date) DESC, customer_ref DESC
            LIMIT 1
        """, (self.bank_account, self.from_date), as_dict=True)

        if opening:
            self.opening_balance = opening[0].balance
        else:
            self.opening_balance = 0

        # Closing balance: balance from the last transaction on or before to_date
        closing = frappe.db.sql("""
            SELECT balance
            FROM `tabHibiscus Connect Transaction`
            WHERE bank_account = %s
              AND COALESCE(value_date, transaction_date) <= %s
            ORDER BY COALESCE(value_date, transaction_date) DESC, customer_ref DESC
            LIMIT 1
        """, (self.bank_account, self.to_date), as_dict=True)

        if closing:
            self.closing_balance = closing[0].balance
        else:
            self.closing_balance = self.opening_balance

    def calculate_transaction_count(self):
        """Count transactions in the selected period."""
        count = frappe.db.count("Hibiscus Connect Transaction", {
            "bank_account": self.bank_account,
            "transaction_date": ["between", [self.from_date, self.to_date]]
        })
        self.transaction_count = count

    def get_transactions(self, order_by=None):
        """Fetch transactions for the selected period.

        Args:
            order_by: Optional custom order_by clause. Defaults to chronological ordering.

        Note: We use customer_ref for intra-day ordering because it's a timestamp-based
        reference from the bank that correctly reflects the sequence of transactions.
        The Frappe 'name' field order doesn't match chronological order.
        """
        if order_by is None:
            order_by = "COALESCE(value_date, transaction_date) ASC, customer_ref ASC"

        transactions = frappe.get_all(
            "Hibiscus Connect Transaction",
            filters={
                "bank_account": self.bank_account,
                "transaction_date": ["between", [self.from_date, self.to_date]]
            },
            fields=[
                "name", "transaction_date", "value_date", "amount", "balance",
                "counterparty_name", "counterparty_iban", "counterparty_bic",
                "purpose", "transaction_type", "gvcode", "primanota",
                "customer_ref", "hibiscus_id", "end_to_end_id"
            ],
            order_by=order_by
        )
        return transactions

    @frappe.whitelist()
    def generate_export(self):
        """Generate the export file based on the selected format."""
        try:
            # Validate inputs
            if not self.bank_account:
                frappe.throw("Please select a bank account")
            if not self.from_date or not self.to_date:
                frappe.throw("Please specify the date range")

            # Re-calculate balances to ensure accuracy
            self.calculate_balances()
            self.calculate_transaction_count()

            # Get bank account details
            bank_account = frappe.get_doc("Hibiscus Connect Bank Account", self.bank_account)

            # Generate file content based on format
            if self.export_format == "camt.052":
                # camt.052 (Proficash): sort by customer_ref (AcctSvcrRef)
                transactions = self.get_transactions(order_by="customer_ref ASC")

                if not transactions:
                    frappe.msgprint("No transactions found in the selected period")

                from hibiscus_connect.export_generators.camt052 import generate_camt052
                content = generate_camt052(
                    bank_account=bank_account,
                    transactions=transactions,
                    opening_balance=self.opening_balance or 0,
                    closing_balance=self.closing_balance or 0,
                    from_date=self.from_date,
                    to_date=self.to_date,
                    statement_id=self.name
                )
                file_extension = "xml"
                content_type = "application/xml"
            elif self.export_format == "camt.053":
                # camt.053: sort by date/name
                transactions = self.get_transactions()

                if not transactions:
                    frappe.msgprint("No transactions found in the selected period")

                from hibiscus_connect.export_generators.camt053 import generate_camt053
                content = generate_camt053(
                    bank_account=bank_account,
                    transactions=transactions,
                    opening_balance=self.opening_balance or 0,
                    closing_balance=self.closing_balance or 0,
                    from_date=self.from_date,
                    to_date=self.to_date,
                    statement_id=self.name
                )
                file_extension = "xml"
                content_type = "application/xml"
            elif self.export_format == "MT940":
                # MT940: sort by date/name
                transactions = self.get_transactions()

                if not transactions:
                    frappe.msgprint("No transactions found in the selected period")

                from hibiscus_connect.export_generators.mt940 import generate_mt940
                content = generate_mt940(
                    bank_account=bank_account,
                    transactions=transactions,
                    opening_balance=self.opening_balance or 0,
                    closing_balance=self.closing_balance or 0,
                    from_date=self.from_date,
                    to_date=self.to_date,
                    statement_id=self.name
                )
                file_extension = "sta"
                content_type = "text/plain"
            else:
                frappe.throw(f"Unsupported export format: {self.export_format}")

            # Generate filename: Konto_XXX_YYYY-MM-DD_[A_]BSEXP-NNNNN.ext
            # A_ before docname indicates automatic export (scheduler or dashboard)
            iban_short = (bank_account.iban or "000")[-3:]
            auto_prefix = "A_" if self.flags.get('auto_export') else ""
            filename = f"Konto_{iban_short}_{self.from_date}_{auto_prefix}{self.name}.{file_extension}"

            # Save file to Frappe's file system
            file_doc = self._save_export_file(filename, content, bank_account.iban)

            # Update status
            self.status = "Generated"
            self.error_log = None
            self.flags.generating_export = True
            self.save()

            frappe.msgprint(_("Export file generated successfully: {0}").format(filename))
            return {
                "success": True,
                "file_url": file_doc.file_url,
                "filename": filename
            }

        except Exception as e:
            self.status = "Error"
            self.error_log = str(e)
            self.flags.generating_export = True
            self.save()
            frappe.log_error(f"Bank Statement Export Error for {self.name}: {str(e)}", "Bank Statement Export")
            frappe.throw(f"Export failed: {str(e)}")

    def _save_export_file(self, filename, content, iban=None):
        """Save the export file with folder structure and optionally upload to SMB."""
        # Create folder path: Bank Statement Exports / IBAN / Year
        year = getdate(self.from_date).year
        iban = iban or "Unknown"

        # Ensure the folder exists
        folder_path = f"Home/Bank Statement Exports/{iban}/{year}"
        self._ensure_folder_exists(folder_path)

        # Save the file
        if isinstance(content, str):
            content_bytes = content.encode('utf-8')
        else:
            content_bytes = content

        file_doc = save_file(
            filename,
            content_bytes,
            self.doctype,
            self.name,
            folder=folder_path,
            is_private=1
        )

        # Upload to SMB if enabled
        if self.smb_enabled:
            self._upload_to_smb(filename, content_bytes)

        return file_doc

    def _upload_to_smb(self, filename, content):
        """Upload file to SMB share.

        SMB errors do not block the export - they are logged and shown as warnings.
        If static filename is enabled, uses that instead of the generated filename.
        """
        try:
            from hibiscus_connect.smb_client import upload_to_smb, SMBConnectionError, SMBUploadError

            # Get password (it's stored encrypted in Frappe)
            password = self.get_password('smb_password')

            # Use static filename if enabled, otherwise use the generated filename
            smb_filename = filename
            if self.smb_static_filename_enabled and self.smb_static_filename:
                smb_filename = self.smb_static_filename

            # Perform upload
            remote_path = upload_to_smb(
                content=content,
                filename=smb_filename,
                server=self.smb_server,
                share=self.smb_share,
                path=self.smb_path or "",
                username=self.smb_username,
                password=password,
                domain=self.smb_domain,
                port=self.smb_port or 445
            )

            # Update status
            status_msg = _("Successfully uploaded to {0} at {1}").format(
                remote_path, now_datetime().strftime("%Y-%m-%d %H:%M:%S")
            )
            self.smb_status = status_msg
            frappe.msgprint(
                _("File uploaded to SMB share: {0}").format(remote_path),
                indicator="green",
                alert=True
            )

        except (SMBConnectionError, SMBUploadError) as e:
            error_msg = _("SMB upload failed at {0}: {1}").format(
                now_datetime().strftime("%Y-%m-%d %H:%M:%S"), str(e)
            )
            self.smb_status = error_msg
            frappe.log_error(
                f"SMB Upload Error for {self.name}: {str(e)}",
                "SMB Upload Error"
            )
            frappe.msgprint(
                _("Warning: SMB upload failed. Local file was saved successfully. Error: {0}").format(str(e)),
                indicator="orange",
                alert=True
            )

        except Exception as e:
            error_msg = _("SMB upload error at {0}: {1}").format(
                now_datetime().strftime("%Y-%m-%d %H:%M:%S"), str(e)
            )
            self.smb_status = error_msg
            frappe.log_error(
                f"SMB Upload Error for {self.name}: {str(e)}",
                "SMB Upload Error"
            )
            frappe.msgprint(
                _("Warning: SMB upload failed. Local file was saved successfully. Error: {0}").format(str(e)),
                indicator="orange",
                alert=True
            )

    @frappe.whitelist()
    def test_smb_connection(self):
        """Test the SMB connection with the configured settings."""
        if not self.smb_enabled:
            return {
                "success": False,
                "message": _("SMB upload is not enabled for this export.")
            }

        if not self.smb_server or not self.smb_share or not self.smb_username:
            return {
                "success": False,
                "message": _("Please fill in all required SMB settings (Server, Share, Username, Password).")
            }

        try:
            from hibiscus_connect.smb_client import test_smb_connection as smb_test

            # Get password
            password = self.get_password('smb_password')
            if not password:
                return {
                    "success": False,
                    "message": _("SMB password is not set.")
                }

            result = smb_test(
                server=self.smb_server,
                share=self.smb_share,
                username=self.smb_username,
                password=password,
                domain=self.smb_domain,
                port=self.smb_port or 445
            )

            # Update status field with test result
            if result.get("success"):
                self.smb_status = _("Connection test successful at {0}").format(
                    now_datetime().strftime("%Y-%m-%d %H:%M:%S")
                )
            else:
                self.smb_status = _("Connection test failed at {0}: {1}").format(
                    now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
                    result.get("message", _("Unknown error"))
                )

            self.flags.generating_export = True  # Skip protection check
            self.save()

            return result

        except Exception as e:
            return {
                "success": False,
                "message": _("Error testing connection: {0}").format(str(e))
            }

    def _ensure_folder_exists(self, folder_path):
        """Ensure the folder structure exists in Frappe's file system."""
        parts = folder_path.split("/")
        current_path = ""

        for part in parts:
            if current_path:
                current_path = f"{current_path}/{part}"
            else:
                current_path = part

            if not frappe.db.exists("File", {"file_name": part, "is_folder": 1, "folder": current_path.rsplit("/", 1)[0] if "/" in current_path else "Home"}):
                try:
                    folder = frappe.get_doc({
                        "doctype": "File",
                        "file_name": part,
                        "is_folder": 1,
                        "folder": current_path.rsplit("/", 1)[0] if "/" in current_path else "Home"
                    })
                    folder.insert(ignore_permissions=True)
                except frappe.DuplicateEntryError:
                    pass

@frappe.whitelist()
def get_export_files(docname):
    """Get list of generated files for a Bank Statement Export.

    Files are identified by their naming pattern: Konto_{iban_last3}_{from_date}_[A_]{docname}.{ext}
    A_ prefix indicates automatic export (scheduler or dashboard).
    Returns all files (manual and automatic), 30 most recent, newest first.
    """
    files = frappe.get_all(
        "File",
        filters=[
            ["file_name", "like", f"%{docname}%"],
            ["is_folder", "=", 0]
        ],
        fields=["file_name", "file_url", "creation", "file_size"],
        order_by="creation DESC",
        limit=30
    )
    return files


@frappe.whitelist()
def get_dashboard_exports():
    """Get all Bank Statement Exports marked for dashboard display.

    Only returns exports for bank accounts the current user has permission to access.
    Includes recent files for each export based on dashboard_file_count setting.
    """
    user = frappe.session.user

    # Get all exports marked for dashboard
    exports = frappe.get_all(
        "Bank Statement Export",
        filters={"show_on_dashboard": 1},
        fields=[
            "name", "description", "bank_account", "date_preset",
            "from_date", "to_date", "export_format", "status",
            "account_description", "account_type",
            "dashboard_file_count"
        ],
        order_by="creation DESC"
    )

    # Get accent colors for all bank accounts
    account_colors = {}
    bank_accounts = frappe.get_all(
        "Hibiscus Connect Bank Account",
        fields=["name", "accent_color_1", "accent_color_2", "text_color"]
    )
    for acc in bank_accounts:
        account_colors[acc.name] = {
            "accent_color_1": acc.accent_color_1 or "#667eea",
            "accent_color_2": acc.accent_color_2 or "#764ba2",
            "text_color": acc.text_color or "Auto"
        }

    # Add colors and files to exports
    for exp in exports:
        colors = account_colors.get(exp.bank_account, {})
        exp["accent_color_1"] = colors.get("accent_color_1", "#667eea")
        exp["accent_color_2"] = colors.get("accent_color_2", "#764ba2")
        exp["text_color"] = colors.get("text_color", "Auto")

        # Get recent files for this export
        file_count = exp.dashboard_file_count or 3
        file_count = max(1, min(10, file_count))  # Limit between 1 and 10

        files = frappe.get_all(
            "File",
            filters=[
                ["file_name", "like", f"%_A_{exp.name}%"],
                ["is_folder", "=", 0]
            ],
            fields=["file_name", "file_url", "creation", "file_size", "owner"],
            order_by="creation DESC",
            limit=file_count
        )

        # Parse date range from filename for each file
        for f in files:
            f["from_date"], f["to_date"] = _parse_dates_from_filename(f.file_name)

        exp["files"] = files

    # Administrator and Banking Manager have full access
    if user == "Administrator" or "Banking Manager" in frappe.get_roles(user):
        return exports

    # Get bank accounts the user has permission for
    permitted_accounts = frappe.get_all(
        "User Permission",
        filters={
            "user": user,
            "allow": "Hibiscus Connect Bank Account"
        },
        pluck="for_value"
    )

    # Filter exports to only those with permitted bank accounts
    filtered_exports = [
        exp for exp in exports
        if exp.bank_account in permitted_accounts
    ]

    return filtered_exports


def _parse_dates_from_filename(filename):
    """Parse from_date from export filename.

    Filename pattern: Konto_{iban_last3}_{from_date}_[A_]{docname}.{ext}
    Example: Konto_601_2025-12-14_A_BSEXP-10465.xml (automatic)
    Example: Konto_601_2025-12-14_BSEXP-10465.xml (manual)

    Returns (from_date, None) since the new format only contains from_date.
    """
    import re
    # Match date pattern: Konto_XXX_YYYY-MM-DD_
    match = re.search(r'Konto_\d{3}_(\d{4}-\d{2}-\d{2})_', filename)
    if match:
        return match.group(1), None
    return None, None


@frappe.whitelist()
def quick_generate_export(docname):
    """Generate export and return the file URL for immediate download.

    Checks user permission for the linked bank account before generating.
    """
    doc = frappe.get_doc("Bank Statement Export", docname)
    user = frappe.session.user

    # Check permission for the bank account
    if user != "Administrator" and "Banking Manager" not in frappe.get_roles(user):
        has_permission = frappe.db.exists("User Permission", {
            "user": user,
            "allow": "Hibiscus Connect Bank Account",
            "for_value": doc.bank_account
        })
        if not has_permission:
            frappe.throw("Sie haben keine Berechtigung für dieses Bankkonto.", frappe.PermissionError)

    # If using a date preset, recalculate the dates
    if doc.date_preset and doc.date_preset != "Custom":
        dates = calculate_preset_dates(doc.date_preset)
        if dates:
            doc.from_date = dates["from_date"]
            doc.to_date = dates["to_date"]
            doc.flags.generating_export = True
            doc.save()

    # Generate the export (mark as automatic for dashboard)
    doc.flags.auto_export = True
    result = doc.generate_export()

    if result and result.get("success"):
        return {
            "success": True,
            "file_url": result.get("file_url"),
            "filename": result.get("filename")
        }
    else:
        return {"success": False, "error": "Export generation failed"}


def process_scheduled_exports():
    """Process all Bank Statement Exports scheduled for the current hour.

    This function is called hourly by the scheduler.
    It finds all exports where auto_generate_enabled=1 and auto_generate_hour matches
    the current hour, then generates the export files.

    Exports with skip_weekends=1 are skipped on Saturdays and Sundays.
    """
    from datetime import datetime

    current_hour = datetime.now().hour
    current_weekday = datetime.now().weekday()  # 0=Monday, ..., 5=Saturday, 6=Sunday
    is_weekend = current_weekday >= 5

    # Find all exports scheduled for this hour
    exports = frappe.get_all(
        "Bank Statement Export",
        filters={
            "auto_generate_enabled": 1,
            "auto_generate_hour": current_hour
        },
        fields=["name", "skip_weekends"]
    )

    if not exports:
        return

    frappe.logger().info(f"Processing {len(exports)} scheduled Bank Statement Exports for hour {current_hour} (weekend: {is_weekend})")

    for export in exports:
        export_name = export.name

        # Skip weekend exports if configured
        if is_weekend and export.skip_weekends:
            frappe.logger().info(f"Skipping export {export_name} - weekend skip enabled")
            continue

        try:
            doc = frappe.get_doc("Bank Statement Export", export_name)

            # Recalculate dates if using a preset
            if doc.date_preset and doc.date_preset != "Custom":
                dates = calculate_preset_dates(doc.date_preset)
                if dates:
                    doc.from_date = dates["from_date"]
                    doc.to_date = dates["to_date"]
                    doc.flags.generating_export = True
                    doc.save()

            # Generate the export (mark as automatic for dashboard)
            doc.flags.auto_export = True
            doc.generate_export()
            frappe.db.commit()

            frappe.logger().info(f"Successfully generated scheduled export: {export_name}")

        except Exception as e:
            frappe.log_error(
                f"Scheduled Bank Statement Export failed for {export_name}: {str(e)}",
                "Scheduled Bank Statement Export Error"
            )
            frappe.db.rollback()


def calculate_preset_dates(preset):
    """Calculate from_date and to_date based on preset."""
    from frappe.utils import today, add_days, get_first_day, get_last_day, getdate
    from datetime import date

    today_date = getdate(today())

    if preset == "Yesterday":
        d = add_days(today_date, -1)
        return {"from_date": d, "to_date": d}

    elif preset == "Day Before Yesterday":
        d = add_days(today_date, -2)
        return {"from_date": d, "to_date": d}

    elif preset == "Last Business Day":
        day_of_week = today_date.weekday()  # 0=Monday, ..., 6=Sunday
        days_back = 1
        if day_of_week == 6:  # Sunday -> Friday
            days_back = 2
        elif day_of_week == 0:  # Monday -> Friday
            days_back = 3
        d = add_days(today_date, -days_back)
        return {"from_date": d, "to_date": d}

    elif preset == "This Week":
        # Monday of current week
        week_start = add_days(today_date, -today_date.weekday())
        return {"from_date": week_start, "to_date": today_date}

    elif preset == "Last Week":
        this_week_start = add_days(today_date, -today_date.weekday())
        last_week_start = add_days(this_week_start, -7)
        last_week_end = add_days(this_week_start, -1)
        return {"from_date": last_week_start, "to_date": last_week_end}

    elif preset == "This Month":
        month_start = get_first_day(today_date)
        return {"from_date": month_start, "to_date": today_date}

    elif preset == "Last Month":
        this_month_start = get_first_day(today_date)
        last_month_end = add_days(this_month_start, -1)
        last_month_start = get_first_day(last_month_end)
        return {"from_date": last_month_start, "to_date": last_month_end}

    elif preset == "This Year":
        year_start = date(today_date.year, 1, 1)
        return {"from_date": year_start, "to_date": today_date}

    elif preset == "Last Year":
        year = today_date.year - 1
        return {"from_date": date(year, 1, 1), "to_date": date(year, 12, 31)}

    elif preset == "Year Before Last":
        year = today_date.year - 2
        return {"from_date": date(year, 1, 1), "to_date": date(year, 12, 31)}

    return None


def get_protected_export_role():
    """Get the role configured for editing protected exports."""
    settings = frappe.get_single("Hibiscus Connect Settings")
    return settings.protected_export_role


def has_protected_export_permission(user=None):
    """Check if user has permission to edit protected exports.

    Returns True if:
    - User is Administrator
    - User has the role configured in settings
    - No role is configured (feature disabled) - returns False per requirement
    """
    if user is None:
        user = frappe.session.user

    # Administrators always have access
    if user == "Administrator":
        return True

    # Get the configured role
    role = get_protected_export_role()

    # If no role configured, nobody can edit (except admins)
    if not role:
        return False

    # Check if user has the required role
    user_roles = frappe.get_roles(user)
    return role in user_roles


@frappe.whitelist()
def get_protection_status(docname):
    """Get protection status and user permission for a Bank Statement Export.

    Returns dict with:
    - is_protected: bool
    - has_permission: bool
    - required_role: str or None
    """
    doc = frappe.get_doc("Bank Statement Export", docname)

    return {
        "is_protected": bool(doc.is_protected),
        "has_permission": has_protected_export_permission(),
        "required_role": get_protected_export_role()
    }
