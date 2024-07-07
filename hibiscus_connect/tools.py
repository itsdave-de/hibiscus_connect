from cmath import e
#from ctypes.wintypes import HINSTANCE
from attr import fields, ib
from erpnext.accounts.doctype import account
import frappe
from hibiscus_connect.hibclient import Hibiscus
import json
from pprint import pprint
from datetime import datetime as dt
from datetime import date, timedelta
from frappe.model.naming import set_name_by_naming_series, get_default_naming_series
import re
from pprint import pprint
from numpy import append
from pyparsing import Regex
from frappe.exceptions import DuplicateEntryError, ValidationError
from razorpay import Payment

@frappe.whitelist()

def get_accounts_from_hibiscus_server():
    #Liefert ungefiltert alle Konten mit sämmtlichen Paramatern zurück
    settings = frappe.get_single("Hibiscus Connect Settings")
    hib = Hibiscus(settings.server, settings.port, settings.get_password("hibiscus_master_password") , settings.ignore_cert)
    return hib.get_accounts()

@frappe.whitelist()

def get_accounts_from_hibiscus_server_for_dialog():
    #Liefert alle Konten zurück, formatiert für die Anzeige des Dialogs "Konten anlegen"
    accounts = get_accounts_from_hibiscus_server()
    fields = []
    for account in accounts:

        account_dict = {
            "label": str(account["bezeichnung"] + ", " + account["name"] + ", IBAN:" + account["iban"]),
            "fieldname": str(account["iban"]),
            "fieldtype": "Check"
        }
        fields.append(account_dict)
    return fields


@frappe.whitelist()

def create_accounts(dialog_accounts):
    hibiscus_accounts = get_accounts_from_hibiscus_server()
    dialog_accounts_dict = json.loads(dialog_accounts)
    for key in dialog_accounts_dict:
        if dialog_accounts_dict[key] == 1:
            iban_account_to_create = key
            for hib_acc in hibiscus_accounts:
                if hib_acc["iban"] == iban_account_to_create:
                    create_hibiscus_connect_bank_account(hib_acc)

def create_hibiscus_connect_bank_account(hib_acc):
    hib_acc["doctype"] = "Hibiscus Connect Bank Account"
    hib_acc["name1"] = hib_acc.pop("name")
    hib_acc["saldo_available"] = float(str(hib_acc["saldo_available"]).replace(".","").replace(",","."))
    hib_acc["saldo"] = float(str(hib_acc["saldo"]).replace(".","").replace(",","."))
    hib_acc_doc = frappe.get_doc(hib_acc)
    hib_acc_doc.save()

@frappe.whitelist()

def get_transactions_for_account(account, von = str(date.today()-timedelta(30)), bis = str(date.today())):
    settings = frappe.get_single("Hibiscus Connect Settings")
    hib = Hibiscus(settings.server, settings.port, settings.get_password("hibiscus_master_password"), settings.ignore_cert)

    account_doc = frappe.get_doc("Hibiscus Connect Bank Account", account)
    if not account_doc.erpnext_bankkonto:
        frappe.throw("Bitte Hibiscus Connect Bank Account mit ERPNext Bankkonto verknüpfen.")
    
    von_dt = dt.strptime (von,"%Y-%m-%d")
    bis_dt = dt.strptime (bis,"%Y-%m-%d")
        
    transactions = hib.get_transactions(account_doc.id, von_dt,bis_dt)
    check_trans_id = frappe.get_all("Hibiscus Connect Transaction", fields = "id")
    check_trans_id_list = [ x["id"] for x in check_trans_id]
    
    for hib_trans in transactions:
        if hib_trans["id"] not in check_trans_id_list:
            create_hibiscus_connect_transaction(hib_trans, account)
    frappe.db.commit()

