import frappe
import xmlrpc.client as xc
import ssl
from datetime import datetime, timedelta


def format_betrag(betrag_str):
    """Formatiert Betrag von deutschem Format zu Float und zurück"""
    try:
        betrag = float(str(betrag_str).replace(".", "").replace(",", "."))
        formatted = "{:,.2f} EUR".format(betrag).replace(",", "X").replace(".", ",").replace("X", ".")
        return betrag, formatted
    except:
        return 0.0, "0,00 EUR"


def parse_date(date_str):
    """Parst deutsches Datum zu ISO-Format"""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        return dt.strftime("%Y-%m-%d")
    except:
        return date_str


@frappe.whitelist()
def get_sepa_lastschriften(filter_status="alle"):
    """
    Ruft alle SEPA-Lastschriften aus Hibiscus ab mit vollständigen Details.

    Args:
        filter_status: 'alle', 'offen', 'ausgefuehrt'
    """
    settings = frappe.get_single("Hibiscus Connect Settings")
    pw = settings.get_password("hibiscus_master_password")

    if not pw:
        frappe.throw("Hibiscus Master Passwort nicht konfiguriert")

    url = "https://admin:{}@{}:{}/xmlrpc".format(pw, settings.server, settings.port)

    if settings.ignore_cert:
        client = xc.Server(url, context=ssl._create_unverified_context())
    else:
        client = xc.Server(url)

    # Datumbereich: letztes Jahr bis nächstes Jahr
    von = (datetime.now() - timedelta(days=365)).strftime("%d.%m.%Y")
    bis = (datetime.now() + timedelta(days=365)).strftime("%d.%m.%Y")

    try:
        # find() gibt strukturierte Daten zurück
        raw_data = client.hibiscus.xmlrpc.sepalastschrift.find("", von, bis)
    except Exception as e:
        frappe.throw("Fehler beim Abrufen der Lastschriften: {}".format(str(e)))

    lastschriften = []

    # Zuerst ALLE Daten verarbeiten für Gesamtstatistiken
    total_offen = 0.0
    total_ausgefuehrt = 0.0
    count_offen = 0
    count_ausgefuehrt = 0

    alle_lastschriften = []

    for item in raw_data:
        # Status ermitteln
        ist_ausgefuehrt = item.get("ausgefuehrt", "false") == "true"

        # Betrag parsen
        betrag, betrag_formatted = format_betrag(item.get("betrag", "0"))

        # Gesamtstatistiken immer aktualisieren (unabhängig vom Filter)
        if ist_ausgefuehrt:
            total_ausgefuehrt += betrag
            count_ausgefuehrt += 1
        else:
            total_offen += betrag
            count_offen += 1

        # Daten für späteren Filter speichern
        alle_lastschriften.append({
            "item": item,
            "ist_ausgefuehrt": ist_ausgefuehrt,
            "betrag": betrag,
            "betrag_formatted": betrag_formatted
        })

    # Jetzt gefilterte Liste erstellen
    total_gefiltert = 0.0

    for entry in alle_lastschriften:
        item = entry["item"]
        ist_ausgefuehrt = entry["ist_ausgefuehrt"]
        betrag = entry["betrag"]
        betrag_formatted = entry["betrag_formatted"]

        # Filter anwenden
        if filter_status == "offen" and ist_ausgefuehrt:
            continue
        if filter_status == "ausgefuehrt" and not ist_ausgefuehrt:
            continue

        total_gefiltert += betrag

        # Verwendungszweck extrahieren (ist ein Array)
        verwendungszweck_raw = item.get("verwendungszweck", [])
        if isinstance(verwendungszweck_raw, list):
            verwendungszweck = verwendungszweck_raw[0] if verwendungszweck_raw else ""
        else:
            verwendungszweck = str(verwendungszweck_raw)

        # Sales Invoice Daten ergänzen
        sinv_data = {}
        if verwendungszweck and verwendungszweck.startswith("SINV-"):
            sinv_doc = frappe.db.get_value(
                "Sales Invoice",
                verwendungszweck,
                ["name", "status", "customer", "customer_name", "posting_date", "due_date", "grand_total"],
                as_dict=True
            )
            if sinv_doc:
                sinv_data = {
                    "sinv_exists": True,
                    "sinv_status": sinv_doc.get("status", ""),
                    "sinv_customer": sinv_doc.get("customer_name") or sinv_doc.get("customer", ""),
                    "sinv_date": str(sinv_doc.get("posting_date", "")),
                    "sinv_due_date": str(sinv_doc.get("due_date", "")),
                    "sinv_grand_total": sinv_doc.get("grand_total", 0)
                }

        # Sequenztyp-Label
        seq_labels = {
            "FRST": "Erstmalig",
            "RCUR": "Wiederkehrend",
            "FNAL": "Letztmalig",
            "OOFF": "Einmalig"
        }

        lastschriften.append({
            # Hibiscus-Daten
            "id": item.get("id", ""),
            "ausgefuehrt": ist_ausgefuehrt,
            "status_label": "Ausgeführt" if ist_ausgefuehrt else "Offen",
            "betrag": betrag,
            "betrag_formatted": betrag_formatted,
            "termin": parse_date(item.get("termin", "")),
            "termin_display": item.get("termin", ""),
            "targetdate": parse_date(item.get("targetdate", "")),
            "targetdate_display": item.get("targetdate", ""),
            "sequencetype": item.get("sequencetype", ""),
            "sequencetype_label": seq_labels.get(item.get("sequencetype", ""), item.get("sequencetype", "")),
            "sepatype": item.get("sepatype", ""),
            "mandateid": item.get("mandateid", ""),
            "sigdate": item.get("sigdate", ""),
            "name": item.get("name", ""),
            "kontonummer": item.get("kontonummer", ""),
            "blz": item.get("blz", ""),
            "konto": item.get("konto", ""),
            "creditorid": item.get("creditorid", ""),
            "verwendungszweck": verwendungszweck,
            "endtoendid": item.get("endtoendid", ""),
            # ERPNext-Daten
            **sinv_data
        })

    # Nach Termin sortieren (neueste zuerst)
    lastschriften.sort(key=lambda x: x.get("termin") or "", reverse=True)

    # Gesamtsumme berechnen
    total_gesamt = total_offen + total_ausgefuehrt
    count_gesamt = count_offen + count_ausgefuehrt

    return {
        "lastschriften": lastschriften,
        # Gefilterte Werte
        "count_gefiltert": len(lastschriften),
        "total_gefiltert": total_gefiltert,
        "total_gefiltert_formatted": "{:,.2f} EUR".format(total_gefiltert).replace(",", "X").replace(".", ",").replace("X", "."),
        # Gesamtwerte (immer gleich, unabhängig vom Filter)
        "count_gesamt": count_gesamt,
        "total_gesamt": total_gesamt,
        "total_gesamt_formatted": "{:,.2f} EUR".format(total_gesamt).replace(",", "X").replace(".", ",").replace("X", "."),
        "count_offen": count_offen,
        "total_offen": total_offen,
        "total_offen_formatted": "{:,.2f} EUR".format(total_offen).replace(",", "X").replace(".", ",").replace("X", "."),
        "count_ausgefuehrt": count_ausgefuehrt,
        "total_ausgefuehrt": total_ausgefuehrt,
        "total_ausgefuehrt_formatted": "{:,.2f} EUR".format(total_ausgefuehrt).replace(",", "X").replace(".", ",").replace("X", "."),
        "filter_status": filter_status
    }
