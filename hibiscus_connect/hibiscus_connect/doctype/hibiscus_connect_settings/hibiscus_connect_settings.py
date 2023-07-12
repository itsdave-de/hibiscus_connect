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
		hibiscus = Hibiscus(self.server, self.port, self.get_password("hibiscus_master_password"), self.ignore_cert)
		konto_list = hibiscus.get_accounts()
		frappe.msgprint(str(konto_list))

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
		
		hib_data = frappe.get_all("Hibiscus Connect Transaction", filters = {"datum":["between", [self.from_date, self.to_date]],
								       										"konto": self.export_konto})
		print(len(hib_data))
		exp_data = []
		for x in hib_data:
			el = frappe.get_doc("Hibiscus Connect Transaction",x.name)

			print(el.empfaenger_name)
			if el.empfaenger_name == "BFS finance GmbH":
				print(True)
				trans = el.name
				bfs_trans = self.get_bfs_transaction(trans)
				for el in bfs_trans:
					exp_data.append(el)
			else:
				print(False)
				data =[self.bic,
	   				self.export_konto , 
					"",
					current_date,
					el.valuta,
					el.datum,
					el.betrag,
					el.empfaenger_name,
					"",
					el.empfaenger_blz,
					el.empfaenger_konto,
					el.zweck,
					
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
	
		# # DataFrame als CSV-Datei speichern
		# csv_data = df_sorted.to_csv(index=False, sep=';',decimal=',',header=False, line_terminator='\r\n', quoting=3)
		# print(csv_data)
		
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
		name = "Bankdaten von "+ self.from_date +" bis " + self.to_date+".csv"
		# #Datei in erpnext hochladen
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
		date = bank_trans.datum
		#date = date_dt.strftime('%d.%m.%Y')


		filters = {"hibiscus_connect_transaction":trans}
		bfs_transaction_list = frappe.get_all("BFS List Item", filters=filters)
		trans_list =[x.name for x in bfs_transaction_list]
		print(bfs_transaction_list)
		transactions =[]
		for el in trans_list:
			trans_doc = frappe.get_doc("BFS List Item",el)
			supplier_name = frappe.get_doc("Supplier", trans_doc.supplier).supplier_name
			transaction =[self.bic,
		 			self.export_konto, 
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

				