def create_hibiscus_connect_transaction(hib_trans, account):
    
    hib_trans["doctype"] = "Hibiscus Connect Transaction"
    hib_trans["saldo"] = float(str(hib_trans["saldo"]))
    hib_trans["betrag"] = float(str(hib_trans["betrag"]).replace(".","").replace(",","."))
    hib_trans["zweck_raw"] = hib_trans["zweck"]
    hib_trans_doc = frappe.get_doc(hib_trans)
    hib_trans_doc.konto = account
    hib_trans_doc.save()

@frappe.whitelist()
def match_hibiscus_transaction(hib_trans):
    payments = frappe.get_all("Hibiscus Connect Transaction", filters={
        "name": hib_trans
    }, fields = ["name", "empfaenger_blz", "empfaenger_konto"])
    hib_trans = payments[0]
    result = match_payment(hib_trans)
    if result["sinvs_matched_strict"]:
        pe = make_payment_entry(result)
        create_bank_account_for_customer(pe.party, hib_trans["empfaenger_konto"], hib_trans["empfaenger_blz"])
        return "Erfolgreich verbucht strict"
    if result["sinvs_matched_loose"]:
        pe = make_payment_entry(result)
        create_bank_account_for_customer(pe.party, hib_trans["empfaenger_konto"], hib_trans["empfaenger_blz"])
        return "Erfolgreich verbucht loose"
    if result["sinvs_matched_cust"]:
        pe = make_payment_entry(result)
        create_bank_account_for_customer(pe.party, hib_trans["empfaenger_konto"], hib_trans["empfaenger_blz"])
        return "Erfolgreich verbucht Kunde"
    frappe.throw("Zahlung konnte nicht automatisiert verbucht werden.<br>" + str(result))
    

def match_payment(hib_trans, sinvs=None, sinv_names=None):
    hib_trans_doc = frappe.get_doc("Hibiscus Connect Transaction", hib_trans)
    matching_list = {
        "sinvs_matched_strict": False,
        "sinvs_matched_loose": False,
        "sinvs_matched_cust": False,
        "totals_matched": False,
        "betrag": hib_trans_doc.betrag,
        "zweck": hib_trans_doc.zweck,
        "account": hib_trans_doc.konto,
        "erpnext_bankkonto": frappe.get_doc("Hibiscus Connect Bank Account", hib_trans_doc.konto),
        "hib_trans_doc": hib_trans_doc,
        "sinvs": [],
        "sinvs_loose": [],
        "cust": "", #Zuordnung der Transaktion zu einem Kunden
        "sinvs_cust": []
        }
    if not sinvs:
        sinvs = _get_unpaid_sinv_numbers()
    if not sinv_names:
        sinv_names = _get_unpaid_sinv_names()
    #Kriterien, die zum verbuchen herangezogen werden:
    #1.) Zweck enthällt mindesten eine Rechnungsnummer einer unbezahlten Rechnung im vollständigen format
    matching_list["sinvs"] = _get_sinv_names(hib_trans_doc.zweck, sinvs)
    if matching_list["sinvs"]:
        matching_list["totals"] = _get_grand_totals(matching_list["sinvs"])
        #1.1) Wenn zusätzlich der Betrag übereinstimmt, können wir verbuchen
        if hib_trans_doc.betrag == matching_list["totals"]:
            matching_list["sinvs_matched_strict"] = True
            matching_list["totals_matched"] = True
            return matching_list
    #2.) Zweck enthällt mindestens eine Rechnungsnummer einer unbezahlten Rechnung im unvollständigen Format (auch ohne Naming Series Prefix)
    matching_list["sinvs_loose"] = _advanced_si_match(hib_trans_doc.zweck, sinvs)
    if matching_list["sinvs_loose"]:
        matching_list["totals"] = _get_grand_totals(matching_list["sinvs_loose"])
        #2.1) Wenn zusätzlich der Betrag übereinstimmt, können wir verbuchen
        if hib_trans_doc.betrag == matching_list["totals"]:
            matching_list["sinvs_matched_loose"] = True
            matching_list["totals_matched"] = True
            return matching_list
    #3.) Transaktion wurde einem Kunden zugeordnet
    if hib_trans_doc.customer:
        if hib_trans_doc.customer != "":
            matching_list["cust"] = hib_trans_doc.customer

    #3.1) Zweck enthällt eine Kundenummer einer unbezahlten Rechnung (auch ohne Naming Series Prefix)
    if matching_list["cust"] == "":
        matching_list["cust"] = _cust_match(hib_trans_doc.zweck, sinv_names)

    #3.2) Die Bankverbindung ist einem Kunden zugeordnet
    if matching_list["cust"] == "" or not matching_list["cust"]:
        acc = frappe.get_all("Bank Account", filters={"iban": hib_trans_doc.empfaenger_konto }, fields=["party"])
        if acc:
            matching_list["cust"] = acc[0]["party"]

    if matching_list["cust"] != "":
        #3.3 Rechnunen ermitteln, deren Summe dem Betrag entspricht.
        matching_list["sinvs_cust"] = find_matching_invoices_for_customer_payment(hib_trans_doc, sinv_names, matching_list["cust"])
        print(matching_list["sinvs_cust"])
        if matching_list["sinvs_cust"]:
            matching_list["sinvs_matched_cust"] = True
            matching_list["totals_matched"] = True
            return matching_list
    
    return matching_list

    
    
