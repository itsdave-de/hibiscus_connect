frappe.ui.form.on('Hibiscus Connect Transaction', {
    refresh: function(frm) {
        // Button: Match mit Compusoft
        if (frm.doc.amount > 0 && !frm.is_new()) {
            frm.add_custom_button(__('Match with Compusoft'), function() {
                frappe.call({
                    method: 'hibiscus_connect.api.match_hibiscus_transaction',
                    args: {
                        transaction_id: frm.doc.name
                    },
                    callback: function(r) {
                        if (r.message && r.message.status === 'success') {
                            frappe.show_alert({
                                message: __('Matching completed: {0}', [r.message.match_status]),
                                indicator: 'green'
                            });
                            frm.reload_doc();
                        } else {
                            frappe.msgprint(__('Matching failed'));
                        }
                    }
                });
            }, __('Actions'));
        }

        // Render Match-Details
        if (frm.doc.compusoft_match_data) {
            render_match_details(frm);
        }

        // Status-Indikator-Farbe
        set_status_indicator(frm);
    },

    compusoft_match_status: function(frm) {
        set_status_indicator(frm);
    }
});

function set_status_indicator(frm) {
    const status = frm.doc.compusoft_match_status;
    const field = frm.get_field('compusoft_match_status');

    if (!field) return;

    let color = 'gray';

    switch(status) {
        case 'Matched (Perfect)':
            color = 'green';
            break;
        case 'Matched (Partial)':
            color = 'orange';
            break;
        case 'Matched (Mismatch)':
            color = 'red';
            break;
        case 'No Match':
            color = 'darkgray';
            break;
        case 'Manual Review':
            color = 'blue';
            break;
        case 'Ignored':
            color = 'lightgray';
            break;
    }

    $(field.disp_area).css('background-color', color);
    $(field.disp_area).css('color', 'white');
    $(field.disp_area).css('padding', '5px 10px');
    $(field.disp_area).css('border-radius', '3px');
    $(field.disp_area).css('font-weight', 'bold');
}

