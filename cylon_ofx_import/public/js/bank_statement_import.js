// Adds an "Import OFX File" button to ERPNext's stock Bank Statement
// Import form that routes operators to our dedicated OFX Import
// DocType. OFX files carry structured metadata (ACCTID, FITID,
// LEDGERBAL) that the generic CSV/Excel importer would discard —
// sending the user straight to the right tool is more useful than
// letting them stumble through a failed CSV parse.

frappe.ui.form.on("Bank Statement Import", {
    refresh(frm) {
        frm.add_custom_button(__("Import OFX File"), () => {
            frappe.set_route("Form", "OFX Import", "new");
        });
    },
});
