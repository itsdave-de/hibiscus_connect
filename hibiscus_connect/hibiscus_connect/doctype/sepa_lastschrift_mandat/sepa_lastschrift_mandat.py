# Copyright (c) 2022, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class SEPALastschriftMandat(Document):
	@frappe.whitelist()
	def get_creditor_from_settings(self):
		settings = frappe.get_single("Hibiscus Connect Settings")
		creditor_iban = settings.creditor_iban
		creditor_account_id = settings.creditor_account_id
		creditor_id = settings.creditor_id
		return [creditor_iban, creditor_account_id, creditor_id]

	#@frappe.whitelist()
	def on_update(self):
		if not self.mandate_reference and self.customer:
			nr = self.get_mandat_nr()
			mandate_reference = "SEPAM-"+ self.customer + "-"+ nr
			self.mandate_reference = mandate_reference
			self.save()

	def get_mandat_nr(self):
		customer = self.customer
		sepa_cust = frappe.get_all("SEPA Lastschrift Mandat", filters= {"customer": customer})
		count = len(sepa_cust)
		if count != 0:
			nächste_nr = count
			if len(str(nächste_nr)) == 1:
				return str(0) + str(nächste_nr)
			else:
				return str(nächste_nr)
		else:
			return str("01")

	# def get_mandateid(self, customer):

	# 	return count
# mandat_list = []
# 		for el in alle_mandate_für_kunden:
#         	mandat_list.push(int(el.rsplit(„-„,1)[1]))
#             if mandat_list:
# 			nächste_nr = max(mandat_list) + 1
