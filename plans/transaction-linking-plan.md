# Plan: Flexible Dokumentverknüpfung für Hibiscus Connect Transaktionen

## Kontext

Aktuell sind Transaktionen nur indirekt mit Payment Entries verknüpft (über ein Custom Field auf dem Payment Entry). Es fehlt eine flexible Möglichkeit, Transaktionen mit beliebigen Dokumenten zu verknüpfen (Purchase Invoices, Journal Entries, Expense Claims, Projekte, Verträge, etc.). Die neue Child Table ermöglicht 1:n-Verknüpfungen mit jedem DocType im System, ohne bestehende Workflows zu brechen.

Links werden **nicht gelöscht**, sondern haben einen eigenen Lifecycle (aktiv → storniert / ersetzt), damit Korrekturen nachvollziehbar bleiben.

---

## 1. Neuer Child Table DocType: `Hibiscus Connect Transaction Link`

**Pfad:** `.../hibiscus_connect/doctype/hibiscus_connect_transaction_link/`

**4 neue Dateien:**
- `__init__.py` (leer)
- `hibiscus_connect_transaction_link.json` (DocType-Definition)
- `hibiscus_connect_transaction_link.py` (minimaler Controller)
- `test_hibiscus_connect_transaction_link.py` (Test-Stub)

**Felder der Child Table:**

| Feld | Typ | Pflicht | In List View | Beschreibung |
|------|-----|---------|-------------|--------------|
| `link_doctype` | Link → DocType | Ja | Ja | Ziel-DocType auswählen |
| `link_name` | Dynamic Link (options=link_doctype) | Ja | Ja | Konkretes Dokument auswählen |
| `link_title` | Read Only | Nein | Ja | Automatisch befüllter Titel des Dokuments |
| `link_status` | Select: aktiv / storniert / ersetzt | Ja | Ja | Status der Verknüpfung, Default: "aktiv" |
| `betrag` | Currency | Nein | Ja | Zugeordneter Teilbetrag (optional) |
| `bemerkung` | Small Text | Nein | Nein | Freitext-Kommentar / Storno-Grund |
| `verknuepft_am` | Datetime | Nein | Nein | Zeitpunkt der Verknüpfung (auto-gesetzt) |

**Link-Status Lifecycle:**
- **aktiv** — Verknüpfung ist gültig und aktuell (Default bei Erstellung)
- **storniert** — Verknüpfung wurde aufgehoben (z.B. falsche Zuordnung). Zeile bleibt als Historie erhalten. Grund wird im `bemerkung`-Feld dokumentiert.
- **ersetzt** — Verknüpfung wurde durch eine neue abgelöst (z.B. falsche Rechnung → richtige Rechnung). Zeile bleibt, und eine neue aktive Zeile wird für das Ersatz-Dokument angelegt.

**Warum `betrag`?** Eine 500€-Transaktion kann z.B. 300€ einer Rechnung und 200€ einer anderen zugeordnet werden. Optional — bei informativen Verknüpfungen (Projekt, Vertrag) bleibt es leer.

**Warum `verknuepft_am`?** Für Audit-Trail / Nachvollziehbarkeit — wann wurde die Zuordnung vorgenommen?

---

## 2. Änderung am Parent DocType: `Hibiscus Connect Transaction`

**Datei:** `.../hibiscus_connect_transaction/hibiscus_connect_transaction.json`

Neue Felder in `field_order` einfügen (zwischen `zweck_raw` und `automatisierung_section`):

```
"verknuepfungen_section",   ← Section Break "Verknüpfungen" (collapsible)
"verknuepfungen"            ← Table → Hibiscus Connect Transaction Link
```

**Was NICHT geändert wird:** `customer`, `protokoll`, `konto`, `status`-Optionen — alles bleibt.

---

## 3. Controller-Logik: `hibiscus_connect_transaction.py`

Aktuell nur `pass`. Neue Methoden:

- **`validate()`** → ruft `set_link_titles()` und `validate_no_duplicate_active_links()` auf
- **`set_link_titles()`** → befüllt `link_title` automatisch aus dem `title_field` des verlinkten DocTypes
- **`validate_no_duplicate_active_links()`** → verhindert doppelte **aktive** (DocType, Name)-Paare. Stornierte/ersetzte Duplikate sind erlaubt (Historie).
- **`add_link(link_doctype, link_name, betrag=None, bemerkung=None)`** → Programmatischer Helper für `tools.py`. Prüft ob bereits ein aktiver Link existiert (idempotent). Setzt `verknuepft_am` automatisch auf `now()`.
- **`cancel_link(link_doctype, link_name, bemerkung=None, ersetzt=False)`** → Setzt bestehenden aktiven Link auf "storniert" oder "ersetzt". Schreibt Grund in `bemerkung`.

---

## 4. Änderung in `tools.py` — Integration in bestehenden Workflow

**Nur additive Änderungen**, bestehende Logik bleibt 1:1 erhalten.

