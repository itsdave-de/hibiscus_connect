frappe.listview_settings['Hibiscus Connect Transaction'] = {
	hide_name_column: true,
    add_fields: ["status", "name"],

	get_indicator: function (doc) {
		if (doc.status === "neu") {
			return [__("neu"), "orange", "status,=,neu"];
		} else if (doc.status === "automatisch verbucht") {
			return [__("automatisch verbucht"), "green", "status,=,automatisch verbucht"];
        } else if (doc.status === "manuell verbucht") {
			return [__("manuell verbucht"), "green", "status,=,manuell verbucht"];
        }
    },
	onload: function(listview) {
		listview.page.add_button(__("Zahlungen Verbuchen"), function() {
			frappe.call({
				method:'hibiscus_connect.tools.match_all_payments',
				callback: function(r) {
					frappe.msgprint(r.message);
					listview.refresh();
				}
			});
		}, "Aktionen");
		listview.page.add_button(__("andere Einnahme"), function() {
			//(console.log(listview),
			let trans_list = []
			$(".list-row-checkbox:checked").each(function(index, value) {
				trans_list.push($(this).attr('data-name'))
			})
			if (trans_list.length > 0) {
				console.log(trans_list.length),
				frappe.call({
					method:'hibiscus_connect.tools.set_andere_einnahme',
					args: {
						"list": trans_list
					},
					callback: function() {
						listview.refresh();
					}
				});
			}
		});
	}

}
