# TAN-Ablauf-Warnung: Analyse und Konzept

**Stand:** 2025-12-11
**Status:** In Analyse

---

## Ziel

Im Health Widget des Banking Workspace soll angezeigt werden, wann voraussichtlich die nächste TAN-Abfrage (SCA - Strong Customer Authentication) für Umsatzabrufe fällig wird.

---

## Erkenntnisse aus der Recherche

### 1. FinTS/HBCI und PSD2-SCA

- **90/180-Tage-Regel:** Unter PSD2 muss SCA für reine Kontoinformationsabfragen nur alle 90 Tage (manche Banken 180 Tage) erfolgen
- **Bank entscheidet:** Der konkrete Zeitpunkt wird serverseitig von der Bank bestimmt
- **Kein Standard-Feld:** Es gibt kein generisches FinTS-Feld wie `SCA_valid_until` oder `daysUntilNextTan`

### 2. Bank-spezifische Meldungen

| Bank | Code | Meldung | Verfügbar |
|------|------|---------|-----------|
| Sparkassen | 3964 | "X Tage bis zur nächsten TAN-Abfrage" | Ja (14 Tage vorher) |
| Volksbank/Atruvia | - | Keine Vorwarnung | Nein |

**Unsere Bank (Volksbank Lüneburger Heide, BLZ 24060300) sendet KEINE Vorwarnung!**

### 3. Erkannte FinTS-Codes in unseren Logs

| Code | Bedeutung | Nutzbar für Tracking |
|------|-----------|---------------------|
| `3956` | "Starke Kundenauthentifizierung noch ausstehend" | ✅ TAN jetzt erforderlich |
| `9941` | "Sicherheitsfreigabe nicht erfolgreich" | ⚠️ TAN abgelehnt/Timeout |
| `3920` | "Zugelassene TAN-Verfahren für den Benutzer" | ❌ Nur Info |
| `0901` | "PIN gültig" | ❌ Normalbetrieb |

---

## Konten-Struktur

### Alle Konten nutzen denselben Bankzugang

```
BLZ:           24060300 (Volksbank Lüneburger Heide)
Kundennummer:  1337625856
Passport:      1765382902319.pt (eine PIN/TAN-Konfiguration)
Anzahl Konten: 21
```

### Konten nach Typ (acctype)

| acctype | Bezeichnung | Anzahl | Konto-IDs |
|---------|-------------|--------|-----------|
| 1 | Kontokorrent (Giro) | 8 | 1-8 |
| 20 | Termineinlage | 1 | 9 |
| 40 | Darlehen | 6 | 14-19 |
| 50 | Kreditkartenkonto | 5 | 11-13, 20-21 |
| 90 | Geschäftsanteile | 1 | 10 |

---

## Offene Frage: Mehrere TANs bei Ersteinrichtung

### Beobachtung

Bei der Ersteinrichtung am 03.12.2025 waren **mehrere TAN-Eingaben** (4-7) erforderlich, obwohl alle Konten demselben Bankzugang gehören.

### Mögliche Erklärungen

1. **Separate SCA-Zähler pro Produktgruppe:**
   - Die Bank könnte intern verschiedene "Verfügungsberechtigungen" pro Kontoart führen
   - Girokonten, Darlehen, Kreditkarten = separate SCA-Zähler

2. **Erstmalige Client-Registrierung:**
   - Neuer FinTS-Client muss sich bei der Bank registrieren
   - SecureGo/Decoupled TAN für Gerätefreischaltung

3. **BPD/UPD-Synchronisation:**
   - Erstmaliger Abruf der Bank-Parameter-Daten kann TAN erfordern

### Noch zu klären

- [ ] Werden bei der nächsten 90-Tage-Erneuerung wieder mehrere TANs benötigt?
- [ ] Oder nur eine TAN für alle Konten?
- [ ] Kann man aus den Logs ein Muster erkennen, welche Kontoarten zusammen synchronisiert werden?

---

## Verfügbare Datenquellen

### 1. Hibiscus REST-API (bereits implementiert)

