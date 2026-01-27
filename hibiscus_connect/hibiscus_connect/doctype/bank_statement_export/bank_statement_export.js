// Copyright (c) 2025, itsdave GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('Bank Statement Export', {
    setup: function(frm) {
        // Initialize date preset handlers
        frm.date_preset_values = {
            'Yesterday': function() {
                let yesterday = frappe.datetime.add_days(frappe.datetime.get_today(), -1);
                return { from_date: yesterday, to_date: yesterday };
            },
            'Day Before Yesterday': function() {
                let day_before = frappe.datetime.add_days(frappe.datetime.get_today(), -2);
                return { from_date: day_before, to_date: day_before };
            },
            'Last Business Day': function() {
                let today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
                let day_of_week = today.getDay(); // 0=Sunday, 1=Monday, ..., 6=Saturday
                let days_back = 1;
                if (day_of_week === 0) { // Sunday -> Friday
                    days_back = 2;
                } else if (day_of_week === 1) { // Monday -> Friday
                    days_back = 3;
                }
                let last_business = frappe.datetime.add_days(frappe.datetime.get_today(), -days_back);
                return { from_date: last_business, to_date: last_business };
            },
            'This Week': function() {
                let today = frappe.datetime.get_today();
                let week_start = frappe.datetime.week_start(today);
                return { from_date: week_start, to_date: today };
            },
            'Last Week': function() {
                let today = frappe.datetime.get_today();
                let this_week_start = frappe.datetime.week_start(today);
                let last_week_start = frappe.datetime.add_days(this_week_start, -7);
                let last_week_end = frappe.datetime.add_days(this_week_start, -1);
                return { from_date: last_week_start, to_date: last_week_end };
            },
            'This Month': function() {
                let today = frappe.datetime.get_today();
                let month_start = frappe.datetime.month_start(today);
                return { from_date: month_start, to_date: today };
            },
            'Last Month': function() {
                let today = frappe.datetime.get_today();
                let this_month_start = frappe.datetime.month_start(today);
                let last_month_end = frappe.datetime.add_days(this_month_start, -1);
                let last_month_start = frappe.datetime.month_start(last_month_end);
                return { from_date: last_month_start, to_date: last_month_end };
            },
            'This Year': function() {
                let today = frappe.datetime.get_today();
                let year = frappe.datetime.str_to_obj(today).getFullYear();
                return { from_date: year + '-01-01', to_date: today };
            },
            'Last Year': function() {
                let today = frappe.datetime.get_today();
                let year = frappe.datetime.str_to_obj(today).getFullYear() - 1;
                return { from_date: year + '-01-01', to_date: year + '-12-31' };
            },
            'Year Before Last': function() {
                let today = frappe.datetime.get_today();
                let year = frappe.datetime.str_to_obj(today).getFullYear() - 2;
                return { from_date: year + '-01-01', to_date: year + '-12-31' };
            }
        };
    },

    refresh: function(frm) {
        // Apply read-only state based on preset
        frm.trigger('toggle_date_readonly');

        // Show date range info
        frm.trigger('render_date_range_info');

        // Show account info box
        frm.trigger('render_account_info');

        // Check and render protection status
        frm.trigger('check_protection_status');

        // Render SMB static filename warning
        frm.trigger('render_smb_static_filename_warning');

        // Add Generate Export button
        if (!frm.is_new()) {
            frm.add_custom_button(__('Generate Export'), function() {
                frm.call({
                    method: 'generate_export',
                    doc: frm.doc,
                    freeze: true,
                    freeze_message: __('Generating export file...'),
                    callback: function(r) {
                        if (r.message && r.message.success) {
                            frm.reload_doc();
                            frappe.show_alert({
                                message: __('Export file generated successfully'),
                                indicator: 'green'
                            });
                        }
                    }
                });
            }, __('Actions')).addClass('btn-primary');

            // Add Test SMB Connection button if SMB is enabled
            if (frm.doc.smb_enabled) {
                frm.add_custom_button(__('Test SMB Connection'), function() {
                    frm.call({
                        method: 'test_smb_connection',
                        doc: frm.doc,
                        freeze: true,
                        freeze_message: __('Testing SMB connection...'),
                        callback: function(r) {
                            if (r.message) {
                                if (r.message.success) {
                                    frappe.show_alert({
                                        message: r.message.message,
                                        indicator: 'green'
                                    });
                                } else {
                                    frappe.show_alert({
                                        message: r.message.message,
                                        indicator: 'red'
                                    });
                                }
                                frm.reload_doc();
                            }
                        }
                    });
                }, __('Actions'));
            }

            // Update generated files display
            frm.trigger('update_generated_files_display');
        }

        // Set status indicator colors
        if (frm.doc.status === 'Generated') {
            frm.page.set_indicator(__('Generated'), 'green');
        } else if (frm.doc.status === 'Error') {
            frm.page.set_indicator(__('Error'), 'red');
        } else {
            frm.page.set_indicator(__('Draft'), 'orange');
        }

        // Refresh file list on form load
        if (!frm.is_new() && frm.doc.bank_account) {
            frm.trigger('update_preview');
        }
    },

    update_generated_files_display: function(frm) {
        // Show loading indicator
        let html_field = frm.fields_dict.generated_files_html;
        if (html_field && html_field.wrapper) {
            html_field.wrapper.innerHTML = `
                <div style="padding: 15px; text-align: center; color: var(--primary); background-color: var(--bg-light-gray); border-radius: 4px;">
                    <i class="fa fa-spinner fa-spin" style="margin-right: 8px;"></i>
                    ${__('Loading files...')}
                </div>
            `;
        }

        // Load files from backend
        frappe.call({
            method: 'hibiscus_connect.hibiscus_connect.doctype.bank_statement_export.bank_statement_export.get_export_files',
            args: { docname: frm.doc.name },
            callback: function(response) {
                let files = response.message || [];
                let html_content = frm.events.generate_files_html(frm, files);

                let html_field = frm.fields_dict.generated_files_html;
                if (html_field && html_field.wrapper) {
                    html_field.wrapper.innerHTML = html_content;
                }
            },
            error: function(error) {
                let html_field = frm.fields_dict.generated_files_html;
                if (html_field && html_field.wrapper) {
                    html_field.wrapper.innerHTML = `
                        <div style="padding: 15px; text-align: center; color: var(--red); background-color: var(--bg-light-gray); border-radius: 4px;">
                            <i class="fa fa-exclamation-triangle" style="margin-right: 8px;"></i>
                            ${__('Error loading files')}
                        </div>
                    `;
                }
            }
        });
    },

    generate_files_html: function(frm, files) {
        if (!files || files.length === 0) {
            return `
                <div style="padding: 20px; text-align: center; color: var(--text-muted); background-color: var(--bg-light-gray); border-radius: 6px;">
                    <i class="fa fa-file-o" style="font-size: 24px; margin-bottom: 10px; display: block;"></i>
                    ${__('No files generated yet. Click "Generate Export" to create a file.')}
                </div>
            `;
        }

        let html = `
            <div style="background-color: var(--bg-light-gray); border: 1px solid var(--border-color); border-radius: 6px; padding: 15px;">
                <div style="margin-bottom: 12px; padding: 8px 12px; background-color: var(--bg-blue); border-radius: 4px; font-size: 12px; color: var(--text-color);">
                    <i class="fa fa-info-circle" style="margin-right: 6px;"></i>
                    ${files.length} ${__('file(s) available')}
                </div>
                <div>
        `;

        files.forEach(function(file) {
            // Format creation date
            let created_str = __('Unknown');
            if (file.creation) {
                let date_part = frappe.datetime.str_to_user(file.creation);
                let time_obj = frappe.datetime.str_to_obj(file.creation);
                let time_part = time_obj.toTimeString().substring(0, 5);
                created_str = date_part + ' ' + time_part;
            }

            // Format file size
            let size_str = '';
            if (file.file_size) {
                if (file.file_size < 1024) {
                    size_str = file.file_size + ' B';
                } else if (file.file_size < 1024 * 1024) {
                    size_str = (file.file_size / 1024).toFixed(1) + ' KB';
                } else {
                    size_str = (file.file_size / (1024 * 1024)).toFixed(1) + ' MB';
                }
            }

            // Determine file icon based on extension
            let file_icon = 'fa-file-o';
            let icon_color = 'var(--text-muted)';
            if (file.file_name && file.file_name.endsWith('.xml')) {
                file_icon = 'fa-file-code-o';
                icon_color = 'var(--orange)';
            } else if (file.file_name && file.file_name.endsWith('.sta')) {
                file_icon = 'fa-file-text-o';
                icon_color = 'var(--blue)';
            }

            html += `
                <div style="display: flex; align-items: center; justify-content: space-between;
                           padding: 12px; margin-bottom: 8px; background-color: var(--fg-color);
                           border: 1px solid var(--border-color); border-radius: 4px;">
                    <div style="flex: 1; min-width: 0;">
                        <div style="font-weight: 500; color: var(--text-color); margin-bottom: 4px; display: flex; align-items: center;">
                            <i class="fa ${file_icon}" style="color: ${icon_color}; margin-right: 8px; font-size: 16px;"></i>
                            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${file.file_name}</span>
                        </div>
                        <div style="font-size: 12px; color: var(--text-muted);">
                            <i class="fa fa-clock-o" style="margin-right: 4px;"></i>
                            ${created_str}
                            ${size_str ? '<span style="margin-left: 12px;"><i class="fa fa-database" style="margin-right: 4px;"></i>' + size_str + '</span>' : ''}
                        </div>
                    </div>
                    <div style="margin-left: 15px; flex-shrink: 0;">
                        <a href="${file.file_url}" target="_blank" class="btn btn-primary btn-sm"
                           style="padding: 6px 14px; font-size: 12px; text-decoration: none; display: inline-flex; align-items: center;">
                            <i class="fa fa-download" style="margin-right: 6px;"></i>
                            ${__('Download')}
                        </a>
                    </div>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;

        return html;
    },

    bank_account: function(frm) {
        // Auto-set default dates when bank account is selected
        if (frm.doc.bank_account && !frm.doc.from_date) {
            // Default to current month
            let today = frappe.datetime.get_today();
            let first_day = frappe.datetime.month_start(today);
            frm.set_value('from_date', first_day);
            frm.set_value('to_date', today);
        }
        frm.trigger('update_preview');
        // Re-render account info after fetch_from updates the fields
        setTimeout(() => frm.trigger('render_account_info'), 500);
    },

    render_account_info: function(frm) {
        let wrapper = frm.fields_dict.account_info_html;
        if (!wrapper || !wrapper.$wrapper) return;

        // Show placeholder if no bank account selected
        if (!frm.doc.bank_account) {
            wrapper.$wrapper.html(`
                <div style="background: var(--bg-light-gray); border: 1px solid var(--border-color);
                            border-radius: var(--border-radius); padding: 15px; color: var(--text-muted);
                            font-size: 12px; text-align: center;">
                    <i class="fa fa-info-circle" style="margin-right: 6px;"></i>
                    ${__('Select a bank account to see details')}
                </div>
            `);
            return;
        }

        // Build compact info box
        let items = [];

        if (frm.doc.account_holder) {
            items.push(`<div><strong>${__('Account Holder')}:</strong> ${frm.doc.account_holder}</div>`);
        }
        if (frm.doc.account_description) {
            items.push(`<div><strong>${__('Description')}:</strong> ${frm.doc.account_description}</div>`);
        }
        if (frm.doc.bic) {
            items.push(`<div><strong>${__('BIC')}:</strong> <code style="font-size: 11px;">${frm.doc.bic}</code></div>`);
        }
        if (frm.doc.account_type) {
            items.push(`<div><strong>${__('Account Type')}:</strong> ${frm.doc.account_type}</div>`);
        }
        if (frm.doc.currency) {
            items.push(`<div><strong>${__('Currency')}:</strong> ${frm.doc.currency}</div>`);
        }

        let html = `
            <div style="background: var(--bg-light-gray); border: 1px solid var(--border-color);
                        border-radius: var(--border-radius); padding: 12px; font-size: 12px;">
                <div style="font-weight: 600; margin-bottom: 8px; color: var(--heading-color);
                            border-bottom: 1px solid var(--border-color); padding-bottom: 6px;">
                    <i class="fa fa-university" style="margin-right: 6px; color: var(--primary);"></i>
                    ${__('Account Details')}
                </div>
                <div style="display: flex; flex-direction: column; gap: 4px; color: var(--text-color);">
                    ${items.join('')}
                </div>
            </div>
        `;

        wrapper.$wrapper.html(html);
    },

    from_date: function(frm) {
        frm.trigger('update_preview');
    },

    to_date: function(frm) {
        frm.trigger('update_preview');
    },

    update_preview: function(frm) {
        // Trigger balance calculation when parameters change
        if (frm.doc.bank_account && frm.doc.from_date && frm.doc.to_date) {
            // This will be calculated on save, but we can show a preview
            frappe.call({
                method: 'frappe.client.get_count',
                args: {
                    doctype: 'Hibiscus Connect Transaction',
                    filters: {
                        bank_account: frm.doc.bank_account,
                        transaction_date: ['between', [frm.doc.from_date, frm.doc.to_date]]
                    }
                },
                callback: function(r) {
                    if (r.message !== undefined) {
                        frm.set_value('transaction_count', r.message);
                    }
                }
            });
        }
    },

    date_preset: function(frm) {
        // Handle date preset selection
        let preset = frm.doc.date_preset;

        if (preset && preset !== 'Custom' && frm.date_preset_values[preset]) {
            let dates = frm.date_preset_values[preset]();
            frm.set_value('from_date', dates.from_date);
            frm.set_value('to_date', dates.to_date);
        }

        frm.trigger('toggle_date_readonly');
        frm.trigger('render_date_range_info');
    },

    toggle_date_readonly: function(frm) {
        // Make date fields read-only when preset is selected (not Custom or empty)
        let preset = frm.doc.date_preset;
        let is_preset_selected = preset && preset !== 'Custom';

        frm.set_df_property('from_date', 'read_only', is_preset_selected ? 1 : 0);
        frm.set_df_property('to_date', 'read_only', is_preset_selected ? 1 : 0);

        // Update field description based on mode
        if (is_preset_selected) {
            frm.set_df_property('from_date', 'description', __('Auto-calculated from preset'));
            frm.set_df_property('to_date', 'description', __('Auto-calculated from preset'));
        } else {
            frm.set_df_property('from_date', 'description', __('Start date for the statement period'));
            frm.set_df_property('to_date', 'description', __('End date for the statement period'));
        }
    },

    validate: function(frm) {
        // Validate date range
        if (frm.doc.from_date && frm.doc.to_date) {
            if (frm.doc.from_date > frm.doc.to_date) {
                frappe.throw(__('From Date cannot be after To Date'));
            }
        }
    },

    render_date_range_info: function(frm) {
        let has_preset = frm.doc.date_preset && frm.doc.date_preset !== 'Custom';
        let html = '';

        if (has_preset) {
            html = `
                <div style="background: var(--bg-light-blue); border: 1px solid var(--blue-200);
                            border-radius: var(--border-radius); padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: flex-start; gap: 10px;">
                        <i class="fa fa-info-circle" style="color: var(--blue-500); margin-top: 2px;"></i>
                        <div style="font-size: 12px; color: var(--text-color);">
                            <strong>${__('Preset active')}:</strong> ${frm.doc.date_preset}<br>
                            <ul style="margin: 8px 0 0 0; padding-left: 18px; color: var(--text-muted);">
                                <li>${__('Auto generation & Dashboard')}: ${__('Date is recalculated automatically based on the preset')}</li>
                                <li>${__('Manual export (this form)')}: ${__('The currently displayed date is used')}</li>
                            </ul>
                        </div>
                    </div>
                </div>
            `;
        } else {
            html = `
                <div style="background: var(--bg-gray); border: 1px solid var(--gray-300);
                            border-radius: var(--border-radius); padding: 12px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: flex-start; gap: 10px;">
                        <i class="fa fa-calendar" style="color: var(--gray-600); margin-top: 2px;"></i>
                        <div style="font-size: 12px; color: var(--text-muted);">
                            ${__('Custom date range')}: ${__('The manually entered dates are always used for all export types.')}
                        </div>
                    </div>
                </div>
            `;
        }

        let wrapper = frm.fields_dict.date_range_info;
        if (wrapper && wrapper.$wrapper) {
            wrapper.$wrapper.html(html);
        }
    },

    check_protection_status: function(frm) {
        // Clear protection info if new document
        if (frm.is_new()) {
            frm.events.render_protection_info(frm, { is_protected: false });
            return;
        }

        // Check if document is protected
        if (!frm.doc.is_protected) {
            frm.events.render_protection_info(frm, { is_protected: false });
            return;
        }

        // Get protection status from server
        frappe.call({
            method: 'hibiscus_connect.hibiscus_connect.doctype.bank_statement_export.bank_statement_export.get_protection_status',
            args: { docname: frm.doc.name },
            callback: function(r) {
                if (r.message) {
                    frm.protection_status = r.message;
                    frm.events.render_protection_info(frm, r.message);
                    frm.events.apply_protection_readonly(frm, r.message);
                }
            }
        });
    },

    render_protection_info: function(frm, status) {
        let wrapper = frm.fields_dict.protection_info;
        if (!wrapper || !wrapper.$wrapper) return;

        if (!status || !status.is_protected) {
            wrapper.$wrapper.html('');
            return;
        }

        let html = '';
        if (status.has_permission) {
            // User has permission - green banner
            html = `
                <div style="background: var(--bg-green); border: 1px solid var(--green-300);
                            border-radius: var(--border-radius); padding: 12px; margin-bottom: 15px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <i class="fa fa-lock" style="color: var(--green-600); font-size: 16px;"></i>
                        <div style="font-size: 12px; color: var(--text-color);">
                            <strong>${__('Protected Export')}</strong><br>
                            <span style="color: var(--text-muted);">
                                ${__('You have edit permissions')} (${__('Role')}: ${status.required_role || __('Administrator')})
                            </span>
                        </div>
                    </div>
                </div>
            `;
        } else {
            // User does not have permission - orange banner
            html = `
                <div style="background: var(--bg-orange); border: 1px solid var(--orange-300);
                            border-radius: var(--border-radius); padding: 12px; margin-bottom: 15px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <i class="fa fa-lock" style="color: var(--orange-600); font-size: 16px;"></i>
                        <div style="font-size: 12px; color: var(--text-color);">
                            <strong>${__('Protected Export')} (${__('Read Only')})</strong><br>
                            <span style="color: var(--text-muted);">
                                ${__('You can view this export and generate files, but cannot edit settings.')}<br>
                                ${__('Required role')}: ${status.required_role || __('Not configured')}
                            </span>
                        </div>
                    </div>
                </div>
            `;
        }

        wrapper.$wrapper.html(html);
    },

    apply_protection_readonly: function(frm, status) {
        if (!status || !status.is_protected || status.has_permission) {
            return;
        }

        // List of fields that should be read-only for protected exports
        const protected_fields = [
            'bank_account', 'description', 'date_preset', 'from_date', 'to_date',
            'export_format', 'show_on_dashboard', 'dashboard_file_count',
            'is_protected', 'auto_generate_enabled', 'auto_generate_hour',
            'smb_enabled', 'smb_server', 'smb_share', 'smb_path',
            'smb_username', 'smb_password', 'smb_domain', 'smb_port',
            'smb_static_filename_enabled', 'smb_static_filename'
        ];

        // Make fields read-only
        protected_fields.forEach(function(fieldname) {
            frm.set_df_property(fieldname, 'read_only', 1);
        });

        // Disable save button but keep Generate Export button
        frm.disable_save();
    },

    smb_static_filename_enabled: function(frm) {
        frm.trigger('render_smb_static_filename_warning');
    },

    smb_enabled: function(frm) {
        frm.trigger('render_smb_static_filename_warning');
    },

    render_smb_static_filename_warning: function(frm) {
        let wrapper = frm.fields_dict.smb_static_filename_warning;
        if (!wrapper || !wrapper.$wrapper) return;

        // Only show warning if SMB and static filename are enabled
        if (!frm.doc.smb_enabled || !frm.doc.smb_static_filename_enabled) {
            wrapper.$wrapper.html('');
            return;
        }

        let html = `
            <div style="background: var(--bg-orange); border: 1px solid var(--orange-300);
                        border-radius: var(--border-radius); padding: 12px; margin-top: 10px;">
                <div style="display: flex; align-items: flex-start; gap: 10px;">
                    <i class="fa fa-exclamation-triangle" style="color: var(--orange-600); margin-top: 2px; font-size: 16px;"></i>
                    <div style="font-size: 12px; color: var(--text-color);">
                        <strong>${__('Warning: File Overwrite')}</strong>
                        <p style="margin: 8px 0 0 0; color: var(--text-muted);">
                            ${__('When using a static filename, the target file on the SMB share will be overwritten with each export. This means:')}
                        </p>
                        <ul style="margin: 8px 0 0 0; padding-left: 18px; color: var(--text-muted);">
                            <li>${__('Previous exports with the same filename will be permanently deleted')}</li>
                            <li>${__('Only the most recent export will be available on the network share')}</li>
                            <li>${__('This is useful when an external system always expects the same filename')}</li>
                            <li>${__('Local copies in Frappe are not affected and retain their unique names')}</li>
                        </ul>
                        <p style="margin: 8px 0 0 0; color: var(--text-muted);">
                            <strong>${__('Tip')}:</strong> ${__('Make sure this is the intended behavior before enabling this option.')}
                        </p>
                    </div>
                </div>
            </div>
        `;

        wrapper.$wrapper.html(html);
    }
});