@frappe.whitelist()
def match_all_payments(von = str(date.today()-timedelta(30)), bis = str(date.today())):
    stats = {
        "sinvs_matched_strict": 0,
        "sinvs_matched_loose": 0,
        "sinvs_matched_cust": 0,
        "totals_matched": 0,
        "payments_processed": 0
        }
    payments = frappe.get_all("Hibiscus Connect Transaction", filters={
        "status": "neu",
        "betrag": [">", 0],
    }, fields = ["name", "empfaenger_blz", "empfaenger_konto"])

    unpaid_sinvs = _get_unpaid_sinv_numbers()
    payments_list = []

    count = 0
    for p in payments:
        count += 1
        payments_list.append(p)
        result = match_payment(p.name, sinvs=unpaid_sinvs)
        
        stats["payments_processed"] += 1
        if result["sinvs_matched_strict"]:
            stats["sinvs_matched_strict"] += 1
            pe = make_payment_entry(result)
            create_bank_account_for_customer(pe.party, p["empfaenger_konto"], p["empfaenger_blz"])
        if result["sinvs_matched_loose"]:
            stats["sinvs_matched_loose"] += 1
            pe = make_payment_entry(result)
            create_bank_account_for_customer(pe.party, p["empfaenger_konto"], p["empfaenger_blz"])
        if result["sinvs_matched_cust"]:
            stats["sinvs_matched_cust"] += 1
            print(result)
            pe = make_payment_entry(result)
            create_bank_account_for_customer(pe.party, p["empfaenger_konto"], p["empfaenger_blz"])
        if result["totals_matched"]:
            stats["totals_matched"] += 1
        else:
            debug_data(result)
        
        frappe.publish_progress(
			count * 100 / len(payments),
			title="Verarbeite Zahlungseingänge...",
		)
    
    pprint(stats)
    return get_text_from_stats(stats)

def debug_data(result):
    print("--------------------")
    print(result["zweck"])
    print(result["betrag"])
   

def _advanced_si_match(zweck, sinvs):
    si_list = []
    regex = "|".join(sinvs)
    zweck = zweck.replace(" ","")
    match_regex_naming_series =re.findall(regex, zweck)
    if match_regex_naming_series:
        for m in match_regex_naming_series:
            sinv_name = "SINV-" + str(m)
            if sinv_name not in si_list:
                si_list.append(sinv_name)
    return si_list