```python
# api.py - Zeile 242
@frappe.whitelist()
def get_hibiscus_server_logs(count=100, level=None, contains=None):
    """Get log entries from the Hibiscus Payment Server."""

# api.py - Zeile 332
@frappe.whitelist()
def get_hibiscus_sync_logs(count=50):
    """Get synchronization-related log entries."""
```

### 2. Hibiscus Datenbank (direkt)

```sql
-- Protokoll-Tabelle mit Erfolgen (typ=1) und Fehlern (typ=2)
SELECT * FROM protokoll WHERE kommentar LIKE '%3956%';

-- Letzter erfolgreicher Sync nach TAN-Fehler = TAN wurde eingegeben
SELECT MIN(datum) as tan_auth_time
FROM protokoll
WHERE typ = 1 AND datum > (
    SELECT MAX(datum) FROM protokoll WHERE kommentar LIKE '%3956%'
);
```

### 3. Jameica Log-Dateien

```
/home/banking/.jameica/jameica.log          # Aktuelles Log
/home/banking/.jameica/jameica.log-*.gz     # Archivierte Logs
```

Relevante Log-Patterns:
- `tan needed: true` - TAN wurde angefordert (bisher nicht gefunden!)
- `tan needed: false` - Keine TAN nötig (Normalfall)
- `execution state: tan needed:` - Status nach Job-Ausführung

---

## Geplanter Lösungsansatz

### Heuristischer Timer (da keine Bank-Vorwarnung)

```
┌─────────────────────────────────────────────────────────────────┐
│                    TAN-Tracking Workflow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Erfolgreicher Sync nach TAN-Fehler (3956) erkannt?         │
│     └─> Speichere: last_sca_authentication = NOW()              │
│                                                                 │
│  2. Bei jedem Health-Check:                                     │
│     days_since_tan = NOW() - last_sca_authentication            │
│     days_remaining = 90 - days_since_tan                        │
│                                                                 │
│  3. Warnstufen:                                                 │
│     • days_remaining > 14  → Grün (OK)                          │
│     • days_remaining <= 14 → Gelb (Bald fällig)                 │
│     • days_remaining <= 3  → Rot (Dringend)                     │
│     • Fehler 3956 erkannt  → Rot (Jetzt TAN eingeben!)         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Tracking-Ebene

**Option A:** Ein Timer pro Bankzugang (BLZ + Kundennummer)
- Einfacher zu implementieren
- Könnte ungenau sein, wenn mehrere SCA-Zähler existieren

**Option B:** Ein Timer pro Kontoart (acctype)
- Komplexer
- Möglicherweise genauer, falls Bank separate Zähler führt

**Empfehlung:** Mit Option A starten, bei Bedarf auf B erweitern.

---

## Nächste Schritte

1. [ ] Beobachten, wie sich die TANs beim nächsten 90-Tage-Zyklus verhalten
2. [ ] API-Methode `get_tan_status()` implementieren
3. [ ] Neues Feld `last_sca_authentication` in Hibiscus Connect Settings oder separatem DocType
4. [ ] Health Widget im Banking Workspace erweitern
5. [ ] Caveat in UI anzeigen: "Schätzung - kann durch Web/App-Login zurückgesetzt werden"

---

## Relevante Dateien

```
apps/hibiscus_connect/hibiscus_connect/api.py                    # Backend-API
apps/hibiscus_connect/hibiscus_connect/hibiscus_rest_client.py   # REST-Client
```

## Server-Zugang

```
SSH: ssh root@hbci.suedsee-camp.de
Hibiscus Home: /home/banking/
Jameica Config: /home/banking/.jameica/
Datenbank: hibiscus (MariaDB, User: hibiscus)
```

---

## Protokoll-Beispiel: TAN-Fehler und Erfolg

**10.12.2025 - TAN-Anforderung:**
```
16:47:07 | Konto 6 | 3956 - Starke Kundenauthentifizierung noch ausstehend | Fehler
16:47:55 | Konto 7 | 9941 - Sicherheitsfreigabe nicht erfolgreich (abgebrochen) | Fehler
16:48:27 | Konto 14+ | Umsätze abgerufen | Erfolg (TAN wurde eingegeben)
```

→ `last_sca_authentication` = 2025-12-10 16:48:27
→ Geschätzte nächste TAN: ~2026-03-10 (+ 90 Tage)
