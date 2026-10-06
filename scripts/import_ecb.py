#!/usr/bin/env python3
"""Convert only the reviewed dated ECB XML fixture, without network access."""
import argparse
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-10-05"
SOURCE = "source/ecb-2026-10-05.xml"
SOURCE_SHA256 = "8ba05b7b0c3afdac3dad7ac653a459df998383b7971386d630984aeb3872c424"
TERMS = "source/ecb-terms-2026-10-06.html"
TERMS_SHA256 = "e1e193a97f9cddc2ce45cedefc08e854c6ad4fc15103ef67d1c575adc9723be4"
SOURCE_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
TERMS_URL = "https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html"
RECORDSET = "FxReferenceQuote"
ARTIFACT = "artifacts/ecb-2026-10-05/native/ecb.sqlite"
ROWS = "artifacts/ecb-2026-10-05/native/FxReferenceQuote.json"
NS = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"
GESMES = "http://www.gesmes.org/xml/2002-08-01"
FIELDS = ("ReferenceDate", "BaseCurrencyCode", "QuoteCurrencyCode", "Rate", "RateRaw", "RateKind", "Provider")
CURRENCIES = frozenset("USD JPY CZK DKK GBP HUF PLN RON SEK CHF ISK NOK TRY AUD BRL CAD CNY HKD IDR ILS INR KRW MXN MYR NZD PHP SGD THB ZAR".split())
TRANSFORMATION = "ECB daily XML Cube attributes were restructured into sorted FxReferenceQuote rows and SQLite TEXT columns. EUR base currency and ECB indicative reference kind were made explicit. Source decimal spellings are unchanged; no derived pairs, rounding or missing-date fill were applied. SQLite header writer-version bytes 96-99 are zeroed for reproducible packaging; source rows are unchanged."


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def parse_xml(data):
    """Strict daily shape; no DTD, entities, external resolution or float coercion."""
    if not isinstance(data, bytes) or len(data) > 65536:
        raise ValueError("daily XML must be bounded bytes")
    text = data.decode("utf-8")  # Reject alternate encodings before parsing.
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise ValueError("DTD and entity declarations are forbidden")
    root = ET.fromstring(text)
    if root.tag != f"{{{GESMES}}}Envelope" or root.attrib:
        raise ValueError("unexpected ECB envelope")
    if [x.tag for x in root] != [f"{{{GESMES}}}subject", f"{{{GESMES}}}Sender", f"{{{NS}}}Cube"]:
        raise ValueError("unexpected ECB envelope children")
    subject, sender, container = root
    if subject.text != "Reference rates" or subject.attrib or len(subject):
        raise ValueError("unexpected source subject")
    if sender.attrib or len(sender) != 1 or sender[0].tag != f"{{{GESMES}}}name" or sender[0].text != "European Central Bank" or sender[0].attrib or len(sender[0]):
        raise ValueError("unexpected source sender")
    if container.attrib or len(container) != 1:
        raise ValueError("expected one reference date")
    day = container[0]
    if day.tag != f"{{{NS}}}Cube" or day.attrib != {"time": DATE}:
        raise ValueError("snapshot reference date must be 2026-10-05")
    quotes = {}
    for cube in day:
        if cube.tag != f"{{{NS}}}Cube" or len(cube) or set(cube.attrib) != {"currency", "rate"}:
            raise ValueError("unexpected quote shape")
        currency, rate = cube.attrib["currency"], cube.attrib["rate"]
        if currency not in CURRENCIES or currency in quotes:
            raise ValueError("unknown or duplicate quote currency")
        if not re.fullmatch(r"[0-9]+\.[0-9]+", rate) or Decimal(rate) <= 0:
            raise ValueError("rate must be a positive exact decimal lexeme")
        quotes[currency] = rate
    if set(quotes) != CURRENCIES:
        raise ValueError("expected the complete 29-currency dated snapshot")
    return [dict(zip(FIELDS, (DATE, "EUR", currency, quotes[currency], quotes[currency], "ECB indicative reference", "ECB"))) for currency in sorted(quotes)]