def _cust_match(zweck, sinvs):
    si_list = []
    cust_list = []
    sinv_doc_list = frappe.get_all("Sales Invoice", filters={
        "name": ["in", sinvs]
    }, fields=[
        "name", "customer"
    ])
    for sinv_el in sinv_doc_list:
        if str(sinv_el["customer"]).lower() not in cust_list:
            cust_list.append(str(sinv_el["customer"]).lower())
    regex = "|".join(cust_list)
    zweck = zweck.replace(" ","")
    zweck = str(zweck).lower()
    match_regex_customer =re.findall(regex, zweck)
    if match_regex_customer:
        if len(match_regex_customer) > 1:
            frappe.throw("Mehr als eine Kundenummern im Verwendungszweck gefunden.")
        return match_regex_customer[0]
    else:
        return False


def find_matching_invoices_for_customer_payment(hib_trans_doc, sinv_names, customer):
    sinv_doc_list = frappe.get_all("Sales Invoice", filters={
        "name": ["in", sinv_names],
        "grand_total": ["<=", float(hib_trans_doc.betrag)],
        "customer": customer
    }, fields=[
        "name", "customer", "grand_total"
    ], order_by="name asc")
    #Prüfen, ob die offenen Rechungsbeträge in irgendeiner Kombination dem Zahlbetrag entsprechen
    combined_totals = combine_totals(hib_trans_doc.betrag, sinv_doc_list)
    matched_sinvs = []
    if combined_totals:
        for ct in combined_totals:
            for sinv in sinv_doc_list:
                if ct == sinv["grand_total"]:
                    if sinv["name"] not in matched_sinvs:
                        matched_sinvs.append(sinv["name"])
    
    return matched_sinvs


def combine_totals(sum, sinvs): #gibt ggf. eine Liste an Beträgen zurück, die summiert den Zahlbetrag ergeben
    #Summen aller Rechnungen sammeln
    sinv_totals = []
    for sinv in sinvs:
        sinv_totals.append(sinv["grand_total"])

    result = subset_sum(sinv_totals, sum)
    if result:
        return result
    else:
        return None

#stolen from https://stackoverflow.com/questions/34517540/find-all-combinations-of-a-list-of-numbers-with-a-given-sum  and adapted afterwards  
def subset_sum(numbers, target, partial=[]): #Ermittelt mögliche Kombinatiinen der Rechnungssummen
    s = sum(partial)
    # check if the partial sum is equals to target
    if round(s,3) == target:
        print("sum(%s)=%s" % (partial, target))
        return partial
    if s > target:
        return # if we reach the number why bother to continue
    for i in range(len(numbers)):
        n = numbers[i]
        remaining = numbers[i + 1:]
        result = subset_sum(remaining, target, partial + [n])
        if result:
            return result

def get_sinvs_for_matched_totals(totals, sinvs):
    pass


def _get_unpaid_sinv_numbers():
    sinv_numbers = []
    sinvs = frappe.get_all("Sales Invoice", filters={
        "status": ["not in", ["Return", "Paid"]],
        "name": ["not like", "SINV-RET-%"]
        })
    for si in sinvs:
        sinv_numbers.append(str(si["name"]).split("-")[1])
    return sinv_numbers

def _get_unpaid_sinv_names():
    sinv_numbers = []
    sinvs = frappe.get_all("Sales Invoice", filters={
        "status": ["not in", ["Return", "Paid"]],
        "name": ["not like", "SINV-RET-%"]
        })
    for si in sinvs:
        sinv_numbers.append(str(si["name"]))
    return sinv_numbers


        
def _get_sinv_names(zweck, sinvs=None, extended_matching=True):
    naming_series = get_default_naming_series("Sales Invoice")
    if "#" not in naming_series:
        naming_series += "######"
    regex_naming_series = str(naming_series).replace(".","").replace("#","\\d")
    match_regex_naming_series =re.findall(regex_naming_series, zweck)
    sinv_name_list = []
    if match_regex_naming_series:
        for m in match_regex_naming_series:
            if m not in sinv_name_list:
                sinv_name_list.append(m)
    return sinv_name_list


