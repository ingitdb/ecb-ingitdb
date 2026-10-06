from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.util.spec_from_file_location("import_ecb", ROOT / "scripts/import_ecb.py")
ecb = importlib.util.module_from_spec(loader)
loader.loader.exec_module(ecb)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / ecb.SOURCE).read_bytes()

    def test_every_xml_rate_survives_json_sqlite_and_paging_as_exact_text(self):
        rows = ecb.parse_xml(self.raw)
        encoded = ecb.json_bytes(rows)
        self.assertEqual(rows, json.loads(encoded))
        self.assertEqual(len(rows), 29)
        self.assertEqual(next(row["Rate"] for row in rows if row["QuoteCurrencyCode"] == "GBP"), "0.84720")
        self.assertTrue(all(row["Rate"] == row["RateRaw"] for row in rows))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite"
            path.write_bytes(ecb.sqlite_bytes(rows))
            with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(), ("ok",))
                self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [("FxReferenceQuote",)])
                paged = []
                for offset in range(0, 29, 7):
                    paged.extend(db.execute("SELECT * FROM FxReferenceQuote ORDER BY ReferenceDate,QuoteCurrencyCode LIMIT 7 OFFSET ?", (offset,)).fetchall())
                self.assertEqual(paged, [tuple(row[key] for key in ecb.FIELDS) for row in rows])
                self.assertEqual(db.execute("SELECT count(*) FROM FxReferenceQuote WHERE typeof(Rate)<>'text' OR typeof(RateRaw)<>'text'").fetchone(), (0,))
                self.assertEqual(db.execute("SELECT count(*) FROM FxReferenceQuote WHERE ReferenceDate='2026-10-04' OR QuoteCurrencyCode='EUR'").fetchone(), (0,))

    def test_reject_invalid_source_shapes(self):
        cases = [
            self.raw.replace(b"2026-10-05", b"2026-10-04"),
            self.raw.replace(b"currency='USD'", b"currency='GBP'"),
            self.raw.replace(b"currency='USD'", b"currency='EUR'"),
            self.raw.replace(b"rate='1.1204'", b"rate='0.0000'"),
            self.raw.replace(b"rate='1.1204'", b"rate='-1.1204'"),
            self.raw.replace(b"rate='1.1204'", b"rate='1.1204e0'"),
            self.raw.replace(b"rate='1.1204'", b"rate='NaN'"),
            self.raw.replace(b"currency='USD' rate='1.1204'", b"currency='USD'"),
            self.raw.replace(b"<Cube currency='USD' rate='1.1204'/>", b""),
            self.raw.replace(b"<Cube currency='USD' rate='1.1204'/>", b"<Other currency='USD' rate='1.1204'/>"),
            b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]>" + self.raw,
            b"<!ENTITY e 'x'>" + self.raw,
            b"x" * 65537,
        ]
        for raw in cases:
            with self.subTest(raw=raw[:80]), self.assertRaises((ValueError, ecb.ET.ParseError)):
                ecb.parse_xml(raw)

    def test_exact_pins_and_repeatable_generation(self):
        built = ecb.build()
        self.assertEqual(built, ecb.build())
        for path, data in built.items():
            self.assertEqual((ROOT / path).read_bytes(), data)
        receipt = json.loads(built["source/artifact-snapshot.json"])
        for group in ("inputs", "terms", "outputs"):
            for pin in receipt[group]:
                data = (ROOT / pin["path"]).read_bytes()
                self.assertEqual(len(data), pin["bytes"])
                self.assertEqual(ecb.digest(data), pin["sha256"])
        self.assertFalse(receipt["publication"]["query"])
        self.assertFalse(receipt["publication"]["available"])
        rights = json.loads(built["metadata/source-rights.json"])
        self.assertEqual(set(rights), {"format", "capturedAt", "attribution", "freeSource", "transformations", "inputs", "terms"})
        profile = json.loads(built["metadata/data-rights-profile.json"])
        self.assertEqual(profile["recordsets"], {})
        self.assertNotIn("server", profile)
        self.assertNotIn("spdx", profile["database"])
        self.assertEqual(profile["provenance"], ecb.pin("metadata/source-rights.json", built["metadata/source-rights.json"]))

    def test_pinned_inputs_fail_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (ecb.SOURCE, ecb.TERMS):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / relative).read_bytes())
            (root / ecb.SOURCE).write_bytes(self.raw.replace(b"0.84720", b"0.84721"))
            with self.assertRaisesRegex(ValueError, "raw XML"):
                ecb.build(root)
            (root / ecb.SOURCE).write_bytes(self.raw)
            (root / ecb.TERMS).write_bytes(b"changed terms")
            with self.assertRaisesRegex(ValueError, "captured terms"):
                ecb.build(root)


if __name__ == "__main__":
    unittest.main()
