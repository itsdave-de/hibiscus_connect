// Book Transactions Page — Split-View for booking bank transactions

frappe.pages['book-transactions'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Zahlungen verbuchen'),
		single_column: true
	});

	wrapper.page = page;
	page.current_page = 1;
	page.page_size = 50;
	page.direction = "All";
	page.search = "";
	page.hide_booked = 1;
	page.selected_txn = null;
	page.request_id = 0;
	page._search_timer = null;

	page.main.html(frappe.render_template("book_transactions"));

	// Toolbar: bind inline controls (rendered inside the template)
	page.main.find(".tb-direction").on("change", function() {
		page.direction = $(this).val();
		page.current_page = 1;
		load_transactions(page);
	});

	page.main.find(".tb-search-input").on("input", function() {
		clearTimeout(page._search_timer);
		var val = $(this).val();
		page._search_timer = setTimeout(function() {
			if (page.search === val) return;
			page.search = val;
			page.current_page = 1;
			load_transactions(page);
		}, 250);
	});

	page.main.find(".tb-hide-booked").on("change", function() {
		page.hide_booked = this.checked ? 1 : 0;
		page.current_page = 1;
		load_transactions(page);
	});

	// Toolbar: Aktionen dropdown — auto-book incoming payments against open Sales Invoices
	page.main.on("click", ".action-match-sinvs", function(e) {
		e.preventDefault();
		frappe.confirm(
			__("Alle eingehenden, unverbuchten Zahlungen der letzten 30 Tage "
			 + "werden gegen offene Ausgangsrechnungen abgeglichen und — "
			 + "wenn eindeutig — automatisch verbucht. Fortfahren?"),
			function() {
				frappe.call({
					method: "hibiscus_connect.tools.match_all_payments",
					freeze: true,
					freeze_message: __("Ausgangsrechnungen werden abgeglichen..."),
					callback: function(r) {
						frappe.msgprint({
							title: __("Automatisches Verbuchen abgeschlossen"),
							indicator: "green",
							message: r.message,
						});
						load_transactions(page);
					},
				});
			}
		);
	});

	// Primary action
	page.set_primary_action(__("Aktualisieren"), function() {
		load_transactions(page);
	}, "refresh");

	// List events
	page.main.on("click", ".txn-row", function() {
		var name = $(this).data("name");
		page.main.find(".txn-row").removeClass("selected");
		$(this).addClass("selected");
		load_detail(page, name);
	});

	// Paging
	page.main.on("click", ".btn-prev", function() {
		if (page.current_page > 1) {
			page.current_page--;
			load_transactions(page);
		}
	});
	page.main.on("click", ".btn-next", function() {
		page.current_page++;
		load_transactions(page);
	});

	// Check all
	page.main.on("change", ".check-all", function() {
		var checked = this.checked;
		page.main.find(".txn-check").prop("checked", checked);
	});

	// Invoice checkbox/amount handlers (delegated on detail panel)
	page.main.on("change", ".inv-check", function() {
		var idx = $(this).data("idx");
		var $amount = page.main.find('.inv-amount[data-idx="' + idx + '"]');
		var outstanding = parseFloat($(this).data("outstanding"));
		if (this.checked) {
			$amount.val(outstanding);
		} else {
			$amount.val(0);
		}
		update_allocation(page);
	});

	page.main.on("input", ".inv-amount", function() {
		var idx = $(this).data("idx");
		var val = parseFloat($(this).val()) || 0;
		var $check = page.main.find('.inv-check[data-idx="' + idx + '"]');
		$check.prop("checked", val > 0);
		update_allocation(page);
	});

	// Resizable split
	_init_resize(page);

	// Initial load
	load_transactions(page);
};

frappe.pages['book-transactions'].refresh = function(wrapper) {
	// No auto-refresh on tab switch
};


// ── Load transaction list ────────────────────────────────────

