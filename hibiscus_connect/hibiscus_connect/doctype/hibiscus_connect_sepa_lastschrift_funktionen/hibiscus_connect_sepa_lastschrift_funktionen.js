// Copyright (c) 2025, itsdave GmbH and contributors
// For license information, please see license.txt

// Globale Variable fuer DataTable-Instanz
let lastschriften_datatable = null;
let lastschriften_data = [];

frappe.ui.form.on("Hibiscus Connect SEPA Lastschrift Funktionen", {
	refresh(frm) {
		frm.disable_save();
		frm.add_custom_button(__("Lastschriften neu laden"), function() {
			frm.trigger("load_lastschriften");
		});

		// Automatisch Lastschriften laden beim Öffnen der Seite
		frm.trigger("load_lastschriften");
	},

	load_lastschriften(frm) {
		frm.fields_dict.lastschriften_html.$wrapper.html(`
			<div class="lastschriften-container">
				<p><i class="fa fa-spinner fa-spin"></i> Lade Lastschriften vom Hibiscus Server...</p>
			</div>
		`);

		frappe.call({
			method: "hibiscus_connect.hibiscus_connect.doctype.hibiscus_connect_sepa_lastschrift_funktionen.hibiscus_connect_sepa_lastschrift_funktionen.get_lastschriften",
			args: {
				filter_status: "offen"
			},
			callback: function(r) {
				if (r.message) {
					render_lastschriften_table(frm, r.message);
				}
			},
			error: function(r) {
				frm.fields_dict.lastschriften_html.$wrapper.html(`
					<div class="lastschriften-container">
						<p class="text-danger">Fehler beim Laden der Lastschriften. Bitte pruefen Sie die Browser-Konsole.</p>
					</div>
				`);
			}
		});
	}
});

function render_lastschriften_table(frm, data) {
	lastschriften_data = data.lastschriften || [];

	let stats_html = `
		<div class="lastschriften-stats" style="margin-bottom: 15px; padding: 10px; background: var(--subtle-fg); border-radius: 5px;">
			<span style="margin-right: 20px;"><strong>Gesamt:</strong> ${data.count_gesamt}</span>
			<span style="margin-right: 20px;"><strong>Offen:</strong> ${data.count_offen} (${data.total_offen})</span>
			<span><strong>Ausgefuehrt:</strong> ${data.count_ausgefuehrt} (${data.total_ausgefuehrt})</span>
		</div>
	`;

	// Bulk-Aktions-Leiste
	let bulk_actions_html = `
		<div class="bulk-actions-bar" style="margin-bottom: 15px; padding: 10px; background: var(--subtle-accent); border-radius: 5px; display: none;">
			<span class="selected-count" style="margin-right: 15px; font-weight: bold;">0 ausgewaehlt</span>
			<button class="btn btn-sm btn-primary bulk-set-next-termin-btn">
				<i class="fa fa-calendar"></i> Faellige auf naechsten Zieltermin setzen
			</button>
		</div>
	`;

	if (lastschriften_data.length === 0) {
		frm.fields_dict.lastschriften_html.$wrapper.html(`
			<div class="lastschriften-container">
				${stats_html}
				<p class="text-muted">Keine Lastschriften gefunden.</p>
			</div>
		`);
		return;
	}

	let today = frappe.datetime.get_today();

	// Tabelle als HTML erstellen
	let table_html = `
		<div class="lastschriften-container">
			${stats_html}
			${bulk_actions_html}
			<div class="table-responsive">
				<table id="lastschriften-datatable" class="table table-bordered table-hover" style="width: 100%;">
					<thead style="background: var(--subtle-fg);">
						<tr>
							<th style="width: 40px; text-align: center;">
								<input type="checkbox" class="select-all-checkbox" title="Alle auswaehlen">
							</th>
							<th>Status</th>
							<th>Zieltermin</th>
							<th>Name</th>
							<th>IBAN</th>
							<th>Verwendungszweck</th>
							<th>Typ</th>
							<th>Sequenz</th>
							<th style="text-align: right;">Betrag</th>
							<th style="width: 50px;"></th>
						</tr>
					</thead>
					<tbody>
	`;

	lastschriften_data.forEach(function(ls) {
		let status_html = ls.ausgefuehrt
			? '<i class="fa fa-check-circle text-success"></i> Ausgefuehrt'
			: '<i class="fa fa-clock-o text-warning"></i> Offen';

		// Zieltermin (targetdate) ist das maßgebliche Datum für den Bankeinzug
		let zieltermin_html = ls.targetdate_display || "-";
		let zieltermin_class = "";
		if (ls.targetdate && ls.targetdate < today && !ls.ausgefuehrt) {
			zieltermin_class = "text-danger font-weight-bold";
		}

		let checkbox_html = ls.ausgefuehrt
			? '<input type="checkbox" class="row-checkbox" disabled>'
			: `<input type="checkbox" class="row-checkbox" data-id="${ls.id}">`;

		let edit_btn_html = ls.ausgefuehrt
			? '<button class="btn btn-xs btn-default edit-lastschrift-btn" disabled><i class="fa fa-pencil"></i></button>'
			: `<button class="btn btn-xs btn-default edit-lastschrift-btn" data-id="${ls.id}"><i class="fa fa-pencil"></i></button>`;

		table_html += `
			<tr data-id="${ls.id}" data-sepatype="${ls.sepatype || 'CORE'}" data-sequencetype="${ls.sequencetype || 'RCUR'}">
				<td style="text-align: center;">${checkbox_html}</td>
				<td data-order="${ls.ausgefuehrt ? 1 : 0}">${status_html}</td>
				<td data-order="${ls.targetdate || '9999-99-99'}" class="${zieltermin_class}">${zieltermin_html}</td>
				<td>${ls.name || "-"}</td>
				<td style="font-family: monospace; font-size: 0.9em;">${ls.kontonummer || "-"}</td>
				<td>${ls.verwendungszweck || "-"}</td>
				<td>${ls.sepatype || "-"}</td>
				<td>${ls.sequencetype_label || "-"}</td>
				<td data-order="${ls.betrag || 0}" style="text-align: right; font-weight: bold;">${ls.betrag_formatted}</td>
				<td style="text-align: center;">${edit_btn_html}</td>
			</tr>
		`;
	});

	table_html += `
					</tbody>
				</table>
			</div>
			<p class="text-muted" style="font-size: 0.85em; margin-top: 10px;">
				<i class="fa fa-info-circle"></i> <b>Zieltermin</b> = Datum fuer Bankeinzug (massgeblich). Klicken Sie auf Spaltenueberschriften zum Sortieren.
			</p>
		</div>
	`;

	frm.fields_dict.lastschriften_html.$wrapper.html(table_html);

	// Sortierbare Header einrichten (ohne externe Bibliothek)
	setup_sortable_table(frm);

	// Event-Handler einrichten
	setup_checkbox_handlers(frm);
	setup_bulk_actions(frm);
	setup_edit_handlers(frm);
}

