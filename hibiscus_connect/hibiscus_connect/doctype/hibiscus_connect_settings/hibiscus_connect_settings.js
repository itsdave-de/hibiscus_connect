// Copyright (c) 2021, itsdave GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('Hibiscus Connect Settings', {
	refresh: function(frm) {
		// Fetch Transactions button
		frm.add_custom_button(__('Fetch Transactions'), function(){
			frappe.call({
				method: 'hibiscus_connect.tasks.fetch_transactions_now',
				freeze: true,
				freeze_message: __('Fetching transactions...'),
				callback: function(r) {
					if (r.message) {
						show_fetch_result(r.message);
					}
				}
			});
		});

		// Create/Update Accounts button
		frm.add_custom_button(__('Create/Update Accounts'), function(){
			frappe.call({
				method: 'hibiscus_connect.tools.get_accounts_from_hibiscus_server_for_dialog',
				callback: function(r){
					// Add "Select All" checkbox at the beginning
					let fields = [
						{
							fieldtype: 'Check',
							fieldname: 'select_all',
							label: __('Select All'),
							onchange: function() {
								let select_all = konten_anlegen.get_value('select_all');
								// Toggle all other checkboxes
								r.message.forEach(function(field) {
									konten_anlegen.set_value(field.fieldname, select_all ? 1 : 0);
								});
							}
						},
						{
							fieldtype: 'Section Break'
						}
					];
					// Add account fields
					fields = fields.concat(r.message);

					let konten_anlegen = new frappe.ui.Dialog({
						title: __('Select accounts to create or update:'),
						fields: fields,
						primary_action_label: __('Submit'),
						primary_action(values) {
							// Remove select_all from values before sending
							delete values.select_all;
							frappe.call({
								method: 'hibiscus_connect.tools.create_or_update_accounts',
								args: { dialog_accounts: values },
								freeze: true,
								freeze_message: __('Processing accounts...'),
								callback: function(r){
									konten_anlegen.hide();
									if (r.message) {
										let msg = '';
										if (r.message.created > 0) {
											msg += __('Created') + ': ' + r.message.created + ' ' + __('account(s)') + '<br>';
										}
										if (r.message.updated > 0) {
											msg += __('Updated') + ': ' + r.message.updated + ' ' + __('account(s)');
										}
										if (msg) {
											frappe.msgprint({
												title: __('Accounts Processed'),
												indicator: 'green',
												message: msg
											});
										}
									}
								}
							})
						}
					});
					konten_anlegen.show();
				}
			})
		});
	},

	test_connection: function(frm) {
		frappe.call({
			method: 'test_connection',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('Testing connection...'),
			callback: function(r) {
				if (r.message) {
					show_connection_result(r.message);
				}
			}
		});
	},

	import_blz_button: function(frm) {
		frappe.call({
			method: 'import_bank_codes',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('Importing bank codes from Bundesbank...'),
			callback: function(r) {
				if (r.message) {
					show_blz_import_result(r.message);
					frm.reload_doc();
				}
			}
		});
	}
});

function show_connection_result(result) {
	if (result.success) {
		// Format number with German locale (dot as thousand separator, comma as decimal)
		function formatBalance(num, currency) {
			return num.toLocaleString('de-DE', {
				minimumFractionDigits: 2,
				maximumFractionDigits: 2
			}) + ' ' + currency;
		}

		// Build table rows
		let rows = result.accounts.map(acc => `
			<tr>
				<td>${acc.id}</td>
				<td>${acc.name}</td>
				<td style="font-family: monospace;">${acc.iban}</td>
				<td>${acc.bic}</td>
				<td style="text-align: right; font-family: monospace;">${formatBalance(acc.balance, acc.currency)}</td>
			</tr>
		`).join('');

		let html = `
			<div style="margin-bottom: 15px;">
				<span class="indicator green"></span>
				<strong>${__('Connection successful!')}</strong><br>
				${__('Found')} <strong>${result.accounts.length}</strong> ${__('bank account(s) on')} ${result.server}
			</div>
			<table class="table table-bordered table-condensed" style="font-size: 12px; margin-bottom: 0;">
				<thead>
					<tr style="background-color: var(--bg-light-gray);">
						<th>ID</th>
						<th>${__('Name')}</th>
						<th>IBAN</th>
						<th>BIC</th>
						<th style="text-align: right;">${__('Balance')}</th>
					</tr>
				</thead>
				<tbody>
					${rows}
				</tbody>
			</table>
		`;

		let dialog = new frappe.ui.Dialog({
			title: __('Hibiscus Connection Test'),
			size: 'extra-large',
			fields: [{
				fieldtype: 'HTML',
				fieldname: 'result_html',
				options: html
			}],
			primary_action_label: __('OK'),
			primary_action: function() {
				dialog.hide();
			}
		});

		dialog.show();

	} else {
		// Show error with icon based on error code
		let icon = 'error';
		let iconColor = '#e74c3c';

		let errorIcons = {
			'AUTH_FAILED': '🔐',
			'SERVER_NOT_FOUND': '🔍',
			'CONNECTION_REFUSED': '🚫',
			'SSL_ERROR': '🔒',
			'TIMEOUT': '⏱️',
			'UNKNOWN': '❌'
		};

		let errorIcon = errorIcons[result.error_code] || '❌';

		let detailsHtml = '';
		if (result.error_details && result.error_details !== result.error) {
			detailsHtml = `
				<details style="margin-top: 15px;">
					<summary style="cursor: pointer; color: var(--text-muted);">${__('Technical Details')}</summary>
					<pre style="margin-top: 10px; padding: 10px; background: var(--bg-light-gray); border-radius: 4px; font-size: 11px; overflow-x: auto;">${frappe.utils.escape_html(result.error_details)}</pre>
				</details>
			`;
		}

		let dialog = new frappe.ui.Dialog({
			title: __('Connection Error'),
			fields: [{
				fieldtype: 'HTML',
				fieldname: 'error_html',
				options: `
					<div style="text-align: center; padding: 20px 0;">
						<div style="font-size: 48px; margin-bottom: 15px;">${errorIcon}</div>
						<h4 style="color: #e74c3c; margin-bottom: 15px;">${__('Connection Failed')}</h4>
						<p style="font-size: 14px; margin-bottom: 20px;">${result.error}</p>
						<div style="background: var(--bg-light-gray); padding: 10px; border-radius: 4px; text-align: left;">
							<strong>${__('Server')}:</strong> ${result.server}<br>
							<strong>${__('Port')}:</strong> ${result.port}
						</div>
						${detailsHtml}
					</div>
				`
			}],
			primary_action_label: __('OK'),
			primary_action: function() {
				dialog.hide();
			}
		});

		dialog.show();
	}
}