function load_transactions(page) {
	page.request_id++;
	var rid = page.request_id;

	page.main.find(".list-loading").show();
	page.main.find(".transaction-rows").empty();
	page.main.find(".list-empty").hide();

	frappe.call({
		method: "hibiscus_connect.hibiscus_connect.page.book_transactions.book_transactions.get_unbooked_transactions",
		args: {
			direction: page.direction,
			search: page.search,
			hide_booked: page.hide_booked,
			page: page.current_page,
			page_size: page.page_size,
		},
		callback: function(r) {
			if (rid !== page.request_id) return; // stale
			page.main.find(".list-loading").hide();

			if (!r.message) return;
			var data = r.message;

			render_stats(page, data.stats);
			render_transactions(page, data.transactions);
			render_paging(page, data);
		}
	});
}


function render_stats(page, stats) {
	page.main.find(".stat-total").html(
		"<b>" + (stats.total || 0) + "</b> offen"
	);
	page.main.find(".stat-outgoing").html(
		(stats.outgoing_count || 0) + " Ausgänge (" + format_currency(stats.outgoing_sum || 0) + ")"
	);
	page.main.find(".stat-incoming").html(
		(stats.incoming_count || 0) + " Eingänge (" + format_currency(stats.incoming_sum || 0) + ")"
	);
}


function render_transactions(page, transactions) {
	var $tbody = page.main.find(".transaction-rows");

	if (!transactions || transactions.length === 0) {
		page.main.find(".list-empty").show();
		return;
	}

	var booked_statuses = ["auto booked", "legacy booked", "manually booked"];

	transactions.forEach(function(tx) {
		var is_out = tx.amount < 0;
		var amount_color = is_out ? "#e24c4c" : "#36a900";

		var badge_html = "";
		if (booked_statuses.indexOf(tx.status) > -1) {
			// Booked takes precedence over any suggestion
			badge_html = '<span class="txn-badge badge-booked">\u2713 '
				+ __("Verbucht") + '</span>';
		} else if (tx.suggestion) {
			var is_learned = tx.suggestion.source === "learned";
			var badge_cls = is_learned ? "badge-learned" : "badge-keyword";
			var badge_icon = is_learned ? "\ud83e\udde0 " : "";
			badge_html = '<span class="txn-badge ' + badge_cls + '">'
				+ badge_icon + frappe.utils.escape_html(tx.suggestion.category)
				+ '</span>';
		}

		// Logo from Booking Rule
		var logo_html = "";
		if (tx.suggestion && tx.suggestion.logo) {
			logo_html = '<img src="' + tx.suggestion.logo + '" class="txn-logo">';
		}

		$tbody.append(
			'<tr class="txn-row" data-name="' + tx.name + '">'
			+ '<td class="col-check"><input type="checkbox" class="txn-check" data-name="' + tx.name + '"></td>'
			+ '<td class="col-date">' + frappe.datetime.str_to_user(tx.transaction_date) + '</td>'
			+ '<td class="col-amount" style="color:' + amount_color + '">'
			+ format_currency(Math.abs(tx.amount)) + '</td>'
			+ '<td class="col-party">' + logo_html
			+ frappe.utils.escape_html(tx.counterparty_name || "\u2013") + '</td>'
			+ '<td class="col-purpose" style="color:var(--text-muted);">'
			+ frappe.utils.escape_html(tx.purpose || "\u2013") + '</td>'
			+ '<td class="col-badge">' + badge_html + '</td>'
			+ '</tr>'
		);
	});
}


function render_paging(page, data) {
	var $paging = page.main.find(".list-paging");
	if (data.pages <= 1) {
		$paging.hide();
		return;
	}
	$paging.show();
	page.main.find(".paging-info").text(
		__("Seite") + " " + data.page + " / " + data.pages
		+ " (" + data.total + " " + __("gesamt") + ")"
	);
	page.main.find(".btn-prev").prop("disabled", data.page <= 1);
	page.main.find(".btn-next").prop("disabled", data.page >= data.pages);
}