function setup_sortable_table(frm) {
	let $wrapper = frm.fields_dict.lastschriften_html.$wrapper;
	let $table = $wrapper.find('#lastschriften-datatable');
	let $headers = $table.find('thead th');
	let currentSortColumn = -1;
	let currentSortOrder = 'asc';

	// Sortierbare Spalten markieren (nicht Checkbox und Aktionen)
	$headers.each(function(index) {
		if (index !== 0 && index !== 9) {
			$(this).css('cursor', 'pointer');
			$(this).append(' <span class="sort-indicator"></span>');
			$(this).hover(
				function() { $(this).css('background-color', 'var(--subtle-accent)'); },
				function() { $(this).css('background-color', ''); }
			);
		}
	});

	// Click-Handler fuer Header
	$headers.on('click', function() {
		let colIndex = $(this).index();

		// Checkbox und Aktionen nicht sortierbar
		if (colIndex === 0 || colIndex === 9) return;

		// Sortierrichtung umschalten
		if (currentSortColumn === colIndex) {
			currentSortOrder = currentSortOrder === 'asc' ? 'desc' : 'asc';
		} else {
			currentSortColumn = colIndex;
			currentSortOrder = 'asc';
		}

		// Sortierindikatoren aktualisieren
		$headers.find('.sort-indicator').text('');
		$(this).find('.sort-indicator').text(currentSortOrder === 'asc' ? ' ↑' : ' ↓');

		// Zeilen sortieren
		let $tbody = $table.find('tbody');
		let $rows = $tbody.find('tr').get();

		$rows.sort(function(a, b) {
			let $cellA = $(a).find('td').eq(colIndex);
			let $cellB = $(b).find('td').eq(colIndex);

			// data-order Attribut verwenden falls vorhanden
			let valA = $cellA.attr('data-order');
			let valB = $cellB.attr('data-order');

			// Falls kein data-order, Textinhalt verwenden
			if (valA === undefined) valA = $cellA.text().trim();
			if (valB === undefined) valB = $cellB.text().trim();

			// Numerischer Vergleich versuchen
			let numA = parseFloat(valA);
			let numB = parseFloat(valB);

			if (!isNaN(numA) && !isNaN(numB)) {
				// Numerische Sortierung
				if (currentSortOrder === 'asc') {
					return numA - numB;
				}
				return numB - numA;
			}

			// String-Sortierung
			valA = String(valA).toLowerCase();
			valB = String(valB).toLowerCase();

			if (currentSortOrder === 'asc') {
				return valA.localeCompare(valB, 'de');
			}
			return valB.localeCompare(valA, 'de');
		});

		// Sortierte Zeilen wieder einfuegen
		$.each($rows, function(index, row) {
			$tbody.append(row);
		});
	});

	// Initial nach Termin sortieren (Spalte 2)
	$headers.eq(2).trigger('click');
}

