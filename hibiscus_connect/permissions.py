# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe


def bank_account_query_conditions(user):
	"""
	Filter bank account list queries.
	- Administrator and Banking Manager: full access
	- Others: only accounts they have User Permission for
	- If no User Permissions exist for user: no access (returns 1=0)
	"""
	if user == "Administrator":
		return ""

	if "Banking Manager" in frappe.get_roles(user):
		return ""

	# Check if user has ANY User Permission for Bank Account
	has_permissions = frappe.db.exists("User Permission", {
		"user": user,
		"allow": "Hibiscus Connect Bank Account"
	})

	if not has_permissions:
		# No permissions defined = no access for non-managers
		return "1=0"

	# Let Frappe's built-in User Permission system handle the filtering
	return ""


def transaction_query_conditions(user):
	"""
	Filter transaction list queries based on permitted bank accounts.
	- Administrator and Banking Manager: full access
	- Others: only transactions from accounts they have User Permission for
	- If no User Permissions exist for user: no access
	"""
	if user == "Administrator":
		return ""

	if "Banking Manager" in frappe.get_roles(user):
		return ""

	# Check if user has ANY User Permission for Bank Account
	has_permissions = frappe.db.exists("User Permission", {
		"user": user,
		"allow": "Hibiscus Connect Bank Account"
	})

	if not has_permissions:
		return "1=0"

	# Let Frappe's built-in User Permission system handle the filtering via the bank_account link
	return ""


def has_bank_account_permission(doc, ptype="read", user=None):
	"""
	Check permission for specific bank account document.
	Called when opening/editing a specific document.
	"""
	user = user or frappe.session.user

	if user == "Administrator":
		return True

	if "Banking Manager" in frappe.get_roles(user):
		return True

	# Get the account name
	account_name = doc.name if hasattr(doc, 'name') else doc.get('name')

	# Check if user has User Permission for this specific account
	has_permission = frappe.db.exists("User Permission", {
		"user": user,
		"allow": "Hibiscus Connect Bank Account",
		"for_value": account_name
	})

	return bool(has_permission)


def has_transaction_permission(doc, ptype="read", user=None):
	"""
	Check permission for specific transaction document.
	Checks if user has permission to the linked bank account.
	"""
	user = user or frappe.session.user

	if user == "Administrator":
		return True

	if "Banking Manager" in frappe.get_roles(user):
		return True

	# Get the linked bank account
	bank_account = doc.bank_account if hasattr(doc, 'bank_account') else doc.get('bank_account')

	if not bank_account:
		return False

	# Check if user has User Permission for this account
	has_permission = frappe.db.exists("User Permission", {
		"user": user,
		"allow": "Hibiscus Connect Bank Account",
		"for_value": bank_account
	})

	return bool(has_permission)


def sync_bank_permissions_for_user(doc, method=None):
	"""
	Sync bank account permissions when a user's roles change.
	Called via doc_events hook on User doctype.

	When a user is added to or removed from a role, we need to update
	their User Permission entries for any bank accounts that use that role.
	"""
	if doc.name == "Administrator":
		return

	# Get user's current roles
	user_roles = {r.role for r in doc.roles or []}

	# Find all bank accounts that have role-based permissions
	role_permissions = frappe.get_all(
		"Bank Account Role Permission",
		fields=["parent", "role"]
	)

	# Group by bank account
	accounts_by_role = {}
	for rp in role_permissions:
		if rp.role not in accounts_by_role:
			accounts_by_role[rp.role] = []
		accounts_by_role[rp.role].append(rp.parent)

	# Determine which accounts this user should have access to via roles
	accounts_user_should_access = set()
	for role in user_roles:
		if role in accounts_by_role:
			accounts_user_should_access.update(accounts_by_role[role])

	# Get existing User Permissions for this user on bank accounts
	existing_permissions = frappe.get_all(
		"User Permission",
		filters={
			"user": doc.name,
			"allow": "Hibiscus Connect Bank Account"
		},
		fields=["name", "for_value"]
	)
	existing_accounts = {p.for_value: p.name for p in existing_permissions}

	# Also check if user is directly permitted on any accounts
	direct_permissions = frappe.get_all(
		"Bank Account User Permission",
		filters={"user": doc.name},
		fields=["parent"]
	)
	directly_permitted_accounts = {dp.parent for dp in direct_permissions}

	# Accounts user should have access to = role-based + direct
	all_permitted_accounts = accounts_user_should_access | directly_permitted_accounts

	# Add missing permissions
	for account in all_permitted_accounts:
		if account not in existing_accounts:
			frappe.get_doc({
				"doctype": "User Permission",
				"user": doc.name,
				"allow": "Hibiscus Connect Bank Account",
				"for_value": account,
				"apply_to_all_doctypes": 1
			}).insert(ignore_permissions=True)

	# Remove permissions for accounts user no longer has access to
	for account, perm_name in existing_accounts.items():
		if account not in all_permitted_accounts:
			frappe.delete_doc("User Permission", perm_name, ignore_permissions=True)
