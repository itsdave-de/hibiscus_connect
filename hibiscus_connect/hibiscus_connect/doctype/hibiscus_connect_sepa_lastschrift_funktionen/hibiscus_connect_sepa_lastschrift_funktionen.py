# Copyright (c) 2025, itsdave GmbH and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import xmlrpc.client as xc
import ssl
import json
from datetime import datetime, timedelta


class HibiscusConnectSEPALastschriftFunktionen(Document):
	pass


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
def get_lastschriften(filter_status="alle"):
	"""
	Ruft alle SEPA-Lastschriften aus Hibiscus ab.

	Args:
		filter_status: 'alle', 'offen', 'ausgefuehrt'

	Returns:
		dict mit lastschriften Liste und Statistiken
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
		raw_data = client.hibiscus.xmlrpc.sepalastschrift.find("", von, bis)
	except Exception as e:
		frappe.throw("Fehler beim Abrufen der Lastschriften: {}".format(str(e)))

	# Statistiken
	total_offen = 0.0
	total_ausgefuehrt = 0.0
	count_offen = 0
	count_ausgefuehrt = 0

	alle_lastschriften = []

	for item in raw_data:
		ist_ausgefuehrt = item.get("ausgefuehrt", "false") == "true"
		betrag, betrag_formatted = format_betrag(item.get("betrag", "0"))

		if ist_ausgefuehrt:
			total_ausgefuehrt += betrag
			count_ausgefuehrt += 1
		else:
			total_offen += betrag
			count_offen += 1

		alle_lastschriften.append({
			"item": item,
			"ist_ausgefuehrt": ist_ausgefuehrt,
			"betrag": betrag,
			"betrag_formatted": betrag_formatted
		})

	# Gefilterte Liste erstellen
	lastschriften = []

	for entry in alle_lastschriften:
		item = entry["item"]
		ist_ausgefuehrt = entry["ist_ausgefuehrt"]

		# Filter anwenden
		if filter_status == "offen" and ist_ausgefuehrt:
			continue
		if filter_status == "ausgefuehrt" and not ist_ausgefuehrt:
			continue

		# Verwendungszweck extrahieren
		verwendungszweck_raw = item.get("verwendungszweck", [])
		if isinstance(verwendungszweck_raw, list):
			verwendungszweck = verwendungszweck_raw[0] if verwendungszweck_raw else ""
		else:
			verwendungszweck = str(verwendungszweck_raw)

		# Sequenztyp-Label
		seq_labels = {
			"FRST": "Erstmalig",
			"RCUR": "Wiederkehrend",
			"FNAL": "Letztmalig",
			"OOFF": "Einmalig"
		}

		lastschriften.append({
			"id": item.get("id", ""),
			"ausgefuehrt": ist_ausgefuehrt,
			"status_label": "Ausgeführt" if ist_ausgefuehrt else "Offen",
			"betrag": entry["betrag"],
			"betrag_formatted": entry["betrag_formatted"],
			"termin": parse_date(item.get("termin", "")),
			"termin_display": item.get("termin", ""),
			"targetdate": parse_date(item.get("targetdate", "")),
			"targetdate_display": item.get("targetdate", ""),
			"sequencetype": item.get("sequencetype", ""),
			"sequencetype_label": seq_labels.get(item.get("sequencetype", ""), item.get("sequencetype", "")),
			"sepatype": item.get("sepatype", ""),
			"mandateid": item.get("mandateid", ""),
			"name": item.get("name", ""),
			"kontonummer": item.get("kontonummer", ""),
			"blz": item.get("blz", ""),
			"verwendungszweck": verwendungszweck,
		})

	# Nach Termin sortieren (neueste zuerst)
	lastschriften.sort(key=lambda x: x.get("termin") or "", reverse=True)

	return {
		"lastschriften": lastschriften,
		"count_gesamt": count_offen + count_ausgefuehrt,
		"count_offen": count_offen,
		"count_ausgefuehrt": count_ausgefuehrt,
		"total_offen": "{:,.2f} EUR".format(total_offen).replace(",", "X").replace(".", ",").replace("X", "."),
		"total_ausgefuehrt": "{:,.2f} EUR".format(total_ausgefuehrt).replace(",", "X").replace(".", ",").replace("X", "."),
	}


def get_hibiscus_client():
	"""Erstellt einen Hibiscus XML-RPC Client"""
	settings = frappe.get_single("Hibiscus Connect Settings")
	pw = settings.get_password("hibiscus_master_password")

	if not pw:
		frappe.throw("Hibiscus Master Passwort nicht konfiguriert")

	url = "https://admin:{}@{}:{}/xmlrpc".format(pw, settings.server, settings.port)

	if settings.ignore_cert:
		return xc.Server(url, context=ssl._create_unverified_context())
	else:
		return xc.Server(url)


def format_date_to_german(date_str):
	"""Konvertiert ISO-Datum (YYYY-MM-DD) zu deutschem Format (DD.MM.YYYY)"""
	if not date_str:
		return None
	try:
		dt = datetime.strptime(str(date_str), "%Y-%m-%d")
		return dt.strftime("%d.%m.%Y")
	except:
		return date_str


@frappe.whitelist()
def get_lastschrift(lastschrift_id):
	"""
	Ruft eine einzelne SEPA-Lastschrift aus Hibiscus ab.

	Args:
		lastschrift_id: Die ID der Lastschrift in Hibiscus

	Returns:
		dict mit Lastschrift-Details
	"""
	client = get_hibiscus_client()

	# Datumbereich: letztes Jahr bis nächstes Jahr
	von = (datetime.now() - timedelta(days=365)).strftime("%d.%m.%Y")
	bis = (datetime.now() + timedelta(days=365)).strftime("%d.%m.%Y")

	try:
		# Alle Lastschriften abrufen und nach ID filtern
		raw_data = client.hibiscus.xmlrpc.sepalastschrift.find("", von, bis)
	except Exception as e:
		frappe.throw("Fehler beim Abrufen der Lastschriften: {}".format(str(e)))

	# Nach ID suchen
	item = None
	for ls in raw_data:
		if str(ls.get("id", "")) == str(lastschrift_id):
			item = ls
			break

	if not item:
		frappe.throw("Lastschrift mit ID {} nicht gefunden".format(lastschrift_id))

	# Verwendungszweck extrahieren
	verwendungszweck_raw = item.get("verwendungszweck", [])
	if isinstance(verwendungszweck_raw, list):
		verwendungszweck = verwendungszweck_raw[0] if verwendungszweck_raw else ""
	else:
		verwendungszweck = str(verwendungszweck_raw)

	betrag, betrag_formatted = format_betrag(item.get("betrag", "0"))
	ist_ausgefuehrt = item.get("ausgefuehrt", "false") == "true"

	return {
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
		"sepatype": item.get("sepatype", ""),
		"mandateid": item.get("mandateid", ""),
		"name": item.get("name", ""),
		"kontonummer": item.get("kontonummer", ""),
		"blz": item.get("blz", ""),
		"verwendungszweck": verwendungszweck,
		"creditorid": item.get("creditorid", ""),
		"endtoendid": item.get("endtoendid", ""),
	}


def get_mysql_connection():
	"""Erstellt eine MySQL-Verbindung zur Hibiscus-Datenbank"""
	import pymysql

	settings = frappe.get_single("Hibiscus Connect Settings")

	if not settings.mysql_enabled:
		frappe.throw("MySQL-Zugriff ist nicht aktiviert. Bitte in den Hibiscus Connect Settings aktivieren.")

	return pymysql.connect(
		host=settings.mysql_host,
		port=int(settings.mysql_port or 3306),
		user=settings.mysql_user,
		password=settings.get_password("mysql_password"),
		database=settings.mysql_database
	)


@frappe.whitelist()
def update_lastschrift(lastschrift_id, termin=None, targetdate=None):
	"""
	Aktualisiert eine SEPA-Lastschrift in Hibiscus via MySQL.

	Args:
		lastschrift_id: Die ID der Lastschrift in Hibiscus
		termin: Neues Einzugsdatum (ISO-Format YYYY-MM-DD)
		targetdate: Neues Fälligkeitsdatum (ISO-Format YYYY-MM-DD)

	Returns:
		dict mit Ergebnis
	"""
	settings = frappe.get_single("Hibiscus Connect Settings")

	if not settings.mysql_enabled:
		frappe.throw("MySQL-Zugriff ist nicht aktiviert. Die Hibiscus XML-RPC API unterstützt keine Updates. Bitte MySQL in den Hibiscus Connect Settings aktivieren.")

	if not termin and not targetdate:
		frappe.throw("Keine Änderungen angegeben")

	try:
		conn = get_mysql_connection()
		cursor = conn.cursor()

		# Prüfen ob Lastschrift existiert und noch offen ist
		cursor.execute(
			"SELECT id, ausgefuehrt FROM sepalastschrift WHERE id = %s",
			(lastschrift_id,)
		)
		result = cursor.fetchone()

		if not result:
			frappe.throw(f"Lastschrift mit ID {lastschrift_id} nicht gefunden")

		if result[1] == 1:
			frappe.throw("Diese Lastschrift wurde bereits ausgeführt und kann nicht mehr geändert werden.")

		# Update-Query bauen
		update_fields = []
		update_values = []

		if termin:
			update_fields.append("termin = %s")
			update_values.append(termin)

		if targetdate:
			update_fields.append("targetdate = %s")
			update_values.append(targetdate)

		update_values.append(lastschrift_id)

		query = f"UPDATE sepalastschrift SET {', '.join(update_fields)} WHERE id = %s AND ausgefuehrt = 0"
		cursor.execute(query, tuple(update_values))
		conn.commit()

		rows_affected = cursor.rowcount
		conn.close()

		if rows_affected > 0:
			frappe.msgprint("Lastschrift erfolgreich aktualisiert", indicator="green")
			return {"success": True, "rows_affected": rows_affected}
		else:
			frappe.throw("Keine Änderungen vorgenommen. Möglicherweise wurde die Lastschrift bereits ausgeführt.")

	except frappe.exceptions.ValidationError:
		raise
	except Exception as e:
		frappe.throw(f"Fehler beim Aktualisieren der Lastschrift: {str(e)}")


@frappe.whitelist()
def delete_lastschrift(lastschrift_id):
	"""
	Löscht eine SEPA-Lastschrift in Hibiscus.

	Args:
		lastschrift_id: Die ID der Lastschrift in Hibiscus

	Returns:
		dict mit Ergebnis
	"""
	client = get_hibiscus_client()

	try:
		result = client.hibiscus.xmlrpc.sepalastschrift.delete(str(lastschrift_id))
		frappe.msgprint("Lastschrift erfolgreich gelöscht")
		return {"success": True, "result": result}
	except Exception as e:
		frappe.throw("Fehler beim Löschen der Lastschrift: {}".format(str(e)))


def calculate_easter(year):
	"""
	Berechnet das Ostersonntag-Datum für ein gegebenes Jahr.
	Verwendet den Gauss'schen Osteralgorithmus.

	Args:
		year: Jahr (int)

	Returns:
		date: Ostersonntag
	"""
	a = year % 19
	b = year // 100
	c = year % 100
	d = b // 4
	e = b % 4
	f = (b + 8) // 25
	g = (b - f + 1) // 3
	h = (19 * a + b - d - g + 15) % 30
	i = c // 4
	k = c % 4
	l = (32 + 2 * e + 2 * i - h - k) % 7
	m = (a + 11 * h + 22 * l) // 451
	month = (h + l - 7 * m + 114) // 31
	day = ((h + l - 7 * m + 114) % 31) + 1

	from datetime import date
	return date(year, month, day)


def get_german_holidays(year):
	"""
	Gibt alle bundesweiten deutschen Feiertage für ein Jahr zurück.

	Feste Feiertage:
		- 1. Januar: Neujahr
		- 1. Mai: Tag der Arbeit
		- 3. Oktober: Tag der Deutschen Einheit
		- 25. Dezember: 1. Weihnachtstag
		- 26. Dezember: 2. Weihnachtstag

	Bewegliche Feiertage (abhängig von Ostern):
		- Karfreitag: 2 Tage vor Ostersonntag
		- Ostermontag: 1 Tag nach Ostersonntag
		- Christi Himmelfahrt: 39 Tage nach Ostersonntag
		- Pfingstmontag: 50 Tage nach Ostersonntag

	Args:
		year: Jahr (int)

	Returns:
		set: Set von date-Objekten
	"""
	from datetime import date

	holidays = set()

	# Feste Feiertage
	holidays.add(date(year, 1, 1))    # Neujahr
	holidays.add(date(year, 5, 1))    # Tag der Arbeit
	holidays.add(date(year, 10, 3))   # Tag der Deutschen Einheit
	holidays.add(date(year, 12, 25))  # 1. Weihnachtstag
	holidays.add(date(year, 12, 26))  # 2. Weihnachtstag

	# Bewegliche Feiertage (abhängig von Ostern)
	easter = calculate_easter(year)
	holidays.add(easter - timedelta(days=2))   # Karfreitag
	holidays.add(easter + timedelta(days=1))   # Ostermontag
	holidays.add(easter + timedelta(days=39))  # Christi Himmelfahrt
	holidays.add(easter + timedelta(days=50))  # Pfingstmontag

	return holidays


def is_workday(check_date):
	"""
	Prüft ob ein Datum ein Werktag ist (Mo-Fr, kein Feiertag).

	Args:
		check_date: Zu prüfendes Datum (date)

	Returns:
		bool: True wenn Werktag
	"""
	# Wochenende prüfen (Sa=5, So=6)
	if check_date.weekday() >= 5:
		return False

	# Feiertage prüfen
	holidays = get_german_holidays(check_date.year)
	if check_date in holidays:
		return False

	return True


def add_workdays(start_date, workdays):
	"""
	Addiert Werktage (Mo-Fr, ohne Feiertage) zu einem Datum.

	Args:
		start_date: Startdatum (date oder datetime)
		workdays: Anzahl Werktage (positiv = Zukunft)

	Returns:
		date: Neues Datum
	"""
	if isinstance(start_date, str):
		start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
	elif isinstance(start_date, datetime):
		start_date = start_date.date()

	current_date = start_date
	days_added = 0

	# Feiertage für das aktuelle und nächste Jahr laden (falls Jahreswechsel)
	holidays = get_german_holidays(start_date.year)
	holidays.update(get_german_holidays(start_date.year + 1))

	while days_added < workdays:
		current_date += timedelta(days=1)

		# Prüfen: Kein Wochenende (Mo=0 bis Fr=4) und kein Feiertag
		if current_date.weekday() < 5 and current_date not in holidays:
			days_added += 1

	return current_date


def get_sepa_vorlaufzeit(sepatype, sequencetype):
	"""
	Gibt die SEPA-Vorlaufzeit in Werktagen zurück.

	CORE:
		- Erstlastschrift (FRST): D-5
		- Folgelastschrift (RCUR, FNAL, OOFF): D-2

	B2B:
		- Alle: D-1

	Args:
		sepatype: CORE, COR1 oder B2B
		sequencetype: FRST, RCUR, FNAL, OOFF

	Returns:
		int: Anzahl Werktage Vorlauf
	"""
	if sepatype == "B2B":
		return 1
	else:  # CORE, COR1
		if sequencetype == "FRST":
			return 5
		else:  # RCUR, FNAL, OOFF
			return 2


def get_next_workday(start_date):
	"""
	Findet den nächsten Werktag (inkl. start_date, falls dieser ein Werktag ist).

	Args:
		start_date: Startdatum (date)

	Returns:
		date: Nächster Werktag
	"""
	current_date = start_date
	holidays = get_german_holidays(start_date.year)
	holidays.update(get_german_holidays(start_date.year + 1))

	while current_date.weekday() >= 5 or current_date in holidays:
		current_date += timedelta(days=1)

	return current_date


def calculate_next_possible_termin(sepatype, sequencetype):
	"""
	Berechnet den nächstmöglichen Einzugstermin basierend auf SEPA-Regeln.

	Die Berechnung berücksichtigt:
	1. Wenn heute kein Werktag ist, kann die Einreichung erst am nächsten Werktag erfolgen
	2. Die SEPA-Vorlaufzeit wird ab dem Einreichungstag berechnet

	Args:
		sepatype: CORE, COR1 oder B2B
		sequencetype: FRST, RCUR, FNAL, OOFF

	Returns:
		str: Nächstmögliches Datum im Format YYYY-MM-DD
	"""
	today = datetime.now().date()
	vorlaufzeit = get_sepa_vorlaufzeit(sepatype, sequencetype)

	# Schritt 1: Finde den nächsten Werktag (= Einreichungstag)
	einreichungstag = get_next_workday(today)

	# Schritt 2: Addiere Vorlaufzeit ab dem Einreichungstag
	next_termin = add_workdays(einreichungstag, vorlaufzeit)

	return next_termin.strftime("%Y-%m-%d")


@frappe.whitelist()
def get_next_termin_for_lastschrift(lastschrift_id):
	"""
	Berechnet den nächstmöglichen Einzugstermin für eine Lastschrift.

	Args:
		lastschrift_id: ID der Lastschrift

	Returns:
		dict mit aktuellem und neuem Termin
	"""
	# Lastschrift-Daten aus MySQL holen
	conn = get_mysql_connection()
	cursor = conn.cursor()

	cursor.execute(
		"SELECT id, termin, targetdate, sepatype, sequencetype FROM sepalastschrift WHERE id = %s AND ausgefuehrt = 0",
		(lastschrift_id,)
	)
	result = cursor.fetchone()
	conn.close()

	if not result:
		frappe.throw(f"Lastschrift {lastschrift_id} nicht gefunden oder bereits ausgeführt")

	current_termin = result[1]
	sepatype = result[3] or "CORE"
	sequencetype = result[4] or "RCUR"

	new_termin = calculate_next_possible_termin(sepatype, sequencetype)

	return {
		"id": lastschrift_id,
		"current_termin": str(current_termin) if current_termin else None,
		"new_termin": new_termin,
		"sepatype": sepatype,
		"sequencetype": sequencetype,
		"vorlaufzeit": get_sepa_vorlaufzeit(sepatype, sequencetype)
	}


@frappe.whitelist()
def bulk_set_next_termin(lastschrift_ids, dry_run=False):
	"""
	Setzt mehrere Lastschriften auf den nächstmöglichen Zieltermin (targetdate).

	Das targetdate ist das maßgebliche Datum für den Bankeinzug.
	Das termin-Feld ist nur ein Hibiscus-interner Erinnerungstermin.

	Args:
		lastschrift_ids: Liste von Lastschrift-IDs (als JSON-String oder Liste)
		dry_run: Wenn True, wird nur eine Vorschau zurückgegeben ohne Änderungen

	Returns:
		dict mit Ergebnis (und bei dry_run zusätzlich Details pro Lastschrift)
	"""
	import json

	dry_run = dry_run in (True, "true", "True", 1, "1")

	settings = frappe.get_single("Hibiscus Connect Settings")
	if not settings.mysql_enabled:
		frappe.throw("MySQL-Zugriff ist nicht aktiviert.")

	# IDs parsen
	if isinstance(lastschrift_ids, str):
		lastschrift_ids = json.loads(lastschrift_ids)

	if not lastschrift_ids:
		frappe.throw("Keine Lastschriften ausgewählt")

	conn = get_mysql_connection()
	cursor = conn.cursor()

	updated = 0
	skipped = 0
	errors = []
	will_update = []
	will_skip = []

	for ls_id in lastschrift_ids:
		try:
			# Lastschrift-Daten holen - targetdate ist das maßgebliche Datum
			cursor.execute(
				"SELECT id, targetdate, sepatype, sequencetype, ausgefuehrt, empfaenger_name FROM sepalastschrift WHERE id = %s",
				(ls_id,)
			)
			result = cursor.fetchone()

			if not result:
				errors.append(f"ID {ls_id}: Nicht gefunden")
				continue

			if result[4] == 1:
				skipped += 1
				will_skip.append({"id": ls_id, "name": result[5] or "", "reason": "Bereits ausgeführt"})
				continue

			current_targetdate = result[1]
			sepatype = result[2] or "CORE"
			sequencetype = result[3] or "RCUR"
			name = result[5] or ""

			# Nächstmöglichen Termin berechnen (berücksichtigt Vorlaufzeit)
			new_targetdate = calculate_next_possible_termin(sepatype, sequencetype)
			new_targetdate_date = datetime.strptime(new_targetdate, "%Y-%m-%d").date()

			# Prüfen ob Zieltermin noch rechtzeitig einreichbar ist
			if current_targetdate and current_targetdate >= new_targetdate_date:
				skipped += 1
				will_skip.append({
					"id": ls_id,
					"name": name,
					"reason": "Zieltermin {} noch fristgerecht".format(
						current_targetdate.strftime("%d.%m.%Y") if hasattr(current_targetdate, "strftime") else current_targetdate
					)
				})
				continue

			if dry_run:
				updated += 1
				will_update.append({
					"id": ls_id,
					"name": name,
					"current_targetdate": str(current_targetdate) if current_targetdate else None,
					"new_targetdate": new_targetdate,
					"sepatype": sepatype,
					"sequencetype": sequencetype,
				})
			else:
				# Update durchführen - targetdate UND termin aktualisieren
				# termin wird auf den gleichen Wert gesetzt (Hibiscus-Erinnerung)
				cursor.execute(
					"UPDATE sepalastschrift SET targetdate = %s, termin = %s WHERE id = %s AND ausgefuehrt = 0",
					(new_targetdate, new_targetdate, ls_id)
				)

				if cursor.rowcount > 0:
					updated += 1

		except Exception as e:
			errors.append(f"ID {ls_id}: {str(e)}")

	if not dry_run:
		conn.commit()

	conn.close()

	if not dry_run:
		# Ergebnis-Meldung
		msg_parts = []
		if updated > 0:
			msg_parts.append(f"<b>{updated}</b> Lastschrift(en) aktualisiert")
		if skipped > 0:
			msg_parts.append(f"<b>{skipped}</b> übersprungen (Zieltermin noch fristgerecht oder bereits ausgeführt)")
		if errors:
			msg_parts.append(f"<b>{len(errors)}</b> Fehler")

		frappe.msgprint("<br>".join(msg_parts), title="Bulk-Update Ergebnis", indicator="green" if not errors else "orange")

	return {
		"success": True,
		"updated": updated,
		"skipped": skipped,
		"errors": errors,
		"will_update": will_update,
		"will_skip": will_skip,
		"dry_run": dry_run
	}


@frappe.whitelist()
def refresh_lastschrift_cache():
	"""
	Aktualisiert den Lastschrift-Cache aus Hibiscus.

	Wird über hooks.py als stündlicher Job aufgerufen
	oder manuell vom Dashboard-Widget.
	Speichert fällige Lastschriften in den Hibiscus Connect Settings.
	"""
	settings = frappe.get_single("Hibiscus Connect Settings")

	# Prüfen ob Cache aktiviert ist
	if not settings.lastschrift_cache_enabled:
		return

	try:
		# Lastschriften abrufen
		data = get_lastschriften(filter_status="offen")
		lastschriften = data.get("lastschriften", [])

		# Fällige filtern (Zieltermin/targetdate in der Vergangenheit oder heute)
		today = datetime.now().date()
		faellige = []
		total_faellig = 0.0

		for ls in lastschriften:
			# targetdate ist das maßgebliche Datum für den Bankeinzug
			targetdate_str = ls.get("targetdate")
			if targetdate_str:
				try:
					targetdate = datetime.strptime(targetdate_str, "%Y-%m-%d").date()
					if targetdate <= today:
						faellige.append({
							"id": ls.get("id"),
							"name": ls.get("name"),
							"betrag": ls.get("betrag"),
							"betrag_formatted": ls.get("betrag_formatted"),
							"targetdate": targetdate_str
						})
						total_faellig += ls.get("betrag", 0)
				except:
					pass

		# Cache-Daten speichern
		cache_data = {
			"faellige": faellige,
			"count_offen": data.get("count_offen", 0),
			"total_offen": data.get("total_offen", "0,00 EUR")
		}

		frappe.db.set_value("Hibiscus Connect Settings", "Hibiscus Connect Settings", {
			"lastschrift_last_check": datetime.now(),
			"lastschrift_count_faellig": len(faellige),
			"lastschrift_total_faellig": total_faellig,
			"lastschrift_cache_data": json.dumps(cache_data)
		})
		frappe.db.commit()

	except Exception as e:
		frappe.log_error(
			title="Lastschrift-Cache Fehler",
			message=f"Fehler beim Aktualisieren des Lastschrift-Cache: {str(e)}"
		)


@frappe.whitelist(allow_guest=False)
def get_dashboard_data():
	"""
	API-Methode für das Dashboard: Gibt gecachte Lastschrift-Daten zurück.

	Returns:
		dict mit Dashboard-Daten (count, total, letzte Aktualisierung, Details)
	"""
	settings = frappe.get_single("Hibiscus Connect Settings")

	# Cache-Daten laden
	cache_data = {}
	if settings.lastschrift_cache_data:
		try:
			cache_data = json.loads(settings.lastschrift_cache_data)
		except:
			cache_data = {}

	# Formatierte Summe
	total_formatted = "{:,.2f} EUR".format(settings.lastschrift_total_faellig or 0).replace(",", "X").replace(".", ",").replace("X", ".")

	return {
		"count_faellig": settings.lastschrift_count_faellig or 0,
		"total_faellig": settings.lastschrift_total_faellig or 0,
		"total_faellig_formatted": total_formatted,
		"last_check": settings.lastschrift_last_check,
		"cache_enabled": settings.lastschrift_cache_enabled,
		"faellige": cache_data.get("faellige", []),
		"count_offen": cache_data.get("count_offen", 0),
		"total_offen": cache_data.get("total_offen", "0,00 EUR")
	}


# ============================================================================
# SEPA-Überweisungen
# ============================================================================

@frappe.whitelist()
def get_ueberweisungen(filter_status="alle"):
	"""
	Ruft alle SEPA-Überweisungen aus Hibiscus ab.

	Args:
		filter_status: 'alle', 'offen', 'ausgefuehrt'

	Returns:
		dict mit ueberweisungen Liste und Statistiken
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
		raw_data = client.hibiscus.xmlrpc.sepaueberweisung.find("", von, bis)
	except Exception as e:
		frappe.throw("Fehler beim Abrufen der Überweisungen: {}".format(str(e)))

	# Statistiken
	total_offen = 0.0
	total_ausgefuehrt = 0.0
	count_offen = 0
	count_ausgefuehrt = 0

	alle_ueberweisungen = []

	for item in raw_data:
		ist_ausgefuehrt = item.get("ausgefuehrt", "false") == "true"
		betrag, betrag_formatted = format_betrag(item.get("betrag", "0"))

		if ist_ausgefuehrt:
			total_ausgefuehrt += betrag
			count_ausgefuehrt += 1
		else:
			total_offen += betrag
			count_offen += 1

		alle_ueberweisungen.append({
			"item": item,
			"ist_ausgefuehrt": ist_ausgefuehrt,
			"betrag": betrag,
			"betrag_formatted": betrag_formatted
		})

	# Gefilterte Liste erstellen
	ueberweisungen = []

	for entry in alle_ueberweisungen:
		item = entry["item"]
		ist_ausgefuehrt = entry["ist_ausgefuehrt"]

		# Filter anwenden
		if filter_status == "offen" and ist_ausgefuehrt:
			continue
		if filter_status == "ausgefuehrt" and not ist_ausgefuehrt:
			continue

		# Verwendungszweck extrahieren
		verwendungszweck_raw = item.get("verwendungszweck", [])
		if isinstance(verwendungszweck_raw, list):
			verwendungszweck = verwendungszweck_raw[0] if verwendungszweck_raw else ""
		else:
			verwendungszweck = str(verwendungszweck_raw)

		ueberweisungen.append({
			"id": item.get("id", ""),
			"ausgefuehrt": ist_ausgefuehrt,
			"status_label": "Ausgeführt" if ist_ausgefuehrt else "Offen",
			"betrag": entry["betrag"],
			"betrag_formatted": entry["betrag_formatted"],
			"termin": parse_date(item.get("termin", "")),
			"termin_display": item.get("termin", ""),
			"name": item.get("name", ""),
			"kontonummer": item.get("kontonummer", ""),
			"blz": item.get("blz", ""),
			"verwendungszweck": verwendungszweck,
			"endtoendid": item.get("endtoendid", ""),
		})

	# Nach Termin sortieren (neueste zuerst)
	ueberweisungen.sort(key=lambda x: x.get("termin") or "", reverse=True)

	return {
		"ueberweisungen": ueberweisungen,
		"count_gesamt": count_offen + count_ausgefuehrt,
		"count_offen": count_offen,
		"count_ausgefuehrt": count_ausgefuehrt,
		"total_offen": "{:,.2f} EUR".format(total_offen).replace(",", "X").replace(".", ",").replace("X", "."),
		"total_ausgefuehrt": "{:,.2f} EUR".format(total_ausgefuehrt).replace(",", "X").replace(".", ",").replace("X", "."),
	}


