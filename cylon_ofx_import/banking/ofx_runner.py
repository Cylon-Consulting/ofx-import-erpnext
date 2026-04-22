"""Whitelisted OFX Import runner.

Reads the file attached to an OFX Import doc, parses it with ofxtools,
and creates Bank Transaction rows (docstatus=0) for every non-zero
STMTTRN, skipping any FITID that already exists for the target Bank
Account (idempotent re-uploads).

Invoked via the OFX Import DocType's client-side Process button,
which calls `process_ofx_import(docname)`.
"""

from decimal import Decimal
from io import BytesIO

import frappe
from frappe import _

from cylon_ofx_import.banking.ofx_preview import (
    _normalise_ofx_header,
    _text,
    parse_ofx_dtdate,
)


@frappe.whitelist()
def process_ofx_import(docname):
    """Entry point for the Process button on an OFX Import doc."""
    doc = frappe.get_doc("OFX Import", docname)

    if doc.status == "Processed":
        frappe.throw(_("This OFX Import has already been processed."))

    if not doc.ofx_file:
        frappe.throw(_("Attach an OFX file before processing."))
    if not doc.bank_account:
        frappe.throw(_("Select a Bank Account before processing."))

    try:
        result = _run_import(doc)
    except Exception as exc:
        doc.status = "Failed"
        doc.log = f"{type(exc).__name__}: {exc}"
        doc.flags.ignore_permissions = True
        doc.save()
        frappe.db.commit()
        raise

    doc.transactions_created = result["created"]
    doc.transactions_duplicate = result["duplicate"]
    doc.transactions_skipped_zero = result["skipped_zero"]
    doc.log = result["log"]
    doc.status = "Processed"
    doc.flags.ignore_permissions = True
    doc.save()
    frappe.db.commit()
    return result


def _run_import(doc):
    from ofxtools.Parser import OFXTree

    file_bytes = _read_attached_file(doc.ofx_file)
    tree = OFXTree()
    tree.parse(BytesIO(_normalise_ofx_header(file_bytes)))
    root = tree.getroot()
    if root is None:
        frappe.throw(_("OFX file is empty or unparseable"))

    stmtrs = root.find(".//STMTRS")
    if stmtrs is None:
        frappe.throw(_("OFX file has no STMTRS (bank statement)"))

    curdef = _text(stmtrs, "CURDEF")
    ba_company = frappe.db.get_value("Bank Account", doc.bank_account, "company")
    if ba_company:
        company_currency = frappe.db.get_value("Company", ba_company, "default_currency")
        if curdef and company_currency and curdef != company_currency:
            frappe.throw(_(
                "OFX statement currency {0} does not match Company currency {1}."
            ).format(curdef, company_currency))

    banktranlist = stmtrs.find("BANKTRANLIST")
    if banktranlist is None:
        return {"created": 0, "duplicate": 0, "skipped_zero": 0, "log": "No BANKTRANLIST found."}

    created = 0
    duplicate = 0
    skipped_zero = 0
    lines = []

    for stmttrn in banktranlist.findall("STMTTRN"):
        fitid = _text(stmttrn, "FITID")
        trnamt_raw = _text(stmttrn, "TRNAMT")
        dtposted_raw = _text(stmttrn, "DTPOSTED")
        # Counterparty in NAME (Nedbank, Investec) or MEMO (FNB, Standard).
        # Prefer whichever is non-empty; if both, MEMO is usually richer.
        name = _text(stmttrn, "NAME")
        memo = _text(stmttrn, "MEMO")
        description = memo or name or ""

        try:
            amount = Decimal(trnamt_raw) if trnamt_raw is not None else Decimal(0)
        except Exception:
            amount = Decimal(0)

        if amount == 0:
            skipped_zero += 1
            continue

        posted_date = parse_ofx_dtdate(dtposted_raw)
        if not posted_date:
            lines.append(f"skip {fitid}: unparseable DTPOSTED {dtposted_raw!r}")
            continue
        if not fitid:
            lines.append(f"skip row with amount {amount} on {posted_date}: no FITID")
            continue

        if frappe.db.exists(
            "Bank Transaction",
            {"bank_account": doc.bank_account, "reference_number": fitid},
        ):
            duplicate += 1
            continue

        # Bank Transaction convention: positive amount = deposit
        # (money in), negative = withdrawal (money out). The native
        # doctype exposes `deposit` and `withdrawal` fields plus a
        # derived `amount`. Use `deposit`/`withdrawal` for UI clarity.
        deposit = amount if amount > 0 else Decimal(0)
        withdrawal = -amount if amount < 0 else Decimal(0)

        bt = frappe.get_doc({
            "doctype": "Bank Transaction",
            "date": posted_date,
            "bank_account": doc.bank_account,
            "company": ba_company,
            "deposit": float(deposit),
            "withdrawal": float(withdrawal),
            "currency": curdef,
            "description": description,
            "reference_number": fitid,
        })
        bt.flags.ignore_permissions = True
        bt.insert()
        created += 1

    log = "\n".join(lines) if lines else "OK"
    return {
        "created": created,
        "duplicate": duplicate,
        "skipped_zero": skipped_zero,
        "log": log,
    }


def _read_attached_file(file_url):
    """Resolve a File URL (/files/foo.ofx or /private/files/foo.ofx)
    to raw bytes on disk."""
    file_doc = frappe.db.get_value(
        "File",
        {"file_url": file_url},
        ["name", "is_private"],
        as_dict=True,
    )
    if not file_doc:
        frappe.throw(_("Attached file {0} not found in File registry").format(file_url))
    # get_doc gives us the full path resolver
    f = frappe.get_doc("File", file_doc.name)
    path = f.get_full_path()
    with open(path, "rb") as handle:
        return handle.read()
