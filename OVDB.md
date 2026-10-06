# ECB source fixture; publication pending

This file intentionally has **no OVDB Publisher opt-in frontmatter**. There is no
root `ovdb.yaml` or public database descriptor until reviewed model/meaning
bindings and released schema contracts exist. The source artifact and prepared
rights block alone do not bypass those validators or admit public queries.

Owner repository: `https://github.com/ingitdb/ecb-ingitdb`.
Candidate local id: `ecb`. Native recordset: `FxReferenceQuote`.
Coverage: 29 EUR reference quotes for calendar date 2026-10-05 only.

`metadata/data-rights-profile.json` prepares the database-scoped raw declaration.
The eventual manifest and descriptor must retain that identical authorship block,
with required materialized `licences.data` equal to its `database` declaration;
the recordset inherits the same whole declaration. The profile's local path/hash/
byte-count references inherit the selected provider commit. Do not embed the
commit being generated in its own evidence files.

Shared Cloud server-scope terms must not be invented from this dataset's terms.
Server inheritance and recordset override behavior belong in synthetic validator
tests and the real runtime acceptance gate. No public available/query/verified
flag is activated by this repository.