def sqlite_bytes(rows):
    # Build a fresh fixed-page-size database. Byte reproducibility is checked on
    # regeneration; SQLite runtime version is recorded separately in the receipt.
    with tempfile.TemporaryDirectory(prefix="ecb-native-") as directory:
        path = Path(directory) / "ecb.sqlite"
        with closing(sqlite3.connect(path)) as db:
            db.execute("PRAGMA page_size=4096")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA user_version=1")
            db.execute('''CREATE TABLE FxReferenceQuote (
                ReferenceDate TEXT NOT NULL CHECK (ReferenceDate = '2026-10-05'),
                BaseCurrencyCode TEXT NOT NULL CHECK (BaseCurrencyCode = 'EUR'),
                QuoteCurrencyCode TEXT NOT NULL,
                Rate TEXT NOT NULL,
                RateRaw TEXT NOT NULL CHECK (RateRaw = Rate),
                RateKind TEXT NOT NULL CHECK (RateKind = 'ECB indicative reference'),
                Provider TEXT NOT NULL CHECK (Provider = 'ECB'),
                PRIMARY KEY (ReferenceDate, QuoteCurrencyCode)
            ) WITHOUT ROWID''')
            db.executemany("INSERT INTO FxReferenceQuote VALUES (?,?,?,?,?,?,?)", [tuple(row[field] for field in FIELDS) for row in rows])
            db.commit()
        data = bytearray(path.read_bytes())
        # SQLite stores the build's library version in header bytes 96-99.
        # Clear only that informational field, not format/read/write versions
        # or change counters. An artifact's writer build is not source data.
        # https://www.sqlite.org/fileformat.html#write_library_version_number_and_version_valid_for_number
        data[96:100] = b"\0" * 4
        return bytes(data)


def pin(path, data):
    return {"path": path, "sha256": digest(data), "bytes": len(data)}


def build(root=ROOT):
    raw, terms = (root / SOURCE).read_bytes(), (root / TERMS).read_bytes()
    if len(raw) != 1547 or digest(raw) != SOURCE_SHA256:
        raise ValueError("raw XML differs from reviewed snapshot")
    if len(terms) != 107588 or digest(terms) != TERMS_SHA256:
        raise ValueError("captured terms differ from dated evidence")
    rows = parse_xml(raw)
    sqlite, encoded_rows = sqlite_bytes(rows), json_bytes(rows)
    parser = (root / "scripts/import_ecb.py").read_bytes()
    receipt = {
        "format": "ecb-snapshot/1", "referenceDate": DATE,
        "coverage": {"kind": "dated-snapshot", "recordset": RECORDSET, "rows": 29, "baseCurrencyCode": "EUR", "quoteCurrencies": sorted(CURRENCIES)},
        "inputs": [{**pin(SOURCE, raw), "url": SOURCE_URL, "observedAt": "2026-10-06T06:02:46.177959+00:00", "lastModified": "Mon, 05 Oct 2026 13:56:17 GMT"}],
        "terms": [{**pin(TERMS, terms), "url": TERMS_URL, "observedAt": "2026-10-06T06:04:40.180917+00:00"}],
        "generator": {**pin("scripts/import_ecb.py", parser), "runtime": "Python standard library; byte-checked fresh SQLite generation"},
        "outputs": [pin(ARTIFACT, sqlite), pin(ROWS, encoded_rows)],
        "decimalEncoding": {"Rate": "positive exact decimal encoded as TEXT/string", "RateRaw": "unchanged XML decimal lexeme", "arithmetic": "none"},
        "attribution": {"text": "Source: European Central Bank (ECB).", "url": "https://www.ecb.europa.eu/"},
        "freeSource": {"text": "The original ECB reference rates are available free of charge from the ECB website. This is a dated 2026-10-05 snapshot; the linked daily XML may later show another date.", "url": SOURCE_URL},
        "transformations": [TRANSFORMATION],
        "publication": {"query": False, "available": False, "deploymentVerified": False, "status": "source fixture; publication and semantic bindings pending"},
    }
    provenance = {
        "format": "ovdb-source-rights/1", "capturedAt": "2026-10-06",
        "attribution": receipt["attribution"], "freeSource": receipt["freeSource"],
        "transformations": receipt["transformations"],
        "inputs": [pin(SOURCE, raw)], "terms": [pin(TERMS, terms)],
    }
    provenance_bytes = json_bytes(provenance)
    profile = {
        "format": "ovdb-data-rights/1",
        "database": {"name": "ECB reuse conditions", "url": TERMS_URL,
                     "text": "Summary of ECB source conditions: reproduce accurately and credit the ECB; disclose modifications. For information incorporated in sold documents, inform buyers before payment and on each access that the original is available free from the ECB. Open ECB business/promotional links in the full browser window. Author-named papers have a separate permission exception. The canonical linked terms govern. Rates are published for information purposes; transaction use is strongly discouraged."},
        "recordsets": {}, "provenance": pin("metadata/source-rights.json", provenance_bytes),
    }
    return {ARTIFACT: sqlite, ROWS: encoded_rows,
            "source/artifact-snapshot.json": json_bytes(receipt),
            "metadata/source-rights.json": provenance_bytes,
            "metadata/data-rights-profile.json": json_bytes(profile)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="byte-compare committed artifacts without modifying them")
    args = parser.parse_args()
    for relative, data in build().items():
        path = ROOT / relative
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                raise SystemExit(f"artifact differs: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print("Verified 29 dated EUR quotes; lexical decimals preserved." if args.check else "Generated dated 2026-10-05 snapshot (29 quotes).")


if __name__ == "__main__":
    main()
