# Prompts — db-connection-resilience

The feature began conversationally (no prompt file). The initiating prompt is reproduced
verbatim below; the follow-on prompts are summarized after it, since each was a short reply
inside the same session.

## 1. Initiating prompt (verbatim)

> In three separate `--all` runs, after more than an hour each time, the program has died with
> the backtrace below. While this could be due to a network blip or database server problem, I
> suspect the DB connection may be open too long and that closing and re-opening the connection
> to the database server periodically (say, every 10 sites) might help. Investigate this problem
> (confirm or challenge my supicion) and let me know what you find and recommend. Adhere to
> everything in `prompts/new-feature-standards.md`. Let's brainstorm this.
>
> ```
> Traceback (most recent call last):
>   File "/workspace/.venv/lib/python3.13/site-packages/sqlalchemy/engine/base.py", line 1969, in _exec_single_context
>     self.dialect.do_execute(
>   ...
> MySQLdb.OperationalError: (2013, 'Lost connection to server during query')
>
> The above exception was the direct cause of the following exception:
>
> Traceback (most recent call last):
>   File "/workspace/./pantheon-sitehealth-emails", line 3972, in <module>
>     main()
>   File "/workspace/./pantheon-sitehealth-emails", line 3280, in main
>     op = db_session.get(
>         PantheonOverageProtection, {"site_id": site["id"], "month": d}
>     )
>   ...
> sqlalchemy.exc.OperationalError: (MySQLdb.OperationalError) (2013, 'Lost connection to server during query')
> [SQL: SELECT pantheon_overage_protection.site_id AS pantheon_overage_protection_site_id, ...
> FROM pantheon_overage_protection
> WHERE pantheon_overage_protection.site_id = %s AND pantheon_overage_protection.month = %s]
> [parameters: ('c913655e-b9c0-4781-8294-546f57e0ffed', datetime.date(2025, 6, 1))]
> (Background on this error at: https://sqlalche.me/e/20/e3q8)
> ```

The two facts the diagnosis turned on were supplied in reply to questions during brainstorming:
the MySQL server's `SHOW VARIABLES` output (`wait_timeout` = `interactive_timeout` = 28800, which
**exonerated the database**), and the topology (a Docker Desktop container on the U-M network →
an AWS RDS instance in us-east-1, i.e. at least two NAT/firewall hops).

## 2. Follow-on prompts (summarized)

1. **Brainstorm → spec** — ran under `prompts/new-feature-standards.md`; four expansion decisions
   were taken (see SPEC.md §2.2: flush-then-abort rather than per-site containment; no keepalive
   sysctls; hardcoded pool settings; run metadata in the artifacts).
2. **"Follow the instructions in `prompts/adversarial-review.md`"** — three review rounds against
   SPEC.md + PLAN.md (31 findings, 29 fixed, 2 accepted and written down).
3. **"Is doing another three rounds likely to catch a significant issue?"** — answered no, with the
   evidence (every blocker after round 1 was in scope the review process had itself added), and
   recommended implementing instead.
4. **Implementation** — `superpowers:subagent-driven-development` against PLAN.md, per
   `prompts/implementation-standards.md`.
5. **"run the live smoke test against its-wws-test1"** — passed; `Database reconnects: 0`.
6. **`/code-review max`** — 10 finder angles + verifiers + a gap sweep. 15 findings, several
   CONFIRMED with executed reproductions, including three defects the three adversarial rounds and
   the whole-branch review had all missed.
7. **"fix that wave"**, then **"do the second wave"**, then **"fix the remaining lower-severity
   items too"** — three fix waves, each reviewed.
