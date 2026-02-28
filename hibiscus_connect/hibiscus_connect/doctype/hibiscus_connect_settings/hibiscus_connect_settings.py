# Copyright (c) 2021, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import xmlrpc.client as xc
import ssl
from hibiscus_connect.hibclient import Hibiscus
import pandas as pd
from datetime import datetime


class HibiscusConnectSettings(Document):
	@frappe.whitelist()
	def test_connection(self):
		try:
			hibiscus = Hibiscus(self.server, self.port, self.get_password("hibiscus_master_password"), self.ignore_cert)
			account_list = hibiscus.get_accounts()

			if not account_list:
				frappe.msgprint(
					msg="Connection successful, but no bank accounts found.",
					title="Hibiscus Connection",
					indicator="orange"
				)
				return

			# Return data for client-side dialog
			accounts_data = []
			for acc in account_list:
				saldo = acc.get("saldo", "0") or "0"
				try:
					saldo_float = float(str(saldo).replace(",", "."))
				except (ValueError, TypeError):
					saldo_float = 0.0

				accounts_data.append({
					"id": acc.get("id", "-"),
					"name": acc.get("bezeichnung", "-"),
					"iban": acc.get("iban", "-"),
					"bic": acc.get("bic", "-"),
					"balance": saldo_float,
					"currency": acc.get("waehrung", "EUR")
				})

			return {
				"success": True,
				"server": self.server,
				"accounts": accounts_data
			}

		except Exception as e:
			error_type = type(e).__name__
			error_msg = str(e)

			# Provide user-friendly error messages
			if "401" in error_msg or "Unauthorized" in error_msg:
				friendly_error = "Authentication failed. Please check the master password."
				error_code = "AUTH_FAILED"
			elif error_type == "gaierror" or "Name or service not known" in error_msg:
				friendly_error = "Server not found. Please check the server hostname."
				error_code = "SERVER_NOT_FOUND"
			elif error_type == "ConnectionRefusedError" or "Connection refused" in error_msg:
				friendly_error = "Connection refused. Please check if the server is running and the port is correct."
				error_code = "CONNECTION_REFUSED"
			elif "SSL" in error_msg or "CERTIFICATE" in error_msg.upper():
				friendly_error = "SSL certificate error. Try enabling 'Ignore Invalid Certificate' option."
				error_code = "SSL_ERROR"
			elif "timed out" in error_msg.lower() or error_type == "TimeoutError":
				friendly_error = "Connection timed out. The server may be unreachable or the port may be wrong."
				error_code = "TIMEOUT"
			else:
				friendly_error = error_msg
				error_code = "UNKNOWN"

			return {
				"success": False,
				"server": self.server,
				"port": self.port,
				"error": friendly_error,
				"error_code": error_code,
				"error_details": error_msg
			}

	@frappe.whitelist()
	def test_mysql_connection(self):
		"""Test the MySQL connection to the Hibiscus database."""
		if not self.mysql_enabled:
			frappe.msgprint("MySQL access is not enabled.", indicator="orange")
			return

		try:
			import pymysql
			conn = pymysql.connect(
				host=self.mysql_host,
				port=int(self.mysql_port or 3306),
				user=self.mysql_user,
				password=self.get_password("mysql_password"),
				database=self.mysql_database
			)
			cursor = conn.cursor()
			cursor.execute("SELECT COUNT(*) FROM sepalastschrift")
			count = cursor.fetchone()[0]
			cursor.execute("SELECT COUNT(*) FROM sepalastschrift WHERE ausgefuehrt = 0")
			count_open = cursor.fetchone()[0]
			conn.close()
			frappe.msgprint(
				f"Connection successful!<br><br>"
				f"<b>Total direct debits:</b> {count}<br>"
				f"<b>Open direct debits:</b> {count_open}",
				indicator="green",
				title="MySQL Connection"
			)
		except Exception as e:
			frappe.msgprint(f"Connection error: {str(e)}", indicator="red", title="MySQL Error")

	@frappe.whitelist()
	def refresh_lastschrift_cache(self):
		"""Manually refresh the direct debit cache."""
		from hibiscus_connect.hibiscus_connect.doctype.hibiscus_connect_sepa_lastschrift_funktionen.hibiscus_connect_sepa_lastschrift_funktionen import refresh_lastschrift_cache as do_refresh
		try:
			do_refresh()
			frappe.msgprint(
				"Direct debit cache has been refreshed.",
				indicator="green",
				title="Cache Refreshed"
			)
		except Exception as e:
			frappe.msgprint(f"Error refreshing cache: {str(e)}", indicator="red", title="Error")

	@frappe.whitelist()
	def get_export(self):
		current_date = datetime.today().strftime('%d.%m.%Y')
		columns = ["Bankleitzahl oder BIC des Kontoinhabers",
	     			"Kontonummer oder IBAN des Kontoinhabers",
					"Auszugsnummer",
					"Auszugsdatum",
					"Valuta",
					"Buchungsdatum",
					"Umsatz",
					"Auftraggebername 1",
					"Auftraggebername 2",
					"Bankleitzahl oder BIC des Auftraggebers",
					"Kontonummer oder IBAN des Auftraggebers",
					"Verwendungszweck 1",
					 ]

		hib_data = frappe.get_all("Hibiscus Connect Transaction", filters = {"transaction_date":["between", [self.export_from_date, self.export_to_date]],
								       										"bank_account": self.export_account})
		print(len(hib_data))
		exp_data = []
		for x in hib_data:
			el = frappe.get_doc("Hibiscus Connect Transaction",x.name)

			print(el.counterparty_name)
			if el.counterparty_name == "BFS finance GmbH":
				print(True)
				trans = el.name
				bfs_trans = self.get_bfs_transaction(trans)
				for el in bfs_trans:
					exp_data.append(el)
			else:
				print(False)
				data =[self.export_bic,
	   				self.export_account,
					"",
					current_date,
					el.value_date,
					el.transaction_date,
					el.amount,
					el.counterparty_name,
					"",
					el.counterparty_bic,
					el.counterparty_iban,
					el.purpose,

				]
				exp_data.append(data)
		print(exp_data)
		print(len(exp_data))
		df = pd.DataFrame(exp_data, columns=columns)
		df_sorted = df.sort_values(by="Buchungsdatum", ascending=True)
		df_sorted['Valuta'] = df_sorted.apply(lambda x: x["Valuta"].strftime('%d.%m.%Y'), axis = 1)
		df_sorted['Buchungsdatum'] = df_sorted.apply(lambda x: x['Buchungsdatum'].strftime('%d.%m.%Y'), axis = 1)
		print(df.dtypes)
		print(df_sorted)

		# CSV-Datei mit den gewünschten Merkmalen manuell erstellen
		csv_data = ""
		for _, row in df_sorted.iterrows():
			csv_row = []
			for value in row.values:
				if isinstance(value, str):
					csv_row.append(f'"{value}"')
				else:
					a= str(value).replace(".", ",")
					csv_row.append(a)
			csv_data += ";".join(csv_row) + "\r\n"

		# CSV-Datei speichern
		with open('data.csv', 'w', encoding='cp1252') as file:
			file.write(csv_data)
		name = "Bankdaten von "+ str(self.export_from_date) +" bis " + str(self.export_to_date)+".csv"
		# Datei in erpnext hochladen
		file_data = frappe.get_doc({
			'doctype': 'File',
			'file_name': 'data.csv',
			'content': csv_data,
			'is_private': 0,
			'attached_to_doctype':"Hibiscus Connect Settings" ,
			'attached_to_name': "Hibiscus Connect Settings",
		})
		file_data.insert()



	def get_bfs_transaction(self,trans):
		bank_trans = frappe.get_doc("Hibiscus Connect Transaction", trans)
		date = bank_trans.transaction_date


		filters = {"hibiscus_connect_transaction":trans}
		bfs_transaction_list = frappe.get_all("BFS List Item", filters=filters)
		trans_list =[x.name for x in bfs_transaction_list]
		print(bfs_transaction_list)
		transactions =[]
		for el in trans_list:
			trans_doc = frappe.get_doc("BFS List Item",el)
			supplier_name = frappe.get_doc("Supplier", trans_doc.supplier).supplier_name
			transaction =[self.export_bic,
		 			self.export_account,
					"",
					datetime.today().strftime('%d.%m.%Y'),
					date,
					date,
					-trans_doc.zahl_betrag,
					supplier_name,
					"",
					"",
					"",
					supplier_name + ", Rechnung: " + trans_doc.belegnummer,

				]

			transactions.append(transaction)
		print(transactions)
		return(transactions)

	@frappe.whitelist()
	def import_bank_codes(self):
		"""
		Import bank codes from Bundesbank.
		Triggered by button click in Settings.
		"""
		from hibiscus_connect.bank_code_import import import_bank_codes_now
		return import_bank_codes_now()
