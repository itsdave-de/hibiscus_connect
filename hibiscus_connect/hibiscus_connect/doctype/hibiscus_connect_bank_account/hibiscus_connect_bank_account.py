# Copyright (c) 2021, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class HibiscusConnectBankAccount(Document):
	def on_update(self):
		self.sync_user_permissions()

	def on_trash(self):
		self.remove_all_user_permissions()

	def sync_user_permissions(self):
		"""
		Sync the permitted_users and permitted_roles fields to Frappe's User Permission doctype.
		- Resolves roles to individual users
		- Deduplicates users
		- Creates/removes User Permission records as needed
		"""
		# Get all users that should have permission
		permitted_users = self.get_resolved_permitted_users()

		# Get existing User Permissions for this bank account
		existing_permissions = frappe.get_all(
			"User Permission",
			filters={
				"allow": "Hibiscus Connect Bank Account",
				"for_value": self.name
			},
			fields=["name", "user"]
		)
		existing_users = {p.user: p.name for p in existing_permissions}

		# Add new permissions
		for user in permitted_users:
			if user not in existing_users:
				frappe.get_doc({
					"doctype": "User Permission",
					"user": user,
					"allow": "Hibiscus Connect Bank Account",
					"for_value": self.name,
					"apply_to_all_doctypes": 1
				}).insert(ignore_permissions=True)

		# Remove permissions for users no longer in the list
		for user, perm_name in existing_users.items():
			if user not in permitted_users:
				frappe.delete_doc("User Permission", perm_name, ignore_permissions=True)

	def get_resolved_permitted_users(self):
		"""
		Get all users who should have access to this bank account.
		Combines direct user assignments and role-based assignments.
		Returns a deduplicated set of user emails.
		"""
		users = set()

		# Add directly permitted users
		for row in self.permitted_users or []:
			if row.user:
				users.add(row.user)

		# Resolve roles to users
		for row in self.permitted_roles or []:
			if row.role:
				role_users = frappe.get_all(
					"Has Role",
					filters={"role": row.role, "parenttype": "User"},
					fields=["parent"]
				)
				for ru in role_users:
					# Skip disabled users and Administrator
					user_doc = frappe.db.get_value("User", ru.parent, ["enabled", "name"], as_dict=True)
					if user_doc and user_doc.enabled and user_doc.name != "Administrator":
						users.add(ru.parent)

		return users

	def remove_all_user_permissions(self):
		"""Remove all User Permissions for this bank account when it's deleted."""
		permissions = frappe.get_all(
			"User Permission",
			filters={
				"allow": "Hibiscus Connect Bank Account",
				"for_value": self.name
			},
			pluck="name"
		)
		for perm_name in permissions:
			frappe.delete_doc("User Permission", perm_name, ignore_permissions=True)