function show_fetch_result(result) {
	let html = '';

	if (result.accounts_processed > 0) {
		html += `<div style="margin-bottom: 15px;">
			<span class="indicator green"></span>
			<strong>${__('Successfully fetched transactions from')} ${result.accounts_processed} ${__('account(s)')}</strong>
		</div>`;

		html += `<table class="table table-bordered table-condensed" style="font-size: 12px;">
			<thead>
				<tr style="background-color: var(--bg-light-gray);">
					<th>${__('Account')}</th>
					<th>${__('Status')}</th>
				</tr>
			</thead>
			<tbody>`;

		result.accounts.forEach(acc => {
			html += `<tr>
				<td>${acc.description}</td>
				<td><span class="indicator green"></span> ${__('Success')}</td>
			</tr>`;
		});

		html += '</tbody></table>';
	}

	if (result.errors && result.errors.length > 0) {
		html += `<div style="margin-top: 15px; margin-bottom: 10px;">
			<span class="indicator red"></span>
			<strong>${__('Errors')} (${result.errors.length})</strong>
		</div>`;

		html += `<table class="table table-bordered table-condensed" style="font-size: 12px;">
			<thead>
				<tr style="background-color: var(--bg-light-gray);">
					<th>${__('Account')}</th>
					<th>${__('Error')}</th>
				</tr>
			</thead>
			<tbody>`;

		result.errors.forEach(err => {
			html += `<tr>
				<td>${err.description}</td>
				<td style="color: #e74c3c;">${err.error}</td>
			</tr>`;
		});

		html += '</tbody></table>';
	}

	if (result.accounts_processed === 0 && (!result.errors || result.errors.length === 0)) {
		html = `<div style="text-align: center; padding: 20px;">
			<div style="font-size: 48px; margin-bottom: 15px;">📭</div>
			<p>${__('No accounts configured for auto-fetch.')}</p>
			<p style="color: var(--text-muted);">${__('Enable "Auto Fetch Transactions" on the accounts you want to fetch.')}</p>
		</div>`;
	}

	let dialog = new frappe.ui.Dialog({
		title: __('Fetch Transactions Result'),
		fields: [{
			fieldtype: 'HTML',
			fieldname: 'result_html',
			options: html
		}],
		primary_action_label: __('OK'),
		primary_action: function() {
			dialog.hide();
		}
	});

	dialog.show();
}

function show_blz_import_result(result) {
	let html = '';

	if (result.success) {
		html = `
			<div style="margin-bottom: 15px;">
				<span class="indicator green"></span>
				<strong>${__('Bank codes imported successfully!')}</strong>
			</div>
			<table class="table table-bordered table-condensed" style="font-size: 12px;">
				<tbody>
					<tr>
						<td><strong>${__('Total Records')}</strong></td>
						<td>${result.stats.total || 0}</td>
					</tr>
					<tr>
						<td><strong>${__('Created')}</strong></td>
						<td>${result.stats.created || 0}</td>
					</tr>
					<tr>
						<td><strong>${__('Updated')}</strong></td>
						<td>${result.stats.updated || 0}</td>
					</tr>
					<tr>
						<td><strong>${__('Errors')}</strong></td>
						<td>${result.stats.errors || 0}</td>
					</tr>
				</tbody>
			</table>
		`;
	} else {
		html = `
			<div style="text-align: center; padding: 20px;">
				<div style="font-size: 48px; margin-bottom: 15px;">❌</div>
				<h4 style="color: #e74c3c;">${__('Import Failed')}</h4>
				<p>${result.message}</p>
			</div>
		`;
	}

	let dialog = new frappe.ui.Dialog({
		title: __('Bank Code Import Result'),
		fields: [{
			fieldtype: 'HTML',
			fieldname: 'result_html',
			options: html
		}],
		primary_action_label: __('OK'),
		primary_action: function() {
			dialog.hide();
		}
	});

	dialog.show();
}