### Stelle 1: Zeile 518-519 (PE erstellt, noch nicht submitted)
```python
# BESTEHEND (bleibt):
matching_list["hib_trans_doc"].customer = pe_doc.party
# NEU hinzufügen:
matching_list["hib_trans_doc"].add_link("Payment Entry", pe_doc.name,
    betrag=pe_doc.paid_amount, bemerkung="Automatisch erstellt")
# BESTEHEND (bleibt):
matching_list["hib_trans_doc"].save()
```

### Stelle 2: Zeile 538-541 (PE submitted)
```python
# BESTEHEND (bleibt):
pe_doc.submit()
matching_list["hib_trans_doc"].protokoll = pe_doc.remarks
matching_list["hib_trans_doc"].status = "automatisch verbucht"
# NEU hinzufügen — Links zu den zugeordneten Sales Invoices:
for sinv in todo:
    matching_list["hib_trans_doc"].add_link("Sales Invoice", sinv,
        bemerkung="Automatisch zugeordnet")
# BESTEHEND (bleibt):
matching_list["hib_trans_doc"].save()
```

`add_link()` ist idempotent — wenn der PE-Link von Stelle 1 schon existiert, wird er nicht doppelt angelegt.

---

## 5. JavaScript: `hibiscus_connect_transaction.js`

Ergänzungen im bestehenden `refresh`-Handler:

```javascript
// DocType-Filter: nur echte Dokument-Typen zeigen
frm.set_query("link_doctype", "verknuepfungen", function() {
    return { filters: { istable: 0, issingle: 0 } };
});
```

Stornierte/ersetzte Zeilen werden per CSS visuell abgegrenzt (durchgestrichen/ausgegraut) über ein kleines `refresh`-Script das die Zeilen-Formatierung setzt.

---

## 6. Transaktions-Status: Keine neuen Status nötig

Verknüpfung ist **orthogonal** zum Buchungsstatus der Transaktion:
- Eine `"neu"`-Transaktion kann bereits manuell verknüpft sein (z.B. mit einem Vertrag)
- Eine `"automatisch verbucht"`-Transaktion hat automatisch Links + kann weitere manuelle haben

Der **Link-Status** (aktiv/storniert/ersetzt) lebt in der Child Table, nicht auf der Transaktion.

---

## 7. Was NICHT geändert wird

| Datei/Bereich | Grund |
|---|---|
| `match_payment()` | Reine Matching-Logik |
| `match_all_payments()` | Ruft `make_payment_entry()` auf — dort sind die Links |
| `subset_sum()`, `combine_totals()` | Algorithmus-Funktionen |
| Custom Field auf Payment Entry | Weiterhin für Reverse-Lookups nötig |
| `hooks.py` (Sales Invoice on_submit) | SEPA-Logik, unberührt |
| `tasks.py` | Scheduler-Tasks, unberührt |
| List View JS | Keine Änderung nötig |
| Transaktions-Status-Optionen | Keine neuen Status |

---

## 8. Optionaler Backfill bestehender Daten

Nach Migration: Einmaliges Bench-Console-Skript, das bestehende Payment Entries mit `hibiscus_connect_transaction`-Feld findet und entsprechende Child-Table-Einträge nachrüstet (Status "aktiv").

---

## 9. Zusammenfassung der Dateien

**NEU (4 Dateien):**
- `.../doctype/hibiscus_connect_transaction_link/__init__.py`
- `.../doctype/hibiscus_connect_transaction_link/hibiscus_connect_transaction_link.json`
- `.../doctype/hibiscus_connect_transaction_link/hibiscus_connect_transaction_link.py`
- `.../doctype/hibiscus_connect_transaction_link/test_hibiscus_connect_transaction_link.py`

**GEÄNDERT (4 Dateien):**
- `.../hibiscus_connect_transaction/hibiscus_connect_transaction.json` — 2 neue Felder (Section + Table)
- `.../hibiscus_connect_transaction/hibiscus_connect_transaction.py` — Controller mit validate, add_link, cancel_link
- `.../hibiscus_connect_transaction/hibiscus_connect_transaction.js` — DocType-Filter + CSS für stornierte Zeilen
- `hibiscus_connect/tools.py` — 2 Stellen: `add_link()`-Aufrufe in `make_payment_entry()`

---

## 10. Verifikation

1. `bench --site erpnext.itsdave.de migrate` — neue Tabelle wird erstellt
2. Transaktion öffnen → Sektion "Verknüpfungen" sichtbar, DocType-Auswahl gefiltert
3. Manuell Dokument verknüpfen → Titel + Datum werden automatisch gesetzt, Status "aktiv"
4. Duplikat-Verknüpfung (gleicher aktiver Link) → Fehlermeldung
5. Link stornieren → Status "storniert", Zeile ausgegraut, Bemerkung mit Grund
6. Link ersetzen → alter Link "ersetzt", neuer Link "aktiv"
7. "Zahlung verbuchen" → PE + Sales Invoices erscheinen automatisch in Child Table
8. Bestehende Buttons "Zahlung verbuchen" / "Bankkonto erstellen" funktionieren wie bisher
9. `match_all_payments` Bulk-Lauf → alle verarbeiteten Transaktionen haben Links
