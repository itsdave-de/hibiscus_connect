// Copyright (c) 2022, itsdave GmbH and contributors
// For license information, please see license.txt

frappe.ui.form.on('SEPA Lastschrift Mandat', {

	refresh: function(frm) {
	frm.trigger("creditor")
	
	},

creditor:function(frm){
frm.call('get_creditor_from_settings', {})
    .then(r => {
        if (r.message) {
            let creditor_doc = r.message;
            console.log(creditor_doc)
			frm.set_value("creditor_iban", creditor_doc[0]),
			frm.set_value("creditor_account_id", creditor_doc[1])
			frm.set_value("creditor_id",creditor_doc[2])
        }
    })
},
// "customer":function(frm){
// if (frm.doc.customer){
	
// 	let cust = frm.doc.customer
	
// 	frappe.model.set_value(frm.doctype,
// 		frm.docname, "mandateid","SEPAM-"+frm.doc.customer+"-")
// 	}

// }

})

// function countDigits(i)  {
// 	return (i + "").length;
//   }