function render_match_details(frm) {
    const match_data = frm.doc.compusoft_match_data;

    if (!match_data) return;

    let html = '<div style="padding: 15px; background: #f8f9fa; border-radius: 5px;">';

    // Header
    html += '<h4 style="margin-top: 0;">🔗 Compusoft Matching Details</h4>';

    // Parsed Data
    if (match_data.parsed_data) {
        html += '<div style="margin-bottom: 15px;">';
        html += '<strong>📋 Geparste Daten:</strong><br>';
        html += '<ul style="margin: 5px 0;">';
        html += '<li>Kundennummer: <strong>' + match_data.parsed_data.kunde_lbnr + '</strong></li>';
        html += '<li>Buchungsnummer: <strong>' + match_data.parsed_data.booking_nr + '</strong></li>';
        html += '<li>Code: <strong>' + match_data.parsed_data.code + '</strong></li>';
        html += '</ul></div>';
    }

    // Kunde Info
    if (match_data.kunde_info) {
        const k = match_data.kunde_info;
        html += '<div style="margin-bottom: 15px;">';
        html += '<strong>👤 Kunde:</strong><br>';
        html += '<ul style="margin: 5px 0;">';
        html += '<li>Name: <strong>' + k.fornavn + ' ' + k.efternavn + '</strong></li>';
        if (k.email) html += '<li>Email: ' + k.email + '</li>';
        if (k.tlf) html += '<li>Telefon: ' + k.tlf + '</li>';
        html += '</ul></div>';
    }

    // Reservierung Info
    if (match_data.reservierung_info) {
        const r = match_data.reservierung_info;
        html += '<div style="margin-bottom: 15px;">';
        html += '<strong>📅 Reservierung:</strong><br>';
        html += '<ul style="margin: 5px 0;">';
        html += '<li>Buchungsnummer: <strong>' + r.booking_nr + '</strong></li>';
        html += '<li>Zeitraum: ' + r.fra_formatted + ' bis ' + r.til_formatted + '</li>';
        html += '<li>Platz: ' + r.plads_nr + '</li>';
        html += '<li>Status: ' + r.status + '</li>';
        html += '</ul></div>';
    }

    // Beträge
    if (match_data.amounts) {
        const a = match_data.amounts;
        html += '<div style="margin-bottom: 15px;">';
        html += '<strong>💰 Beträge:</strong><br>';
        html += '<table style="width: 100%; border-collapse: collapse; margin: 5px 0;">';
        html += '<tr><td>Hibiscus:</td><td style="text-align: right;"><strong>' + format_currency(a.hibiscus) + '</strong></td></tr>';
        html += '<tr><td>Compusoft:</td><td style="text-align: right;"><strong>' + format_currency(a.compusoft_total) + '</strong></td></tr>';
        html += '<tr style="border-top: 1px solid #ddd;"><td>Differenz:</td><td style="text-align: right; color: ' + (a.difference < 0.01 ? 'green' : 'red') + '"><strong>' + format_currency(a.difference) + '</strong></td></tr>';
        html += '<tr><td>Übereinstimmung:</td><td style="text-align: right;"><strong>' + a.percentage_match.toFixed(1) + '%</strong></td></tr>';
        html += '</table></div>';
    }

    // PAYINFO Entries
    if (match_data.payinfo_entries && match_data.payinfo_entries.length > 0) {
        html += '<div style="margin-bottom: 15px;">';
        html += '<strong>💳 PAYINFO-Einträge (' + match_data.payinfo_entries.length + '):</strong><br>';
        html += '<table style="width: 100%; border-collapse: collapse; margin: 5px 0; font-size: 12px;">';
        html += '<tr style="background: #e9ecef;"><th style="padding: 5px; text-align: left;">ID</th><th style="padding: 5px; text-align: right;">Betrag</th><th style="padding: 5px;">Zeitpunkt</th><th style="padding: 5px;">PosterID</th></tr>';

        match_data.payinfo_entries.forEach(p => {
            html += '<tr style="border-bottom: 1px solid #ddd;">';
            html += '<td style="padding: 5px;">' + p.id + '</td>';
            html += '<td style="padding: 5px; text-align: right;">' + format_currency(p.belob) + '</td>';
            html += '<td style="padding: 5px;">' + (p.timestamp_formatted || 'N/A') + '</td>';
            html += '<td style="padding: 5px;">' + (p.poster_id || 'N/A') + '</td>';
            html += '</tr>';
        });

        html += '</table></div>';
    }

    // Poster Positionen
    if (match_data.poster_positionen && match_data.poster_positionen.length > 0) {
        html += '<div style="margin-bottom: 15px;">';
        html += '<strong>📝 Rechnungspositionen (' + match_data.poster_positionen.length + '):</strong><br>';
        html += '<table style="width: 100%; border-collapse: collapse; margin: 5px 0; font-size: 12px;">';
        html += '<tr style="background: #e9ecef;"><th style="padding: 5px; text-align: left;">Beschreibung</th><th style="padding: 5px; text-align: right;">Betrag</th><th style="padding: 5px;">UdlignerID</th></tr>';

        match_data.poster_positionen.forEach(p => {
            const is_payment = p.pris < 0;
            html += '<tr style="border-bottom: 1px solid #ddd; ' + (is_payment ? 'background: #e8f5e9;' : '') + '">';
            html += '<td style="padding: 5px;">' + (p.beschr || p.vare_nr) + '</td>';
            html += '<td style="padding: 5px; text-align: right; font-weight: bold;">' + format_currency(p.gesamt) + '</td>';
            html += '<td style="padding: 5px;">' + (p.udligner_id || '-') + '</td>';
            html += '</tr>';
        });

        html += '</table></div>';
    }

    // Match Result
    if (match_data.match_result) {
        const m = match_data.match_result;
        html += '<div style="margin-bottom: 15px; padding: 10px; background: #fff3cd; border-left: 4px solid #ffc107; border-radius: 3px;">';
        html += '<strong>🎯 Match-Ergebnis:</strong><br>';
        html += '<ul style="margin: 5px 0;">';
        html += '<li>Qualität: <strong>' + (m.quality_score * 100).toFixed(0) + '%</strong></li>';
        if (m.is_anzahlung) {
            html += '<li>Anzahlung: <strong>' + m.anzahlung_percentage.toFixed(1) + '%</strong></li>';
        }
        if (m.notes) {
            html += '<li>Hinweis: <em>' + m.notes + '</em></li>';
        }
        html += '</ul></div>';
    }

    html += '</div>';

    // Setze HTML
    frm.set_df_property('compusoft_match_display', 'options', html);
}

function format_currency(amount) {
    if (amount === null || amount === undefined) return 'N/A';
    return new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(amount);
}
