"""Lightweight OFX header + metadata reader.

Used by the OFX Import DocType's validate() to populate read-only
metadata fields before the user clicks Process. Intentionally avoids
building any Bank Transaction rows; the full ingest path lives in
`ofx_runner.py`.

Uses `ofxtools.Parser.OFXTree` only as a SGML-aware tokeniser —
FNB / Standard Bank / Investec all ship OFX 1.0.2 SGML with unclosed
tags that stdlib `xml.etree.ElementTree` cannot parse. After parsing,
we navigate the resulting ElementTree with plain `.find()` calls so
this module is resilient to ofxtools API drift between versions.
"""

from io import BytesIO


def _normalise_ofx_header(file_bytes):
    """Swap OFX 1.x header values that ofxtools rejects.

    ofxtools' OFXHeaderV1 enforces `CHARSET ∈ {ISO-8859-1, 1252, NONE}`,
    but Investec's samples declare `CHARSET:CSUNICODE`. Since the
    parallel `ENCODING:UTF-8` already drives decoding, CHARSET is
    diagnostic here — swap to NONE. Safe because `CHARSET:` only
    appears in the OFX 1.x header block.
    """
    return file_bytes.replace(b"CHARSET:CSUNICODE", b"CHARSET:NONE", 1)


def preview_ofx(file_bytes):
    """Parse an OFX file and return a dict of top-level metadata.

    Args:
        file_bytes: raw bytes of the OFX file.

    Returns:
        {
          "acctid": str,       # BANKACCTFROM/ACCTID
          "bankid": str,       # BANKACCTFROM/BANKID (may not be a real routing ID)
          "fi_org": str | None, # SONRS/FI/ORG (Investec populates; others don't)
          "fi_fid": str | None, # SONRS/FI/FID
          "acct_type": str,    # BANKACCTFROM/ACCTTYPE e.g. CHECKING
          "curdef": str,       # STMTRS/CURDEF e.g. ZAR
          "dtstart": str,      # BANKTRANLIST/DTSTART (raw YYYYMMDD[HHMMSS])
          "dtend": str,        # BANKTRANLIST/DTEND
          "txn_count": int,    # number of STMTTRN nodes (pre-filter)
        }
    """
    from ofxtools.Parser import OFXTree

    tree = OFXTree()
    tree.parse(BytesIO(_normalise_ofx_header(file_bytes)))
    root = tree.getroot()
    if root is None:
        raise ValueError("OFX file is empty or unparseable")

    # Pull the first STMTRS we find. SA banks ship a single statement
    # per file (BANKMSGSRSV1/STMTTRNRS/STMTRS); credit-card statements
    # live under CREDITCARDMSGSRSV1/CCSTMTTRNRS/CCSTMTRS and are out
    # of scope for this plan.
    stmtrs = root.find(".//STMTRS")
    if stmtrs is None:
        raise ValueError("OFX file contains no STMTRS (bank statement response)")

    acctfrom = stmtrs.find("BANKACCTFROM")
    if acctfrom is None:
        raise ValueError("OFX STMTRS has no BANKACCTFROM block")

    banktranlist = stmtrs.find("BANKTRANLIST")
    transactions = banktranlist.findall("STMTTRN") if banktranlist is not None else []

    fi = root.find(".//SONRS/FI")

    return {
        "acctid": _text(acctfrom, "ACCTID"),
        "bankid": _text(acctfrom, "BANKID"),
        "fi_org": _text(fi, "ORG") if fi is not None else None,
        "fi_fid": _text(fi, "FID") if fi is not None else None,
        "acct_type": _text(acctfrom, "ACCTTYPE"),
        "curdef": _text(stmtrs, "CURDEF"),
        "dtstart": _text(banktranlist, "DTSTART") if banktranlist is not None else None,
        "dtend": _text(banktranlist, "DTEND") if banktranlist is not None else None,
        "txn_count": len(transactions),
    }


def _text(elem, tag):
    if elem is None:
        return None
    child = elem.find(tag)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def parse_ofx_dtdate(s):
    """Normalise an OFX DT* field to a plain YYYY-MM-DD string.

    OFX dates come in two forms in our samples:
      * YYYYMMDD               (Nedbank, FNB, Standard)
      * YYYYMMDDHHMMSS[.xxx]   (Investec)
    Both reduce to the first 8 digits.
    """
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) < 8:
        return None
    return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
