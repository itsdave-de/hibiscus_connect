# Copyright (c) 2021, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now


class HibiscusConnectTransaction(Document):

	def validate(self):
		self.set_link_titles()
		self.validate_no_duplicate_active_links()

	def set_link_titles(self):
		for row in self.verknuepfungen or []:
			if row.link_doctype and row.link_name:
				meta = frappe.get_meta(row.link_doctype)
				title_field = meta.get_title_field()
				if title_field and title_field != "name":
					row.link_title = frappe.db.get_value(
						row.link_doctype, row.link_name, title_field
					) or row.link_name
				else:
					row.link_title = row.link_name

			if not row.verknuepft_am:
				row.verknuepft_am = now()

	def validate_no_duplicate_active_links(self):
		seen = set()
		for row in self.verknuepfungen or []:
			if row.link_status == "aktiv":
				key = (row.link_doctype, row.link_name)
				if key in seen:
					frappe.throw(
						_("Doppelte aktive Verknüpfung: {0} {1}").format(
							row.link_doctype, row.link_name
						)
					)
				seen.add(key)

	def add_link(self, link_doctype, link_name, betrag=None, bemerkung=None):
		for row in self.verknuepfungen or []:
			if (
				row.link_doctype == link_doctype
				and row.link_name == link_name
				and row.link_status == "aktiv"
			):
				return row

		row = self.append("verknuepfungen", {
			"link_doctype": link_doctype,
			"link_name": link_name,
			"link_status": "aktiv",
			"betrag": betrag,
			"bemerkung": bemerkung,
			"verknuepft_am": now(),
		})
		return row

	def cancel_link(self, link_doctype, link_name, bemerkung=None, ersetzt=False):
		for row in self.verknuepfungen or []:
			if (
				row.link_doctype == link_doctype
				and row.link_name == link_name
				and row.link_status == "aktiv"
			):
				row.link_status = "ersetzt" if ersetzt else "storniert"
				if bemerkung:
					row.bemerkung = bemerkung
				return row
		return None