// ── Detail panel ─────────────────────────────────────────────

function load_detail(page, txn_name) {
	var $panel = page.main.find(".detail-content");
	var $empty = page.main.find(".detail-empty");

	$empty.hide();
	$panel.show().html(
		'<div class="text-center text-muted" style="padding:30px;">'
		+ '<div class="spinner-border spinner-border-sm"></div> Lade...'
		+ '</div>'
	);

	frappe.call({
		method: "hibiscus_connect.tools.get_booking_dialog_data",
		args: { hib_trans: txn_name },
		callback: function(r) {
			if (!r.message) return;
			page.selected_txn = r.message;
			render_detail(page, r.message);
		}
	});
}


function render_detail(page, data) {
	var tx = data.transaction;
	var is_out = tx.amount < 0;

	// Shared header (rendered for both booked and unbooked transactions)
	var header_html = ''
		+ '<div style="border-bottom:1px solid var(--border-color);padding-bottom:12px;margin-bottom:16px;">'
		+ '<div style="display:flex;justify-content:space-between;align-items:baseline;">'
		+ '<h5 style="margin:0;">' + frappe.utils.escape_html(tx.counterparty_name || "\u2013") + '</h5>'
		+ '<span style="font-size:18px;font-weight:600;color:' + (is_out ? '#e24c4c' : '#36a900') + ';">'
		+ format_currency(Math.abs(tx.amount)) + ' EUR</span>'
		+ '</div>'
		+ '<div style="font-size:12px;color:var(--text-muted);margin-top:4px;">'
		+ frappe.datetime.str_to_user(tx.transaction_date)
		+ ' &middot; ' + frappe.utils.escape_html(tx.transaction_type || "")
		+ ' &middot; <a href="/app/hibiscus-connect-transaction/' + tx.name + '" target="_blank">' + tx.name + '</a>'
		+ '</div>'
		+ '<div style="margin-top:6px;font-family:monospace;font-size:12px;color:var(--text-muted);">'
		+ frappe.utils.escape_html(tx.purpose || "\u2013")
		+ '</div>'
		+ '<div style="font-size:11px;color:var(--text-light);margin-top:2px;">'
		+ 'IBAN: ' + frappe.utils.escape_html(tx.counterparty_iban || "\u2013")
		+ '</div>'
		+ '</div>';

	var $panel = page.main.find(".detail-content");

	// Already booked → render summary with links to booking docs instead of the form
	var booked_statuses = ["auto booked", "legacy booked", "manually booked"];
	if (booked_statuses.indexOf(tx.status) > -1) {
		$panel.html(header_html + render_booked_summary(tx, data.linked_bookings || []));
		return;
	}

	// Not yet booked → render booking form
	var cats = data.categories;
	var cat_options = cats.map(function(c) {
		return '<option value="' + frappe.utils.escape_html(c.category_name) + '">'
			+ frappe.utils.escape_html(c.category_name) + '</option>';
	}).join("");

	var auto_cat = data.auto_category ? data.auto_category.category : "";

	var html = header_html
		// Category
		+ '<div class="form-group">'
		+ '<label class="control-label" style="font-size:12px;">' + __("Kategorie") + '</label>'
		+ '<select class="form-control form-control-sm detail-category">'
		+ cat_options
		+ '</select>'
		+ '</div>'

		// Dynamic sections (rendered based on category)
		+ '<div class="detail-fields" style="margin-top:12px;"></div>'

		// Action buttons
		+ '<div style="margin-top:20px;display:flex;gap:8px;">'
		+ '<button class="btn btn-primary btn-sm btn-book">' + __("Verbuchen") + '</button>'
		+ '<button class="btn btn-default btn-sm btn-skip">' + __("\u00dcberspringen") + '</button>'
		+ '</div>';

	$panel.html(html);

	// Set auto-classified category
	if (auto_cat) {
		$panel.find(".detail-category").val(auto_cat);
	}

	// Category change → render fields
	$panel.find(".detail-category").on("change", function() {
		render_category_fields(page, data);
	});

	// Book button
	$panel.find(".btn-book").on("click", function() {
		submit_booking(page, data);
	});

	// Skip button
	$panel.find(".btn-skip").on("click", function() {
		select_next_transaction(page);
	});

	// Initial field render
	render_category_fields(page, data);
}