@frappe.whitelist()
def refresh_ueberweisung_cache():
	"""
	Aktualisiert den Überweisungs-Cache aus Hibiscus.

	Wird über hooks.py als stündlicher Job aufgerufen
	oder manuell vom Dashboard-Widget.
	Speichert fällige Überweisungen in den Hibiscus Connect Settings.
	"""
	settings = frappe.get_single("Hibiscus Connect Settings")

	# Prüfen ob Cache aktiviert ist
	if not settings.ueberweisung_cache_enabled:
		return

	try:
		# Überweisungen abrufen
		data = get_ueberweisungen(filter_status="offen")
		ueberweisungen = data.get("ueberweisungen", [])

		# Fällige filtern (Termin in der Vergangenheit oder heute)
		today = datetime.now().date()
		faellige = []
		total_faellig = 0.0

		for ue in ueberweisungen:
			termin_str = ue.get("termin")
			if termin_str:
				try:
					termin = datetime.strptime(termin_str, "%Y-%m-%d").date()
					if termin <= today:
						faellige.append({
							"id": ue.get("id"),
							"name": ue.get("name"),
							"betrag": ue.get("betrag"),
							"betrag_formatted": ue.get("betrag_formatted"),
							"termin": termin_str
						})
						total_faellig += ue.get("betrag", 0)
				except:
					pass

		# Alle offenen Überweisungen für Info-Modal
		offene = []
		for ue in ueberweisungen:
			offene.append({
				"id": ue.get("id"),
				"name": ue.get("name"),
				"betrag": ue.get("betrag"),
				"betrag_formatted": ue.get("betrag_formatted"),
				"termin": ue.get("termin")
			})

		# Cache-Daten speichern
		cache_data = {
			"faellige": faellige,
			"offene": offene,
			"count_offen": data.get("count_offen", 0),
			"total_offen": data.get("total_offen", "0,00 EUR")
		}

		frappe.db.set_value("Hibiscus Connect Settings", "Hibiscus Connect Settings", {
			"ueberweisung_last_check": datetime.now(),
			"ueberweisung_count_faellig": len(faellige),
			"ueberweisung_total_faellig": total_faellig,
			"ueberweisung_cache_data": json.dumps(cache_data)
		})
		frappe.db.commit()

	except Exception as e:
		frappe.log_error(
			title="Überweisungs-Cache Fehler",
			message=f"Fehler beim Aktualisieren des Überweisungs-Cache: {str(e)}"
		)


