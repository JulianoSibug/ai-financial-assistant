"""Stage 3: raw parsed rows -> normalized Transaction records."""
from __future__ import annotations

import re
from pathlib import Path

from backend import db
from backend.ingest.parse_csv import RawTransaction
from backend.models import Transaction

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

# Payment-processor prefixes glued onto the front of the real merchant name.
_PROCESSOR_PREFIX = re.compile(r"^(SQ|TST|PY|IC|PP|CKO)\s?\*\s*", re.IGNORECASE)
# Credit-card statements often append an MCC-derived category column after
# the merchant ("WALMART STORE 02015 FAIRFAX VA Merchandise") -- stripped
# before city/state so that suffix is trailing again afterward. Not
# exhaustive; anything unrecognized just falls through unstripped.
_KNOWN_CATEGORY_LABELS = (
    r"Merchandise|Restaurants|Services|Warehouse Clubs|Supermarkets|Gasoline|"
    r"Gas Stations|Travel/Entertainment|Department Stores|Discount Stores|"
    r"Home Improvement|Grocery Stores|Drug Stores|Recreation|Automotive|"
    r"Utilities|Government Services|Airlines|Hotels/Motels|Car Rental"
)
_TRAILING_CATEGORY_LABEL = re.compile(rf"\s+(?:{_KNOWN_CATEGORY_LABELS})\s*$", re.IGNORECASE)
# "MERCHANT NAME CITY ST" — a single trailing place-name word followed by a
# 2-letter state code. Deliberately single-word: allowing 2-3 city words
# greedily eats real merchant words too (e.g. "SHELL OIL AUSTIN TX" would
# otherwise mistake "OIL" for part of the city). Multi-word cities (e.g.
# "SAN JOSE CA") are a known miss, not a false strip -- an acceptable
# trade-off given a false strip mangles a merchant name outright.
_CITY_STATE_SUFFIX = re.compile(r"\s+([A-Z][A-Za-z.\-]*)\s+([A-Z]{2})\s*$")
# Reference/auth/trace codes: alphanumeric with at least one digit, 6+ chars,
# so real words (e.g. "COFFEE", "MARKET") are never mistaken for a code.
_TRAILING_REF_CODE = re.compile(
    r"\s+(?:REF|CONF|AUTH|TRACE)?#?\s*(?=[A-Z0-9]*\d)[A-Z0-9]{6,}\s*$", re.IGNORECASE
)
_TRAILING_STORE_NUMBER = re.compile(r"\s+#\d+\b")
_TRAILING_DIGITS = re.compile(r"\s+\d{3,}\s*$")
_EDGE_JUNK = re.compile(r"^[\s*\-.]+|[\s*\-.]+$")
_MULTI_SPACE = re.compile(r"\s{2,}")


def clean_merchant(raw_description: str) -> str:
    """Strip processor prefixes, city/state suffixes, reference codes, store
    numbers, and trailing digits from a raw transaction description."""
    text = raw_description.strip()
    text = _PROCESSOR_PREFIX.sub("", text)
    text = _TRAILING_CATEGORY_LABEL.sub("", text)

    m = _CITY_STATE_SUFFIX.search(text)
    if m and m.group(2).upper() in _US_STATES:
        text = text[: m.start()].strip()

    text = _TRAILING_REF_CODE.sub("", text)
    text = _TRAILING_STORE_NUMBER.sub("", text)
    text = _TRAILING_DIGITS.sub("", text)
    text = _EDGE_JUNK.sub("", text)
    text = _MULTI_SPACE.sub(" ", text).strip()

    if not text:
        text = raw_description.strip() or "Unknown"

    return text.title() if text.isupper() else text


def normalize_merchant_key(merchant: str) -> str:
    return re.sub(r"\s+", " ", merchant.strip().lower())


def derive_account_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem.title() if stem else "Unknown Account"


def build_transactions(
    raw_transactions: list[RawTransaction],
    *,
    account: str,
    source_file: str,
    extraction_method: str,
) -> list[Transaction]:
    result: list[Transaction] = []
    for raw in raw_transactions:
        merchant = clean_merchant(raw.description)
        merchant_key = normalize_merchant_key(merchant)
        tx_id = db.make_transaction_id(account, raw.date.isoformat(), raw.description, raw.amount)
        result.append(
            Transaction(
                id=tx_id,
                date=raw.date,
                description=raw.description,
                merchant=merchant,
                merchant_normalized=merchant_key,
                amount=raw.amount,
                account=account,
                source_file=source_file,
                extraction_method=extraction_method,  # type: ignore[arg-type]
            )
        )
    return result
