# Prompt: refresh terminus fixtures and goldens

Reusable prompt for the periodic maintenance chore of re-syncing the offline fixtures with what
Pantheon actually returns today, and regenerating the rendered-report snapshots.

---

Refresh the harness's recorded fixtures and golden snapshots:

1. Run `./run-tests --record`. This runs the program live (read-only) against `its-wws-test1`,
   re-captures the terminus responses, and re-applies the trims/scrubs (org list → test site
   only, domain list → platform domain only, team emails → `test-owner{1,2}@umich.edu`).
2. `git diff tests/fixtures/terminus/` — review the changes. Confirm no real customer data or
   emails leaked in, and that only expected fields moved. Each fixture should still carry a
   `recorded` date.
3. Run `./run-tests --fast`. If the rendered output changed *intentionally* because the fixtures
   changed, run `./run-tests --update-goldens` and review the snapshot diff; otherwise investigate
   the failure.
4. Run the `live` tier (`./run-tests -m live`) to confirm the real Terminus surface still matches
   what the fixtures assume.
5. Show the diffs and the final green run.

Never commit fixtures containing real owner emails or the full org site list — the scrub/trim in
`tests/tools/record.py` handles this, but verify.
