"""Account-number normalisation for OFX ACCTID ↔ Bank Account matching.

Different SA banks encode account numbers differently in their OFX
files vs. their customer-facing labels:

* Nedbank NETBANK: `1000000001` (clean, matches label)
* FNB:             `62000000002` (clean, matches label)
* Investec PB:     `10000000003` (clean, matches label)
* Standard Bank:   OFX says `1234567` but customers see `00-123-456-7`
                   on statements — leading zeros + hyphen separators.

Operators enter whatever is printed on their statement into the Bank
Account doctype's `account_number` field, so validate() must tolerate
both forms. Strip non-digits, then strip leading zeros.
"""


def normalise_acctid(value):
    """Return digits-only, no leading zeros. Empty string if no digits.

    >>> normalise_acctid("00-123-456-7")
    '1234567'
    >>> normalise_acctid("1234567")
    '1234567'
    >>> normalise_acctid("1000000001")
    '1000000001'
    >>> normalise_acctid(None)
    ''
    """
    if value is None:
        return ""
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.lstrip("0")
