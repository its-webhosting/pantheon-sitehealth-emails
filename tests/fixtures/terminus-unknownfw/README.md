# terminus-unknownfw — hand-derived fixtures (do not `--record`)

A copy of `tests/fixtures/terminus/` with exactly one edit: the `org:site:list`
fixture's `framework` for its-wws-test1 is `"mystery"`, driving `main()`'s
unknown-framework branch (campaign I1, SPEC F3).  Like `terminus-cdnchange/`, this
directory is hand-maintained: `./run-tests --record` refreshes only `terminus/` and
`terminus-drupal/`, so keep this copy in sync by hand if those are ever re-recorded.
