# Persist custom chord sequences in SQLite while keeping the song catalog in CSV

Sequence search (`GET /similares?sequencia=...`) was limited to six sequences
hardcoded in `main.py`, matched against a pre-computed `SEQ_FAMOSA` tag in the
CSV. There was no way to register a new sequence, no runtime matching, and no
catalog: the frontend kept its own four hardcoded sequences, so the feature
could not grow without a code change and a redeploy.

We are introducing a small embedded catalog for chord sequences, backed by
SQLite, and moving sequence matching to runtime. The six existing sequences
are seeded into the database and every sequence — old or new — is matched with
one rule: the sequence must appear as a contiguous ordered block in the song's
chord list and the song must not use any chord outside the sequence's
vocabulary. This is the rule the research measured against the real dataset;
it reproduced the six current result sets exactly (zero missing, zero extra),
while the more intuitive contiguous-subsequence rule added hundreds or
thousands of songs. Matching therefore reads `musica.cifra` (ordered, with
repetitions) and no longer consults `SEQ_FAMOSA`, which remains in the CSV only
as legacy data.

SQLite was chosen because it is already available in `python:3.9-slim` through
the standard library, so it adds no dependency and no rebuild cost. It provides
a single file, transactions, and a `UNIQUE` constraint for deduplication, which
is enough for an open, anonymous catalog. The database file lives at
`/app/instance/sequencias.db`, outside `/app/data`, so a volume does not shadow
the CSV copied into the image. The `Dockerfile` declares `VOLUME
/app/instance`; without it the catalog survives `docker restart` but is lost
when the container is removed. The song and genre catalogs stay exactly as they
are: loaded from the CSV into memory at startup, per the task constraint.

The trade-offs are deliberate. The chosen matching rule is stricter than the
intuitive notion of "the progression appears": a song that contains the
progression but also uses an extra chord outside the sequence will not match.
That is the price of keeping the six existing searches byte-for-byte
compatible. The old query form without commas (`GET
/similares?sequencia=CGAmF`) is intentionally no longer supported; only the
canonical comma-separated form used by the frontend is accepted, and that
format preserves the six existing result sets. Matching now scans `musica.cifra` on every request (about 3.5
million chord tokens in total), which is acceptable with the current single
gunicorn worker but should be measured and cached if traffic or worker count
grows. SQLite serializes writes; the current single-writer setup is fine, and
WAL mode plus short transactions keeps it safe if that changes. Finally, the
seed and schema must be idempotent at startup; if the database file is deleted,
the six original sequences are recreated automatically, but any custom
sequences are lost unless the volume is in place.