function render_booked_summary(tx, linked_bookings) {
	var html = ''
		+ '<div style="background:#e8f5e9;border:1px solid #c8e6c9;border-radius:4px;'
		+ 'padding:10px 12px;color:#1b5e20;display:flex;align-items:center;gap:8px;'
		+ 'font-weight:600;">'
		+ '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">'
		+ '<path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>'
		+ '</svg>'
		+ __("Verbucht")
		+ '</div>';

	if (linked_bookings && linked_bookings.length) {
		html += '<div style="margin-top:16px;">'
			+ '<label class="control-label" style="font-size:12px;">'
			+ __("Verknüpfte Buchungsbelege") + '</label>';

		linked_bookings.forEach(function(b) {
			var slug = b.doctype.toLowerCase().replace(/\s+/g, "-");
			var doctype_label = b.doctype_label || b.doctype;
			var meta_parts = [frappe.utils.escape_html(doctype_label)];
			if (b.posting_date) {
				meta_parts.push(frappe.datetime.str_to_user(b.posting_date));
			}
			if (b.extra) {
				meta_parts.push(frappe.utils.escape_html(b.extra));
			}
			html += '<div style="padding:8px 10px;border:1px solid var(--border-color);'
				+ 'border-radius:4px;margin-top:6px;">'
				// Row 1: document link (left) + amount (right, nowrap)
				+ '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;">'
				+ '<a href="/app/' + slug + '/' + frappe.utils.escape_html(b.name)
				+ '" target="_blank" style="font-size:13px;font-weight:500;">'
				+ frappe.utils.escape_html(b.name) + '</a>'
				+ '<span style="font-size:13px;font-weight:600;white-space:nowrap;">'
				+ format_currency(b.amount) + '</span>'
				+ '</div>'
				// Row 2: meta info, wraps freely below
				+ '<div style="font-size:11px;color:var(--text-muted);margin-top:2px;line-height:1.4;">'
				+ meta_parts.join(' &middot; ')
				+ '</div>'
				+ '</div>';
		});

		html += '</div>';
	}

	return html;
}


