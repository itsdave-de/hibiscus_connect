# Custom HTML Block als Workspace Widget

## Aufbau

**HTML:** Container-Struktur
```html
<div id="my-widget">
    <div class="loading">Lade...</div>
    <div class="content" style="display: none;"></div>
</div>
```

**Script:** JavaScript mit `root_element` als Einstiegspunkt
```javascript
const $content = root_element.querySelector(".content");
frappe.call({ method: "..." }).then(r => {
    $content.innerHTML = "...";
});
```

## Shadow DOM

Custom HTML Blocks laufen isoliert im Shadow DOM. Das wird in `frappe.create_shadow_element()` implementiert (siehe `frappe/public/js/frappe/dom.js`).

**Struktur im Shadow DOM:**
```
<custom-block-xxxxx>
  #shadow-root (open)
    ├── <link href="desk.bundle.css">   ← Globale Styles
    ├── <div>...</div>                   ← Dein HTML
    ├── <style>...</style>               ← Dein CSS
    └── <script>...</script>             ← Dein JS (in IIFE)
```

**Wichtig:** Der Shadow DOM ist `open`, d.h. von außen per `.shadowRoot` zugänglich.

## Icons im Shadow DOM

### Das Problem
`<use href="#icon-xxx">` referenziert SVG-Symbole im Hauptdokument. Diese Referenzen funktionieren **nicht** über die Shadow DOM-Grenze hinweg.

### Die Lösung: Symbol-Kopie
Symbole aus dem Hauptdokument in den Shadow DOM kopieren:

```javascript
// === Icon Helper für Shadow DOM ===
var _shadowSymbols = null;
var _copiedSymbols = {};

function ensureSymbolContainer() {
    if (!_shadowSymbols) {
        _shadowSymbols = document.createElement("svg");
        _shadowSymbols.id = "shadow-icons";
        _shadowSymbols.setAttribute("aria-hidden", "true");
        _shadowSymbols.style.cssText = "position:absolute;width:0;height:0;overflow:hidden";
        root_element.appendChild(_shadowSymbols);
    }
    return _shadowSymbols;
}

function icon(symbolId, size) {
    size = size || "sm";
    var shadowId = "s-" + symbolId;
    var container = ensureSymbolContainer();

    // Symbol kopieren falls noch nicht vorhanden
    if (!_copiedSymbols[shadowId]) {
        var src = document.getElementById(symbolId);  // getElementById braucht kein CSS-Escaping!
        if (src) {
            var clone = src.cloneNode(true);
            clone.id = shadowId;
            container.appendChild(clone);
            _copiedSymbols[shadowId] = true;
        }
    }

    // CSS-Klasse je nach Icon-Typ
    var isEspresso = symbolId.startsWith("es-");
    var cssClass = isEspresso ? "es-icon" : "icon";
    if (isEspresso && symbolId.includes("-solid-")) {
        cssClass += " es-solid";
    } else if (isEspresso) {
        cssClass += " es-line";
    }

    // Inline Styles für korrekte Darstellung (wichtig!)
    var style = "width:14px;height:14px;stroke:currentColor;fill:currentColor;overflow:visible;display:block;";

    return '<svg class="' + cssClass + '" style="' + style + '" aria-hidden="true"><use href="#' + shadowId + '"></use></svg>';
}
// === Ende Icon Helper ===

// Verwendung:
$content.innerHTML = icon("icon-check") + " Erledigt";
$content.innerHTML = icon("es-line-search") + " Suchen";
```

### Wichtige SVG-Styles

Icons im Shadow DOM brauchen diese Inline-Styles:

```css
width: 14px;              /* Feste Größe */
height: 14px;
stroke: currentColor;     /* Farbe vom Parent erben */
fill: currentColor;
overflow: visible;        /* Verhindert Abschneiden (es-icon hat overflow:hidden) */
display: block;           /* Entfernt Baseline-Abstand bei inline-Elementen */
```

**Warum Inline Styles?** CSS-Klassen wie `icon-sm` oder `es-icon` aus dem Frappe CSS können unerwünschte Effekte haben (z.B. `overflow: hidden`). Inline Styles überschreiben diese zuverlässig.

### Verfügbare Icon-Sets

| Set | Anzahl | Prefix | Beispiele |
|-----|--------|--------|-----------|
| **Timeless** | ~179 | `icon-` | `icon-check`, `icon-users`, `icon-calendar` |
| **Espresso** | ~269 | `es-line-` / `es-solid-` | `es-line-search`, `es-solid-delete` |

**Alle Icons auflisten (Browser-Konsole):**
```javascript
document.querySelectorAll("symbol").forEach(s => console.log(s.id));
```