def _get_outstanding_amounts(sinv_list):
    outstanding_amount_sum = 0.0
    for sinv in sinv_list:
        sinv_doc = frappe.get_doc("Sales Invoice", sinv)
        outstanding_amount_sum += sinv_doc.outstanding_amount
    return outstanding_amount_sum

def _get_grand_totals(sinv_list):
    grand_total_sum = 0.0
    for sinv in sinv_list:
        try:
            sinv_doc = frappe.get_doc("Sales Invoice", sinv)
            grand_total_sum += sinv_doc.grand_total
        except frappe.DoesNotExistError:
            print(f"Sales Invoice {sinv} does not exist and will be skipped.")
        except Exception as e:
            print(f"An error occurred while processing Sales Invoice {sinv}: {e}")
    return round(grand_total_sum, 2)


def make_payment_entry(matching_list, settings=None):
    other_account_sinv = []
    if not settings:
        settings = frappe.get_single("Hibiscus Connect Settings")

    pe_doc = frappe.get_doc({
        "doctype": "Payment Entry",
        "payment_type": "Receive",
        "party_type": "Customer",
        "party": "", #erstmal leer, wird später anhand vorliegender Rechnungen befüllt
        "party_name": "",
        "paid_from": "",
        "paid_to":  matching_list["erpnext_bankkonto"].erpnext_bankkonto,
        "paid_amount": matching_list["betrag"],
        "received_amount": matching_list["betrag"],
        "source_exchange_rate": 1,
        "target_exchange_rate": 1,
        "reference_no": matching_list["hib_trans_doc"].name,
        "reference_date": matching_list["hib_trans_doc"].datum,
        "hibiscus_connect_transaction": matching_list["hib_trans_doc"].name,
        "referneces": []
    })

    todo = list(matching_list["sinvs"])
    todo.extend(x for x in matching_list["sinvs_loose"] if x not in todo)
    todo.extend(x for x in matching_list["sinvs_cust"] if x not in todo)

    todo.sort()
    error = ""
    print(todo)
    for sinv in todo:
        print("processing " + sinv)
        
        reference_doc_response = _get_payment_entry_reference(sinv)
       
        #Kundennummer setzen wenn bisher leer
        if pe_doc.party == "":
            pe_doc.party = reference_doc_response["sinv_doc"].customer
            pe_doc.party_name = frappe.get_value(doctype="Customer", filters={"name": pe_doc.party}, fieldname="customer_name"),
        #Fehler, wenn eine bereits befüllte Kundenummer verändert werden soll
        if pe_doc.party != reference_doc_response["sinv_doc"].customer:
            error += "Verschiedene Kundenummern in automatisiert zugeordneten Rechnungen.<br>"
            break

        #Debitoren Konte anhand Rechnungskonto setzen
        if pe_doc.paid_from == "":
            pe_doc.paid_from = reference_doc_response["sinv_doc"].debit_to
        #Fehler, wenn mehrere Debitoren Konten in einem PE angesprochen werden würden
        if pe_doc.paid_from != reference_doc_response["sinv_doc"].debit_to:
            other_account_sinv.append(sinv)
            continue
        pe_doc.append("references", reference_doc_response["reference_doc"])
        try:
            pe_doc.save()
            if pe_doc.unallocated_amount == 0:
                print("pe_doc.unallocated_amount = 0")
                break

        except Exception as e:
            error += "<p>" + repr(e) + "</p>"
    
    if error:
        frappe.msgprint(error + dict_to_html_ul(matching_list,2))
        return pe_doc
    else:
        pe_doc.save()
        print("letztes save")
        print(pe_doc.total_allocated_amount)
        print(pe_doc.unallocated_amount)
        print(pe_doc.difference_amount)
        matching_list["hib_trans_doc"].customer = pe_doc.party
        matching_list["hib_trans_doc"].save()
        matching_list["Payment Entry"] = pe_doc.name

    if len(other_account_sinv) > 0:
        frappe.msgprint("Zahlung konnte nicht automatisiert verbucht werden. Es wurden verschiedene Konten angesrpochen.<br>" + dict_to_html_ul(matching_list,2))
        return pe_doc
   
    if settings.submit_pe:
        if pe_doc.difference_amount != 0:
            frappe.msgprint("Zahlung konnte nicht automatisiert verbucht werden. Es kamen mehrere identische Beträge in Frage.<br>" + dict_to_html_ul(matching_list,2))
            return pe_doc
        
        if round(pe_doc.unallocated_amount + pe_doc.total_allocated_amount, 2) != pe_doc.paid_amount:
            frappe.msgprint("Zahlung konnte nicht automatisiert verbucht werden. Es gibt noch unzugeordnete Beträge.<br>" + dict_to_html_ul(matching_list,2))
            return pe_doc

        pe_doc.submit()
        matching_list["hib_trans_doc"].protokoll = pe_doc.remarks
        matching_list["hib_trans_doc"].status = "automatisch verbucht"
        matching_list["hib_trans_doc"].save()
       
    return pe_doc
    

