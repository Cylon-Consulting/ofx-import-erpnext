# Cylon OFX Import

OFX bank statement import for ERPNext v16 (Frappe Cloud or self-hosted).

Accepts OFX 1.0.x SGML and 2.0 XML files, creates native Bank
Transaction rows in ERPNext, then hands off to the stock Bank
Reconciliation Tool for matching against Payment Entries, Journal
Entries, and invoices.

## Verified against real South African bank exports

| Bank | Format |
|---|---|
| Nedbank NETBANK | OFX 2.0 XML |
| FNB | OFX 1.0.2 SGML |
| Standard Bank | OFX 1.0.2 SGML |
| Investec Private Bank | OFX 1.0.2 SGML |
| ABSA | OFX 1.x (same family) |

For Tier-2 banks without OFX export (Capitec, TymeBank, Discovery,
Bidvest, African Bank), use ERPNext's stock **Bank Statement Import**
DocType with CSV instead.

## Install on Frappe Cloud

1. Add the repo to a Frappe Cloud bench group (*Apps → Add*).
2. Install onto the target site.
3. `ofxtools` is picked up automatically from `pyproject.toml` during
   the bench deploy — no bench shell access required.

## Usage

1. As a user with the `Accounts Manager`, `Accounts User`, or
   `System Manager` role, go to `/desk/ofx-import/new`.
2. Pick the target **Company** and **Bank Account**, attach the
   OFX file, and Save. The form pre-populates ACCTID, BANKID,
   FI/ORG, currency, and statement period from the file.
3. Click **Process**. The parser creates one Bank Transaction per
   non-zero `STMTTRN`, skipping:
   - Rows with `TRNAMT=0` (BROUGHT/CARRIED FORWARD, VAT memos)
   - Rows whose FITID already exists for the same Bank Account
     (idempotent re-uploads)
4. Open `/desk/bank-reconciliation-tool`, select the Bank Account,
   and reconcile as usual.

## Parsing notes

Each bank's OFX has quirks worth knowing about before extending the
parser:

- **Three of four SA banks ship OFX 1.0.2 SGML**, not 2.x XML. Only
  Nedbank emits proper XML. The `ofxtools` dependency handles both
  uniformly; stdlib `xml.etree.ElementTree` cannot parse SGML.
- **Counterparty tag varies:** Nedbank + Investec put the
  counterparty in `<NAME>`; FNB + Standard Bank put it in `<MEMO>`.
  The runner resolves it as `memo or name`.
- **Investec declares `CHARSET:CSUNICODE`**, which `ofxtools` rejects
  (only allows ISO-8859-1 / 1252 / NONE). `ofx_preview._normalise_ofx_header`
  rewrites it to `CHARSET:NONE` before parsing; `ENCODING:UTF-8`
  already drives decoding.
- **Standard Bank ACCTID normalisation:** the OFX file ships
  `1234567` but customers see `00-123-456-7` on printed statements.
  `acctid.normalise_acctid` strips non-digits + leading zeros on
  both sides of the ACCTID match.
- **DTPOSTED precision varies:** Nedbank/FNB/Standard use
  `YYYYMMDD`; Investec uses `YYYYMMDDHHMMSS`. `parse_ofx_dtdate`
  takes the first 8 digits only.

## Permissions

Shipped DocPerms on the `OFX Import` DocType:

| Role | Read | Write | Create | Delete |
|---|---|---|---|---|
| System Manager | ✓ | ✓ | ✓ | ✓ |
| Accounts Manager | ✓ | ✓ | ✓ | ✓ |
| Accounts User | ✓ | ✓ | ✓ | |

Downstream apps may layer additional role perms via Custom DocPerms;
this app does not try to enforce any franchise/multi-tenant model.

## License

MIT — see `license.txt`.