function setup_checkbox_handlers(frm) {
	let $wrapper = frm.fields_dict.lastschriften_html.$wrapper;

	// "Alle auswaehlen" Checkbox
	$wrapper.find(".select-all-checkbox").on("change", function() {
		let checked = $(this).prop("checked");
		$wrapper.find(".row-checkbox:not(:disabled)").prop("checked", checked);
		update_selection_count(frm);
	});

	// Einzelne Checkboxen
	$wrapper.on("change", ".row-checkbox", function() {
		update_selection_count(frm);

		// "Alle auswaehlen" Status aktualisieren
		let total = $wrapper.find(".row-checkbox:not(:disabled)").length;
		let checked = $wrapper.find(".row-checkbox:checked").length;
		$wrapper.find(".select-all-checkbox").prop("checked", total > 0 && total === checked);
	});
}

function update_selection_count(frm) {
	let $wrapper = frm.fields_dict.lastschriften_html.$wrapper;
	let selected = $wrapper.find(".row-checkbox:checked").length;

	$wrapper.find(".selected-count").text(selected + " ausgewaehlt");

	// Bulk-Aktions-Leiste ein-/ausblenden
	if (selected > 0) {
		$wrapper.find(".bulk-actions-bar").slideDown(200);
	} else {
		$wrapper.find(".bulk-actions-bar").slideUp(200);
	}
}

function get_selected_ids(frm) {
	let $wrapper = frm.fields_dict.lastschriften_html.$wrapper;
	let ids = [];
	$wrapper.find(".row-checkbox:checked").each(function() {
		ids.push($(this).data("id"));
	});
	return ids;
}

function setup_bulk_actions(frm) {
	let $wrapper = frm.fields_dict.lastschriften_html.$wrapper;

	// Bulk: Faellige auf naechsten Termin setzen
	$wrapper.find(".bulk-set-next-termin-btn").on("click", function() {
		let selected_ids = get_selected_ids(frm);

		if (selected_ids.length === 0) {
			frappe.msgprint("Bitte waehlen Sie mindestens eine Lastschrift aus.");
			return;
		}

		frappe.confirm(
			`Moechten Sie fuer <b>${selected_ids.length}</b> ausgewaehlte Lastschrift(en) den <b>Zieltermin</b> auf den naechstmoeglichen Termin setzen?<br><br>
			<small class="text-muted">
				<b>SEPA-Vorlaufzeiten (ab heute):</b><br>
				- CORE Erstlastschrift (FRST): 5 Werktage<br>
				- CORE Folgelastschrift (RCUR): 2 Werktage<br>
				- B2B: 1 Werktag<br><br>
				Nur Lastschriften mit bereits abgelaufenem Zieltermin werden aktualisiert.
			</small>`,
			function() {
				frappe.call({
					method: "hibiscus_connect.hibiscus_connect.doctype.hibiscus_connect_sepa_lastschrift_funktionen.hibiscus_connect_sepa_lastschrift_funktionen.bulk_set_next_termin",
					args: {
						lastschrift_ids: JSON.stringify(selected_ids)
					},
					callback: function(r) {
						if (r.message) {
							// Tabelle neu laden
							frm.trigger("load_lastschriften");
						}
					}
				});
			}
		);
	});
}

function setup_edit_handlers(frm) {
	let $wrapper = frm.fields_dict.lastschriften_html.$wrapper;

	// Click-Handler fuer Bearbeiten-Button
	$wrapper.on("click", ".edit-lastschrift-btn", function(e) {
		e.stopPropagation();
		let id = $(this).data("id");
		if (id && !$(this).prop("disabled")) {
			open_edit_dialog(frm, id);
		}
	});
}

