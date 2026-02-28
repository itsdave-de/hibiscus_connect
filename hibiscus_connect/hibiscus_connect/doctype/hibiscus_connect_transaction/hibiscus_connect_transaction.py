# Copyright (c) 2021, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class HibiscusConnectTransaction(Document):

	def before_insert(self):
		from hibiscus_connect.utils import is_erpnext_installed
		if is_erpnext_installed():
			self.customer_type = "Customer"

	def validate(self):
		self.set_link_titles()
		self.validate_no_duplicate_active_links()

	def set_link_titles(self):
		for row in self.transaction_links or []:
			if row.link_doctype and row.link_name:
				meta = frappe.get_meta(row.link_doctype)
				title_field = meta.get_title_field()
				if title_field and title_field != "name":
					row.link_title = frappe.db.get_value(
						row.link_doctype, row.link_name, title_field
					) or row.link_name
				else:
					row.link_title = row.link_name

			if not row.linked_at:
				row.linked_at = now()

	def validate_no_duplicate_active_links(self):
		seen = set()
		for row in self.transaction_links or []:
			if row.link_status == "active":
				key = (row.link_doctype, row.link_name)
				if key in seen:
					frappe.throw(
						_("Duplicate active link: {0} {1}").format(
							row.link_doctype, row.link_name
						)
					)
				seen.add(key)

	def add_link(self, link_doctype, link_name, amount=None, note=None):
		for row in self.transaction_links or []:
			if (
				row.link_doctype == link_doctype
				and row.link_name == link_name
				and row.link_status == "active"
			):
				return row

		row = self.append("transaction_links", {
			"link_doctype": link_doctype,
			"link_name": link_name,
			"link_status": "active",
			"amount": amount,
			"note": note,
			"linked_at": now(),
		})
		return row

	def cancel_link(self, link_doctype, link_name, note=None, replaced=False):
		for row in self.transaction_links or []:
			if (
				row.link_doctype == link_doctype
				and row.link_name == link_name
				and row.link_status == "active"
			):
				row.link_status = "replaced" if replaced else "cancelled"
				if note:
					row.note = note
				return row
		return None