def _get_payment_entry_reference(sinv):
    sinv_doc = frappe.get_doc("Sales Invoice", sinv)
    reference_doc = frappe.get_doc({ 
        "doctype": "Payment Entry Reference",
        "reference_doctype": "Sales Invoice",
        "reference_name": sinv,
        "due_date": sinv_doc.due_date,
        "total_amount": sinv_doc.grand_total,
        "outstanding_amount": sinv_doc.outstanding_amount,
        "allocated_amount": sinv_doc.outstanding_amount
    })
    return {"reference_doc": reference_doc, "sinv_doc": sinv_doc}

### wip

def get_text_from_stats(stats):
    return "blub" + str(stats)

@frappe.whitelist()
def set_andere_einnahme(list):
    print("#####################")
    hbt_list = json.loads(list)
    print(hbt_list)
    for el in hbt_list:
        hbdoc = frappe.get_doc("Hibiscus Connect Transaction", el)
        hbdoc.status = "andere Einnahme"
        hbdoc.save()

@frappe.whitelist()
def dump_checked(list):
    pprint(list)

def create_debit_charge(sinv, method=None):
    print(sinv.name)
    settings = frappe.get_single("Hibiscus Connect Settings")
    if settings.debit_charge_active == 0:
        return

    else:
        invoice = frappe.get_doc("Sales Invoice", sinv.name)
        customer = invoice.customer
        termin = invoice.due_date - timedelta(days=2)
        betrag = str(invoice.grand_total).replace(".", ",")
        payment_terms = invoice.payment_terms_template
        print("payment_terms")
        print(payment_terms)
        if payment_terms == "SEPA Einzug 7 Tage":
            if invoice.grand_total >0:
                sepa_mandat = frappe.get_all("SEPA Lastschrift Mandat",
                                            filters = {
                                                "status": "active",
                                                "customer":customer
                                                },
                
                                            )

                print(len(sepa_mandat))
                if len(sepa_mandat) == 1:
                    sepa_mandat_doc = frappe.get_doc("SEPA Lastschrift Mandat", sepa_mandat[0]["name"])
                    print(sepa_mandat_doc.frst, sepa_mandat_doc.final)
                    if sepa_mandat_doc.frst == 0 and sepa_mandat_doc.final == 0:
                        sequencetype = "FRST"
                        sepa_mandat_doc.frst = 1
                        sepa_mandat_doc.save()
                    elif sepa_mandat_doc.frst == 1 and sepa_mandat_doc.final == 0:
                        sequencetype = "RCUR"
                    elif sepa_mandat_doc.final == 1:
                        sequencetype = "FNAL"
                        sepa_mandat_doc.status = "inactive"
                        sepa_mandat_doc.save()
                    print(sequencetype)
                    params =  {"betrag": str(betrag),
                            "termin": str(termin),
                            "konto": str(sepa_mandat_doc.konto_id),
                            "name": str(sepa_mandat_doc.gegenkonto_name),
                            "blz": str(sepa_mandat_doc.blz),
                            "kontonummer": str(sepa_mandat_doc.kontonummer),
                            "verwendungszweck": str(invoice.name),
                            "creditorid":str(sepa_mandat_doc.creditorid),
                            "mandateid":str(sepa_mandat_doc.mandateid),
                            "sigdate":str(sepa_mandat_doc.sigdate),
                            "sequencetype":str(sequencetype),
                            "sepatype":str(sepa_mandat_doc.sepatype),
                            "targetdate": str(invoice.due_date)
                            
                            }           
                    print(params)
                    
                    hib = Hibiscus(settings.server, settings.port, settings.get_password("hibiscus_master_password"), settings.ignore_cert)
                    deb = hib.get_debit_charge(params)
                    print(deb)
                    if not deb:
                        frappe.msgprint("Es wurde eine SEPA-Lastschrift erzeugt")
                    else:
                        frappe.msgprint(deb)
                
                elif len(sepa_mandat) == 0:
                    print("Für den Kunden wurde kein aktives SEPA Mandat gefunden")
                    #frappe.msgprint("Für den Kunden wurde kein aktives SEPA Mandat gefunden") 
                else:
                    print("Mandat nicht eindeutig, bitte prüfen")
                    #frappe.msgprint("Mandat nicht eindeutig, bitte prüfen")
            