function open_edit_dialog(frm, lastschrift_id) {
	// Erst Daten laden
	frappe.call({
		method: "hibiscus_connect.hibiscus_connect.doctype.hibiscus_connect_sepa_lastschrift_funktionen.hibiscus_connect_sepa_lastschrift_funktionen.get_lastschrift",
		args: {
			lastschrift_id: lastschrift_id
		},
		callback: function(r) {
			if (r.message) {
				show_edit_dialog(frm, r.message);
			}
		}
	});
}

function show_edit_dialog(frm, data) {
	let d = new frappe.ui.Dialog({
		title: "Lastschrift bearbeiten",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "info_html",
				options: `
					<div style="margin-bottom: 15px; padding: 10px; background: var(--subtle-fg); border-radius: 5px;">
						<p style="margin: 0;"><strong>Name:</strong> ${data.name}</p>
						<p style="margin: 0;"><strong>IBAN:</strong> ${data.kontonummer}</p>
						<p style="margin: 0;"><strong>Betrag:</strong> ${data.betrag_formatted}</p>
						<p style="margin: 0;"><strong>Verwendungszweck:</strong> ${data.verwendungszweck}</p>
						<p style="margin: 0;"><strong>Mandat-ID:</strong> ${data.mandateid}</p>
					</div>
				`
			},
			{
				fieldtype: "Column Break"
			},
			{
				fieldtype: "Section Break",
				label: "Termine anpassen"
			},
			{
				fieldtype: "Date",
				fieldname: "targetdate",
				label: "Zieltermin (Bankeinzug)",
				default: data.targetdate,
				description: "Das Datum fuer den Bankeinzug - massgeblich!"
			},
			{
				fieldtype: "Column Break"
			},
			{
				fieldtype: "Date",
				fieldname: "termin",
				label: "Erinnerungstermin (Hibiscus)",
				default: data.termin,
				description: "Hibiscus-interner Erinnerungstermin"
			},
			{
				fieldtype: "Section Break"
			},
			{
				fieldtype: "HTML",
				fieldname: "delete_section",
				options: `
					<div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-color);">
						<button class="btn btn-danger btn-sm delete-lastschrift-btn" style="width: 100%;">
							<i class="fa fa-trash"></i> Lastschrift loeschen
						</button>
					</div>
				`
			}
		],
		primary_action_label: "Speichern",
		primary_action: function(values) {
			// Pruefen ob sich etwas geaendert hat
			let termin_changed = values.termin !== data.termin;
			let targetdate_changed = values.targetdate !== data.targetdate;

			if (!termin_changed && !targetdate_changed) {
				frappe.msgprint("Keine Aenderungen vorgenommen.");
				return;
			}

			frappe.call({
				method: "hibiscus_connect.hibiscus_connect.doctype.hibiscus_connect_sepa_lastschrift_funktionen.hibiscus_connect_sepa_lastschrift_funktionen.update_lastschrift",
				args: {
					lastschrift_id: data.id,
					termin: termin_changed ? values.termin : null,
					targetdate: targetdate_changed ? values.targetdate : null
				},
				callback: function(r) {
					if (r.message && r.message.success) {
						d.hide();
						// Tabelle neu laden
						frm.trigger("load_lastschriften");
					}
				}
			});
		}
	});

	// Loeschen-Button Handler
	d.$wrapper.find(".delete-lastschrift-btn").on("click", function() {
		frappe.confirm(
			`Sind Sie sicher, dass Sie diese Lastschrift loeschen moechten?<br><br>
			<strong>Name:</strong> ${data.name}<br>
			<strong>Betrag:</strong> ${data.betrag_formatted}<br>
			<strong>Verwendungszweck:</strong> ${data.verwendungszweck}`,
			function() {
				frappe.call({
					method: "hibiscus_connect.hibiscus_connect.doctype.hibiscus_connect_sepa_lastschrift_funktionen.hibiscus_connect_sepa_lastschrift_funktionen.delete_lastschrift",
					args: {
						lastschrift_id: data.id
					},
					callback: function(r) {
						if (r.message && r.message.success) {
							d.hide();
							// Tabelle neu laden
							frm.trigger("load_lastschriften");
						}
					}
				});
			}
		);
	});

	d.show();
}
