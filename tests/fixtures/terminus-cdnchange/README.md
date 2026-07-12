# terminus-cdnchange fixtures

Replay fixtures for the 4th e2e golden, `tests/e2e/test_golden_cdn_change.py` (the Pantheon
CDN-change check driven through the real `main()`).

**These are HAND-MAINTAINED. Neither `./run-tests --record` nor `python tests/tools/record.py
--drupal` refreshes this directory** — both write to `tests/fixtures/terminus/` (WordPress) and
`tests/fixtures/terminus-drupal/`. If Pantheon's JSON shape changes and someone re-records those,
this directory keeps replaying the old shape, and the golden keeps passing while testing a payload
the program will never see again.

Most of these files are copies of `tests/fixtures/terminus/`. Only two are specific to this
golden, and only these two need hand-editing when Pantheon's shape changes:

- the **`domain:list`** fixture — a synthetic **custom** domain (`cdn-change.example.edu`) was
  ADDED alongside the platform domain, so the check has something to find. The other goldens'
  fixtures are platform-only, which is why they can only prove the check stays silent.
- the **`domain:dns`** fixture — Pantheon's required records for that domain. Its filename is a
  hash of the argv, which contains the site **UUID** (`<uuid>.live`), not the site name. If the
  key is wrong, the shim finds no fixture, `terminus()` returns `None`, and the golden renders
  "unavailable" — a plausible-looking golden that silently tests the wrong thing. The golden
  asserts `"unavailable" not in html` precisely so that failure is loud.

When the CDN-change check is deleted after Pantheon's migration, delete this directory with it
(see the removal checklist in `docs/pantheon-cdn-change.md`).