###### einmal-methoden für inbetreibnahme

def set_lagacy_verbucht():
    hib_transactions = frappe.get_all("Hibiscus Connect Transaction", filters={
        "status": "neu"
    })
    for ht in hib_transactions:
        ht_doc= frappe.get_doc("Hibiscus Connect Transaction", ht["name"])
        regex = "PE-\\d\\d\\d\\d\\d"
        result = re.findall(regex, ht_doc.kommentar)
        
        if result:
            print(ht_doc.kommentar)
            ht_doc.status = "legacy verbucht"
            ht_doc.save()
    frappe.db.commit()

@frappe.whitelist()
def create_bank_account_for_customer(customer, iban, bic):
    if frappe.get_all("Bank Account", filters={"iban": iban}):
        return "Bankkonto bereits vorhanden."
    
    cdoc = frappe.get_doc("Customer", customer)
    bank = frappe.get_all("Bank", filters={"swift_number": bic})
    if not bank:
        bank = create_unknown_bank(bic).name
    else:
        bank = bank[0]["name"]
    len_ges = len(bank) + len(cdoc.customer_name) + len(iban) + 6

    str_to = 140 - 6 - len(bank) - len(iban)
    account_name = cdoc.customer_name[0:str_to] + " | " + iban

    badoc = frappe.get_doc({
        "doctype": "Bank Account",
        "account_name": account_name,
        "bank" : bank,
        "party_type": "Customer",
        "party": customer,
        "iban": iban
        })

    badoc.save()
    return "Bankkonto erfolgreich erstellt."

def create_unknown_bank(bic):
    bdoc = frappe.get_doc({
        "doctype": "Bank",
        "bank_name": "unknown "+ bic,
        "swift_number": bic
    })
    bdoc.save()
    return bdoc

        
def dict_to_html_ul(dd, level=0):
    text = '<ul>'
    import json
    for k, v in dd.items():
        text += '<li><b>%s</b>: %s</li>' % (k, dict_to_html_ul(v, level+1) if isinstance(v, dict) else (json.dumps(v) if isinstance(v, list) else v))
    text += '</ul>'
    return text


