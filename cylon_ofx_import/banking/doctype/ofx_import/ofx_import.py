"""OFX Import DocType controller.

`validate()` runs a lightweight header-only parse on the attached
file to populate read-only metadata fields and to fail early if the
OFX file targets a different account than the selected Bank Account.
The full ingest (STMTTRN iteration + Bank Transaction creation) runs
only when the user clicks Process, which calls
`ofx_runner.process_ofx_import(self.name)`.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from cylon_ofx_import.banking.acctid import normalise_acctid
from cylon_ofx_import.banking.ofx_preview import parse_ofx_dtdate, preview_ofx


class OFXImport(Document):
    def validate(self):
        self._check_bank_account_company_match()
        if self.ofx_file and self.status != "Processed":
            self._populate_metadata_if_blank()
            self._check_acctid_match()

    def _check_bank_account_company_match(self):
        if not (self.company and self.bank_account):
            return
        ba_company = frappe.db.get_value("Bank Account", self.bank_account, "company")
        if ba_company and ba_company != self.company:
            frappe.throw(_(
                "Bank Account {0} belongs to Company {1}, not {2}."
            ).format(self.bank_account, ba_company, self.company))

    def _populate_metadata_if_blank(self):
        # Only re-read on initial attach — if the user later reuploads
        # a different file they should create a new OFX Import.
        if self.ofx_acctid and self.ofx_currency:
            return
        file_bytes = _read_attached_bytes(self.ofx_file)
        if not file_bytes:
            return
        try:
            meta = preview_ofx(file_bytes)
        except Exception as exc:
            frappe.throw(_("Could not read OFX file: {0}").format(exc))

        self.ofx_acctid = meta.get("acctid")
        self.ofx_bankid = meta.get("bankid")
        self.ofx_fi_org = meta.get("fi_org")
        self.ofx_period_start = parse_ofx_dtdate(meta.get("dtstart"))
        self.ofx_period_end = parse_ofx_dtdate(meta.get("dtend"))
        curdef = meta.get("curdef")
        if curdef and frappe.db.exists("Currency", curdef):
            self.ofx_currency = curdef

        ledgerbal = meta.get("ledgerbal")
        if ledgerbal is not None:
            self.ofx_closing_balance = float(ledgerbal)
            # OFX has no explicit opening balance tag; derive it as
            # closing minus the net of the statement's transactions.
            self.ofx_opening_balance = float(ledgerbal - meta.get("txn_net", 0))
        self.ofx_closing_balance_date = parse_ofx_dtdate(meta.get("ledgerbal_dtasof"))

    def _check_acctid_match(self):
        if not (self.bank_account and self.ofx_acctid):
            return
        ba_number = frappe.db.get_value("Bank Account", self.bank_account, "bank_account_no")
        if not ba_number:
            # Bank Account has no bank_account_no yet — admin hasn't
            # filled it in. Accept anything; the first successful
            # import is the operator's implicit confirmation of
            # which OFX account maps to this row.
            return
        if normalise_acctid(self.ofx_acctid) != normalise_acctid(ba_number):
            frappe.throw(_(
                "OFX ACCTID {0} does not match Bank Account {1} (bank_account_no {2})."
            ).format(self.ofx_acctid, self.bank_account, ba_number))


def _read_attached_bytes(file_url):
    file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not file_name:
        return None
    f = frappe.get_doc("File", file_name)
    try:
        path = f.get_full_path()
        with open(path, "rb") as handle:
            return handle.read()
    except Exception:
        return None