function render_category_fields(page, data) {
	var $fields = page.main.find(".detail-fields");
	var cat_name = page.main.find(".detail-category").val();
	var cat = data.categories.find(function(c) { return c.category_name === cat_name; });
	if (!cat) { $fields.html(""); return; }

	var html = "";

	if (cat.needs_invoice_matching) {
		// Supplier/Customer link + invoice table
		var party_label = cat.party_type === "Supplier" ? __("Lieferant") : __("Kunde");
		html += '<div class="form-group">'
			+ '<label class="control-label" style="font-size:12px;">' + party_label + '</label>'
			+ '<div class="detail-party-field"></div>'
			+ '</div>'
			+ '<div class="invoice-table" style="margin-top:8px;"></div>'
			+ '<div class="allocation-bar" style="margin-top:4px;"></div>';

	} else if (cat.booking_type === "Journal Entry") {
		html += '<div class="form-group">'
			+ '<label class="control-label" style="font-size:12px;">' + __("Konto") + '</label>'
			+ '<div class="detail-account-field"></div>'
			+ '</div>'
			+ '<div class="form-group">'
			+ '<label class="control-label" style="font-size:12px;">' + __("Kostenstelle") + '</label>'
			+ '<div class="detail-costcenter-field"></div>'
			+ '</div>'
			+ '<div class="form-group">'
			+ '<label class="control-label" style="font-size:12px;">' + __("Bemerkung") + '</label>'
			+ '<input class="form-control form-control-sm detail-remark" value="'
			+ frappe.utils.escape_html(data.transaction.purpose || "") + '">'
			+ '</div>';

	} else if (cat.payment_type === "Internal Transfer") {
		html += '<div class="form-group">'
			+ '<label class="control-label" style="font-size:12px;">' + __("Zielkonto") + '</label>'
			+ '<div class="detail-target-field"></div>'
			+ '</div>';
	}

	$fields.html(html);

	// Create Frappe Link controls inside the rendered containers
	if (cat.needs_invoice_matching) {
		var party_control = frappe.ui.form.make_control({
			df: {
				fieldname: "detail_party",
				label: "",
				only_input: true,
				fieldtype: "Link",
				options: cat.party_type || "Supplier",
				placeholder: cat.party_type === "Supplier" ? __("Lieferant suchen...") : __("Kunde suchen..."),
				change: function() {
					var val = party_control.get_value();
					if (val) {
						load_invoices_for_detail(page, data, cat.party_type, val);
					}
				},
			},
			parent: $fields.find(".detail-party-field"),
			render_input: true,
		});
		// Also catch awesomplete selection
		party_control.$input.on("awesomplete-selectcomplete", function() {
			var val = party_control.get_value();
			if (val) {
				load_invoices_for_detail(page, data, cat.party_type, val);
			}
		});
		// Store reference for later
		page._detail_party = party_control;

		// Auto-set if party match available
		if (data.party_match && data.party_match.party_type === cat.party_type) {
			party_control.set_value(data.party_match.party);
			setTimeout(function() {
				load_invoices_for_detail(page, data, cat.party_type, data.party_match.party);
			}, 200);
		}

	} else if (cat.booking_type === "Journal Entry") {
		var account_control = frappe.ui.form.make_control({
			df: {
				fieldname: "detail_account",
				label: "",
				only_input: true,
				fieldtype: "Link",
				options: "Account",
				default: cat.default_account || "",
				get_query: function() {
					return { filters: { is_group: 0, company: frappe.defaults.get_default("company") }};
				},
			},
			parent: $fields.find(".detail-account-field"),
			render_input: true,
		});
		if (cat.default_account) {
			account_control.set_value(cat.default_account);
		}
		page._detail_account = account_control;

		var cc_control = frappe.ui.form.make_control({
			df: {
				fieldname: "detail_costcenter",
				label: "",
				only_input: true,
				fieldtype: "Link",
				options: "Cost Center",
				default: cat.default_cost_center || "",
			},
			parent: $fields.find(".detail-costcenter-field"),
			render_input: true,
		});
		if (cat.default_cost_center) {
			cc_control.set_value(cat.default_cost_center);
		}
		page._detail_costcenter = cc_control;

	} else if (cat.payment_type === "Internal Transfer") {
		var target_control = frappe.ui.form.make_control({
			df: {
				fieldname: "detail_target",
				label: "",
				only_input: true,
				fieldtype: "Link",
				options: "Account",
				get_query: function() {
					return { filters: { account_type: "Bank", is_group: 0, company: frappe.defaults.get_default("company") }};
				},
			},
			parent: $fields.find(".detail-target-field"),
			render_input: true,
		});
		page._detail_target = target_control;
	}
}


// ── Invoice table in detail panel ────────────────────────────

function load_invoices_for_detail(page, data, party_type, party) {
	var $table = page.main.find(".invoice-table");
	$table.html('<div class="text-muted" style="font-size:12px;">Lade Rechnungen...</div>');

	frappe.call({
		method: "hibiscus_connect.tools.get_open_invoices",
		args: { party_type: party_type, party: party },
		callback: function(r) {
			if (!r.message || r.message.length === 0) {
				$table.html('<div class="text-muted" style="font-size:12px;">Keine offenen Rechnungen.</div>');
				page.main.find(".allocation-bar").html("");
				return;
			}
			render_invoice_table(page, data, r.message);
		}
	});
}


