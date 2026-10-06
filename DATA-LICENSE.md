# ECB source data conditions

Source: European Central Bank (ECB).

The original ECB reference rates are available **free of charge** from
[ECB daily XML](https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml).
The committed XML is the dated 2026-10-05 snapshot, not a promise that the daily
URL will continue to return those bytes.

The canonical [ECB disclaimer and copyright terms](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html)
are authoritative. A dated capture from 2026-10-06 is committed and hash-pinned
in `source/fetch-receipts.json` and `metadata/source-rights.json`.

Summary: reuse requires accurate reproduction and ECB attribution, disclosure of
modifications, and free-original availability notices before payment and at each
access where the information is incorporated in sold documents. Business or
promotional links must open the ECB site in the full browser window. Papers that
bear their authors' names have a separate permission exception.

Transformation disclosure: the daily XML was restructured into sorted native
`FxReferenceQuote` rows and SQLite TEXT columns. EUR base currency and ECB
indicative reference kind were made explicit. Original decimal spellings are
unchanged; no cross-rate calculation, rounding or missing-date fill was applied.
The SQLite informational header writer-version bytes 96-99 are cleared for
reproducible packaging; source rows stay unchanged.

These are custom source conditions, without an invented SPDX identifier. Software
licensing is separate. Paid-product applicability and before-payment UI acceptance
remain a root publication gate. The rates are informational; the ECB strongly
discourages their use for transactions.