@frappe.whitelist(allow_guest=False)
def get_ueberweisung_dashboard_data():
	"""
	API-Methode für das Dashboard: Gibt gecachte Überweisungs-Daten zurück.

	Returns:
		dict mit Dashboard-Daten (count, total, letzte Aktualisierung, Details)
	"""
	settings = frappe.get_single("Hibiscus Connect Settings")

	# Cache-Daten laden
	cache_data = {}
	if settings.ueberweisung_cache_data:
		try:
			cache_data = json.loads(settings.ueberweisung_cache_data)
		except:
			cache_data = {}

	# Formatierte Summe
	total_formatted = "{:,.2f} EUR".format(settings.ueberweisung_total_faellig or 0).replace(",", "X").replace(".", ",").replace("X", ".")

	return {
		"count_faellig": settings.ueberweisung_count_faellig or 0,
		"total_faellig": settings.ueberweisung_total_faellig or 0,
		"total_faellig_formatted": total_formatted,
		"last_check": settings.ueberweisung_last_check,
		"cache_enabled": settings.ueberweisung_cache_enabled,
		"faellige": cache_data.get("faellige", []),
		"offene": cache_data.get("offene", []),
		"count_offen": cache_data.get("count_offen", 0),
		"total_offen": cache_data.get("total_offen", "0,00 EUR")
	}
