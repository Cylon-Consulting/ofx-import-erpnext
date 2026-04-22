"""Helper for ensuring ERPNext `Bank Account` doctype rows exist.

The Bank Reconciliation Tool and any OFX Import workflow key off the
Bank Account *doctype row* (not the underlying GL Account), so a
shell row must exist per Company + GL pair before reconciliation can
auto-match. This helper is idempotent — if a row already links the
given GL account and company, it's returned unchanged.

Used standalone by consumers that already hold a Bank-type GL leaf
account and want to surface it for bank-reconciliation workflows.
The `bank` and `account_number` fields are optional on first create;
admins fill them in later via /desk/bank-account when they have the
real details from the bank.
"""

import frappe


def ensure_bank_account_doctype(company, gl_account, bank=None, acctid=None):
    """Create or return a Bank Account doctype row for (company, gl_account).

    Args:
      company: Company doctype name.
      gl_account: leaf GL Account name with account_type='Bank'.
      bank: optional Bank doctype name (e.g. "Nedbank").
      acctid: optional account number string (e.g. the OFX ACCTID).

    Returns a dict:
      status: 'already_exists' | 'created' | 'failed'
      bank_account: the Bank Account docname (or None on failure)
      reason: human-readable note
    """
    if not frappe.db.exists("Company", company):
        return {"status": "failed", "bank_account": None, "reason": f"Company {company} not found"}
    if not frappe.db.exists("Account", gl_account):
        return {"status": "failed", "bank_account": None, "reason": f"Account {gl_account} not found"}

    existing = frappe.db.get_value(
        "Bank Account",
        {"account": gl_account, "company": company},
        "name",
    )
    if existing:
        return {"status": "already_exists", "bank_account": existing, "reason": "Bank Account doctype row already present"}

    # Derive a human label from the GL account; strip the " - <abbr>"
    # suffix that ERPNext CoAs append so the label reads naturally.
    abbr = frappe.db.get_value("Company", company, "abbr") or ""
    label = gl_account
    if abbr and label.endswith(f" - {abbr}"):
        label = label[: -len(f" - {abbr}")]

    doc = frappe.get_doc({
        "doctype": "Bank Account",
        "account_name": label,
        "account": gl_account,
        "company": company,
        "is_company_account": 1,
        "bank": bank,
        "account_number": acctid,
    })
    doc.flags.ignore_permissions = True
    try:
        doc.insert()
        return {"status": "created", "bank_account": doc.name, "reason": f"Created for {company} linked to {gl_account}"}
    except Exception as exc:
        return {"status": "failed", "bank_account": None, "reason": str(exc)}
