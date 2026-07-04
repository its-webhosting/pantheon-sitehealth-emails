#!/usr/bin/env python3
"""Re-record the terminus fixtures for the offline e2e/golden tier (SPEC §5.8, §8).

Runs the program LIVE against the WordPress test site with the terminus shim in
`record` mode, then trims/scrubs the captured fixtures so they are safe to commit and
deterministic to replay:
  * org:site:list  -> keep only the test site (the raw call returns every org site)
  * domain:list    -> keep only the platform domain (drop custom domains so replay makes
                      no live DNS calls)
  * site:team:list -> replace real member emails with test-owner{N}@umich.edu

Read-only against the test site; never uses --all/--for-real.  Run via `./run-tests --record`.

The workdir builder, constants, and shim environment come from tests/conftest.py so there is a
single source of truth; recording goes through the same run_program() interlock as the tests.
"""
import json
import sys
import tempfile
from pathlib import Path

# Import the harness helpers rather than re-implementing them.
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "tests"))
import conftest  # noqa: E402

FIXTURES = conftest.TERMINUS_FIXTURES
SITE = conftest.E2E_SITE
DATE = conftest.E2E_DATE
MINIMAL_CONFIG = conftest.MINIMAL_CONFIG


def _find(argv_prefix):
    for fn in FIXTURES.glob("*.json"):
        d = json.loads(fn.read_text())
        if d.get("argv", [])[: len(argv_prefix)] == argv_prefix:
            return fn, d
    raise SystemExit(f"record: no captured fixture for {argv_prefix}")


def _rewrite(fn, d):
    fn.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


def scrub():
    # org:site:list -> only the test site
    fn, d = _find(["org:site:list"])
    sites = json.loads(d["stdout"])
    kept = {sid: s for sid, s in sites.items() if s.get("name") == SITE}
    if len(kept) != 1:
        raise SystemExit(f"record: expected exactly one {SITE} in org:site:list, got {len(kept)}")
    d["stdout"] = json.dumps(kept)
    d["_scrubbed"] = "trimmed to the test site only (raw call returns all org sites)"
    _rewrite(fn, d)

    # domain:list -> platform domain only (offline-safe replay)
    fn, d = _find(["domain:list"])
    dl = json.loads(d["stdout"])
    plat = {k: v for k, v in dl.items() if v.get("type") == "platform"}
    if not plat:
        raise SystemExit("record: no platform domain in domain:list")
    d["stdout"] = json.dumps(plat)
    d["_scrubbed"] = "custom domains removed so replay makes no live DNS calls"
    _rewrite(fn, d)

    # site:team:list -> scrub emails
    fn, d = _find(["site:team:list"])
    team = json.loads(d["stdout"])
    scrubbed = {}
    for i, (mid, m) in enumerate(list(team.items())[:2]):
        m = dict(m)
        m["email"] = f"test-owner{i + 1}@umich.edu"
        scrubbed[mid] = m
    d["stdout"] = json.dumps(scrubbed)
    d["_scrubbed"] = "real team emails replaced with test-owner{1,2}@umich.edu"
    _rewrite(fn, d)


def main():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as base:
        work = conftest.make_workdir(base)
        # schema (offline), then the live recording run — both through the sanctioned
        # run_program interlock, with the shim in record mode.
        conftest.run_program(["--create-tables", "--config", MINIMAL_CONFIG], cwd=work, mode="record")
        print(f"record: running LIVE against {SITE} (read-only) to capture fixtures ...")
        proc = conftest.run_program([SITE, "--date", DATE, "--config", MINIMAL_CONFIG],
                                    cwd=work, mode="record")
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout[-2000:] + "\n" + proc.stderr[-2000:] + "\n")
            raise SystemExit(f"record: live run failed (exit {proc.returncode})")
    scrub()
    n = len(list(FIXTURES.glob("*.json")))
    print(f"record: captured and scrubbed {n} terminus fixtures in {FIXTURES}")


if __name__ == "__main__":
    main()