function render_invoice_table(page, data, invoices) {
	var $table = page.main.find(".invoice-table");
	var purpose = (data.transaction.purpose || "").replace(/\s/g, "").toLowerCase();
	var abs_amount = data.transaction.abs_amount;

	page._invoice_data = invoices;

	var html = '<table class="table table-sm" style="font-size:12px;margin:0;">'
		+ '<thead><tr>'
		+ '<th style="width:24px;"></th>'
		+ '<th>' + __("RE-Nr.") + '</th>'
		+ '<th style="text-align:right;">' + __("Offen") + '</th>'
		+ '<th style="text-align:right;width:90px;">' + __("Zuordnung") + '</th>'
		+ '</tr></thead><tbody>';

	invoices.forEach(function(inv, idx) {
		var bill_no_clean = (inv.bill_no || "").replace(/\s/g, "").toLowerCase();
		// Extract a numeric core (e.g. "SINV-254938" → "254938") so we also
		// match purposes that list just the invoice number without the naming
		// series prefix, which is the common case on bank statements.
		var bill_no_digits = bill_no_clean.replace(/[^0-9]/g, "");
		var is_match = false;
		if (bill_no_clean && purpose.indexOf(bill_no_clean) > -1) {
			is_match = true;
		} else if (bill_no_digits.length >= 4 && purpose.indexOf(bill_no_digits) > -1) {
			is_match = true;
		}
		if (!is_match && invoices.length === 1 && Math.abs(inv.outstanding_amount - abs_amount) < 0.01) {
			is_match = true;
		}

		var overdue = inv.is_overdue ? ' style="color:#e24c4c;"' : '';

		html += '<tr>'
			+ '<td><input type="checkbox" class="inv-check" data-idx="' + idx + '"'
			+ ' data-outstanding="' + inv.outstanding_amount + '"'
			+ (is_match ? ' checked' : '') + '></td>'
			+ '<td' + overdue + '>' + frappe.utils.escape_html(inv.bill_no || inv.name) + '</td>'
			+ '<td style="text-align:right;">' + format_currency(inv.outstanding_amount) + '</td>'
			+ '<td><input type="number" class="inv-amount form-control input-xs" data-idx="' + idx + '"'
			+ ' value="' + (is_match ? inv.outstanding_amount : 0) + '"'
			+ ' min="0" max="' + inv.outstanding_amount + '" step="0.01"'
			+ ' style="width:80px;text-align:right;padding:1px 4px;font-size:12px;"></td>'
			+ '</tr>';
	});

	html += '</tbody></table>';
	$table.html(html);
	update_allocation(page);
}


function update_allocation(page) {
	var total = 0;
	page.main.find(".inv-check:checked").each(function() {
		var idx = $(this).data("idx");
		var val = parseFloat(page.main.find('.inv-amount[data-idx="' + idx + '"]').val()) || 0;
		total += val;
	});
	total = Math.round(total * 100) / 100;

	var data = page.selected_txn;
	if (!data) return;

	var abs_amount = data.transaction.abs_amount;
	var diff = Math.round((abs_amount - total) * 100) / 100;
	var diff_color = Math.abs(diff) < 0.01 ? "#36a900" : "#e24c4c";

	page.main.find(".allocation-bar").html(
		'<div style="display:flex;justify-content:flex-end;gap:12px;font-size:12px;padding:4px 0;">'
		+ '<span>Zugeordnet: <b>' + format_currency(total) + '</b></span>'
		+ '<span style="color:' + diff_color + ';">Diff: <b>' + format_currency(diff) + '</b></span>'
		+ '</div>'
	);
}


// ── Submit booking ───────────────────────────────────────────

