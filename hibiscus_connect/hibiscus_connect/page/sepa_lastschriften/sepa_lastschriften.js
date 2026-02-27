// SEPA Lastschriften Page - Version 2.0 (2025-12-12)
// Mit verbesserter Race-Condition-Prevention und defensive Programmierung

frappe.pages['sepa-lastschriften'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'SEPA Lastschriften',
		single_column: true
	});

	// Page-Referenz speichern
	wrapper.page = page;

	// Aktueller Filter-Status und Request-Counter für Race Condition Prevention
	page.filter_status = 'alle';
	page.request_id = 0;
	page.is_loading = false;

	page.main.html(frappe.render_template("sepa_lastschriften"));

	// Refresh Button
	page.set_primary_action(__('Aktualisieren'), function() {
		load_lastschriften(page);
	}, 'refresh');

	// Initial laden
	load_lastschriften(page);
};

frappe.pages['sepa-lastschriften'].refresh = function(wrapper) {
	// Nicht automatisch neu laden beim Tab-Wechsel
};

function load_lastschriften(page) {
	// Verhindere parallele Aufrufe
	if (page.is_loading) {
		return;
	}

	page.is_loading = true;
	page.request_id++;
	let current_request_id = page.request_id;

	// Loading-Spinner nur beim ersten Laden anzeigen
	page.main.find('.lastschriften-container').html(`
		<div class="text-center" style="padding: 50px;">
			<div class="spinner-border text-primary" role="status">
				<span class="sr-only">Laden...</span>
			</div>
			<p class="mt-3 text-muted">Lade SEPA-Lastschriften aus Hibiscus...</p>
		</div>
	`);

	// Filter-Status zum Zeitpunkt des Requests speichern
	let request_filter = page.filter_status;

	frappe.call({
		method: 'hibiscus_connect.hibiscus_connect.page.sepa_lastschriften.sepa_lastschriften.get_sepa_lastschriften',
		args: {
			filter_status: request_filter
		},
		callback: function(r) {
			// Nur verarbeiten wenn dies der letzte Request ist
			if (current_request_id !== page.request_id) {
				console.log('SEPA: Stale request ignored', current_request_id, 'vs', page.request_id);
				return;
			}

			page.is_loading = false;

			if (r && r.message) {
				render_lastschriften(page, r.message);
			} else {
				console.warn('SEPA: Keine Daten empfangen', r);
				render_lastschriften(page, {});
			}
		},
		error: function(r) {
			// Bei Error immer is_loading zurücksetzen
			page.is_loading = false;

			if (current_request_id !== page.request_id) {
				console.log('SEPA: Stale error ignored', current_request_id, 'vs', page.request_id);
				return;
			}

			page.main.find('.lastschriften-container').html(`
				<div class="alert alert-danger">
					<strong>Fehler:</strong> Lastschriften konnten nicht geladen werden.
				</div>
			`);
		}
	});
}