### Alternativen

**Unicode-Symbole** (einfach, aber begrenzt):
```javascript
var icons = { check: "✓", warn: "⚠", error: "✕", dot: "●" };
html = icons.check + " OK";
```

**Inline SVG** (unabhängig, aber mehr Code):
```javascript
function inlineSvg(path, viewBox) {
    return '<svg viewBox="' + (viewBox || "0 0 24 24") + '" style="width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.5">' +
           '<path d="' + path + '"/></svg>';
}
var checkIcon = inlineSvg("M20 6L9 17l-5-5");
```

## Layout und Styling

### Inline Styles vs CSS-Klassen

**Empfehlung:** Inline Styles funktionieren im Shadow DOM zuverlässiger als CSS-Klassen, besonders bei komplexeren Layouts. Frappe CSS-Klassen können unerwartete Seiteneffekte haben.

### Buttons mit Icons

```javascript
var btnStyle = "padding: 8px 18px; display: inline-flex; align-items: center; justify-content: center; overflow: visible;";

html += '<button class="btn btn-sm btn-default" style="' + btnStyle + '">' + icon("es-line-reload") + '</button>';
```

**Wichtig bei Buttons:**
- `btn-sm` statt `btn-xs` (mehr Kontrolle über Größe)
- `display: inline-flex` + `align-items: center` für zentrierte Icons
- `overflow: visible` falls Icons abgeschnitten werden

### Badges mit Icons

```javascript
var bgColor = hasError ? "var(--red-100)" : "var(--green-100)";
var textColor = hasError ? "var(--red-600)" : "var(--green-600)";
var badgeIcon = hasError ? icon("es-line-alert-triangle") : icon("icon-tick");

html += '<span style="background-color: ' + bgColor + '; color: ' + textColor + '; padding: 6px 12px; display: inline-flex; align-items: center; gap: 6px; border-radius: 6px; font-weight: 600;">' +
    badgeIcon + '<span>Label</span>' +
'</span>';
```

## Navigation

**Immer `frappe.set_route()` verwenden statt direkter Links!**

```javascript
// FALSCH - direkter Link
html += '<a href="/app/doctype-name">Öffnen</a>';

// RICHTIG - Button mit frappe.set_route
html += '<button class="btn btn-sm btn-default goto-btn">Öffnen</button>';

// Event-Handler
$content.querySelector(".goto-btn").addEventListener("click", function() {
    frappe.set_route("doctype-name");
});

// Oder mit Parametern:
frappe.set_route("doctype-name", "document-id");
```

**Warum?** Frappe ist eine Single Page Application. Direkte Links (`<a href>`) verursachen einen vollständigen Page-Reload, während `frappe.set_route()` die Navigation innerhalb der SPA durchführt (schneller, behält State).

## String-Escaping

Template Literals mit Quotes können Probleme machen:
```javascript
// Problematisch:
html = `<span class="text-muted">Text</span>`;

// Sicher:
html = '<span class="text-muted">Text</span>';

// Bei verschachtelten Quotes:
html = "<div class=\"info\">" + value + "</div>";
```

## CSS-Variablen

Frappe CSS-Variablen sind im Shadow DOM verfügbar:

```css
/* Farben */
--red-100, --red-500, --red-600
--green-100, --green-500, --green-600
--orange-100, --orange-500, --orange-600
--yellow-100, --yellow-500
--blue-100, --blue-500
--gray-100, --gray-200, --gray-500

/* Semantisch */
--primary
--text-color, --text-muted, --text-light
--card-bg, --bg-light-gray
--border-color

/* Icons */
--icon-stroke, --icon-fill
```

## Update via Bench Console

```bash
bench --site SITE console
```

```python
import frappe
block = frappe.get_doc("Custom HTML Block", "NAME")
block.html = '''...'''
block.style = '''...'''
block.script = '''...'''
block.save()
frappe.db.commit()
```

Danach Cache leeren:
```bash
bench --site SITE clear-cache
```

## Debugging

Console-Ausgaben im Script:
```javascript
console.group("Widget Debug");
console.log("root_element:", root_element);
console.log("Shadow DOM children:", root_element.childNodes);
console.groupEnd();
```

## Quellcode-Referenzen

- Shadow DOM Engine: `frappe/public/js/frappe/dom.js` (Zeile ~375)
- Custom Block Widget: `frappe/public/js/frappe/widgets/custom_block_widget.js`
- Icon-Funktion: `frappe/public/js/frappe/utils/utils.js` (Zeile ~1220)
- Timeless Icons: `frappe/public/icons/timeless/icons.svg`
- Espresso Icons: `frappe/public/icons/espresso/icons.svg`
