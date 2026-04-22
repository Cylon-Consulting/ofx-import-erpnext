// OFX Import client script — adds a Process button that triggers the
// server-side runner.

frappe.ui.form.on("OFX Import", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }
        if (frm.doc.status === "Pending" && frm.doc.ofx_file) {
            frm.add_custom_button(__("Process"), () => {
                frm.dashboard.set_headline(__("Processing OFX file…"));
                frappe.call({
                    method: "cylon_ofx_import.banking.ofx_runner.process_ofx_import",
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Parsing OFX and creating Bank Transactions…"),
                }).then((r) => {
                    frm.dashboard.clear_headline();
                    frm.reload_doc();
                    if (r && r.message) {
                        const m = r.message;
                        frappe.show_alert({
                            message: __("OFX imported: {0} created, {1} duplicate, {2} skipped (zero).",
                                [m.created, m.duplicate, m.skipped_zero]),
                            indicator: "green",
                        }, 10);
                    }
                }).catch(() => {
                    frm.dashboard.clear_headline();
                    frm.reload_doc();
                });
            }, __("Actions"));
        }
    },

    ofx_file(frm) {
        // Clear cached metadata on new attachment so validate() re-runs.
        if (frm.doc.status !== "Processed") {
            frm.set_value("ofx_acctid", null);
            frm.set_value("ofx_bankid", null);
            frm.set_value("ofx_fi_org", null);
            frm.set_value("ofx_period_start", null);
            frm.set_value("ofx_period_end", null);
            frm.set_value("ofx_currency", null);
        }
    },
});