function render_lastschriften(page, data) {
	// v2: Verbesserte Null-Checks und defensive Programmierung

	// Sicherstellen dass data ein Objekt ist
	if (!data || typeof data !== 'object') {
		console.warn('SEPA Lastschriften: Ungültige Daten empfangen', data);
		data = {};
	}

	// Explizite Konvertierung zu Number mit Fallback
	let count_gesamt = parseInt(data.count_gesamt, 10);
	if (isNaN(count_gesamt)) count_gesamt = 0;

	let count_offen = parseInt(data.count_offen, 10);
	if (isNaN(count_offen)) count_offen = 0;

	let count_ausgefuehrt = parseInt(data.count_ausgefuehrt, 10);
	if (isNaN(count_ausgefuehrt)) count_ausgefuehrt = 0;

	let count_gefiltert = parseInt(data.count_gefiltert, 10);
	if (isNaN(count_gefiltert)) count_gefiltert = 0;

	// String-Werte mit Fallback
	let total_gesamt_formatted = (data.total_gesamt_formatted && typeof data.total_gesamt_formatted === 'string')
		? data.total_gesamt_formatted : '0,00 EUR';
	let total_offen_formatted = (data.total_offen_formatted && typeof data.total_offen_formatted === 'string')
		? data.total_offen_formatted : '0,00 EUR';
	let total_ausgefuehrt_formatted = (data.total_ausgefuehrt_formatted && typeof data.total_ausgefuehrt_formatted === 'string')
		? data.total_ausgefuehrt_formatted : '0,00 EUR';
	let total_gefiltert_formatted = (data.total_gefiltert_formatted && typeof data.total_gefiltert_formatted === 'string')
		? data.total_gefiltert_formatted : '0,00 EUR';

	let filter_status = page.filter_status;

	let html = `
		<div class="frappe-card mb-4">
			<div class="card-body">
				<!-- Filter Buttons -->
				<div class="d-flex flex-wrap align-items-center mb-3">
					<span class="mr-3 font-weight-bold">Filter:</span>
					<div class="btn-group">
						<button class="btn btn-sm filter-btn ${filter_status === 'alle' ? 'btn-primary' : 'btn-default'}"
								data-filter="alle">
							Alle (${count_gesamt})
						</button>
						<button class="btn btn-sm filter-btn ${filter_status === 'offen' ? 'btn-primary' : 'btn-default'}"
								data-filter="offen">
							Offen (${count_offen})
						</button>
						<button class="btn btn-sm filter-btn ${filter_status === 'ausgefuehrt' ? 'btn-primary' : 'btn-default'}"
								data-filter="ausgefuehrt">
							Ausgef&uuml;hrt (${count_ausgefuehrt})
						</button>
					</div>
				</div>

				<!-- Statistik-Karten -->
				<div class="row">
					<div class="col-md-4">
						<div class="stat-card stat-card-total">
							<div class="stat-label">Gesamt</div>
							<div class="stat-value">${count_gesamt} Lastschriften</div>
							<div class="stat-amount">${total_gesamt_formatted}</div>
						</div>
					</div>
					<div class="col-md-4">
						<div class="stat-card stat-card-offen">
							<div class="stat-label">Offen</div>
							<div class="stat-value">${count_offen} Lastschriften</div>
							<div class="stat-amount">${total_offen_formatted}</div>
						</div>
					</div>
					<div class="col-md-4">
						<div class="stat-card stat-card-ausgefuehrt">
							<div class="stat-label">Ausgef&uuml;hrt</div>
							<div class="stat-value">${count_ausgefuehrt} Lastschriften</div>
							<div class="stat-amount">${total_ausgefuehrt_formatted}</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<div class="frappe-card">
			<div class="card-body p-0">
				<div class="table-responsive">
					<table class="table table-hover mb-0">
						<thead class="thead-light">
							<tr>
								<th style="width: 80px;">Status</th>
								<th style="width: 100px;">Termin</th>
								<th style="width: 130px;">Rechnung</th>
								<th>Empf&auml;nger</th>
								<th style="width: 200px;">IBAN</th>
								<th style="width: 90px;">Typ</th>
								<th style="width: 90px;">Sequenz</th>
								<th style="width: 120px; text-align: right;">Betrag</th>
							</tr>
						</thead>
						<tbody>
	`;

	let lastschriften = data.lastschriften || [];

	if (lastschriften.length === 0) {
		html += `
			<tr>
				<td colspan="8" class="text-center text-muted py-4">
					Keine Lastschriften gefunden.
				</td>
			</tr>
		`;
	} else {
		lastschriften.forEach(function(ls) {
			// Status Badge
			let status_badge = ls.ausgefuehrt
				? '<span class="badge badge-success">Ausgef&uuml;hrt</span>'
				: '<span class="badge badge-warning">Offen</span>';

			// Rechnungslink
			let sinv_link = ls.verwendungszweck || '-';
			if (ls.sinv_exists && ls.verwendungszweck) {
				sinv_link = `<a href="/app/sales-invoice/${ls.verwendungszweck}" class="font-weight-bold">${ls.verwendungszweck}</a>`;
				if (ls.sinv_status === 'Paid') {
					sinv_link += '<br><small class="text-success">Bezahlt</small>';
				} else if (ls.sinv_status === 'Overdue') {
					sinv_link += '<br><small class="text-danger">&Uuml;berf&auml;llig</small>';
				} else if (ls.sinv_status) {
					sinv_link += '<br><small class="text-muted">' + ls.sinv_status + '</small>';
				}
			}

			// Sequenztyp Badge
			let seq_badge = '';
			switch(ls.sequencetype) {
				case 'FRST':
					seq_badge = '<span class="badge badge-info">Erstmalig</span>';
					break;
				case 'RCUR':
					seq_badge = '<span class="badge badge-secondary">Wiederk.</span>';
					break;
				case 'FNAL':
					seq_badge = '<span class="badge badge-dark">Letztmalig</span>';
					break;
				default:
					seq_badge = '<span class="badge badge-light">' + (ls.sequencetype || '-') + '</span>';
			}

			// SEPA-Typ Badge
			let sepa_badge = ls.sepatype === 'B2B'
				? '<span class="badge badge-primary">B2B</span>'
				: '<span class="badge badge-secondary">' + (ls.sepatype || '-') + '</span>';

			html += `
				<tr class="${ls.ausgefuehrt ? 'row-ausgefuehrt' : 'row-offen'}">
					<td>${status_badge}</td>
					<td>
						<span class="font-weight-bold">${ls.termin_display || '-'}</span>
						${ls.targetdate_display ? '<br><small class="text-muted">F&auml;llig: ' + ls.targetdate_display + '</small>' : ''}
					</td>
					<td>${sinv_link}</td>
					<td>
						<div class="font-weight-bold">${frappe.utils.escape_html(ls.name || '')}</div>
						${ls.sinv_customer ? '<small class="text-muted">' + frappe.utils.escape_html(ls.sinv_customer) + '</small>' : ''}
						${ls.mandateid ? '<br><small class="text-muted">Mandat: ' + ls.mandateid + '</small>' : ''}
					</td>
					<td>
						<code class="iban-code">${ls.kontonummer || ''}</code>
						<br><small class="text-muted">${ls.blz || ''}</small>
					</td>
					<td>${sepa_badge}</td>
					<td>${seq_badge}</td>
					<td style="text-align: right;">
						<span class="font-weight-bold betrag">${ls.betrag_formatted || '0,00 EUR'}</span>
					</td>
				</tr>
			`;
		});
	}

	html += `
						</tbody>
					</table>
				</div>
			</div>
			<div class="card-footer bg-light">
				<div class="d-flex justify-content-between align-items-center">
					<span class="text-muted">
						Zeige ${count_gefiltert} von ${count_gesamt} Lastschriften
					</span>
					<span class="font-weight-bold">
						Summe: ${total_gefiltert_formatted}
					</span>
				</div>
			</div>
		</div>
	`;

	page.main.find('.lastschriften-container').html(html);

	// Event-Handler für Filter-Buttons nach dem Rendern binden
	page.main.find('.filter-btn').off('click').on('click', function() {
		let new_filter = $(this).data('filter');
		if (new_filter !== page.filter_status && !page.is_loading) {
			page.filter_status = new_filter;
			load_lastschriften(page);
		}
	});
}