function submit_booking(page, data) {
	var cat_name = page.main.find(".detail-category").val();
	var cat = data.categories.find(function(c) { return c.category_name === cat_name; });
	if (!cat) return;

	var booking_data = { category: cat_name };

	if (cat.needs_invoice_matching) {
		var party = page._detail_party ? page._detail_party.get_value() : "";
		if (!party) {
			frappe.show_alert({ message: __("Bitte Lieferant/Kunde auswählen."), indicator: "orange" });
			return;
		}
		booking_data.party = party;
		booking_data.invoices = [];
		page.main.find(".inv-check:checked").each(function() {
			var idx = $(this).data("idx");
			var inv = page._invoice_data[idx];
			var amount = parseFloat(page.main.find('.inv-amount[data-idx="' + idx + '"]').val()) || 0;
			if (inv && amount > 0) {
				booking_data.invoices.push({ name: inv.name, allocated_amount: amount });
			}
		});

	} else if (cat.booking_type === "Journal Entry") {
		var account = page._detail_account ? page._detail_account.get_value() : "";
		if (!account) {
			frappe.show_alert({ message: __("Bitte Konto auswählen."), indicator: "orange" });
			return;
		}
		booking_data.expense_account = account;
		booking_data.cost_center = page._detail_costcenter ? page._detail_costcenter.get_value() : "";
		booking_data.remark = page.main.find(".detail-remark").val() || "";

	} else if (cat.payment_type === "Internal Transfer") {
		var target = page._detail_target ? page._detail_target.get_value() : "";
		if (!target) {
			frappe.show_alert({ message: __("Bitte Zielkonto auswählen."), indicator: "orange" });
			return;
		}
		booking_data.target_account = target;
	}

	page.main.find(".btn-book").prop("disabled", true).text(__("Verbuche..."));

	frappe.call({
		method: "hibiscus_connect.tools.book_transaction",
		args: {
			hib_trans: data.transaction.name,
			booking_data: booking_data,
		},
		callback: function(r) {
			page.main.find(".btn-book").prop("disabled", false).text(__("Verbuchen"));
			if (r.message) {
				frappe.show_alert({
					message: r.message.message + ' <a href="/app/'
						+ frappe.router.slug(r.message.doctype)
						+ '/' + r.message.name + '">' + r.message.name + '</a>',
					indicator: "green"
				}, 5);

				// Remove booked row from list and select next
				page.main.find('.txn-row[data-name="' + data.transaction.name + '"]').fadeOut(300, function() {
					$(this).remove();
					select_next_transaction(page);
				});
			}
		},
		error: function() {
			page.main.find(".btn-book").prop("disabled", false).text(__("Verbuchen"));
		}
	});
}


function select_next_transaction(page) {
	var $next = page.main.find(".txn-row:first");
	if ($next.length) {
		$next.click();
	} else {
		// Reload to check for more
		page.main.find(".detail-content").hide();
		page.main.find(".detail-empty").show();
		load_transactions(page);
	}
}


// ── Resizable split pane ─────────────────────────────────────

function _init_resize(page) {
	var $handle = page.main.find(".resize-handle");
	var $list = page.main.find(".list-panel");
	var $split = page.main.find(".split-view");
	var dragging = false;

	$handle.on("mousedown", function(e) {
		e.preventDefault();
		dragging = true;
		$handle.addClass("active");
		$("body").css("cursor", "col-resize").css("user-select", "none");
	});

	$(document).on("mousemove", function(e) {
		if (!dragging) return;
		var splitLeft = $split.offset().left;
		var splitWidth = $split.width();
		var newListWidth = e.pageX - splitLeft;

		// Clamp: min 250px, max 80% of split
		newListWidth = Math.max(250, Math.min(newListWidth, splitWidth * 0.8));
		$list.css("width", newListWidth + "px").css("flex", "none");
	});

	$(document).on("mouseup", function() {
		if (!dragging) return;
		dragging = false;
		$handle.removeClass("active");
		$("body").css("cursor", "").css("user-select", "");
	});
}
