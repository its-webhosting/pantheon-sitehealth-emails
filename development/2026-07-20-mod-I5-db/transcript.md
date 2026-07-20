# Session transcript

## User

start I5 by reading CAMPAIGN.md + LEDGER.md first

## Assistant

I'll start I5 by reading the governing documents in full, as CLAUDE.md requires. Reading CAMPAIGN.md and LEDGER.md now.

### ⚙ Tool call: `Read`

```json
{
  "file_path": "/workspace/development/2026-07-17-modularization-campaign/CAMPAIGN.md"
}
```

### ↳ Tool result

```
1	# CAMPAIGN.md — Modularization Campaign (frozen architecture)
2	
3	**Status:** approved design, 2026-07-17. Brainstormed and approved section-by-section in
4	the campaign planning session (see `transcript.md` once archived); prompt in `PROMPT.md`.
5	
6	This is the **one** copy of the campaign's architecture, decisions, invariants, and
7	increment plan. Increment specs **cite this document and re-derive nothing** — the
8	campaign-level brainstorm and adversarial review run once, here; increments inherit that
9	scrutiny and do not repeat it. Any change to this document is an **amendment**: edit the
10	document *and* append a ledger entry (`LEDGER.md`) saying what changed and why. An
11	increment spec that contradicts this document without a ledger amendment is wrong by
12	definition.
13	
14	Related documents (all in this directory unless pathed): `PROMPT.md` (the campaign
15	request), `BLOCKMAP.md` (the B1–B60 functional map of `main()` all scope assignments
16	reference), `LEDGER.md` (append-only cross-increment record), `/workspace/CONTEXT.md`
17	(domain glossary — created by this campaign), `/workspace/prompts/directives.md` (the
18	Spine; PD#n citations below refer to it).
19	
20	## Glossary (campaign terms — domain terms live in `CONTEXT.md`)
21	
22	- **Campaign** — this whole program of work: one architecture, N increments.
23	- **Increment** — one unit of work with its own session, spec, implementation, review,
24	  commit, and archive. Numbered I0–I14.
25	- **Wave** — an ordered group of increments (0–4); increments within a wave may be
26	  reordered if the ledger records why, waves may not.
27	- **Block** — a `Bnn` region of `main()` per `BLOCKMAP.md`; the stable unit of scope
28	  assignment.
29	- **Core package** — the new importable `psh/` package holding infrastructure (Tier 1).
30	- **Gateway** — `psh/gateway.py`, the single module through which every Terminus/WP-CLI/
31	  Drush subprocess flows; the future Pantheon-API replacement seam.
32	- **Façade** — `script_context.py` (`sc`), the stable API surface that checks and plugins
33	  import; implementations move, the façade's names do not break.
34	- **Contract** — the per-phase guaranteed `site_context` keys (CLAUDE.md table), which
35	  this campaign turns into a machine-readable **contract registry**.
36	- **Hook DAG** — the per-phase topological ordering of hooks derived from declared
37	  `consumes`/`produces` keys, validated fatally at startup.
38	- **Ratchet** — the lint/type regime: broad ruff+pyright rules applied as a hard gate to
39	  moved/new modules immediately, the remnant grandfathered until I14.
40	- **Remnant** — whatever remains of the original script at any point mid-campaign.
41	- **Shim** — the thin committed `./pantheon-sitehealth-emails` entry script that calls
42	  `psh.cli.main()` after I0.
43	- **Ledger** — `LEDGER.md`; how increment N learns what N−1 actually did.
44	- **Behavior bar** — the tiered definition of which observable behavior may change (§8).
45	- **Invariant** — a named property no increment may alter (§9).
46	
47	**MUST** = required, violation fails review. **NEVER** = prohibited, violation fails
48	review. **SHOULD** = required unless the increment spec states why not. **MAY** =
49	allowed, at the implementer's judgment.
50	
51	## 1. Goal and non-goals
52	
53	**Goal.** Modularize the 4,752-line main script into (a) a `psh/` core package of
54	infrastructure modules, (b) self-registering `check/` packages for every notice/section
55	emitter, and (c) the existing `plugin/` integrations — taking full advantage of the hook
56	system — while the four e2e goldens stay byte-identical, the per-phase contract is
57	honored, and the non-U-M path keeps working. End state: `main()` is a ~250–400-line
58	orchestrator; every U-M-specific behavior lives in `umich` packages; the whole tree
59	passes the broadened ruff+pyright configuration.
60	
61	**Non-goals** (exhaustive; each is either declined or deferred with reasoning in §15):
62	replacing terminus with the Pantheon API; implementing parallel site processing; any new
63	report content (CSV attachment, cached-% column, env-lock section); SendGrid; refreshing
64	goldens or recorded fixtures; changing what any check reports (except the named bug
65	fixes in I1).
66	
67	## 2. Decision record (exhaustive — from the approved brainstorm)
68	
69	| # | Decision | Choice | Why |
70	|---|---|---|---|
71	| D1 | Pantheon API | **Seam only**: gateway module now, transport swap post-campaign | Swapping transports mid-campaign invalidates terminus fixtures + goldens in every touched increment |
72	| D2 | Lint/type broadening | **Ratchet in-campaign** (§13) | Code is cleaned exactly once, as it moves; bar fixed in I0 so it never shifts |
73	| D3 | Behavior bar | **Tiered, config renames allowed** (§8) | Cleanest final schema; production config edited once, at I14, with a migration table |
74	| D4 | Increment granularity | **Fine: 15 increments** | Safest for session/context limits; split-never-compress backstop (§12) |
75	| D5 | Target architecture | **Three-tier split** (§3) | Infrastructure ≠ report content ≠ data source; fulfills "full advantage of the frameworks" |
76	| D6 | Hook flexibility | **Phases stay; hooks declare consumes/produces; per-phase DAG validated at startup** (§4) | Keeps every existing hook/test valid; a phase-less key scheduler rewrites everything for no added power |
77	| D7 | `--only-warn` plan rec | **In campaign** (I7) | Small, no golden impact, existing TODO |
78	| D8 | Parallel-ready | **Design constraint only** (§3.4) | Near-free now; actual parallelism stays a README TODO |
79	| D9 | CSV attachment / cached-% / env-lock | **README TODO** | Each changes rendered email → golden churn mid-campaign |
80	| D10 | Packaging | **Real package + thin shim** (I0; console-script dropped — see LEDGER I0 amendment 1) | Dissolves the extension-less-script problem; normal imports for tests/pyright/ruff |
81	
82	## 3. Target architecture
83	
84	```
85	                 ./pantheon-sitehealth-emails  (thin shim)
86	                                │
87	                        psh.cli.main()  ── orchestrator: bootstrap, site loop,
88	                                │           phase firing, lifecycle dispatch
89	        ┌───────────────────────┼──────────────────────────┐
90	        ▼ Tier 1: psh/ core     ▼ seams (sc façade)        ▼
91	  configuration  modules   ┌─────────────────────┐   Tier 3: plugin/
92	  gateway        db        │  hook phases + DAG  │   aws  cloudflare
93	  traffic        plans     │  contract registry  │   env  umich
94	  gather         charts    └─────────┬───────────┘   (unchanged roles)
95	  render         mail                ▼
96	  lifecycle                Tier 2: check/  (all notice/section emitters)
97	                           pantheon  wordpress  drupal  addon_updates
98	                           dns  cloudflare  pantheon_cdn_change  umich
99	```
100	
101	### 3.1 Tier 1 — `psh/` core package (exhaustive module map)
102	
103	| Module | Receives (functions / blocks) |
104	|---|---|
105	| `psh/cli.py` | `build_arg_parser`, `parse_args`, arg validation (B5), `main()` orchestrator |
106	| `psh/configuration.py` | `process_config`, `config_substitution`, `gate_disabled_sections`, DEFER machinery, `load_news_items`, `umich_enabled`, `cloudflare_enabled` |
107	| `psh/modules.py` | `find_modules`, module loading (B2/B4), hook engine (`add_hook`/`invoke_hooks`/`PHASES`), DAG build/validation, contract registry |
108	| `psh/gateway.py` | `run_terminus`, `terminus`, `terminus_data`, `wp`, `wp_eval`, `drush`, `drush_php_script`, `fix_drush_output`, `wp_error`, `drush_error`, `TerminusError` |
109	| `psh/notice.py` | `Notice`, `Severity`, `NoticeRegistry`, `DuplicateNoticeCodeError`, `registry` (added I3; §6 Notice type + code registry) |
110	| `psh/db.py` | ORM models, `TrafficRow`/`OverageProtectionRow`, `db_engine_args`, `db_retry`/`db_retryable`/`record_db_reconnect`, `update_traffic_rows`, `insert_traffic_rows`, `load_traffic_rows`, `load_overage_protection_window`, `DatabaseUnavailableError` |
111	| `psh/traffic.py` | `get_old_metrics`, `estimate_month_visits`, `build_traffic_table_rows`, the `traffic_table_columns` global, metrics gather + DB update/load flow (B22–B26), visits-by-month aggregation (B43) |
112	| `psh/plans.py` | plan_info normalization (B12 part), SKU resolution (B17), `overage_blocks`, `contract_year_end`, `plan_costs`, `build_plan_over_time`, the `cost_table_columns` global, recommendation flow (B47) |
113	| `psh/gather.py` | Slimmed framework gathers feeding the `site_post_gather` contract (from B32–B35), `check_wordpress_plugin`/`check_drupal_module` helpers |
114	| `psh/charts.py` | Cap geometry (B13 part), chart data prep + matplotlib build (B44–B45) — returns PNG bytes |
115	| `psh/render.py` | Jinja render (B53), PHP inline + `!important` pass (B54), `escape_url` |
116	| `psh/mail.py` | Recipient resolution (B49), MIME assembly (B55), `smtp_login`, send (B57) |
117	| `psh/lifecycle.py` | `RunState`, `finish_run`, `abort_run`, `abort_reason`, `resume_point`, `resume_command`, `rerun_command`, `option_strings_taking_a_value`, `sites_from_resume_point`, `merge_prior_results`, `ResumeSiteNotFoundError` |
118	
119	`dns_classify.py` stays a top-level module (already extracted; moving it into `psh/` is
120	MAY-scope for I14, decided by ledger state then).
121	
122	**Whole-file coverage.** The campaign modularizes the entire script, not just `main()`:
123	every top-level def and module-level global in `pantheon-sitehealth-emails` (lines
124	1–2107 included) is assigned to a `psh/` module in this table and appears in exactly one
125	increment's scope (§11). End state: the original file is the thin shim and nothing else
126	— a top-level def still there at I14 is a defect the closing audit (§17) catches. Moved
127	helpers get the full §7 treatment (types, ratchet, verified docs, tests); they do NOT
128	get algorithmic redesign — moves are behavior-preserving except where §8 says otherwise
129	(I1, I7's D7, I12's B51).
130	
131	### 3.2 Tier 2 — new/changed `check/` packages (exhaustive)
132	
133	| Package | Contents (blocks) | Phase(s) |
134	|---|---|---|
135	| `check/pantheon/` (new) | frozen site (B19), no-live-env (B21), upstream updates (B38), PHP EOL (B41) | `site_pre` (frozen, no-live-env), `site_post_gather` (updates, PHP EOL) |
136	| `check/wordpress/` (new) | PAPC + native-sessions checks, OCP config probe, favicon (from B34) | `site_post_gather` |
137	| `check/drupal/` (new) | PAPC module check, D7 EOL + tag1_d7es, multisite probe (from B30/B35) | `site_post_dns` (multisite), `site_post_gather` |
138	| `check/addon_updates/` (new) | add-on updates table notice (B39), smell notices (B48) | `site_post_gather` |
139	| `check/umich/` (existing, grows) | umich-oidc-login, Hummingbird fork (B34), Drupal UA check (B35), annual-billing notices (B50/B51), portal-URL text for the recommendation notice (B47's U-M half) | `site_post_gather`, `site_pre_render` (billing) |
140	
141	`check/dns/`, `check/cloudflare/`, `check/pantheon_cdn_change/` are untouched tenants.
142	A check MAY fetch its own data through `sc` gateway wrappers when the data is
143	check-specific (e.g. `upstream:updates:list`); data used by core *and* checks is
144	published through the contract instead (e.g. `envs`).
145	
146	### 3.3 What stays in `main()` (exhaustive, with why)
147	
148	Config/arg bootstrap ordering (B1–B8 — the two-pass substitution *order* is the
149	program); overage constants + date window (B9, B13 part); the site-loop skeleton (skips,
150	banner, sorted order, resume filter — B14–B18, B20, B25, B42); phase firing and contract
151	stuffing (B27, B28, B31, B37, B52); notice sort + subject (B50 minus billing); the
152	`try`/`except BaseException` lifecycle dispatch (B59–B60 call sites). Everything else
153	leaves. Target: 250–400 lines.
154	
155	### 3.4 Parallel-ready constraint (D8)
156	
157	Per-site work MUST be a function of `(site, config, db_session, site_context)`: no new
158	module-level mutable state; run-scoped accumulators live only in `RunState`. This is a
159	review criterion from I2 onward, not a parallelism implementation.
160	
161	### 3.5 The `sc` façade
162	
163	Checks and plugins import **only** `sc` (and their own package). `sc` keeps every name
164	listed in CLAUDE.md's runtime-exposed block, re-exporting from `psh/` modules as they
165	move. NEVER remove or rename an `sc` attribute mid-campaign; additions are fine. The
166	house-rules test suite gains an assertion that every documented `sc` name exists (I2).
167	
168	## 4. Phases, hooks, and the DAG
169	
170	Phases stay the coarse spine: `setup`, `site_pre`, `site_post_traffic`, `site_post_dns`,
171	`site_post_gather`, `site_pre_render`, plus **new** `run_finish` (fired inside
172	`finish_run` before artifacts are written, receiving the `RunState`; for future run-level
173	artifact hooks — no consumer at introduction, like `site_pre_render` was). Dotted
174	plugin-defined events are unchanged.
175	
176	From I4, `add_hook` requires two new entries per hook: `consumes` and `produces` — each
177	a (possibly empty) list of contract-key names. Validation at module-load completion
178	(exhaustive fatal conditions):
179	
180	1. A consumed key that nothing produces (neither core's registry for that phase or an
181	   earlier phase, nor another hook) → fatal.
182	2. Two producers of the same key → fatal (one owner per key; PD#1 — a silent overwrite
183	   is a silent failure).
184	3. A cycle among same-phase hooks → fatal.
185	4. A hook consuming a key first produced in a *later* phase → fatal.
186	5. A missing `consumes`/`produces` entry on any hook → fatal (no legacy mode; I4
187	   retrofits all in-repo hooks in the same change).
188	
189	`invoke_hooks` orders same-phase hooks topologically (producers before consumers;
190	registration order breaks ties, so existing behavior is preserved where no edges exist).
191	The permanent test `tests/integration/test_hook_dag.py` loads **all** real check/plugin
192	packages and asserts the DAG builds — the "future changes can never make the DAG
193	impossible" guarantee — and a unit suite proves each fatal condition actually fires
194	(PD#14: the validator must be shown able to go red).
195	
196	```
197	 module load ──► collect hooks ──► per phase: build edges (produces→consumes)
198	                                        │
199	                              cycle? unknown key? dup producer? ──► fatal exit (named error)
200	                                        │ ok
201	                                topo order stored ──► invoke_hooks uses it
202	```
203	
204	**Contract registry.** `psh/modules.py` holds the machine-readable registry: phase →
205	keys core stuffs (today's CLAUDE.md table, verbatim). Core's stuffing code is checked
206	against it in tests; CLAUDE.md's table gains a line saying the registry is authoritative.
207	New contract keys added by increments (exhaustive for this campaign): `envs` (I8, at
208	`site_pre`), `add_on_updates` + `wp_smell`/`drush_smell`/`composer_smell` (I9/I10, at
209	`site_post_gather`), plan/cost keys `current_plan`, `recommended_plan`, `plan_costs`,
210	`savings` (I7, at `site_pre_render`). Each addition updates registry + CLAUDE.md table +
211	ledger in the same increment.
212	
213	## 5. Configuration
214	
215	Principles: one section per feature, named for the operator's mental model; every
216	relocated check gets an `enabled` flag under `[Check.<name>]`, **default true** —
217	relocating code MUST NOT silently disable a check that runs unconditionally today.
218	U-M-only checks additionally require `[UMich].enabled` (existing `umich_enabled()`
219	rule). `gate_disabled_sections()` semantics (nested `enabled`, children dropped) apply to
220	`[Check.*]` unchanged.
221	
222	Example (actual TOML, the shape I8 introduces — illustrative of the family, exhaustive
223	for `check/pantheon/`):
224	
225	```toml
226	[Check.pantheon]
227	enabled = true          # frozen-site, live-env, upstream-updates, PHP-EOL checks
228	```
229	
230	New keys land in final shape as introduced (I3 onward). Renames/moves of *existing* keys
231	happen once, in I14, which MUST deliver: the old→new migration table in
232	`docs/config-migration.md`, a rewritten `sample-pantheon-sitehealth-emails.toml`, and
233	exact edit instructions for the production config repo. Until I14, every existing
234	production key keeps working unchanged.
235	
236	## 6. Types
237	
238	Reused as-is: `TrafficRow`, `OverageProtectionRow`, `DnsFacts`, `FetchResult`,
239	`SiteContext`. Introduced (exhaustive):
240	
241	| Type | Increment | Shape |
242	|---|---|---|
243	| `GatewayResult` | I2 | NamedTuple `(result, errors, fatal)` replacing the anonymous 3-tuples |
244	| `Notice` | I3 (class) → adopted per increment | frozen dataclass: `severity` (StrEnum alert/warning/info), `code` (unique — registry test), `html`, `text`, `short`, `icon`, `order`; `SiteContext.add_notice` accepts `Notice` or legacy dict; dict form retired in I14 |
245	| `PlanInfo` / `PlanCatalog` | I7 | typed view over `[Pantheon.plan_info]` |
246	| `RunState` | I13 | dataclass holding `all_warnings`, `site_results`, `site_savings`, `emails_sent`, reconnect counters |
247	
248	House-style tuple annotations (`-> (str, str, bool)`) are replaced with real annotations
249	in every module as it moves — never fixed in place in the remnant (one pass per line,
250	D2). CLAUDE.md's house-style note is updated in I14 when the last one dies.
251	
252	## 7. Per-increment obligations
253	
254	Every increment MUST (this list is exhaustive and lives only here; increment specs cite
255	it): (1) start by reading `CAMPAIGN.md`, `LEDGER.md`, `CLAUDE.md`, `BLOCKMAP.md` rows in
256	scope; (2) follow `prompts/implementation-standards.md` (subagent-driven, test-first,
257	`psh-implementer`/`psh-reviewer`); (3) replace house styles in moved code (§6);
258	(4) verify — not assume — every claim in comments/docs it moves or writes;
259	(5) update tests in the same change; (6) update README/docs/CLAUDE.md for what moved;
260	(7) update auto-memory where a durable fact changed; (8) append its ledger entry
261	(§12); (9) preserve every invariant (§9); (10) end with `/code-review`, a full
262	`./run-tests`, and one checkpoint commit including its `development/` folder.
263	
264	## 8. Behavior bar (canonical gate table)
265	
266	| Surface | Rule | Until |
267	|---|---|---|
268	| Rendered emails (4 goldens) | NEVER change (byte-identical) | end of campaign |
269	| `-results.json` / `-notices.csv` / `-run.json` structure (keys, row shape) | NEVER change | end of campaign |
270	| Notice csv *values* | MAY change only in I1 (named bug fixes) and I12 (scheduled B51 deletion) | — |
271	| stdout / console / error messages | MAY improve freely | — |
272	| Config: existing keys | NEVER break | I14 (renames with migration table) |
273	| Config: new keys | MUST land in final schema shape | — |
274	| Exit codes, resume semantics, artifact write gates | NEVER change | end of campaign |
275	
276	## 9. Named invariants (exhaustive; NEVER violated by any increment)
277	
278	1. Four e2e goldens byte-identical (`./run-tests` proves it; refresh is forbidden — an
279	   existing golden going red is a defect in the increment, PD#14).
280	2. Per-phase data contract: existing keys never removed/renamed/retyped; additions only.
281	3. Non-U-M path works: non-U-M golden green; no new un-gated U-M content (I1 *removes*
282	   the one known leak).
283	4. Run lifecycle: single `except BaseException` flush path; `abort_reason`'s three
284	   outcomes; artifacts dropped-site rule; notices appended before send; resume-point
285	   next-site-after-email rule; soft-wrapped copy-pasteable commands.
286	5. DB: `db_retry` retries whole idempotent units only; `db_retryable` predicate
287	   unchanged; the read-release commit in the loaders stays (guarded by
288	   `test_load_traffic_rows_releases_the_connection`).
289	6. Rich console rules: escape untrusted text; production width reproduced in tests.
290	7. Test safety interlock (`run_program` forbidden flags) never bypassed or weakened.
291	8. Column-0 `f"""` notice literals move **verbatim** — never re-indented; `git diff -w`
292	   is not acceptable evidence for any change touching them.
293	9. Checks/plugins import only `sc`; `sc` names never removed mid-campaign (§3.5).
294	10. Recorded fixtures are not regenerated (`terminus-cdnchange/` is hand-maintained and
295	    `--record` must not run).
296	11. `--create-tables`/`--update`/`--import-older-metrics` phase-gating rules (CLAUDE.md
297	    table) unchanged.
298	
299	## 10. Known-bug inventory → I1
300	
301	The five bugs and the dead code listed in `BLOCKMAP.md` §Bugs (composer-smell
302	nesting+variable; shared `php-eol` code; `site_results` omission; un-gated U-M portal
303	URLs; duplicate `annual-bill` code — B51 handled as: distinct code now, scheduled
304	deletion when its Aug-2026 date passes, ledgered to I12; dead code deleted). Each fix is
305	test-first with the test shown red on the old behavior. **Verified 2026-07-17**: the
306	goldens contain zero `php-eol`/`wp-smell`/`drush-smell`/`composer-smell`/`annual-bill`
307	occurrences and the golden fixtures report PHP 8.2, so none of these fixes can touch a
308	golden:
309	
310	```
311	$ grep -c 'php-eol\|composer-smell\|wp-smell\|drush-smell\|annual-bill' tests/e2e/__snapshots__/*.ambr
312	tests/e2e/__snapshots__/test_golden.ambr:0
313	tests/e2e/__snapshots__/test_golden_cdn_change.ambr:0
314	tests/e2e/__snapshots__/test_golden_drupal.ambr:0
315	tests/e2e/__snapshots__/test_golden_nonumich.ambr:0
316	```
317	
318	## 11. The increments
319	
320	Wave dependency structure (increments within a wave are ordered but MAY be resequenced
321	with a ledger entry; waves MUST NOT be reordered):
322	
323	```
324	Wave 0: I0 bootstrap ──► I1 bug fixes
325	Wave 1: I2 gateway ──► I3 config ──► I4 hooks+DAG ──► I5 DB
326	Wave 2: I6 traffic ──► I7 plans ──► I8 check/pantheon ──► I9 wordpress ──► I10 drupal
327	Wave 3: I11 charts ──► I12 render+mail ──► I13 lifecycle
328	Wave 4: I14 closing sweep
329	```
330	
331	| Inc | Scope (blocks / functions) | Delivers |
332	|---|---|---|
333	| **I0** | — (no logic moves) | `psh/` skeleton + thin shim (console-script dropped — see LEDGER I0 amendment); conftest `import psh` rework (same collected-test count gate); ratchet config (§13) with rule sets pinned; pyright baseline measured; `LEDGER.md` started; README TODO edits (§15 dispositions); CLAUDE.md pointer to campaign |
334	| **I1** | B36, B40, B41, B47 (URLs), B48, B50/B51 (codes), dead code | §10 fixes, each test-first |
335	| **I2** | 302–597 wrappers | `psh/gateway.py`, `GatewayResult`, sc re-exports + façade test; no-subprocess-outside-gateway house rule |
336	| **I3** | 792–934, 1209–1253, 1608–1648 (`umich_enabled`/`cloudflare_enabled`) | `psh/configuration.py`; `Notice` class + code-uniqueness registry test |
337	| **I4** | 935–950, hook engine from `script_context.py` | `psh/modules.py`; consumes/produces on all in-repo hooks; DAG validation + fatal-condition tests; `run_finish` phase; contract registry |
338	| **I5** | 95–178; DB defs within 1285–1575 (`DatabaseUnavailableError` through `db_engine_args`; the resume helpers `ResumeSiteNotFoundError`, `sites_from_resume_point`, `merge_prior_results` stay for I13) | `psh/db.py`; DB test suites relocated intact |
339	| **I6** | B22–B26, B43; 598–671, 977–1127 | `psh/traffic.py` |
340	| **I7** | B9, B12 (plans), B17, B47; 967–976, 1128–1208, 1254–1280 | `psh/plans.py`; `PlanInfo`; D7 (`--only-warn` runs recommendation); plan/cost contract keys |
341	| **I8** | B19, B21, B38, B41 | `check/pantheon/` + `[Check.pantheon]`; `envs` contract key |
342	| **I9** | B32–B34; 672–739 | `psh/gather.py` (WP half); `check/wordpress/`; U-M WP checks → `check/umich/`; `add_on_updates` + smell contract keys |
343	| **I10** | B30, B35, B39, B48; 740–791 | gather (Drupal half); `check/drupal/`; `check/addon_updates/`; UA check → `check/umich/` |
344	| **I11** | B13 (caps), B44–B45 | `psh/charts.py` |
345	| **I12** | B49–B57 minus sort/subject core | `psh/render.py`, `psh/mail.py`; annual billing → `check/umich/` at `site_pre_render`; B51 deletion if past its date |
346	| **I13** | B14 (accumulators), B56, B59–B60; 1649–2107 plus the resume helpers I5 left behind (1281–1284, 1528–1542, 1576–1607) | `psh/lifecycle.py`; `RunState`; `main()` reaches final form |
347	| **I14** | — | Config renames + migration doc + sample rewrite + production-config instructions; global ratchet flip + remnant cleanup; docs/README/CLAUDE.md full refresh; `Notice` dict form retired; ledger fully resolved; retrospective + closing audit (§17) |
348	
349	Sizing note: the largest moves are I9 (~330 main-loop lines + helpers) and I10 (~320 +
350	helpers). If any increment proves oversized mid-session: **split, never compress** —
351	commit nothing partial, ledger the split, the second half becomes its own increment.
352	
353	## 12. Coordination protocol
354	
355	**Ledger entry template** (append per increment, and for any amendment):
356	
357	```markdown
358	## I<N> — <slug> (<date>, commit <sha>)
359	- Moved: <blocks/functions actually moved>
360	- Deviations from CAMPAIGN.md: <none | what + why>
361	- Contract/config/sc additions: <keys/names>
362	- Discovered tasks: <each with disposition: fixed here | I<M> | README TODO>
363	- Open questions for next increment: <…>
364	```
365	
366	**Discovered-task disposition rules** (canonical): fits current increment's scope and
367	<~30 min → fix now, note in ledger; belongs to a later increment → ledger it against
368	that increment (the increment's spec author MUST read these); major/risky/scope-widening
369	→ README TODO with a sentence of context. Nothing is carried in memory or chat — if it
370	is not in the ledger or README, it does not exist (PD#9).
371	
372	**Session flow per increment:** read the §7 documents → write the increment SPEC.md in
373	`development/<date>-mod-I<N>-<slug>/` citing CAMPAIGN.md sections by number →
374	`superpowers:writing-plans` → subagent-driven implementation → `/code-review` → full
375	`./run-tests` → per-task commits, each green; the increment's final commit includes the dev
376	folder → `/archive-session` → ledger entry.
377	
378	## 13. Lint/type ratchet
379	
380	Mechanism (as shipped by I0; see LEDGER I0 amendment 2): TWO ruff configs —
381	`pyproject.toml` `[tool.ruff.lint]` keeps the narrow PD-rule set running everywhere
382	including the remnant, and `ruff-broad.toml` carries `select = ["ALL"]` minus a
383	justified ignore list, with `extend-exclude` grandfathering exactly the remnant
384	(`psh/_legacy.py`) and not-yet-moved files; each increment deletes its
385	files from the grandfather list, and the two configs merge at I14. pyright runs in
386	`./run-tests` from I0 via `[tool.pyright]` (standard mode, `psh/` minus `_legacy.py`),
387	ratcheting toward strict as typed code moves in. The four existing narrow rules (`E722`, `BLE001`, `S105`, `S106`) remain global
388	throughout — they mechanize PD#2/PD#6 and are never grandfathered. No
389	`target-version` pin (CLAUDE.md: it masks the 3.12-only syntax detection).
390	
391	Baselines measured 2026-07-17 (I0 re-measures and pins both in its spec):
392	
393	```
394	$ ./run-tests --fast --llm   (tail)
395	LLM_SUMMARY passed=727 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
396	25 snapshots passed.
397	
398	$ uvx ruff check --isolated --statistics .
399	26  F541  f-string-missing-placeholders
400	 8  E741  ambiguous-variable-name
401	 4  E713  not-in-test
402	 3  F841  unused-variable
403	 2  F401  unused-import
404	 1  E402  module-import-not-at-top-of-file
405	 1  E712  true-false-comparison
406	Found 45 errors.
407	```
408	
409	(README's "~55" ruff and "39" pyright figures are stale/unverified claims; I0 replaces
410	them with measured numbers. pyright was not measured in planning — no pyright binary in
411	the dev container yet; installing it is I0 scope.)
412	
413	## 14. Risk / control table
414	
415	| Risk | Control |
416	|---|---|
417	| Re-indented column-0 notice literals silently change emails | Invariant 8; goldens as tripwire; AST/token comparison, never `git diff -w` |
418	| conftest rework silently drops tests | I0 gate: identical collected-test count (727 passed / 1 skipped / 2 deselected baseline) before and after |
419	| Long-range `main()` local coupling breaks a move | BLOCKMAP produces/consumes; each increment spec lists exactly which locals cross its boundary |
420	| Session/context overrun mid-increment | Fine granularity (D4); split-never-compress; commits only at increment completion |
421	| Architecture drift across 15 sessions | This document frozen; amendments only via ledger; specs cite section numbers |
422	| Hidden hook-order dependencies surface in I4 | I4 audits every hook; real dependencies become explicit DAG edges |
423	| Ratchet churn on moved code | Rules fixed at I0; cleaning is part of each move |
424	| Goldens blind to stdout/artifacts | Invariants 4–5 name the artifact/abort test suites as the cover; artifact structure frozen until campaign end |
425	| Implementer sessions lack context | `psh-implementer`/`psh-reviewer` carry the read list; specs name seams (Spine spec bar); §7 reading list |
426	| Two annual-bill notices / removal date passes mid-campaign | Explicitly scheduled: codes split in I1, deletion decision in I12, ledger tracks |
427	
428	## 15. NOT in scope (reasoning preserved so it is never re-litigated)
429	
430	- **Terminus → Pantheon API swap** — D1; post-campaign project against `psh/gateway.py`.
431	- **Parallel site processing** — D8; constraint only; README TODO remains.
432	- **CSV data attachment, cached-% column, env-lock section** — D9; each becomes a small
433	  post-campaign change (env-lock: a ~50-line `check/` package) once goldens may move.
434	- **SendGrid, secrets-handling completion, portal traffic capture, daily alerts,
435	  accessibility/security/Cloudflare scores, AI recommendations, dependency updates,
436	  terraform-infra** — pre-existing README TODOs, untouched by this campaign.
437	- **Approach B (library-only) and C (everything-is-a-hook)** — rejected in brainstorm:
438	  B fails the "full advantage of the frameworks" goal; C forces infrastructure into
439	  optional-content clothing.
440	- **Golden/fixture refreshes** — forbidden (Invariants 1, 10).
441	
442	## 16. Acceptance baseline
443	
444	§13 outputs are the campaign-start baseline (run and pasted 2026-07-17). Every
445	increment's definition of done re-runs `./run-tests` at increment end — the full suite
446	when the live tier's credentials are available in the session, otherwise `--fast` with a
447	ledger note saying the live tier was skipped — and MUST reproduce goldens
448	byte-identically. I0 additionally records the collected-test count gate.
449	
450	## 17. Closing audit (queued for I14; exhaustive)
451	
452	1. Is `main()` within 250–400 lines, and does everything left match §3.3?
453	2. Has every DAG fatal condition been demonstrated red at least once?
454	3. Do the contract registry and CLAUDE.md table agree (test-enforced)?
455	4. Is any `sc` re-export now consumed by nobody (dead façade surface)?
456	5. Is the `.py` symlink still needed for anything beyond the shim? If not, note in
457	   CLAUDE.md; if yes, say for what.
458	6. Are all ledger items resolved (done, scheduled, or README TODO)?
459	7. Has the production config repo received and applied the migration instructions?
460	8. Do README, CLAUDE.md, docs/, and memory reflect the final architecture (no stale
461	   line-number or module references)?
462	9. Were any invariants amended mid-campaign, and is each amendment ledgered?
463
```

### ⚙ Tool call: `Read`

```json
{
  "file_path": "/workspace/development/2026-07-17-modularization-campaign/LEDGER.md"
}
```

### ↳ Tool result

```
1	# LEDGER — Modularization Campaign
2	
3	Append-only. One entry per completed increment, plus one per CAMPAIGN.md amendment.
4	This file is how increment N learns what N−1 actually did; if a deviation, discovered
5	task, or decision is not recorded here (or in the README TODO list), it does not exist.
6	Entry template: CAMPAIGN.md §12.
7	
8	## Campaign planning (2026-07-17)
9	
10	- Produced: `CAMPAIGN.md` (frozen architecture), `BLOCKMAP.md` (B1–B60 map),
11	  `/workspace/CONTEXT.md` (domain glossary, new), this ledger.
12	- Baselines: fast tier 727 passed / 1 skipped / 2 deselected; ruff `--isolated` 45
13	  findings; pyright unmeasured (no binary in container — I0 scope).
14	- Discovered during planning, dispositioned:
15	  - Five bugs + dead code → I1 (CAMPAIGN.md §10, BLOCKMAP §Bugs).
16	  - README's "~55 ruff / 39 pyright" figures stale/unverified → I0 re-measures.
17	  - B51 second annual-bill notice: marked "remove Aug 2026" — code split in I1,
18	    deletion decision in I12.
19	  - WordPress/Drupal duplication + update-table HTML duplication (BLOCKMAP §Bugs 7–8)
20	    → addressed structurally by I9/I10 (shared gather + `check/addon_updates/`).
21	- Open questions for I0: exact ruff rule list; pyright strictness per environment;
22	  whether `dns_classify.py` moves under `psh/` (deferred to I14, MAY).
23	- Amendment (2026-07-17, user spec review): added the "Whole-file coverage" paragraph to
24	  CAMPAIGN.md §3.1 — clarification only, no scope change; the module map already
25	  assigned every top-level def.
26	
27	## I0 — bootstrap (2026-07-17, closing commit `docs(campaign-I0): close the bootstrap increment`)
28	
29	Commits (per-task, each green): `b1ccc72` (package move + shim + conftest + coverage),
30	`d0e3027` (lint/type ratchet), `5b536fa` + `239955d` (README/CLAUDE.md docs), plus this
31	closing docs commit (ledger + CAMPAIGN amendments + SPEC acceptance + README pyright number).
32	
33	- **Moved:** the whole 4,752-line program → `psh/_legacy.py` (`git mv`, **zero logic
34	  changes**; the `__main__` tail is inert in a module, left for I13). New: `psh/__init__.py`
35	  (docstring), `psh/cli.py` (`from psh._legacy import main, parse_args` re-export), and a new
36	  7-line thin shim at `./pantheon-sitehealth-emails` calling `psh.cli.main()`. No blocks
37	  (B-map) moved — I0 moves the file, not logic (§11 row I0).
38	
39	- **Deviations from CAMPAIGN.md (three amendments, all applied to the document this commit):**
40	  1. **No console-script entry point** (amends §11 row I0 / D10). The program is repo-rooted
41	     by design (`find_modules`, templates, `inline-styles.php`, `vendor/`, config symlink are
42	     all CWD-relative); a pip entry point would need a data-file overhaul serving no campaign
43	     goal. D10's real benefits (normal imports; native ruff/pyright/CodeGraph coverage; no
44	     `SourceFileLoader`) all arrive via the package + shim without installation. `pyproject.toml`
45	     stays deps-only (`py-modules = []`, `packages = []` to stop setuptools auto-discovery
46	     installing a stale shadow copy — PD#1). §11 row I0 now reads "thin shim (console-script
47	     dropped — see LEDGER I0 amendment)".
48	  2. **Grandfather is `psh/_legacy.py` via `ruff-broad.toml` `extend-exclude`** (amends §13,
49	     which named `pantheon-sitehealth-emails.py` and "per-file-ignores" — both written before
50	     the legacy-module + two-config mechanics were settled). The shipped mechanism is TWO ruff
51	     configs, not per-file-ignores: `pyproject.toml` `[tool.ruff.lint]` carries the narrow
52	     PD-rule set (`E722`/`BLE001`/`S105`/`S106`) that runs EVERYWHERE including `_legacy.py`;
53	     `ruff-broad.toml` carries `select = ["ALL"]` minus the ignore list and grandfathers the
54	     remnant via `extend-exclude`. `./run-tests` and `.claude/hooks/ruff-check.sh` run BOTH
55	     passes; the two files merge into `pyproject.toml` at I14. §13 now names `psh/_legacy.py`
56	     and "ruff-broad.toml exclude".
57	  3. **Per-task commits, each green** (amends §12's "one commit (code + dev folder)"). Each I0
58	     task committed independently once its gates were green; this increment's final (closing)
59	     commit includes the `development/` folder. Rationale: finer checkpoints serve the campaign
60	     prompt's revert/inspect intent, and SDD review packages diffs as commit ranges. §12 now
61	     reads "per-task commits, each green; the increment's final commit includes the dev folder".
62	
63	- **Ratchet as pinned.** pyright runs in `./run-tests` at **standard** mode, not strict
64	  (DECISION): `psh/cli.py` re-exports from the untyped legacy module, so strict would fail on
65	  re-export; strictness ratchets up as increments move typed code in. Scope `[tool.pyright]`
66	  = `include = ["psh"]`, `exclude = ["psh/_legacy.py"]`. Ruff-broad ignore list (pinned; each
67	  justified in `ruff-broad.toml`): `COM812`, `ISC001`, `E501`, `Q000`, `Q001`, `Q002`, `Q003`,
68	  `ANN`, `TD002`, `TD003`, `FIX002`, `EM101`, `EM102`, `TRY003`, `D`, `CPY001`. `CPY001` is a
69	  **preview** rule in ruff 0.15.22 (cannot fire under non-preview `select=["ALL"]`); ruff
70	  accepts it in `ignore` with no warning, so it is kept verbatim to document the intent
71	  (no per-file copyright headers). `D` (docstring convention) is undecided → README TODO.
72	
73	- **pyright whole-tree baseline (informational; replaces README's unverified "39").**
74	  **220 errors, 0 warnings, 0 informations** across 118 first-party files, standard mode,
75	  pyright 1.1.411 (SPEC ACCEPTANCE §Task 5 has the command + breakdown). Measured OUTSIDE the
76	  scoped gate config via a repo-root config (pyright roots a project at the config's directory
77	  and ignores includes outside it; a config's `exclude` still drops CLI-passed paths — so
78	  neither a scratchpad-rooted config nor CLI args can re-include `_legacy.py`, and a repo-root
79	  temp config is the reproducible form). By area: `tests/` 139, `psh/_legacy.py` 36, `check/`
80	  21, `plugin/` 18, `script_context.py` 5, `dns_classify.py` 1 (`check/`+`plugin/` = 39, the
81	  origin of the old figure). The gated scope (`psh/` minus `_legacy.py`) is `0 errors`.
82	
83	- **Contract/config/sc additions:** none (I0 moves no logic; no `[Check.*]` sections, no new
84	  contract keys, no `sc` names added or removed).
85	
86	- **Discovered tasks:**
87	  - **`Path(psh.__file__).parent` as a repo-root proxy** — 25 sites across 23 files: 22 test files (plus
88	    `tests/helpers/checkload.py`) anchored repo paths on the program file's parent, which the
89	    move shifted from repo root to `psh/`. Fixed here, mechanically and minimally:
90	    `→ Path(psh.__file__).resolve().parents[1]` at exactly those sites. Proper cleanup lands
91	    when later increments un-grandfather those test files; the `psh` fixture itself is
92	    redesigned when `_legacy` dies (I13/I14). Disposition: **fixed here**, further cleanup **I13/I14**.
93	  - **ruff lints explicitly-passed files even when excluded** — passing a path on ruff's
94	    command line overrides `extend-exclude`, so the edit hook (which passes the just-edited
95	    file) would lint `_legacy.py` against the broad set. Fixed by giving the broad-pass
96	    invocation `--force-exclude` and running it from repo-root cwd; documented in
97	    `.claude/hooks/ruff-check.sh`. Disposition: **fixed here**.
98	
99	- **Open questions for I1/I2:**
100	  - I1 (bug fixes) touches `_legacy.py` in place (fixes retire as code moves); it must keep
101	    the narrow PD set green there (broad set stays grandfathered) and the four goldens
102	    byte-identical (§10 verified the fixed codes appear in zero goldens).
103	  - I2 (gateway) is the first real logic move: as it un-grandfathers the wrapper functions it
104	    deletes them from `ruff-broad.toml` `extend-exclude` and must clean them to the broad set
105	    + pyright standard in the same change (§13 ratchet; §6 house-style tuple hints replaced).
106	  - `dns_classify.py` under `psh/` remains a MAY for I14 (unchanged from planning).
107	- Amendment (2026-07-17, post-Task-5 review): CAMPAIGN.md §13 mechanism paragraph
108	  rewritten to describe the SHIPPED two-config mechanism (it still said "pyproject gets
109	  extend-select" and "executionEnvironments", both superseded by amendment 2 above);
110	  ledger reanchor note corrected to "22 test files plus checkload.py" (23 files total).
111	  Both changes doc-accuracy only.
112	- Amendment (2026-07-17, final I0 code review, spec axis): D10's Decision cell still said
113	  "console-script" after amendment 1 changed only §11 row I0 — CAMPAIGN.md briefly
114	  self-contradicted. D10 cell now matches. Doc-accuracy only.
115	
116	## I1 — known-bug fixes (2026-07-17, commits `5518de7..1ff9153` + closing docs commit)
117	
118	Spec/plan: `development/2026-07-17-mod-I1-bug-fixes/` (SPEC.md carries the pasted
119	acceptance results). Six per-task commits, each green; full suite at close = 751 passed /
120	1 skipped **including the live tier**, 27 snapshots, all three gates; four goldens
121	byte-identical across the whole range (`git diff aa8afd1 -- tests/e2e/__snapshots__/`
122	empty).
123	
124	- **Moved:** no blocks (fixes land in place in `psh/_legacy.py` per I0's open-question
125	  note). Extracted five pure notice-builder helpers as consecutive module-level defs
126	  above `main()` (preserved-bug-extraction pattern; every literal interior byte-verified
127	  against the pre-move original by task reviewers AND the final review):
128	  `build_smell_notices`, `build_php_eol_notice`, `build_annual_bill_upcoming_notice`,
129	  `build_annual_bill_in_progress_notice`, `build_plan_recommendation_notice`. These
130	  travel later: smells → I10, php-eol → I8, annual-bill → I12, plan-rec → I7.
131	- **Fixed (CAMPAIGN §10 / BLOCKMAP §Bugs, all test-first with RED shown on old
132	  behavior):** (1) B48 composer-smell nesting + wrong interpolated variable;
133	  (2) B41 shared `php-eol` csv code → `php-eol-warning` (7.4/8.1) / `php-eol-alert`
134	  (<8.2), following the `updates-*` suffix pattern; (3) B36 unknown-framework sites now
135	  get a `site_results` entry (`version: "unknown"`, same 3-key row shape) — covered by a
136	  new offline e2e (`tests/e2e/test_unknown_framework_e2e.py`) asserting the
137	  `finish_run()` stdout pprint, since `-results.json` is written only on `--all` runs the
138	  interlock bans; (4) B47 un-gated U-M portal URLs — two of the four named URL sites
139	  (`extra_message`/`extra_text`) were **dead stores** (assigned, never read; §10's
140	  4240/4248 refined — bug partially lived in dead code), deleted; the live
141	  `its-recommends-plan` notice now selects U-M vs generic copy via `umich_enabled()`
142	  (generic drops the portal anchor AND the June-16-30 downgrade-window sentence — U-M
143	  billing policy, factually wrong elsewhere); both variants pinned by syrupy snapshots
144	  (`test_plan_recommendation_notice_render`); (5) B50/B51 duplicate `annual-bill` code —
145	  B51 now emits `annual-bill-in-progress`; B50 keeps `annual-bill`; B51's Aug-2026
146	  deletion decision remains I12's; (6) dead code deleted (B40 Gen2 block, overage debug
147	  query, `# plt.show()`, redundant second `plt.close(fig)` with its stale memory claim).
148	- **Deviations from CAMPAIGN.md:** none.
149	- **Contract/config/sc additions:** none. Sanctioned notice-csv value changes (§8 I1
150	  exception): the three codes above. New **hand-maintained** fixture dir
151	  `tests/fixtures/terminus-unknownfw/` (copy of `terminus/`, one framework value →
152	  `"mystery"`, README states `--record` never refreshes it — Invariant 10, cdnchange
153	  precedent) + conftest constant `TERMINUS_FIXTURES_UNKNOWNFW`.
154	- **Discovered tasks (dispositions):**
155	  - Template `email_template.{html,txt}` portal URLs render `sites/0/` in every non-U-M
156	    run including the non-U-M golden (SPEC Obs. 1) → I12/I14 (goldens freeze it now;
157	    already on CLAUDE.md's still-hardcoded-U-M list).
158	  - `php_version < "8.2"` string comparison + KeyError if key absent (Obs. 2) → I8.
159	  - B47 downgrade path: owner gets NO notice (dead `extra_message` was presumably meant
160	    for this) and a non-Basic downgrade appends no `site_savings` entry (Obs. 3) → I7
161	    decides intended behavior.
162	  - Composer-smell literals carry baked-in 8-space indentation (Obs. 4) → I10.
163	  - `its-recommends-plan` csv embeds `{savings:,.2f}` — thousands comma inside a
164	    comma-separated field, variable column count (Obs. 5) → I7, or I3's `Notice`
165	    class/code-registry work.
166	  - Residual test gap (final-review triage): `main()`'s umich-only annual-bill call
167	    sites have no runtime test (goldens are umich-disabled; interlock bans a U-M run) —
168	    I12's spec author MUST cover this when relocating annual billing to `check/umich/`
169	    at `site_pre_render`.
170	- **Process note (PD#14 instance):** one implementer's report Write silently failed
171	  against a stale `.superpowers/sdd/` report file from I0 and was misreported as
172	  success; caught by the task reviewer (report content was for the wrong task). Stale
173	  scratch reports are now purged before dispatch; future increments should start by
174	  clearing `.superpowers/sdd/task-*-report.md` leftovers.
175	- **Open questions for I2:** none new — proceed per I0's notes (un-grandfather the
176	  wrapper functions from `ruff-broad.toml`, clean to broad set + pyright standard,
177	  replace house-style tuple hints, `GatewayResult`, façade test).
178	
179	## I2 — gateway extraction (2026-07-17, commits `7044b12` (Task 1), `0141f76` (Task 2), house-rule-scope fix + closing docs commit)
180	
181	Spec/plan: `development/2026-07-17-mod-I2-gateway/` (SPEC.md carries the pasted acceptance
182	results). Two per-task code commits, each green, plus a whole-branch-review follow-up commit
183	(the `ENVIRON_SCOPE` widening below) and this closing docs commit (CLAUDE.md / tests/README.md /
184	gateway docstrings / memory / this ledger entry). Full suite (live tier present) at close =
185	**755 passed / 1 skipped** (the 1 skip is `test_db_credentials.py`'s `importorskip("MySQLdb")`
186	on a sqlite-only install), all three gates; four goldens byte-identical across the increment
187	(`git diff 8b1466b -- tests/e2e/__snapshots__/` empty).
188	
189	- **Moved:** the eleven Terminus/WP/Drush subprocess-facing wrapper defs (the 302–597 wrapper
190	  region of `psh/_legacy.py` **minus** `escape_url`, which §3.1 assigns to `psh/render.py`/I12) →
191	  `psh/gateway.py`: `run_terminus`, `TerminusError`, `terminus`, `terminus_data`, `wp`, `wp_eval`,
192	  `wp_error`, `fix_drush_output`, `drush`, `drush_php_script`, `drush_error`. `psh/_legacy.py`
193	  re-imports all eleven (plus `GatewayResult`), so its ~54 call sites and the `sc` exposure block
194	  resolve unchanged. Logic and the two column-0 `f"""` notice literals (`wp_error`/`drush_error`)
195	  moved byte-for-byte (Invariant 8; extracted-block diff pasted empty in the Task 1 report).
196	- **Deviations from CAMPAIGN.md:** the SPEC's §Broad-ruff-findings table enumerated **seven**
197	  findings on the moved code; the actual count was **EIGHT**. Wrapping `run_terminus`'s literal
198	  `return … True`/`return … False` statements in the `GatewayResult(...)` constructor introduced an
199	  `FBT003` (Boolean-positional-value-in-function-call) the spec did not foresee. Resolved
200	  **behavior-preservingly** by constructing with the `fatal=` keyword (`GatewayResult(output,
201	  errors, fatal=True)`) — no `ruff-broad.toml` ignore-list change (that would be a §13 amendment)
202	  and no `# noqa`. The other seven dispositions landed exactly as specced.
203	- **Ratchet (§13):** nothing was deleted from `ruff-broad.toml`'s `extend-exclude` this increment.
204	  The wrappers moved to a **new** file (`psh/gateway.py`), which is gated by the broad ruff set +
205	  pyright standard from birth (it was never in the exclude list). So LEDGER I0's "un-grandfather the
206	  wrapper functions from `ruff-broad.toml`" open-question was a **no-op for the exclude list** — its
207	  premise (functions cleaned in place inside an excluded file) didn't apply once they moved to a
208	  fresh gated file; the cleaning obligation is discharged by gateway.py being born under the full
209	  gate (`uvx ruff check --config ruff-broad.toml psh/gateway.py` → All checks passed!; pyright 0
210	  errors). Recorded per SPEC §Ratchet.
211	- **Contract/config/sc additions:** `GatewayResult` NamedTuple `(result, errors, fatal)` introduced
212	  in `psh/gateway.py`, re-exported via the `_legacy` import. **No new `sc` name** (no check/plugin
213	  references the type — it is unpacked positionally; adding it would be dead façade surface,
214	  CAMPAIGN.md §17 Q4). **No new contract keys.** New `gateway` conftest fixture and two house-rule
215	  instruments (no-`subprocess.Popen`-outside-gateway; documented-`sc`-façade-names-exist).
216	- **Discovered tasks (dispositions):**
217	  - The `wp`/`wp_eval`/`drush`/`drush_php_script` docstrings said "Returns a 3-tuple" after the
218	    move → **fixed here** (Task 3): updated to "Returns a GatewayResult (result, errors, fatal)".
219	    Doc-accuracy only, no logic change; gateway.py re-passed ruff-broad + pyright with 0 findings.
220	  - **`ENVIRON_SCOPE` house-rule was blind to the program body** (whole-branch review finding).
221	    `tests/unit/test_house_rules.py`'s PD#6 `os.environ` guard scoped to `check`/`plugin`/
222	    `dns_classify.py`/`script_context.py`/the 17-line shim — but **not** `psh/`, where the program
223	    body has lived since campaign I0. A direct `os.environ` read added to `psh/_legacy.py` or
224	    `psh/gateway.py` (the largest feature-code files) would have passed silently (PD#1/PD#6/PD#14 —
225	    an instrument blind to what it guards). Latent (grep found no offender) and **pre-existing**
226	    (introduced at I0's file move, not by I2's tasks), but I2 owns this test file and I2's own
227	    `_scoped_sources(scope)` parameterization made the fix one word → **fixed here**: added `"psh"`
228	    to `ENVIRON_SCOPE`, with the new red demonstration (adding `os.environ` to `psh/_legacy.py`
229	    fails naming it) observed, reverted, and recorded in the test docstring. Suite stayed green.
230	- **Open questions for I3:** none new — proceed per CAMPAIGN.md §11 row I3 (`psh/configuration.py`;
231	  `Notice` class + code-uniqueness registry test).
232	
233	## I3 — configuration module + `Notice` class (2026-07-17, commits `ed2698f` (Task 1), `d21a1d2` (Task 2), plus this closing docs commit)
234	
235	Spec/plan: `development/2026-07-17-mod-I3-config-notice/` (`SPEC.md` cites CAMPAIGN.md by
236	section; task reports under `.superpowers/sdd/task-{1,2}-report.md` carry the pasted
237	red/green evidence and pre-suppression ruff findings). Two per-task code commits, each
238	green, plus this closing docs commit (CLAUDE.md / CAMPAIGN.md §3.1 amendment / this ledger
239	entry). Full suite at close (`--fast`; **no live credentials in this environment**, so the
240	live tier did not run — same caveat as prior increments where noted) = **761 passed / 1
241	skipped / 2 deselected**, all three gates green, 27 snapshots; four goldens byte-identical
242	across the increment (`git diff 45b8a88 -- tests/e2e/__snapshots__/` empty).
243	
244	- **Moved:** `config_substitution`, the DEFER machinery (`_DEFER_TAG` + the two compiled
245	  regexes), `process_config`, `gate_disabled_sections`, `load_news_items`, `umich_enabled`,
246	  and `cloudflare_enabled` (the six defs + DEFER machinery named in SPEC §Deliverable A) from
247	  `psh/_legacy.py` into a new `psh/configuration.py`, re-imported back into `_legacy.py` (I2
248	  gateway precedent — the ~11 existing tests calling `psh.process_config` etc. needed no
249	  repoint). **New:** `psh/notice.py` (`Severity` StrEnum, frozen `Notice` dataclass,
250	  `NoticeRegistry`, `DuplicateNoticeCodeError`, module `registry`) — pure, stdlib-only, no
251	  `script_context` dependency. `SiteContext.add_notice` (`script_context.py`) now accepts a
252	  `Notice` or the legacy dict via a new `_notice_to_dict` projection. The `no-domains` notice
253	  (`psh/_legacy.py`, B29) was converted to construct a `Notice` end-to-end, with its code
254	  registered once at module scope; its `html`/`text` f-string interiors (including the
255	  pre-existing "the ste" typo) moved byte-for-byte.
256	
257	- **Deviations from CAMPAIGN.md:**
258	  1. **New module `psh/notice.py`** — §3.1's module map is exhaustive and named no home for
259	     the `Notice` type (§6 introduces the type without pinning a module). Handled as a
260	     CAMPAIGN.md **amendment**, not a ledger-note-only, per §Preamble ("edit the document
261	     *and* append a ledger entry"): this closing commit adds the one-row `psh/notice.py`
262	     entry to §3.1 (`Notice`, `Severity`, `NoticeRegistry`, `DuplicateNoticeCodeError`,
263	     `registry`) between the `psh/gateway.py` and `psh/db.py` rows.
264	  2. **PoC converts `no-domains` (B29), out of I3's declared block scope** (§11 row I3 lists
265	     only the config functions). Deliberate — §6 says the class is "adopted per increment",
266	     the user chose `no-domains` as a PoC, and it is core-and-staying-core (CLAUDE.md: "remain
267	     in core") so no later increment re-touches it. The notice's *home* is unchanged, only its
268	     representation, so this is a **ledger note**, not a §3.1/architecture change.
269	  3. **`sc.Notice`/`sc.Severity` reach `sc` via a module-level `from psh.notice import Notice,
270	     Severity` import at the top of `script_context.py`, NOT the `sc.Notice = Notice` /
271	     `sc.Severity = Severity` assignment pair the SPEC's §sc re-exports section showed** (added
272	     "near the existing `sc.umich_enabled = …` lines" in `_legacy.py`). Task 2's dispatch
273	     carried an explicit correction (surfaced by the Task 2 review, folded into the task
274	     brief before implementation): a plain module-level import makes both names module
275	     attributes automatically, so the assignment pair would have been a same-observable-effect
276	     duplicate of the import — the DRY Engineering Preference favors the single mechanism. The
277	     façade surface is identical either way (`hasattr(sc, "Notice")` etc. — pinned by
278	     `test_documented_sc_facade_names_exist`), so this is a mechanism choice, not a behavior
279	     change; recorded here because the SPEC's illustrative code block, read literally, would
280	     have produced dead/duplicate assignment lines.
281	
282	- **Contract/config/sc additions:** `sc.Notice`, `sc.Severity` (mechanism above). **No new
283	  contract keys** — no phase, `site_context` key, or config section was added; `Notice`
284	  is a producer-side representation change only. `sc.register_notice_code`/`sc.registry` were
285	  **NOT** added (SPEC §sc re-exports, D — deferred until a `check`/`plugin` package first
286	  adopts `Notice`; the PoC imports `registry` from `psh.notice` directly, being core code).
287	
288	- **`script_context.py` typing fix:** `options`/`config` module globals, previously untyped
289	  `= {}`, are now `options: argparse.Namespace = argparse.Namespace()` and
290	  `config: dict[str, Any] = {}` (new `argparse`/`Any` imports) — the minimal fix pyright
291	  standard mode needed to resolve `sc.options.verbose`/`sc.options.config` inside the moved
292	  `psh/configuration.py`. No other name in `script_context.py` was retyped (it stays
293	  grandfathered from the broad ruff ratchet; this is an out-of-gate, minimal, honest fix per
294	  the SPEC's own instruction).
295	
296	- **Ratchet (§13):** both new files gated from birth — neither is nor was in
297	  `ruff-broad.toml`'s `extend-exclude`. `uvx ruff check --config ruff-broad.toml
298	  psh/configuration.py psh/notice.py` → "All checks passed!"; pyright standard mode over
299	  `psh/` minus `_legacy.py` → 0 errors. Nothing deleted from `extend-exclude` (same as I2 —
300	  the moved/new code lands in fresh gated files, not an un-grandfathered old one).
301	
302	- **Ruff/pyright dispositions actually applied (corrections to the SPEC's finding table,
303	  both confirmed against real ruff/pyright output by the Task 1 implementer, not assumed):**
304	  - **`PLR2004` lands on only the two `sc.options.verbose >= 2` comparisons**, not the
305	    `> 1` one the SPEC's illustrative table also listed: ruff's default magic-value
306	    allowlist already covers `-1, 0, 1`, so `> 1` never triggers the rule, and a `# noqa:
307	    PLR2004` there is a live `RUF100` (unused-noqa) finding. Dropped from that line; kept
308	    (with the SPEC's inline reason) on both `>= 2` lines.
309	  - **`S101` (`Use of assert detected`) on both `best_match is not None` asserts** — a real
310	    finding the SPEC's ruff-findings table didn't enumerate (that table covered the
311	    moved-as-is code; the pyright-findings section separately *mandates* the asserts, but
312	    neither section flagged the S101 the asserts themselves introduce). Resolved inline:
313	    `# noqa: S101` with a reason (pyright type-narrowing only, not a security check).
314	  - **`glob` and `Any` were in fact orphaned** in `psh/_legacy.py` by the move — the SPEC's
315	    "expect none" prediction for orphaned imports was wrong for these two (`load_news_items`
316	    was their only user); `tomllib`/`re`/`shlex`/`sys`/`escape`/`pprint` all had other live
317	    users as predicted. Removed per the SPEC's own fallback instruction ("remove only what
318	    this change orphans").
319	  - All other dispositions (the `C901`/`PLR0912`/`PLR0915` triple noqa on
320	    `config_substitution`, the `FBT002` keyword-only fix, `SIM118`, `PTH207`/`PTH123`) landed
321	    exactly as the SPEC specified.
322	
323	- **Discovered tasks (dispositions):**
324	  - **Extra-csv-field `Notice` modeling is deferred** (SPEC §Notice field set, by design —
325	    not newly discovered here, but re-flagging its disposition for I4+): `Notice` currently
326	    carries `severity, code, html, text, short, icon, order` — no `csv`/`csv_extra`. A notice
327	    whose csv needs extra fields (e.g. `turned-off,{name}`, the `its-recommends-plan`
328	    savings figure) stays a dict until the first increment that converts one, which MUST
329	    amend CAMPAIGN.md §6 (add the field) via its own ledger entry — not silently widen
330	    `Notice` here. Disposition: **first adopting increment** (candidates per LEDGER I1:
331	    `check/addon_updates/` smells, I10; `annual-bill`/`annual-bill-in-progress`, I12; the
332	    `its-recommends-plan` comma-in-csv issue, I7).
333	  - No other discovered tasks — Task 1/Task 2's own reports found no further gaps beyond the
334	    three ruff/pyright corrections recorded above.
335	
336	- **Open questions for I4:** none new beyond CAMPAIGN.md §11 row I4 (`psh/modules.py`:
337	  `find_modules`, the hook engine, and the `consumes`/`produces` DAG additions §4 describes).
338	  I4's spec author should note that `psh.notice.registry` is import-time-once metadata (same
339	  contract as `sc.substitutions`/`sc.hooks`, per `psh/notice.py`'s own "Reload constraint"
340	  docstring) — relevant if the DAG work touches module reload/re-registration semantics.
341	
342	## I4 — hooks + DAG + contract registry (2026-07-20, commits `82d62ff..1f2a6af` + closing docs commit)
343	
344	Spec/plan: `development/2026-07-20-mod-I4-hooks-dag/` (SPEC.md carries the pasted acceptance
345	results; task reports under `.superpowers/sdd/task-{1..6}-report.md` carry the red/green
346	evidence). Six per-task code commits plus one review-fix commit, each green, plus this
347	closing docs commit (CLAUDE.md / memory / this ledger entry / the dev folder). Full suite at
348	close **including the live tier** (Terminus token present) = **782 passed / 1 skipped**
349	(the skip is `test_db_credentials.py`'s `importorskip("MySQLdb")`), all three gates, 27
350	snapshots; four goldens byte-identical across the increment
351	(`git diff d46f56d -- tests/e2e/__snapshots__/` empty).
352	
353	- **Moved:** `find_modules` (from `psh/_legacy.py`) and the hook engine — `PHASES`,
354	  `_valid_hook_name`, `add_hook`, `invoke_hooks` (from `script_context.py`) — into the new
355	  `psh/modules.py` (gated from birth). `script_context.py` re-exports
356	  `PHASES`/`add_hook`/`invoke_hooks` via a top-of-file `from psh.modules import …` (the I3
357	  `Notice`/`Severity` mechanism), so every `sc.*` call site resolves unchanged; `_legacy.py`
358	  re-imports `find_modules` + the new names. **New:** mandatory `consumes`/`produces`
359	  declarations (§4 condition 5, enforced at `add_hook` — nothing enters `sc.hooks`
360	  undeclared); `validate_hooks()` (§4 conditions 1–4 as named `HookDagError` subclasses:
361	  `UnproducedKeyError`, `DuplicateProducerError`, `HookCycleError`, `LaterPhaseKeyError`),
362	  called in `main()` after the check-import loop; `ordered_hooks()` (Kahn, registration-order
363	  tie-break) used by `invoke_hooks`; the authoritative `CONTRACT` registry +
364	  `stuff_traffic_contract`/`stuff_gather_contract` extracted from `main()`'s B28/B37 stuffing
365	  lines (registry-pinned by `tests/unit/test_contract_registry.py`, alongside
366	  `dns_classify.stuff_dns_contract`); the **`run_finish`** phase (first statement of
367	  `finish_run()`, completed AND aborted runs). All 11 in-repo `add_hook` registrations
368	  retrofitted with code-verified declarations; permanent
369	  `tests/integration/test_hook_dag.py` loads every real check/plugin package and validates.
370	
371	- **Deviations from CAMPAIGN.md (all ledger notes, no amendments — each stays within §4's
372	  observable contract; rationale in SPEC D-i4-1…7):**
373	  1. The mutable `hooks` dict **stays in `script_context.py`** (§3.1 moves the engine
374	     functions; §3.4 bars new module-level mutable state in `psh/`, and `reset_sc` rebinds
375	     `sc.hooks` — a second home would silently desync, PD#14). Engine functions read it via
376	     a call-time `import script_context as sc` (cycle-avoidance; module docstring diagram).
377	  2. **Dotted events must declare `consumes`/`produces` BOTH empty** — §4's "dotted events
378	     unchanged" read as invocation semantics, not registration schema; a non-empty
379	     declaration on a phase-less event is unvalidatable and therefore fatal.
380	  3. **Condition 5 enforces at `add_hook` time** (stricter placement than §4's
381	     "module-load completion"; conditions 1–4 validate at load completion as written).
382	  4. **Invoke order is computed per invocation** by pure `ordered_hooks()` rather than
383	     stored at validation (§4 diagram says "stored") — same inputs, same order; removes the
384	     stale-cache mode for tests that register without validating.
385	  5. **`run_finish` fires with no arguments until I13's `RunState`** (§4 says "receiving
386	     the RunState", a type that does not exist until I13; no consumer exists, so the
387	     signature change then is safe).
388	  6. **B2/B4 module-import loops stay in `main()`** (§3.1 assigns them to `psh/modules.py`
389	     eventually; §11 row I4 does not list them — they move with `main()`'s final form, I13).
390	
391	- **Contract/config/sc additions:** `run_finish` phase (registry entry `()` — CLAUDE.md
392	  table row added). **No new contract keys, no config keys, no new `sc` names** (the
393	  re-exported engine names already existed on `sc`). SPEC §6 correction during Task 3:
394	  `check.cloudflare.cache` consumes `['fqdns_behind_cloudflare', 'primary_domain']` — the
395	  spec-time grep pattern (`site_context[`) missed the `.get("primary_domain")` read at
396	  `cache.py:233`; the brief's mandated code re-verification caught it (PD#14 working as
397	  designed).
398	
399	- **Ratchet (§13):** `psh/modules.py` born gated (broad ruff + pyright standard, 0
400	  findings). **`script_context.py` un-grandfathered** — deleted from `ruff-broad.toml`
401	  `extend-exclude`; findings fixed: `I001`, 2× `SIM401` (`.get` rewrites), 2× `PLR1714`
402	  (tuple-membership rewrites, deliberately tuples not ruff's suggested set literals — no new
403	  hashability assumption), all equivalence-argued in the Task 6 report. No ignore-list
404	  changes; noqa inventory in `psh/modules.py`: `PLC0415` (call-time sc imports, cycle
405	  reason), `PTH116`/`PTH118` (find_modules keeps str paths for its `.split("/")`),
406	  `PLR0913` (stuff_gather_contract's spec-pinned 7-arg signature).
407	
408	- **Discovered tasks (dispositions):**
409	  - **Pre-existing raw hook-dict write** in `tests/integration/test_plugin_umich_portal.py`
410	    (`sc.hooks[...] = [...]` bypassing `add_hook`) broke under `ordered_hooks`' unconditional
411	    key indexing → **fixed here** (Task 5), converted to a declared `add_hook` call;
412	    repo-wide grep confirmed it was the only instance (fix-the-class rule).
413	  - `tests/helpers/checkload.py` gained a backward-compatible `base=` param so the DAG test
414	    can load `plugin/` packages standalone → **fixed here** (Task 5).
415	  - The two pre-existing unknown-phase fatals interpolated `hook_name` unescaped
416	    (Invariant 6 gap, latent since the engine's script_context days) → **fixed here**
417	    (Task 5, §8 sanctions stdout improvement).
418	  - `main()`'s `except HookDagError` → print + exit glue is untested (every condition is
419	    proven red at the `validate_hooks` seam; the goldens prove the success path through
420	    `main()`) → accepted, **noted here** (PD#14: the glue rests on inspection).
421	  - `run_finish` abort-path firing is covered transitively (shared unconditional first line
422	    + `test_abort_run.py` proves `finish_run` runs on abort) → accepted per SPEC §9;
423	    a direct probe in the abort tests is a cheap add if `finish_run`'s call structure ever
424	    changes → **noted here**.
425	  - **Runtime-registered hooks bypass DAG conditions 1–4** (validation runs once,
426	    post-import; only `add_hook`'s declaration check fires later). No in-repo hook registers
427	    dynamically; import-time registration is the assumed model → **I13** (lifecycle) should
428	    make the assumption explicit when `main()` reaches final form.
429	- **Open questions for I5:** none new — proceed per CAMPAIGN.md §11 row I5 (`psh/db.py`;
430	  DB test suites relocated intact; note the resume helpers stay behind for I13).
431
```

### ⚙ Tool call: `Read`

```json
{
  "file_path": "/workspace/development/2026-07-17-modularization-campaign/BLOCKMAP.md"
}
```

### ↳ Tool result

```
1	# BLOCKMAP — functional map of `main()` (baseline a47418c)
2	
3	The block-by-block map of `pantheon-sitehealth-emails` `main()` (lines 2108–4752) that the
4	campaign's increment assignments are built on. Line numbers are against commit `a47418c`
5	("prepare for modularization campaign") and will drift as increments land — **the block IDs
6	(B1–B60), not the line numbers, are the stable references** used by `CAMPAIGN.md` and the
7	increment specs. An increment that moves a block records it in `LEDGER.md` by block ID.
8	
9	Produced 2026-07-17 by a very-thorough read of `main()`; bug claims in B40/B47/B48/B51 were
10	independently re-verified against the source before this file was written.
11	
12	Helper functions called by `main()` but defined elsewhere in the same file: `build_traffic_table_rows`
13	(1002), `plan_costs` (1128), `update_traffic_rows` (1393), `load_traffic_rows` (1447),
14	`insert_traffic_rows` (1428), `load_overage_protection_window` (1488), `finish_run` (1649),
15	`abort_run` (1913). The two report table-column globals are module-level:
16	`traffic_table_columns` (68), `cost_table_columns` (85).
17	
18	Already extracted before this campaign (NOT in main()): SiteLens, DNS-resolution notices,
19	umich-cloudflare CMS checks, Cloudflare FQDN loading — all hook packages.
20	
21	## Pre-loop setup (runs once)
22	
23	| ID | Lines | What it does | Classification | Config read |
24	|---|---|---|---|---|
25	| B1 | 2110–2116 | Config load (tomllib) + `gate_disabled_sections()` | generic | whole file |
26	| B2 | 2118–2122 | Import `plugin/` packages → `sc.plugin` | generic | — |
27	| B3 | 2124–2125 | Pass-1 `process_config()` substitution | generic | — |
28	| B4 | 2127–2131 | Import `check/` packages → `sc.check` | generic | — |
29	| B5 | 2133–2162 | Arg validation (`--resume-from` guards, sites-or-all, fqdns flag) | generic | `[Cloudflare].enabled` |
30	| B6 | 2164–2168 | Verbose banner; `terminus("self:info")` | generic | — |
31	| B7 | 2170–2174 | `build/` dir; `invoke_hooks("setup")` | generic | — |
32	| B8 | 2176–2180 | Deferred-pass `process_config()` | generic | — |
33	| B9 | 2182–2183 | Overage constants | generic-Pantheon | `[Pantheon].overage_*` |
34	| B10 | 2185–2202 | DB engine + sessionmaker (`expire_on_commit=False`) | generic | `[Database]` |
35	| B11 | 2204–2206 | `--create-tables` short-circuit (`create_all`, exit) | generic | — |
36	| B12 | 2208–2228 | Wordmark image read; `load_news_items()`; `plan_info` normalization (`"-"`→None), `plan_names` | generic-Pantheon | `[Pantheon].plan_info`, `[News]` |
37	| B13 | 2230–2246 | Date window (`end_date`, `start_date`, `contract_year_end`); numpy chart-cap geometry | generic (cap geometry chart-specific) | — |
38	| B14 | 2248–2285 | `terminus_data("org:site:list")`; run accumulators (`emails_sent`, `site_savings`, `all_warnings`, `site_results`); `smtp_enabled`; sorted site names; `sites_from_resume_point` | generic | `[Pantheon].org_id`, `[SMTP].enabled` |
39	
40	## Per-site loop (2289–2720 body refs; wrapped in `try`/`except BaseException`)
41	
42	| ID | Lines | What it does | Classification | Emits notices (csv code) |
43	|---|---|---|---|---|
44	| B15 | 2290–2304 | Smell resets; U-M portal gate (`[UMich].portal.sites`), `portal_site_id` | **U-M** | — |
45	| B16 | 2306–2321 | Site-selection skip + banner | generic | — |
46	| B17 | 2323–2349 | Elite plan SKU → name via `terminus("plan:info")`, `plan_sku_to_name` | generic-Pantheon | — |
47	| B18 | 2351–2358 | Sandbox skip; `SiteContext` creation | generic | — |
48	| B19 | 2360–2387 | Frozen-site notice | generic (U-M link in body) | `frozen` (alert) |
49	| B20 | 2389–2394 | Unknown-plan guard (`sys.exit`) | generic | — |
50	| B21 | 2396–2442 | `terminus("env:list")` → `envs`; live-env validation | generic-Pantheon | `no-live-env-but-paid-plan` (alert) |
51	| B22 | 2444–2452 | `terminus("env:metrics")` traffic gather | generic-Pantheon | — |
52	| B23 | 2454–2460 | `db_retry(update_traffic_rows)` — DB WRITE | generic | — |
53	| B24 | 2462–2476 | `--import-older-metrics`: `get_old_metrics` + `insert_traffic_rows`, `continue` | generic | — |
54	| B25 | 2478–2480 | `--update` early `continue` | generic | — |
55	| B26 | 2482–2497 | `db_retry(load_traffic_rows)` → `results` (commit releases conn) | generic | — |
56	| B27 | 2499 | `invoke_hooks("site_pre")` | seam | — |
57	| B28 | 2501–2506 | Stuff `traffic_rows`/`start_date`/`end_date`; `invoke_hooks("site_post_traffic")` | seam | — |
58	| B29 | 2508–2561 | `terminus("domain:list")`; `dns_classify.classify_domains` → `facts` | generic, CF-aware | `no-domains` (alert) |
59	| B30 | 2562–2621 | Primary-domain check; Drupal multisite probe (`drush_php_script`) | framework-branching | `no-primary-domain` (info); `multisite-check` (error path) |
60	| B31 | 2623–2630 | `stuff_dns_contract`; `invoke_hooks("site_post_dns")`; `site_url` | seam | — |
61	| B32 | 2632–2655 | WP-network `network_home_url()` via `wp_eval` | WordPress | `version-check` (error path) |
62	| B33 | 2657–2667 | Gather init (`plugins`/`mods`/versions None; `add_on_updates=[]`) | generic | — |
63	| B34 | 2668–2984 | WordPress branch: version, plugin list, PAPC + native-sessions checks, per-plugin loop (updates; **umich-oidc-login**; **object-cache-pro** probe; **Hummingbird fork**), theme list, favicon | WordPress; oidc+Hummingbird **U-M** | `umich-oidc-login-reinstall` (warn), `ocp-config-fix-needed` (alert), `unsupported-turned-off`/`unsupported`, `no-favicon` (warn); error paths `version-check`, `plugin-list`, `ocp-config-check`, `favicon-check` |
64	| B35 | 2986–3302 | Drupal branch: core-status, pm:list, PAPC module check, **D7 EOL** + tag1_d7es, pm:updatestatus (D7) / composer dry-run+audit (D8+), **Drupal UA check** | Drupal; UA check **U-M** | `drupal7-eol` (alert), `composer-update` (alert), `drupal-ua` (info); error paths `core-status`, `pm-list`, `pm-updatestatus`, `drupal-ua-check` |
65	| B36 | 3303–3306 | Unknown-framework fallback (print only; **no `site_results` entry** — see Bugs) | generic | — |
66	| B37 | 3308–3320 | Stuff gather contract keys; `invoke_hooks("site_post_gather")` | seam | — |
67	| B38 | 3322–3489 | `terminus("upstream:updates:list")` → update table + age-tiered notice | generic-Pantheon | `updates-info`/`updates-warning`/`updates-alert` |
68	| B39 | 3491–3566 | Add-on updates table from `add_on_updates` | generic | `updates-addons` (warn) |
69	| B40 | 3568–3634 | **DEAD**: commented-out PHP-runtime-Gen2 notice (pre-SiteContext idiom) | dead | — |
70	| B41 | 3636–3694 | PHP EOL check on `envs["live"]["php_version"]` | generic-Pantheon | `php-eol` (**same code for warn and alert branches** — see Bugs) |
71	| B42 | 3696–3702 | `--only-warn`: dump csv codes to `all_warnings`, `continue` (TODO at 3698: run plan rec first) | generic | — |
72	| B43 | 3704–3742 | `visits_by_month`, `plan_on_day`, `build_plan_over_time` | generic | — |
73	| B44 | 3744–3801 | Chart data prep (`estimate_month_visits`, surge threshold, ymax) | generic-Pantheon | — |
74	| B45 | 3803–4113 | Matplotlib chart build → `chart_image` (BytesIO PNG) | generic-Pantheon | — |
75	| B46 | 4117–4156 | `db_retry(build_traffic_table_rows)` — DB read + commit | generic-Pantheon | — |
76	| B47 | 4158–4333 | Cost model: `load_overage_protection_window` → `plan_costs` → recommendation, savings, cost table. **Un-gated U-M portal URLs at 4240/4275** — see Bugs | generic-Pantheon (**U-M leak**) | `its-recommends-plan` (info) |
77	| B48 | 4335–4408 | Smell notices (`wp_smell`, `drush_smell`, `composer_smell`). **composer block nested in drush block + interpolates `drush_smell`** — see Bugs | generic | `wp-smell`/`drush-smell`/`composer-smell` (info) |
78	| B49 | 4410–4431 | Recipients: U-M portal owner groups OR `terminus("site:team:list")` | **U-M** branch + generic | — |
79	| B50 | 4433–4520 | Notice sort (alert→warn→info); subject; **annual-billing notice** on contract-year end | **U-M** (annual billing) | `annual-bill` (alert) |
80	| B51 | 4522–4555 | Second annual-billing notice, marked "remove Aug 2026" (**duplicate `annual-bill` csv code**) | **U-M**, temporary | `annual-bill` (alert) |
81	| B52 | 4557–4559 | `invoke_hooks("site_pre_render")` | seam | — |
82	| B53 | 4561–4608 | `make_msgid` CIDs; template dict; Jinja render → `build/{name}.html`/`.txt` | generic | — |
83	| B54 | 4610–4633 | PHP Emogrifier inline + `!important` regex → `-inline.html`/`-inline2.html` | generic | — |
84	| B55 | 4635–4696 | MIME assembly (`[Email]` config, dry-run addressing, banner/chart CIDs, attachments) → `.eml` | generic (U-M defaults) | — |
85	| B56 | 4698–4707 | Notice rows → `all_warnings` (deliberately BEFORE send — resume safety) | generic | — |
86	| B57 | 4709–4715 | SMTP send (gated `[SMTP].enabled`) | generic | — |
87	| B58 | 4717–4720 | `plt.close(fig)` (redundant — already closed at 4113); TODO markers | generic | — |
88	
89	## Loop exit / finish (runs once)
90	
91	| ID | Lines | What it does |
92	|---|---|---|
93	| B59 | 4721–4737 | `except BaseException` → `abort_reason` → `abort_run` (single flush path) |
94	| B60 | 4739–4747 | `finish_run` (sole writer of run artifacts) |
95	
96	## Wrapper usage by block
97	
98	- `terminus` (raw): B6, B17, B21, B22, B29, B35 (composer audit), B38, B49; inside `get_old_metrics` (B24)
99	- `terminus_data`: B14 · `run_terminus` (list form): B35 (composer dry-run)
100	- `wp`: B34 (plugin list, theme list) · `wp_eval`: B32, B34 (version, OCP probe, favicon)
101	- `drush`: B35 (core-status, pm:list, pm:updatestatus) · `drush_php_script`: B30, B35 (UA check)
102	
103	DB session touches (all through `db_retry` except schema): B10, B11, B23, B24, B26, B46, B47, B59, B60.
104	
105	## Bugs and smells found during mapping (all re-verified in source)
106	
107	1. **B48 composer-smell double bug (4385–4408):** the `if composer_smell != "":` block is
108	   nested inside `if drush_smell != "":`, so composer smells are only reported when a drush
109	   smell also exists; and the HTML `message` interpolates `{drush_smell}` (4395) where
110	   `{composer_smell}` is meant. (The plaintext `text` uses the right variable.)
111	2. **B41 shared `php-eol` csv code:** warning (7.4/8.1) and alert (<8.2) branches emit the
112	   identical `csv={name},php-eol`, so the notices CSV cannot distinguish severity.
113	3. **B36 `site_results` omission:** only the framework branches (B34 at 2690, B35 at 3009)
114	   create a site's `site_results` entry; an unknown-framework site silently vanishes from
115	   the results artifact (and from `monthly-report.txt`'s stats).
116	4. **B47 un-gated U-M URLs (4240, 4275):** the Basic-alternative and recommendation notice
117	   bodies embed `admin.webservices.umich.edu/sites/{portal_site_id}/plan/` without a
118	   `umich_enabled()` guard; non-U-M runs would render a broken U-M URL with
119	   `portal_site_id = 0`.
120	5. **B50/B51 duplicate `annual-bill` code:** both notices emit the same csv code and both
121	   `insert(0, …)`; on a contract-year U-M run a site gets two `annual-bill` rows that the
122	   CSV cannot tell apart. B51 is marked for removal August 2026.
123	6. **Dead code:** B40 (3568–3634) entire commented-out Gen2 notice (uses the removed
124	   `site_notices.append` idiom, cannot be revived as-is); commented overage debug query
125	   (4124–4133); redundant second `plt.close(fig)` (4717, already closed at 4113);
126	   commented `plt.show()` (4107).
127	7. **WordPress/Drupal duplication:** version-fetch→`site_results`, add-on-update
128	   collection, and the `*_error`/`*_smell` pattern are re-implemented per framework; the
129	   PAPC recommended-add-on check exists as both `check_wordpress_plugin(…)` and
130	   `check_drupal_module(…)` calls.
131	8. **Update-table HTML duplication:** B38 and B39 each build near-identical responsive
132	   update tables; B38's three severity bodies largely overlap.
133	9. **In-code TODO markers** (seams for extracted modules, not dead code): no-Autopilot
134	   warning (3696), plan-rec before `--only-warn` (3698), SVG chart (4115), traffic-table
135	   icons/coloring (4119–4122), Basic-plan performance-feature detection (4220–4221),
136	   %-pages-cached + CSV attachment (4719–4720).
137
```

### ⚙ Tool call: `Read`

```json
{
  "file_path": "/workspace/psh/_legacy.py",
  "offset": 80,
  "limit": 110
}
```

### ↳ Tool result

```
80	    {"name": "previous-plan", "label": "Downgrade To"},
81	]
82	
83	cost_table_columns = [
84	    {"name": "plan", "label": "Plan"},
85	    {"name": "cost-same", "label": "Same Traffic Cost"},
86	    {"name": "cost-median", "label": "Median Traffic Cost"},
87	    {"name": "notes", "label": ""},
88	]
89	
90	fqdn_re = re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.IGNORECASE)
91	
92	
93	class Base(DeclarativeBase):
94	    pass
95	
96	
97	class PantheonTraffic(Base):
98	    __tablename__ = "pantheon_traffic"
99	
100	    # id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
101	    site_id: Mapped[str] = mapped_column(CHAR(36))
102	    traffic_date: Mapped[datetime.date] = mapped_column(Date)
103	    site_plan: Mapped[str] = mapped_column(String(64))
104	    visits: Mapped[int] = mapped_column(Integer)
105	    pages_served: Mapped[int] = mapped_column(Integer)
106	    cache_hits: Mapped[int] = mapped_column(Integer)
107	
108	    __table_args__ = (
109	        PrimaryKeyConstraint("site_id", "traffic_date", name="pk_site_id_traffic_date"),
110	        UniqueConstraint("site_id", "traffic_date", name="uix_site_id_traffic_date"),
111	    )
112	
113	    def __repr__(self):
114	        return (
115	            f"<{self.site_id} {self.traffic_date} : {self.site_plan} visits={self.visits} "
116	            f"pages={self.pages_served} cache_hits={self.cache_hits}>"
117	        )
118	
119	
120	class PantheonOverageProtection(Base):
121	    __tablename__ = "pantheon_overage_protection"
122	
123	    site_id: Mapped[str] = mapped_column(CHAR(36))
124	    month: Mapped[datetime.date] = mapped_column(Date)
125	    months_remaining: Mapped[int] = mapped_column(Integer)
126	    used_this_month: Mapped[bool] = mapped_column(Boolean)
127	
128	    __table_args__ = (
129	        PrimaryKeyConstraint("site_id", "month", name="pk_op_site_id_traffic_date"),
130	        UniqueConstraint("site_id", "month", name="uix_op_site_id_traffic_date"),
131	    )
132	
133	    def __repr__(self):
134	        return f"<{self.site_id} {self.month} : {self.months_remaining}>"
135	
136	
137	class TrafficRow(NamedTuple):
138	    """A pantheon_traffic row, detached from the ORM.
139	
140	    Plain data on purpose: a db_retry() rollback expires every live ORM object, so a row held
141	    across a retryable unit would emit an unretried SELECT on the next attribute read -- outside
142	    every unit of work.  The attribute names match PantheonTraffic's, so consumers of the
143	    site_post_traffic data-contract key `traffic_rows` are unaffected.  See SPEC 3.3.2.
144	    """
145	
146	    site_id: str
147	    traffic_date: datetime.date
148	    site_plan: str
149	    visits: int
150	    pages_served: int
151	    cache_hits: int
152	
153	
154	class OverageProtectionRow(NamedTuple):
155	    """A pantheon_overage_protection row, detached from the ORM.
156	
157	    Plain data for the same reason as TrafficRow: load_overage_protection_window() snapshots the
158	    site's whole window in one unit of work, and plan_costs() reads it minutes later, after other
159	    db_retry() units may have rolled back (which expires every live ORM object).  The attribute
160	    names match PantheonOverageProtection's.
161	    """
162	
163	    site_id: str
164	    month: datetime.date
165	    months_remaining: int
166	    used_this_month: bool
167	
168	
169	#
170	# Global initialization:
171	#
172	
173	
174	# Command-line argument parsing.  Building the parser is side-effect-free; parse_args()
175	# (which reads sys.argv) is only invoked from the __main__ block at the bottom of this
176	# file, so the module can be imported by the test harness without argv side effects.
177	# Every function reads sc.options (set by the caller) at call time, not at import time.
178	def build_arg_parser() -> argparse.ArgumentParser:
179	    args_parser = argparse.ArgumentParser(
180	        # Reject option abbreviations (e.g. `--for` resolving to `--for-real`, `--al` to
181	        # `--all`).  These are dangerous options; requiring the exact spelling is a safety guard.
182	        allow_abbrev=False,
183	        description="Send emails to website owners letting them know what their Pantheon traffic has been"
184	        "and make recommendations about whether/how they should change their current plan or"
185	        "the configuration of their site.",
186	    )
187	    args_parser.add_argument(
188	        "sites",
189	        metavar="SITE",
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "grep -n -E '^(class|def) ' /workspace/psh/_legacy.py | sed -n '1,80p'",
  "description": "List top-level defs/classes with line numbers in _legacy.py"
}
```

### ↳ Tool result

```
93:class Base(DeclarativeBase):
97:class PantheonTraffic(Base):
120:class PantheonOverageProtection(Base):
137:class TrafficRow(NamedTuple):
154:class OverageProtectionRow(NamedTuple):
178:def build_arg_parser() -> argparse.ArgumentParser:
296:def parse_args(argv=None):
300:def escape_url(url):
338:def get_old_metrics(
412:def check_wordpress_plugin(
480:def check_drupal_module(
532:def smtp_login() -> SMTP_SSL:
548:def overage_blocks(overage, overage_block_size) -> int:
553:def contract_year_end(report_date: datetime.date) -> bool:
558:def estimate_month_visits(visits_by_month, dates, last_day, end_day) -> int:
583:def build_traffic_table_rows(
709:def plan_costs(
790:def build_plan_over_time(plan_on_day: dict, plot_right_date) -> list:
817:class ResumeSiteNotFoundError(Exception):
821:class DatabaseUnavailableError(RuntimeError):
841:def record_db_reconnect(counter: dict, site: str) -> None:
847:def db_retryable(error: DBAPIError) -> bool:
865:def db_retry(session, unit, *, what: str, site: str = None):
929:def update_traffic_rows(session, site: dict, metrics: dict, start_date, end_date) -> None:
964:def insert_traffic_rows(session, rows: list) -> None:
983:def load_traffic_rows(session, site: dict, start_date, end_date) -> list:
1024:def load_overage_protection_window(session, site: dict, start_date, end_date) -> dict:
1064:def sites_from_resume_point(sorted_site_names: list, resume_from: str) -> list:
1079:def db_engine_args(db_config: dict) -> (str, dict):
1112:def merge_prior_results(path: str, new_results: dict, *, what: str = "results") -> dict:
1159:def finish_run(
1328:def resume_point(site_names: list, site_name: str, emailed: bool) -> str:
1342:def option_strings_taking_a_value() -> set:
1357:def resume_command(argv: list, site_name: str) -> str:
1381:def rerun_command(argv: list, original_sites: list, remaining_sites: list) -> str:
1404:def abort_reason(error: BaseException) -> str:
1426:def abort_run(
1621:def build_smell_notices(site_name, wp_smell, drush_smell, composer_smell):
1701:def build_php_eol_notice(site_name, php_version):
1759:def build_annual_bill_upcoming_notice(site_name, plan_name, annual_bill, shortcode, portal_site_id):
1827:def build_annual_bill_in_progress_notice(site_name, plan_name, annual_bill, shortcode):
1855:def build_plan_recommendation_notice(site_name, current_plan, recommended_plan, savings,
1905:def main() -> None:
```

### ⚙ Tool call: `Skill`

```json
{
  "skill": "andrej-karpathy-skills:karpathy-guidelines"
}
```

### ↳ Tool result

```
Launching skill: andrej-karpathy-skills:karpathy-guidelines
```

## User

Base directory for this skill: /home/node/.claude/plugins/cache/karpathy-skills/andrej-karpathy-skills/1.0.0/skills/karpathy-guidelines

# Karpathy Guidelines

Behavioral guidelines to reduce common LLM coding mistakes, derived from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876) on LLM coding pitfalls.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### ⚙ Tool call: `Read`

```json
{
  "file_path": "/workspace/psh/_legacy.py",
  "offset": 817,
  "limit": 345
}
```

### ↳ Tool result

```
817	class ResumeSiteNotFoundError(Exception):
818	    """--resume-from named a site not present in the org site list."""
819	
820	
821	class DatabaseUnavailableError(RuntimeError):
822	    """A database operation failed, was retried once, and failed again.
823	
824	    Raised by db_retry().  Caught once, around the site loop in main(), which flushes the
825	    end-of-run artifacts and exits nonzero with a command to re-run what is left (SPEC 3.5).
826	    """
827	
828	
829	# Reconnects HEALED by db_retry() -- the retry ran and succeeded -- attributed to the site that
830	# caused them.  Counted only after the second attempt returns: counting the attempt instead would
831	# let an aborted run report a reconnect it never actually made.
832	db_reconnects_by_site = {}
833	
834	# Connection losses db_retry() could NOT heal, attributed the same way: the retry failed, or the
835	# rollback before it did.  The counterpart of the dict above, and the reason it can be trusted --
836	# every lost connection lands in exactly one of the two, so "0 healed" never means "nothing
837	# happened".  Both are reported on the console and in {ymd}-run.json (SPEC 3.6).
838	db_reconnect_failures_by_site = {}
839	
840	
841	def record_db_reconnect(counter: dict, site: str) -> None:
842	    """Attribute one reconnect (healed or failed) to `site`, or to "(no site)" outside the loop."""
843	    key = site if site is not None else "(no site)"
844	    counter[key] = counter.get(key, 0) + 1
845	
846	
847	def db_retryable(error: DBAPIError) -> bool:
848	    """Is this DBAPI error one db_retry() may roll back and re-run?
849	
850	    NOT a hardcoded class list.  SQLAlchemy's MySQLdb dialect classifies a lost connection by
851	    error code, not by exception class: mysqlclient raises InterfaceError for errno 0 and
852	    ProgrammingError for CR_COMMANDS_OUT_OF_SYNC (2014, a connection reaped mid-result-set), and
853	    both are SIBLINGS of OperationalError under DBAPIError, not subclasses.  What every disconnect
854	    DOES share is connection_invalidated -- SQLAlchemy sets it from the dialect's is_disconnect().
855	    So retry on that, plus OperationalError (a deadlock, a lock-wait timeout or too-many-connections
856	    does not invalidate the connection but is still worth one retry -- SPEC 2.2).
857	
858	    Everything else -- an IntegrityError, a genuine ProgrammingError bug -- is a real bug: it is a
859	    DBAPIError but neither an OperationalError nor an invalidated connection, so it propagates
860	    untouched and stays loud.
861	    """
862	    return isinstance(error, OperationalError) or error.connection_invalidated
863	
864	
865	def db_retry(session, unit, *, what: str, site: str = None):
866	    """Run `unit()`; on a database failure, roll back and re-run it exactly once.
867	
868	    `unit` MUST be idempotent.  A rollback discards every pending ORM change in the session, so
869	    the retry re-runs the unit from scratch -- which is why retries happen at unit-of-work
870	    granularity and NEVER around a single statement that runs while writes are pending
871	    (SPEC 3.3.1).
872	
873	    A rollback ALSO expires every loaded ORM object, regardless of expire_on_commit.  So a
874	    retryable unit must never be placed where live ORM rows will be read afterwards: the read
875	    would emit a fresh SELECT outside any unit, and therefore outside any retry.  This is why
876	    load_traffic_rows() returns plain TrafficRow data (SPEC 3.3.2).
877	
878	    What is retried is decided by db_retryable(), not by an exception class: an OperationalError
879	    (a lost connection, but also a deadlock, a lock-wait timeout, or too-many-connections -- we
880	    deliberately do not sniff codes to tell those apart, SPEC 2.2), or ANY DBAPIError whose
881	    connection was invalidated.  A reaped connection can arrive as an InterfaceError or even a
882	    ProgrammingError(2014); those are not OperationalError subclasses, and retrying them is the
883	    whole point of this function.  A DBAPIError that is neither -- an IntegrityError, a real
884	    ProgrammingError bug -- is a bug and must stay loud, so it is re-raised untouched.
885	    """
886	    try:
887	        return unit()
888	    except DBAPIError as first_error:
889	        if not db_retryable(first_error):
890	            raise
891	        try:
892	            session.rollback()
893	        except DBAPIError as rollback_error:
894	            if not db_retryable(rollback_error):
895	                raise  # a real bug surfacing on the rollback: still not ours to rename
896	            # The rollback hit the wire and died too (the connection was not invalidated, so
897	            # SQLAlchemy really emitted a ROLLBACK).  Name it rather than let a raw
898	            # DBAPIError escape past main()'s handler -- SPEC 3.3.3.  It is also the run's most
899	            # definite connection loss, so it is COUNTED (as a failure): reporting zero here would
900	            # tell the operator nothing went wrong on the very run that died of it.
901	            record_db_reconnect(db_reconnect_failures_by_site, site)
902	            raise DatabaseUnavailableError(
903	                f"{what}: rollback failed after {first_error}"
904	            ) from rollback_error
905	        sc.console.print(
906	            f":warning: [bold yellow]Lost the database connection during {escape(what)}; "
907	            "reconnecting and retrying."
908	        )
909	        time.sleep(1)
910	        try:
911	            result = unit()
912	        except DBAPIError as retry_error:
913	            if not db_retryable(retry_error):
914	                # Not a connection issue itself, but first_error's connection loss never got
915	                # healed -- record it as a failure so it lands in a dict, not neither (the
916	                # comment above promises every lost connection lands in exactly one).
917	                record_db_reconnect(db_reconnect_failures_by_site, site)
918	                raise  # a real bug surfacing on the retry: still not ours to rename
919	            record_db_reconnect(db_reconnect_failures_by_site, site)
920	            raise DatabaseUnavailableError(f"{what}: {retry_error}") from retry_error
921	        # Counted HERE, not before the retry: a reconnect is a connection that came BACK.  An
922	        # abort that reported "1 reconnect" alongside "reason: database" was claiming a heal that
923	        # never happened -- and the operator reads this number to judge whether the connection
924	        # fix is working.
925	        record_db_reconnect(db_reconnects_by_site, site)
926	        return result
927	
928	
929	def update_traffic_rows(session, site: dict, metrics: dict, start_date, end_date) -> None:
930	    """Merge a site's daily metrics into pantheon_traffic and commit.
931	
932	    Idempotent (session.merge() is upsert-by-primary-key), so db_retry() may re-run it.
933	    """
934	    # Preload the session with the data we're going to be updating.  This makes the merge()
935	    # calls below much faster.
936	    _ = (
937	        session.query(PantheonTraffic)
938	        .filter(
939	            PantheonTraffic.site_id == site["id"],
940	            PantheonTraffic.traffic_date.between(start_date, end_date),
941	        )
942	        .all()
943	    )
944	    for e in metrics["timeseries"]:
945	        entry = metrics["timeseries"][e]
946	        traffic_date = datetime.datetime.strptime(
947	            entry["datetime"], "%Y-%m-%dT%H:%M:%S"
948	        ).date()
949	        if traffic_date == end_date:
950	            continue  # skip today's partial data
951	        session.merge(
952	            PantheonTraffic(
953	                site_id=site["id"],
954	                traffic_date=traffic_date,
955	                site_plan=site["plan_name"],
956	                visits=entry["visits"],
957	                pages_served=entry["pages_served"],
958	                cache_hits=entry["cache_hits"],
959	            )
960	        )
961	    session.commit()
962	
963	
964	def insert_traffic_rows(session, rows: list) -> None:
965	    """Insert-or-ignore historical traffic rows and commit.
966	
967	    Idempotent (ON CONFLICT DO NOTHING / INSERT IGNORE), so db_retry() may re-run it.
968	    """
969	    if len(rows) == 0:
970	        return
971	    if sc.config["Database"]["type"] == "sqlite":
972	        session.execute(
973	            sqlite_insert(PantheonTraffic).on_conflict_do_nothing(
974	                index_elements=["site_id", "traffic_date"]
975	            ),
976	            rows,
977	        )
978	    else:  # mysql:
979	        session.execute(insert(PantheonTraffic).prefix_with("IGNORE"), rows)
980	    session.commit()
981	
982	
983	def load_traffic_rows(session, site: dict, start_date, end_date) -> list:
984	    """Read a site's traffic rows for the report, then RELEASE the connection.
985	
986	    The commit here looks redundant for a read-only query.  It is not, and it MUST NOT be
987	    removed: without it the session holds its connection, inside an open transaction, for the
988	    entire per-site gather (terminus, wp/drush, DNS, cache checks, matplotlib -- minutes).  A
989	    NAT/firewall on the path to RDS reaps that idle flow and the next query dies with MySQL error
990	    2013.  Committing returns the connection to the pool, where pool_pre_ping can validate and
991	    silently replace it on the next checkout.
992	
993	    Returns plain TrafficRow data rather than ORM rows, so that a later db_retry() rollback --
994	    which expires every live ORM object -- cannot turn a downstream attribute read into an
995	    unretried SELECT.  See development/2026-07-13-db-connection-resilience/SPEC.md 3.1, 3.3.2.
996	
997	    The TrafficRow list is built BEFORE the commit, on purpose: a default session (unlike
998	    main()'s, which sets expire_on_commit=False) expires every loaded ORM object on commit, and
999	    reading r.site_id etc. from an expired object triggers a lazy-refresh SELECT that opens a new
1000	    transaction -- silently reintroducing the very connection-holding bug this function exists to
1001	    fix. Materializing first makes "the connection is released on return" true unconditionally,
1002	    independent of expire_on_commit.
1003	    """
1004	    rows = [
1005	        TrafficRow(
1006	            site_id=r.site_id,
1007	            traffic_date=r.traffic_date,
1008	            site_plan=r.site_plan,
1009	            visits=r.visits,
1010	            pages_served=r.pages_served,
1011	            cache_hits=r.cache_hits,
1012	        )
1013	        for r in session.query(PantheonTraffic)
1014	        .filter(
1015	            PantheonTraffic.site_id == site["id"],
1016	            PantheonTraffic.traffic_date.between(start_date, end_date),
1017	        )
1018	        .all()
1019	    ]
1020	    session.commit()  # releases the connection -- see the docstring; MUST NOT be removed
1021	    return rows
1022	
1023	
1024	def load_overage_protection_window(session, site: dict, start_date, end_date) -> dict:
1025	    """Snapshot a site's overage-protection rows for the report window in ONE query.
1026	
1027	    Returns {month (a date, day=1) -> OverageProtectionRow}, for plan_costs()' op_lookup to read
1028	    as a plain dict.  A missing month is simply absent from the dict, so op_lookup's `.get()`
1029	    returns None exactly where the old per-month Session.get() did.
1030	
1031	    One query, not ~91.  plan_costs() asks for the overage state once per candidate plan PER
1032	    MONTH (~7 non-Basic plans x ~13 months), and a Session.get() that misses is never negatively
1033	    cached, so it re-SELECTs every time -- and a Basic-plan site, which has no rows at all, missed
1034	    on every single call.  Each of those was its own db_retry() unit against a remote RDS over the
1035	    WAN: pool checkout + pre-ping probe + SELECT + COMMIT.  A snapshot is equivalent because
1036	    nothing writes to pantheon_overage_protection between build_traffic_table_rows()' commit and
1037	    plan_costs()' reads.
1038	
1039	    The commit is load_traffic_rows()' commit, for the same reason and with the same rule: it MUST
1040	    NOT be removed.  Even a read autobegins a transaction, and without the commit the session
1041	    would hold that connection, idle, through matplotlib, the Jinja render, the php inliner, the
1042	    SMTP send and the NEXT site's terminus calls -- exactly the reaped-idle-flow bug this change
1043	    exists to fix.  The rows are materialized as plain data BEFORE the commit, so that holds
1044	    regardless of expire_on_commit (see load_traffic_rows()).
1045	    """
1046	    rows = {
1047	        r.month: OverageProtectionRow(
1048	            site_id=r.site_id,
1049	            month=r.month,
1050	            months_remaining=r.months_remaining,
1051	            used_this_month=r.used_this_month,
1052	        )
1053	        for r in session.query(PantheonOverageProtection)
1054	        .filter(
1055	            PantheonOverageProtection.site_id == site["id"],
1056	            PantheonOverageProtection.month.between(start_date.replace(day=1), end_date),
1057	        )
1058	        .all()
1059	    }
1060	    session.commit()  # releases the connection -- see the docstring; MUST NOT be removed
1061	    return rows
1062	
1063	
1064	def sites_from_resume_point(sorted_site_names: list, resume_from: str) -> list:
1065	    """
1066	    Return the suffix of sorted_site_names starting at resume_from (inclusive).
1067	
1068	    sorted_site_names is the already-sorted list of org site names; resume_from is the
1069	    --resume-from value.  Raises ResumeSiteNotFoundError if resume_from is absent, so that a
1070	    typo becomes a fatal error rather than degrading into "silently skip every site".
1071	    """
1072	    try:
1073	        i = sorted_site_names.index(resume_from)
1074	    except ValueError:
1075	        raise ResumeSiteNotFoundError(resume_from)
1076	    return sorted_site_names[i:]
1077	
1078	
1079	def db_engine_args(db_config: dict) -> (str, dict):
1080	    """Build the (connection string, create_engine kwargs) for the traffic database.
1081	
1082	    Behavior-preserving extraction of main()'s inline construction, so the pool settings below
1083	    are unit-testable.  `type` and `name` are read unconditionally: a [Database] section without
1084	    them is a KeyError, not a default (see CLAUDE.md).
1085	    """
1086	    if db_config["type"] == "sqlite":
1087	        return f"sqlite:///{db_config['name']}", {}
1088	    if db_config["type"] == "mysql":
1089	        conn_str = (
1090	            f"mysql+mysqldb://{db_config['user']}:{db_config['password']}@"
1091	            f"{db_config['host']}:{db_config['port']}/{db_config['name']}"
1092	        )
1093	        # The database is remote (RDS) and the network path crosses NAT/firewall middleboxes
1094	        # that reap idle flows.  pool_pre_ping is the LOAD-BEARING setting: it validates the
1095	        # connection at pool checkout and transparently replaces a reaped one -- it is the only
1096	        # thing here that actually defends against the reaping this whole change exists to fix.
1097	        # pool_recycle does NOT: it bounds a connection's total AGE since creation (SQLAlchemy
1098	        # compares time.time() - starttime at checkout), not its idle time, so a NAT gateway with
1099	        # a 350s idle timeout can reap a connection nowhere near 1800s old.  It is a cheap
1100	        # backstop against long-lived-connection problems, nothing more.  Do not weaken or drop
1101	        # pool_pre_ping on the strength of it.  Deliberately hardcoded rather than configurable:
1102	        # development/2026-07-13-db-connection-resilience/SPEC.md section 2.2.
1103	        return conn_str, {
1104	            "pool_size": 10,
1105	            "max_overflow": 20,
1106	            "pool_pre_ping": True,
1107	            "pool_recycle": 1800,
1108	        }
1109	    sys.exit(f"Unsupported database type: {db_config['type']}")
1110	
1111	
1112	def merge_prior_results(path: str, new_results: dict, *, what: str = "results") -> dict:
1113	    """
1114	    Return the JSON dict already at path merged with new_results, which wins on key collision
1115	    (a site processed by the resumed run supersedes any earlier entry for it).
1116	
1117	    A missing file yields new_results alone.  A malformed existing file warns loudly and yields
1118	    new_results alone, rather than crashing at the very end of an otherwise-complete run.
1119	    "Malformed" covers valid JSON that is not an object (a hand-edited `[]` or `null`) as well as
1120	    unparseable or unreadable content: both would otherwise blow up on merged.update() below.
1121	
1122	    `what` names, in the warning, the kind of content being merged/read -- this helper reads
1123	    both {ymd}-results.json ("results") and {ymd}-run.json ("run metadata"; see finish_run()),
1124	    and the warning must name whichever file actually failed to read.
1125	    """
1126	    merged = {}
1127	    if os.path.exists(path):
1128	        try:
1129	            with open(path, encoding="utf-8") as f:
1130	                merged = json.load(f)
1131	            if not isinstance(merged, dict):
1132	                raise ValueError(f"expected a JSON object, found {type(merged).__name__}")
1133	        # json.JSONDecodeError is a ValueError, so this catches an unparseable file too.
1134	        except (ValueError, OSError) as e:
1135	            sc.console.print(
1136	                f":warning: [bold yellow]could not read existing {path} "
1137	                f"({escape(str(e))}); writing only this run's {what}."
1138	            )
1139	            merged = {}
1140	    merged.update(new_results)
1141	    return merged
1142	
1143	
1144	# Expose helpers for check/ packages, which cannot import this dash-named script.
1145	# Same convention as sc.plugin_context['plugin.cloudflare']['get_client']: shared state /
1146	# callables travel via the sc module.  Tests monkeypatch these sc attributes when loading
1147	# check modules standalone.
1148	sc.escape_url = escape_url
1149	sc.check_wordpress_plugin = check_wordpress_plugin
1150	sc.check_drupal_module = check_drupal_module
1151	sc.umich_enabled = umich_enabled
1152	sc.cloudflare_enabled = cloudflare_enabled
1153	sc.terminus = terminus      # check packages: Pantheon calls (e.g. domain:dns) go through this
1154	sc.fqdn_re = fqdn_re        # check packages: validate remote domain ids with the SAME regex
1155	sc.db_engine_args = db_engine_args  # plugin/umich/portal.py: ONE URL builder, ONE set of pool
1156	                                    # settings for every database this program connects to
1157	
1158	
1159	def finish_run(
1160	    db_session,
1161	    db_engine,
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "grep -rn 'db_engine_args\\|db_retry\\|db_retryable\\|record_db_reconnect\\|DatabaseUnavailableError\\|load_traffic_rows\\|update_traffic_rows\\|insert_traffic_rows\\|load_overage_protection_window\\|TrafficRow\\|OverageProtectionRow\\|PantheonTraffic\\|PantheonOverageProtection' /workspace --include='*.py' -l | grep -v _legacy | sort",
  "description": "Find all files referencing the DB defs"
}
```

### ↳ Tool result

```
/workspace/plugin/umich/portal.py
/workspace/tests/conftest.py
/workspace/tests/e2e/test_abort_e2e.py
/workspace/tests/integration/test_abort_run.py
/workspace/tests/integration/test_db_credentials.py
/workspace/tests/integration/test_db_roundtrip.py
/workspace/tests/integration/test_plugin_umich_portal.py
/workspace/tests/integration/test_terminus_seam.py
/workspace/tests/shims/pyshim/dbshim.py
/workspace/tests/unit/test_abort_reason.py
/workspace/tests/unit/test_db_resilience.py
/workspace/tests/unit/test_house_rules.py
/workspace/tests/unit/test_plan_costs.py
/workspace/tests/unit/test_traffic_table_rows.py
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "grep -rn 'db_reconnects_by_site\\|db_reconnect_failures_by_site' /workspace --include='*.py' | grep -v '\\.superpowers'",
  "description": "Find every reference to the two reconnect counter dicts"
}
```

### ↳ Tool result

```
/workspace/tests/unit/test_traffic_table_rows.py:80:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/unit/test_db_resilience.py:74:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})  # never assign: psh is session-scoped
/workspace/tests/unit/test_db_resilience.py:75:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/unit/test_db_resilience.py:93:    assert psh.db_reconnects_by_site == {"its-wws-test1": 1}
/workspace/tests/unit/test_db_resilience.py:94:    assert psh.db_reconnect_failures_by_site == {}
/workspace/tests/unit/test_db_resilience.py:100:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/unit/test_db_resilience.py:101:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/unit/test_db_resilience.py:114:    assert psh.db_reconnects_by_site == {}
/workspace/tests/unit/test_db_resilience.py:115:    assert psh.db_reconnect_failures_by_site == {"its-wws-test1": 1}
/workspace/tests/unit/test_db_resilience.py:124:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/unit/test_db_resilience.py:125:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/unit/test_db_resilience.py:136:    assert psh.db_reconnects_by_site == {}
/workspace/tests/unit/test_db_resilience.py:137:    assert psh.db_reconnect_failures_by_site == {"its-wws-test1": 1}
/workspace/tests/unit/test_db_resilience.py:147:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/unit/test_db_resilience.py:148:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/unit/test_db_resilience.py:159:    assert psh.db_reconnects_by_site == {}
/workspace/tests/unit/test_db_resilience.py:160:    assert psh.db_reconnect_failures_by_site == {}
/workspace/tests/unit/test_db_resilience.py:168:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/unit/test_db_resilience.py:169:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/unit/test_db_resilience.py:467:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/unit/test_db_resilience.py:468:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/unit/test_db_resilience.py:482:    assert psh.db_reconnects_by_site == {"its-wws-test1": 1}
/workspace/tests/unit/test_db_resilience.py:490:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/unit/test_db_resilience.py:491:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/unit/test_db_resilience.py:510:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/unit/test_db_resilience.py:511:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/unit/test_db_resilience.py:523:    assert psh.db_reconnects_by_site == {}
/workspace/tests/unit/test_db_resilience.py:524:    assert psh.db_reconnect_failures_by_site == {"its-wws-test1": 1}
/workspace/tests/integration/test_db_credentials.py:24:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_abort_run.py:38:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_abort_run.py:39:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:54:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:55:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:71:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:72:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:103:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:104:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:116:    monkeypatch.setattr(psh, "db_reconnects_by_site", {"its-wws-test2": 3})
/workspace/tests/integration/test_finish_run.py:117:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {"its-wws-test2": 1})
/workspace/tests/integration/test_finish_run.py:148:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:149:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:171:    monkeypatch.setattr(psh, "db_reconnects_by_site", {"its-wws-test1": 2})
/workspace/tests/integration/test_finish_run.py:172:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:197:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:198:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:210:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:211:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:232:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:233:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:275:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:276:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:304:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:305:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/tests/integration/test_finish_run.py:327:    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
/workspace/tests/integration/test_finish_run.py:328:    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
/workspace/psh/_legacy.py:832:db_reconnects_by_site = {}
/workspace/psh/_legacy.py:838:db_reconnect_failures_by_site = {}
/workspace/psh/_legacy.py:901:            record_db_reconnect(db_reconnect_failures_by_site, site)
/workspace/psh/_legacy.py:917:                record_db_reconnect(db_reconnect_failures_by_site, site)
/workspace/psh/_legacy.py:919:            record_db_reconnect(db_reconnect_failures_by_site, site)
/workspace/psh/_legacy.py:925:        record_db_reconnect(db_reconnects_by_site, site)
/workspace/psh/_legacy.py:1210:    reconnects = sum(db_reconnects_by_site.values())
/workspace/psh/_legacy.py:1211:    reconnect_failures = sum(db_reconnect_failures_by_site.values())
/workspace/psh/_legacy.py:1296:                "reconnects_by_site": dict(db_reconnects_by_site),
/workspace/psh/_legacy.py:1297:                "reconnect_failures_by_site": dict(db_reconnect_failures_by_site),
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "sed -n '1,60p' /workspace/psh/_legacy.py; echo ====; grep -n 'reset_sc' -A 40 /workspace/tests/conftest.py | sed -n '1,60p'",
  "description": "Show _legacy.py imports and the reset_sc fixture"
}
```

### ↳ Tool result

```
#!/usr/bin/env python
#
# pantheon-sitehealth-emails
#
# Send emails to website owners letting them know what their Pantheon traffic has been and make recommendations about
# whether/how they should change their current plan or the configuration of their site.
#
# Usage:
#   pantheon-sitehealth-emails [-h|--help]
#
# TODO: add WordPress MU plugin check (report on anything except plugin)

import argparse
import calendar
import copy
import datetime
import html
import importlib
import io
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import tomllib
import urllib.parse
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import make_msgid
from smtplib import SMTP_SSL
from typing import NamedTuple

import matplotlib
import matplotlib.dates as mdates
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
import semver
import sqlalchemy as db
from jinja2 import Template
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Polygon
from rich.markup import escape
from rich.padding import Padding
from rich.pretty import pprint
from sqlalchemy import (
    Boolean,
    Date,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    insert,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
====
10:  * script_context (`sc`) holds process-global mutable state; the reset_sc autouse
11-    fixture restores it (deep-copied) between tests.
12-  * run_program() is the ONLY sanctioned way to invoke the program in a subprocess; it
13-    raises ForbiddenFlagError before exec if --all/-a/--for-real appear (constraints C1/C2).
14-"""
15-import copy
16-import datetime
17-import importlib.util
18-import os
19-import re
20-import sqlite3
21-import subprocess
22-import sys
23-from pathlib import Path
24-
25-import pytest
26-
27-# ── Determinism: pin the matplotlib backend before the target module (which imports
28-# matplotlib.pyplot at its top) is ever loaded. ──────────────────────────────────────
29-os.environ.setdefault("MPLBACKEND", "Agg")
30-
31-REPO_ROOT = Path(__file__).resolve().parent.parent
32-PROGRAM = REPO_ROOT / "pantheon-sitehealth-emails"
33-TESTS_DIR = REPO_ROOT / "tests"
34-SHIM_DIR = TESTS_DIR / "shims"          # on PATH: the fake `terminus`
35-PYSHIM_DIR = SHIM_DIR / "pyshim"        # on PYTHONPATH: the ONE sitecustomize (DNS + DB shims)
36-FIXTURES = TESTS_DIR / "fixtures"
37-CONFIG_DIR = FIXTURES / "config"
38-TERMINUS_FIXTURES = FIXTURES / "terminus"
39-REAL_TERMINUS = os.environ.get("TERMINUS_SHIM_REAL", "/usr/local/bin/terminus")
40-
41-# Static assets the program reads relative to its CWD; symlinked into an isolated
42-# working directory so e2e runs never touch the repo's real build/, news/, database.db.
43-_CWD_ASSETS = (
44-    "email_template.html",
45-    "email_template.txt",
46-    "header-image.png",
47-    "inline-styles.php",  # PHP resolves vendor/ via realpath __DIR__, so no vendor symlink needed
48-    # find_modules() walks os.walk("check") / os.walk("plugin") -- CWD-RELATIVE
49-    # (pantheon-sitehealth-emails:900).  Without these, an e2e run in the isolated workdir
50-    # discovers NO check or plugin package at all, so no hook ever registers and the e2e tier
--
126:def reset_sc(psh):
127-    """Restore script_context's mutable globals (deep-copied) around every test.
128-
129-    `sc.hooks` is a dict-of-lists and add_hook/add_news_item (and SiteContext.add_notice)
130-    mutate the nested lists in place, so a shallow snapshot would leak between tests.
131-    """
132-    import script_context as sc
133-
134-    saved = {name: copy.deepcopy(getattr(sc, name)) for name in _SC_ATTRS}
135-    # Start each test from a clean slate.  sc.options must expose .verbose (many helpers
136-    # call sc.debug() -> sc.options.verbose), so use a real parsed default namespace.
137-    sc.options = psh.parse_args([])
138-    sc.config = {}
139-    sc.news = []
140-    sc.hooks = {phase: [] for phase in sc.PHASES}
141-    sc.substitutions = []
142-    sc.plugin = {}
143-    sc.check = {}
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "sed -n '60,92p' /workspace/psh/_legacy.py; echo ==CHAR==; grep -n 'CHAR' /workspace/psh/_legacy.py | head; echo ==B10-B11==; grep -n 'create_engine\\|sessionmaker\\|create_all\\|Session(' /workspace/psh/_legacy.py; echo ==sqlalchemy-usage==; grep -n '\\bdb\\.\\|SQLAlchemyError' /workspace/psh/_legacy.py | head -20",
  "description": "Show remaining imports and engine/session usage in _legacy.py"
}
```

### ↳ Tool result

```
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR

import dns_classify
import script_context as sc

traffic_table_columns = [
    {"name": "month", "label": "Month"},
    {"name": "visitors", "label": "Pantheon Visitors"},
    {"name": "month", "label": "Month"},
    {"name": "visitors", "label": "Pantheon Visitors"},
    {"name": "plan", "label": "Plan"},
    {"name": "plan-limit", "label": "Plan Limit"},
    {"name": "overage", "label": "Overage"},
    {"name": "overage-blocks", "label": "Overage Blocks"},
    {"name": "overage-cost", "label": "Overage Cost"},
    {"name": "overage-protection", "label": "Overage Protection"},
    {"name": "upgrade-at", "label": "Upgrade At"},
    {"name": "next-plan", "label": "Upgrade To"},
    {"name": "downgrade-at", "label": "Downgrade At"},
    {"name": "previous-plan", "label": "Downgrade To"},
]

cost_table_columns = [
    {"name": "plan", "label": "Plan"},
    {"name": "cost-same", "label": "Same Traffic Cost"},
    {"name": "cost-median", "label": "Median Traffic Cost"},
    {"name": "notes", "label": ""},
]

fqdn_re = re.compile(r"^_?[a-z0-9-]+\.[a-z0-9.-]+$", re.IGNORECASE)


==CHAR==
61:from sqlalchemy.types import CHAR
101:    site_id: Mapped[str] = mapped_column(CHAR(36))
123:    site_id: Mapped[str] = mapped_column(CHAR(36))
==B10-B11==
1080:    """Build the (connection string, create_engine kwargs) for the traffic database.
1997:    db_engine = db.create_engine(
2007:    db_session_factory = db.orm.sessionmaker(bind=db_engine, expire_on_commit=False)
2011:        Base.metadata.create_all(db_engine)
==sqlalchemy-usage==
59:from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
1189:    # catches are narrow -- (SQLAlchemyError, OSError), not Exception -- so a TypeError from a
1199:    except (SQLAlchemyError, OSError) as e:
1205:    except (SQLAlchemyError, OSError) as e:
1463:    except (SQLAlchemyError, OSError) as e:  # the database is already sick; see finish_run()
1997:    db_engine = db.create_engine(
2007:    db_session_factory = db.orm.sessionmaker(bind=db_engine, expire_on_commit=False)
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "grep -n '_SC_ATTRS' -B2 -A12 /workspace/tests/conftest.py | head -40; echo ==ruff-broad==; cat /workspace/ruff-broad.toml; echo ==release-test==; grep -rn 'test_load_traffic_rows_releases_the_connection' /workspace/tests -l",
  "description": "Show _SC_ATTRS, ruff-broad.toml, and locate the connection-release test"
}
```

### ↳ Tool result

```
111-
112-# ── Global-state isolation ──────────────────────────────────────────────────────────
113:_SC_ATTRS = (
114-    "options",
115-    "config",
116-    "news",
117-    "hooks",
118-    "substitutions",
119-    "plugin",
120-    "check",
121-    "plugin_context",
122-)
123-
124-
125-@pytest.fixture(autouse=True)
--
132-    import script_context as sc
133-
134:    saved = {name: copy.deepcopy(getattr(sc, name)) for name in _SC_ATTRS}
135-    # Start each test from a clean slate.  sc.options must expose .verbose (many helpers
136-    # call sc.debug() -> sc.options.verbose), so use a real parsed default namespace.
137-    sc.options = psh.parse_args([])
138-    sc.config = {}
139-    sc.news = []
140-    sc.hooks = {phase: [] for phase in sc.PHASES}
141-    sc.substitutions = []
142-    sc.plugin = {}
143-    sc.check = {}
144-    sc.plugin_context = {}
145-    try:
146-        yield sc
==ruff-broad==
# The modularization campaign's ratchet (CAMPAIGN.md section 13) -- ruff pass 2.
# Pass 1 is pyproject.toml's narrow PD-rule set, which runs EVERYWHERE including
# the files excluded here; run-tests and .claude/hooks/ruff-check.sh run BOTH
# passes.  This file dies at I14 when its settings merge into pyproject.toml.
#
# select = ALL, minus the ignores below, gates every file NOT excluded.  An
# increment "un-grandfathers" a file by deleting it from exclude.  Adding an
# ignore requires a justification comment here and a LEDGER.md entry.

# Same inference rule as pyproject.toml: no target-version (PD#14 -- pinning it
# masks the 3.12-only f-string syntax detection).
extend-exclude = [
    # Grandfathered until their increment moves/cleans them:
    "psh/_legacy.py",       # the remnant; shrinks I2-I13, dies I14
    "dns_classify.py",      # cleaned if/when moved (I14 MAY, CAMPAIGN section 3.1)
    "check/",               # cleaned as I8-I10 restructure them
    "plugin/",              # cleaned as increments touch them
    "tests/",               # cleaned per-increment alongside their code
    "development/",         # historical archive, never linted
]

[lint]
select = ["ALL"]
ignore = [
    # -- Formatter territory (no autoformatter is adopted; these fight hand style):
    "COM812",  # trailing-comma
    "ISC001",  # implicit str concat (conflicts with COM812 tooling advice)
    "E501",    # line length -- house style has long notice literals; revisit at I14
    "Q000", "Q001", "Q002", "Q003",  # quote style
    # -- Owned by pyright, not ruff:
    "ANN",     # type annotations -- pyright gates typing (pyproject [tool.pyright])
    # -- Deliberate house practice:
    "TD002", "TD003", "FIX002",  # TODOs are tracked in README/ledger, not as issues
    "EM101", "EM102",  # message-in-raise is accepted; PD#2 covers the real risk
    "TRY003",  # long exception messages in-line -- same rationale as EM
    "D",       # docstring convention undecided -- README TODO (see Task 4)
    "CPY001",  # no per-file copyright headers in this repo
]

[lint.per-file-ignores]
# (none yet -- tests/ is excluded wholesale above; when an increment
# un-grandfathers a test file, add S101 etc. HERE with justification)
==release-test==
/workspace/tests/unit/test_db_resilience.py
```

## Assistant

All facts in hand except the test suites' calling patterns. Quick look at how the DB tests target the functions and patch `time.sleep`:

### ⚙ Tool call: `Bash`

```json
{
  "command": "sed -n '1,95p' /workspace/tests/unit/test_db_resilience.py; echo ====; grep -n 'time\\|sleep' /workspace/tests/unit/test_db_resilience.py | head; echo ==credentials==; sed -n '1,40p' /workspace/tests/integration/test_db_credentials.py",
  "description": "Show DB resilience/credentials test patterns"
}
```

### ↳ Tool result

```
"""Unit tests for the database connection-resilience layer.

See development/2026-07-13-db-connection-resilience/SPEC.md.
"""

import datetime

import pytest
import sqlalchemy as db
from sqlalchemy.exc import (
    IntegrityError,
    InterfaceError,
    OperationalError,
    ProgrammingError,
)


@pytest.mark.unit
def test_db_engine_args_sqlite_has_no_pool_kwargs(psh):
    conn_str, kwargs = psh.db_engine_args({"type": "sqlite", "name": "database.db"})
    assert conn_str == "sqlite:///database.db"
    assert kwargs == {}


@pytest.mark.unit
def test_db_engine_args_mysql_enables_pre_ping_and_recycle(psh):
    # pre_ping and recycle are what let SQLAlchemy silently replace a connection that a
    # middlebox reaped while it sat in the pool (SPEC 3.2).  A future edit that drops them
    # re-opens the bug, so they are pinned here.
    conn_str, kwargs = psh.db_engine_args(
        {
            "type": "mysql",
            "name": "sitehealth",
            "user": "u",
            "password": "p",
            "host": "db.example.org",
            "port": 3306,
        }
    )
    assert conn_str == "mysql+mysqldb://u:p@db.example.org:3306/sitehealth"
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 1800
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20


@pytest.mark.unit
def test_db_engine_args_unsupported_type_exits(psh):
    with pytest.raises(SystemExit):
        psh.db_engine_args({"type": "postgres", "name": "x"})


class FakeSession:
    """Minimal stand-in: records rollbacks so the retry contract can be asserted."""

    def __init__(self, rollback_raises=False, rollback_error=None):
        self.rollbacks = 0
        self.rollback_raises = rollback_raises
        self.rollback_error = rollback_error

    def rollback(self):
        self.rollbacks += 1
        if self.rollback_raises:
            raise self.rollback_error if self.rollback_error is not None else _op_error()


def _op_error():
    return OperationalError("SELECT 1", {}, Exception("(2013, 'Lost connection')"))


@pytest.mark.unit
def test_db_retry_heals_a_lost_connection(psh, monkeypatch):
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})  # never assign: psh is session-scoped
    monkeypatch.setattr(psh, "db_reconnect_failures_by_site", {})
    session = FakeSession()
    calls = []

    def unit():
        calls.append(1)
        if len(calls) == 1:
            raise _op_error()
        return "rows"

    result = psh.db_retry(
        session, unit, what="loading traffic rows for its-wws-test1", site="its-wws-test1"
    )
    assert result == "rows"
    assert len(calls) == 2         # the unit was re-run from scratch
    assert session.rollbacks == 1  # ... after a rollback, which is what makes that safe
    # Attributed, not just counted: an operator seeing 37 reconnects needs to know WHICH sites
    # (SPEC 3.6, audit question 4).  A HEAL, counted only because the retry actually returned.
    assert psh.db_reconnects_by_site == {"its-wws-test1": 1}
    assert psh.db_reconnect_failures_by_site == {}

====
6:import datetime
73:    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
99:    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
123:    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
146:    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
167:    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
195:            traffic_date=datetime.date(2026, 3, 1),
205:        session, {"id": "s1"}, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)
214:    assert rows[0].traffic_date == datetime.date(2026, 3, 1)
233:            traffic_date=datetime.date(2026, 3, 1),
==credentials==
"""The abort handler prints the underlying database error.  It must never render the connection
URL, which embeds the DB password.  See SPEC section 3.8.
"""

import pytest
import sqlalchemy as db

# create_engine("mysql+mysqldb://...") imports the DBAPI EAGERLY, so on a sqlite-only install
# (the [mysql] extra is optional and CLAUDE.md's setup line sanctions dropping it) that line
# raises ModuleNotFoundError OUTSIDE the pytest.raises block below -- a hard ERROR in the
# documented offline inner loop (`./run-tests --fast`), unrelated to whatever the contributor
# changed.  Skip cleanly instead.
pytest.importorskip(
    "MySQLdb", reason="needs the optional [mysql] extra: the leak test drives a real MySQL engine"
)


@pytest.mark.integration
def test_db_retry_error_leaks_no_credentials(psh, monkeypatch):
    # Driven through a REAL engine whose URL contains a password, so a leak is actually possible
    # and this assertion can fail.  (A hand-built OperationalError contains no URL at all, which
    # is what made an earlier draft of this test vacuous.)
    monkeypatch.setattr(psh.time, "sleep", lambda _s: None)
    monkeypatch.setattr(psh, "db_reconnects_by_site", {})
    # connect_timeout=1: loopback port 1 normally REFUSES instantly, but a host that DROPs it
    # would otherwise hang the suite for MySQLdb's default timeout.
    engine = db.create_engine(
        "mysql+mysqldb://dbuser:hunter2@127.0.0.1:1/sitehealth",
        connect_args={"connect_timeout": 1},
    )
    session = db.orm.sessionmaker(bind=engine)()

    def unit():  # the connection is refused: MySQLdb raises OperationalError on connect
        return session.execute(db.text("SELECT 1")).all()

    with pytest.raises(psh.DatabaseUnavailableError) as excinfo:
        psh.db_retry(session, unit, what="probing the database", site="its-wws-test1")
    message = str(excinfo.value)
    # The UNREDACTED URL: str(engine.url) is render_as_string(hide_password=True), i.e.
    # "mysql+mysqldb://dbuser:***@..." -- a string no credential leak could ever produce, so
```

### ⚙ Tool call: `Read`

```json
{
  "file_path": "/workspace/prompts/implementation-standards.md"
}
```

### ↳ Tool result

```
1	# Implementation Standards
2	
3	A **standards overlay** for the `superpowers:subagent-driven-development` skill. The skill
4	drives the *process* (read plan → dispatch a fresh implementer per task → task review →
5	fix loop → whole-branch review → finish the branch). This file defines the *bar* and the
6	*judgment* to apply inside that flow. Where they overlap, the skill owns the process; this
7	file owns the standards. Nothing here restates skill mechanics (model selection, the
8	review-package/task-brief scripts, the progress ledger, status handling) — read the skill
9	for those.
10	
11	> **Read `prompts/directives.md` first** — the Spine. This file does not restate a rule from
12	> it; it says what those rules mean **in code**, and cites them by number.
13	
14	## Posture — during execution
15	
16	The bar is not "does the task pass its reviewer" — it is **"would this survive adversarial
17	review"** (`prompts/adversarial-review.md`). Build to that bar the first time so the fix
18	loop stays short.
19	
20	## How this overlay is applied (read first)
21	
22	You are the **controller**. Implementer and reviewer subagents have fresh context: they
23	never see this file, the spec conversation, or `CLAUDE.md` unless it reaches them somehow.
24	**An un-injected standard does not exist.**
25	
26	**Dispatch every code-touching subagent as `psh-implementer`, and every reviewer as
27	`psh-reviewer`** (`.claude/agents/`). Those agent definitions carry the read list, so the
28	standards arrive as **configuration** rather than as prose you must remember to paste:
29	
30	```
31	Before doing anything, read IN FULL:
32	  1. prompts/directives.md               (the standards spine)
33	  2. prompts/implementation-standards.md (implementation bar + house style)
34	  3. CLAUDE.md — the sections the task touches
35	  4. the task brief and the spec named in the dispatch
36	```
37	
38	`superpowers:subagent-driven-development`'s template dispatches `Subagent
39	(general-purpose)`. **Override it**, here in the same way and place this file already
40	overrides the TDD default. Fix-subagents are code-touching and dispatch as
41	`psh-implementer` too.
42	
43	> **Why not curate.** An earlier version of this file told the controller to inject "not the
44	> whole file, only the relevant subset." That makes standards delivery depend on the
45	> controller's judgment at the moment its context is fullest and momentum highest — which is
46	> exactly when standards got dropped. A fixed list removes the judgment. The Spine is small
47	> enough (≤9 KB) that reading it in full costs nothing worth optimizing: the whole read list
48	> is ~4.7k tokens per dispatch.
49	
50	**Every task report MUST cite the Spine directives it applied — by number — and quote a
51	verbatim clause from each.** Grep the quotes against `prompts/directives.md`; a paraphrase
52	fails. This is the only observable that separates "read the standards" from "did not," and
53	PD#14 forbids an instrument that cannot go red.
54	
55	**Do not tell a reviewer what to downgrade or ignore.** That is the skill's rule and it
56	holds regardless of how inconvenient a finding is.
57	
58	**Plan-vs-standards conflict.** If the plan mandates something this file treats as a defect
59	(a catch-all handler, a test that asserts nothing, `terminus` where a wrapper exists), that
60	is a human decision — surface the finding beside the plan text and ask which governs. Fold
61	it into the skill's pre-flight plan scan; don't silently "fix" the plan.
62	
63	**TDD override.** The skill defaults implementer subagents to
64	`superpowers:test-driven-development`. This project uses **`mattpocock-skills:tdd`** instead
65	— inject it by name in every implementer brief, because **the host's default wins silently if
66	you don't**. The two differ in ways that decide the work here:
67	
68	- **Test only at pre-agreed seams.** Matt's skill forbids a test at an unconfirmed seam and
69	  tells the implementer to confirm seams *with the user* — an implementer subagent has fresh
70	  context and cannot. So **the spec declares the seams** (§ *Spec & internal-doc quality bar*
71	  in `prompts/directives.md`) and you copy them into the brief verbatim. A task whose spec
72	  names no seam is `NEEDS_CONTEXT`, not a licence to pick one.
73	- **Refactoring is not part of the red→green loop.** It belongs to review
74	  (`prompts/adversarial-review.md`), not the implementer's cycle. Superpowers' TDD puts it
75	  inside the loop; here it doesn't go there.
76	
77	## Directives at implementation time
78	
79	The Spine's Prime Directives (`prompts/directives.md`), re-expressed as what the implementer
80	does **in code**. The implementer reads all of them via the read list above — this section is
81	the translation, not a menu to pick from:
82	
83	1. **Every error has a name — in code.** Raise a named exception (this codebase uses
84	   `TerminusError` and friends), add the test that trips it, and wire the operator-visible
85	   message at the right verbosity. `except Exception`/bare `except` **fails the lint gate**
86	   (`BLE001`/`E722`) — you'll see it at edit time via the hook, and `./run-tests` blocks on
87	   it. A deliberate catch-all carries `# noqa: BLE001` **with an inline reason** — a bare
88	   `noqa` is itself a silent failure (PD#1). `main()`'s `except BaseException` is the worked
89	   example: the reason cites why enumerating classes lost 249 sites' work.
90	2. **Zero silent failures.** A code path that can fail without the system, the operator, or
91	   the run's exit status showing it is a defect, not a smaller version of done.
92	3. **Shadow paths are written and tested.** For every new flow, implement and cover the
93	   three shadows beside the happy path: nil input, empty/zero-length input, upstream error.
94	4. **Runs are not atomic — code for partial state.** Idempotent DB writes (`ON CONFLICT DO
95	   NOTHING` / `INSERT IGNORE`), honor `--resume-from`, no partial-write-then-fail, and never
96	   weaken the `--for-real`/dry-run gate.
97	5. **Observability is code you write now.** `debug()` at the correct `-v`/`-vv`/`-vvv` level,
98	   actionable operator messages, dry-run visibility — not a follow-up task.
99	6. **Security is not optional.** Secrets flow through `<{secret env …}>` config
100	   substitutions — never read from the environment, never logged, never committed.
101	   Threat-model any new outbound HTTP/subprocess path; route it through the existing
102	   monkeypatchable seams.
103	7. **Where a diagram exists in a comment or docstring, updating it is part of changing the
104	   flow it describes** — a stale ASCII diagram is worse than none. Writing one in code is
105	   REQUIRED only where the flow is **non-local** (spans files, packages, or phase seams);
106	   the design/spec is where diagrams are mandatory (PD#8).
107	8. **Everything deferred is written down** — as a `README.md` TODO or a named follow-up, in
108	   the same commit. Vague intentions are lies.
109	9. **Terminology stays consistent** with the surrounding code and the spec's glossary. Fix
110	   drift you introduce; flag drift you find.
111	
112	## The fresh-context trap — house style a new subagent will get wrong
113	
114	- **Use the wrappers, not the raw tools.** `run_terminus`/`terminus`/`terminus_data`,
115	  `wp`/`wp_eval`, `drush`/`drush_php_script` (all return 3-tuples); build failure notices
116	  with `wp_error`/`drush_error`. Never shell out to `terminus`/`wp`/`drush` directly.
117	- **Add notices/sections via the `SiteContext` methods** (`add_notice`, `add_section`,
118	  `add_attachment`) — the module-level free functions are gone. Every notice needs a `csv`
119	  key.
120	- **Wire new behavior through the `sc.PHASES` seams** and honor the per-phase data contract;
121	  don't reach across phases for data the contract doesn't guarantee yet.
122	- **Follow the local idioms even where non-idiomatic** — e.g. the `-> (str, str, bool)`
123	  tuple type hints. This is house style; don't "correct" it.
124	- **Prefer the Pantheon API over `terminus` for new code** unless `terminus` is clearly
125	  better (missing endpoint, materially simpler/cleaner, better result). State which and why.
126	
127	## Definition of Done (per task)
128	
129	The bar the task reviewer verifies against. A task is done only when **all** hold:
130	
131	- Tests for the change **written first at the spec's declared seam, watched fail for the
132	  right reason**, then added/adjusted in the same commit at the right tier, and **run with
133	  the command and output pasted** — evidence, never "should pass" or a summarized "green."
134	  (Carve-outs in § Test discipline are the exhaustive exceptions.)
135	- House style matched (§ Fresh-context trap); no unrequested scope, no gold-plating.
136	- Directives for the touched paths satisfied (§ Directives) — named errors, shadow paths,
137	  observability, secrets handled.
138	- Diagram comments and `README.md` TODO updated; memory updated with any non-obvious gotcha
139	  or decision.
140	- No debug cruft (stray prints, commented-out code, temp files) left behind.
141	- **The report cites the Spine directives applied — by number, with a verbatim quote from
142	  each** (§ How this overlay is applied).
143	- **`CLAUDE.md` prose that existed to explain logic this task moved into a package is
144	  deleted in the same commit.** Report the line-count delta. **EXEMPT:** prose recording a
145	  shipped defect's root cause and its non-obvious repair — **unless a named test already
146	  guards that defect**, in which case it reduces to a one-line pointer at that test. Prose
147	  is not exempt merely for being old, long, or architectural. *Intent:* much of `CLAUDE.md`
148	  stands in for structure the code doesn't express, and retires with it; defect knowledge
149	  does not, and deleting a line of it re-opens a closed defect. Where a test guards the
150	  defect, the test is the durable record — it can go red; prose cannot.
151	
152	## Test discipline
153	
154	- **Test-first, at the seams the spec declares.** Write the failing test, **watch it fail for
155	  the right reason**, then write the minimal code to pass. A test that passes the moment you
156	  write it is testing existing behavior — fix the test, don't move on. One seam, one test,
157	  one minimal implementation per cycle (vertical slices, not all-tests-then-all-code).
158	- **No seam above the golden? Make one — or say why not, in the spec.** If a core `main()`
159	  change has no honest seam, extracting a pure module-level helper is **part of the change**;
160	  that is how `overage_blocks`, `plan_costs`, `sites_from_resume_point` and the rest came to
161	  exist, behavior-preserving with the goldens byte-identical. The escape hatch is explicit and
162	  lives in the spec ("no seam is worth making here, because…") — never a silent skip. If you
163	  discover mid-task that the seam the spec named doesn't hold, that is
164	  `DONE_WITH_CONCERNS`/`BLOCKED`, not an improvised seam.
165	- **Carve-outs from test-first — exhaustive, not illustrative.** These are the only places
166	  red→green is structurally impossible, because the expected value is derived from the code
167	  that just ran:
168	  1. **A new golden or syrupy snapshot** (`--update-goldens`) — written after, with the
169	     initial content reviewed byte-by-byte as if it were the assertion, because it is.
170	  2. **Recorded fixtures** (`--record`, `tests/tools/record.py`) — captured from live
171	     Pantheon; they are inputs, not tests.
172	
173	  Nothing else is carved out. And the carve-out is *creation only*: **an existing golden going
174	  red is a signal**, never refreshed to green (see the load-bearing rule below).
175	- **Tests are load-bearing.** Never weaken an assertion, add a `sleep`/retry, or loosen a
176	  matcher to turn a test green. A failing test is a signal to fix the code, not the test.
177	- **Right tier, `./run-tests --fast` as the inner loop.** Match the change to its tier
178	  (`unit`/`integration`/`e2e`/`render`/`email`/`live`); pure logic gets a unit/property test,
179	  a new report path gets a golden or e2e assertion.
180	- **Golden/fixture regeneration requires a reviewed diff.** `--update-goldens`/`--record` is
181	  never a reflex to make a test pass — inspect the diff and justify every changed byte.
182	- **Respect the safety interlock.** No `--all`/`-a`/`--for-real`, and no live/non-fixture
183	  `--create-tables`/`--import-older-metrics` in tests. Route new I/O through the existing
184	  mock seams (`run_terminus`, the `httpseam`/`egress` probes) so it stays offline-testable.
185	
186	## Deviation & debugging discipline
187	
188	- **No silent deviation.** If the plan is wrong or underspecified, the implementer surfaces
189	  it via the skill's `DONE_WITH_CONCERNS`/`BLOCKED`/`NEEDS_CONTEXT` status — it never
190	  quietly changes the plan's intent or invents scope.
191	- **Root cause, not symptom.** On a failure or surprising behavior, debug systematically to
192	  the actual cause — `/diagnosing-bugs`, under the standards in
193	  `prompts/debugging-standards.md`, which maps its feedback-loop gate onto this repo's real
194	  loops. Never mask a failure with a catch-all, a retry-until-green, or a broadened exception.
195	- **Right-sized diff.** The smallest change that cleanly expresses the task — but don't
196	  compress a necessary rewrite into a minimal patch. If the foundation the task sits on is
197	  broken, raise it (Prime Directive #12) rather than building on it.
198	
199	## Commit hygiene
200	
201	- Atomic **conventional commits** (`feat:`/`fix:`/`docs:` — matching this repo's log), one
202	  logical change each, tests included in the same commit as the code they cover.
203	- End commit messages with the `Co-Authored-By` trailer this environment requires.
204	- Never commit secrets, `.env` contents, or unreviewed golden/fixture regenerations.
205	
206	## This project's context
207	
208	Read `prompts/directives.md` for the standards and `CLAUDE.md` for the conventions every change must respect — the single-file core plus
209	self-registering `plugin/`/`check/` packages, the `sc.PHASES` seams and per-phase data
210	contract, the test harness and its interlock, the Pantheon-API preference, and keeping
211	institution-specific logic behind config flags / the `umich` packages so the tool stays
212	reusable by other institutions.
213
```

### ⚙ Tool call: `Read`

```json
{
  "file_path": "/workspace/development/2026-07-20-mod-I4-hooks-dag/SPEC.md"
}
```

### ↳ Tool result

```
1	# SPEC — Increment I4: `psh/modules.py` (hook engine, DAG, contract registry, `run_finish`)
2	
3	**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites
4	`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope
5	authority: §11 row I4. Design authority for the DAG: §4. Module map: §3.1. Per-increment
6	obligations: §7. Behavior bar: §8. Invariants: §9. Ratchet: §13.
7	
8	**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I3), `CLAUDE.md`,
9	`BLOCKMAP.md` rows B2/B4/B7/B27/B28/B31/B37/B52/B59/B60, `prompts/directives.md`,
10	`prompts/implementation-standards.md`.
11	
12	## Glossary (delta over CAMPAIGN.md's; terms used exactly once per concept)
13	
14	- **Engine** — the hook machinery: `PHASES`, `_valid_hook_name`, `add_hook`,
15	  `invoke_hooks` (today in `script_context.py`), plus the new DAG validation.
16	- **Registry** — the machine-readable per-phase contract: phase → the `site_context`
17	  keys core stuffs *first at that phase* (§4 "Contract registry").
18	- **Declaration** — a hook's `consumes` and `produces` entries (each a possibly-empty
19	  list of contract-key names).
20	- **Stuffer** — a pure helper that writes exactly one phase's registry keys onto the
21	  `SiteContext` (existing precedent: `dns_classify.stuff_dns_contract`).
22	- **Bare phase** — a name in `PHASES`. **Dotted event** — a plugin-defined `a.b.c` name
23	  (unchanged semantics, §4).
24	
25	## 1. Scope (exhaustive) and non-scope
26	
27	In scope (§11 row I4):
28	
29	1. **Move** `find_modules` (14 lines, `psh/_legacy.py:526–539`; the "935–950" in §11 is
30	   the pre-campaign line range, drifted per BLOCKMAP preamble) and the engine (from
31	   `script_context.py`) into a new `psh/modules.py`. Re-import pattern as I2/I3.
32	2. **`run_finish` phase** appended to `PHASES`; fired inside `finish_run()` before
33	   anything is torn down or written.
34	3. **Declarations required on every hook**; retrofit all 12 in-repo registrations.
35	4. **DAG validation** with the five fatal conditions of §4, each a named error, each
36	   demonstrably red in tests (PD#14).
37	5. **Topological invoke order** (producers before consumers; registration order breaks
38	   ties — today's DAG is edgeless, see §5 below, so observed order is unchanged).
39	6. **Contract registry** in `psh/modules.py` + stuffer extraction so core's stuffing is
40	   registry-checked in tests (§4; extraction sanctioned by
41	   `prompts/implementation-standards.md` § Test discipline).
42	7. **Ratchet:** `psh/modules.py` gated from birth; **un-grandfather `script_context.py`**
43	   (delete from `ruff-broad.toml` `extend-exclude` — its own comment assigns this to I4).
44	8. Docs/CLAUDE.md/memory/ledger updates (§7 obligations 6–8).
45	
46	NOT in scope: B2/B4 module-loading loops stay in `main()` (§11 row I4 does not list
47	them; §3.1 assigns them to `psh/modules.py` eventually — they move with `main()`'s
48	final form, I13; **ledger note**). No `[Check.*]` config sections (I8+). No new §6
49	type for hooks — targets remain dicts (a `Hook` dataclass would amend §6's exhaustive
50	table for no consumer benefit; registration call sites stay minimal-churn). No pyright
51	scope widening (stays `psh/` minus `_legacy.py`). No golden/fixture changes (Invariants
52	1, 10).
53	
54	## 2. Architecture decisions (each with why; deviations flagged for the ledger)
55	
56	### D-i4-1: the mutable `hooks` dict STAYS in `script_context.py`
57	
58	§3.1 moves the engine *functions*; it names `PHASES` but not the `hooks` state dict.
59	The dict stays put because: (a) CLAUDE.md defines `script_context` as the home of
60	cross-cutting mutable state; (b) §3.4 forbids new module-level mutable state in `psh/`
61	modules (review criterion since I2); (c) `tests/conftest.py::reset_sc` **rebinds**
62	`sc.hooks` around every test — a second home in `psh.modules` would desync engine from
63	tests the first time anything rebound one and not the other, a silent instrument defect
64	(PD#14). The engine reads it as `sc.hooks` at call time. **Ledger note, not an
65	amendment** — §3.1's engine list is satisfied; state placement follows existing §3.4 +
66	CLAUDE.md rules.
67	
68	### D-i4-2: import direction and the cycle
69	
70	`script_context.py` re-exports `PHASES`, `add_hook`, `invoke_hooks` via a top-of-file
71	`from psh.modules import PHASES, add_hook, invoke_hooks` (module-level import → names
72	become module attributes automatically; the I3 amendment-3 precedent for
73	`Notice`/`Severity`, recorded in LEDGER I3 deviation 3). Therefore `psh/modules.py`
74	MUST NOT import `script_context` at module level (importing `psh.modules` first would
75	hit a partially-initialized from-import and die with `ImportError`; `psh.notice`'s
76	docstring states the same rule for itself). Engine functions do a **function-level**
77	`import script_context as sc` (`# noqa: PLC0415` with this reason inline) to reach
78	`sc.hooks`, `sc.console`, `sc.debug`. `find_modules`, the registry, the validator's
79	pure core, and the stuffers need no `sc` at all.
80	
81	```
82	        script_context.py  ──(module-level from-import: PHASES/add_hook/invoke_hooks)──►  psh/modules.py
83	                ▲                                                                            │
84	                └────────────(function-level import, call-time only: hooks/console/debug)────┘
85	   checks/plugins import ONLY sc (Invariant 9); sc.add_hook etc. keep resolving unchanged
86	```
87	
88	### D-i4-3: declarations required on ALL hooks, dotted events declare empty
89	
90	`consumes`/`produces` are required on **every** registration — §4 condition 5 says "any
91	hook", "no legacy mode". For dotted events the *semantics* stay unchanged (§4: not
92	ordered, invoked by their owner) but the schema is uniform: a dotted-event hook MUST
93	declare `consumes=[]` and `produces=[]`, and a **non-empty** declaration on a dotted
94	event is fatal (contract keys are phase-anchored; a dotted event has no phase position,
95	so a non-empty declaration is unvalidatable and therefore a lie — PD#1). **Ledger
96	note** (interprets "unchanged" as invocation semantics, not registration schema).
97	
98	### D-i4-4: condition 5 enforces at `add_hook` time; conditions 1–4 at validation
99	
100	`add_hook` already owns registration-time fatals (unknown phase → `console.print` +
101	`sys.exit(1)`). A missing/malformed declaration (absent key, non-list, non-str member,
102	or non-empty on a dotted event) fails there, in the same style — the error names the
103	offending hook at its registration site, the loudest possible locality. This is
104	*stricter placement* of §4's condition 5, not a relaxation (nothing can enter `sc.hooks`
105	undeclared; `tests/integration/test_plugin_cloudflare_init.py` already pins that
106	registration goes through `add_hook`, not raw dict appends). Conditions 1–4 need the
107	complete producer set and run in `validate_hooks()` at module-load completion. **Ledger
108	note.**
109	
110	### D-i4-5: `validate_hooks()` raises named errors; `main()` catches and exits
111	
112	`psh/modules.py` defines `HookDagError(Exception)` and four named subclasses (PD#2), one
113	per condition 1–4 — see the canonical table in §4 below. `main()` calls
114	`validate_hooks()` immediately after the check-import loop (B4) inside
115	`try/except HookDagError` → `sc.console.print` (with `rich.markup.escape` on the
116	message — hook names come from module authors, Invariant 6) + `sys.exit(1)`. Raising
117	named classes keeps the validator a pure, precisely testable unit; the catch site keeps
118	the operator experience a clean fatal line, matching every other startup fatal.
119	
120	### D-i4-6: invoke order is computed per invocation by a pure helper
121	
122	`invoke_hooks` calls a pure `ordered_hooks(hook_name, hooks_list) -> list` each time:
123	Kahn's algorithm over produces→consumes edges among same-phase hooks, ready-queue in
124	registration order (deterministic, explicit — no `graphlib.TopologicalSorter`, whose
125	tie order is not contractually registration-stable). §4's diagram shows "topo order
126	stored"; computing per call is behaviorally identical (same inputs → same order),
127	removes a stale-cache failure mode (tests register hooks without running validation),
128	and costs O(hooks²) on lists of ≤4. **Ledger note** (mechanism choice within §4's
129	observable contract). Dotted events and edgeless phases yield registration order —
130	byte-identical behavior today.
131	
132	### D-i4-7: `run_finish` fires with no arguments until I13
133	
134	§4 says the phase receives the `RunState` — a type I13 introduces (§6). I4 fires
135	`sc.invoke_hooks("run_finish")` as the **first statement** of `finish_run()` (before the
136	session close/engine dispose teardown and all artifact writes — the §4 placement rule,
137	applied to the earliest point so future hooks see the run still intact). No consumer
138	exists (like `site_pre_render` at its introduction); I13 adds the `RunState` argument
139	before any consumer appears, so the signature change is safe. **Ledger note.**
140	
141	## 3. Deliverable A — `psh/modules.py` (new file; gated from birth)
142	
143	Contents (exhaustive):
144	
145	| Item | From | Notes |
146	|---|---|---|
147	| `find_modules(module_type)` | `psh/_legacy.py:526–539` | verbatim move; `os`/`stat` imports; `_legacy` re-imports it |
148	| `PHASES` | `script_context.py:46–55` | tuple gains `'run_finish'` as its last element; move the phase-semantics comment block with it and extend it (run_finish: once per run, inside `finish_run`, before artifacts; fired on completed AND aborted runs — both call `finish_run`) |
149	| `_valid_hook_name` | `script_context.py:73–74` | verbatim |
150	| `add_hook(hook_name, target)` | `script_context.py:77–82` | + declaration enforcement (D-i4-4); state via `sc.hooks` (D-i4-1/2) |
151	| `invoke_hooks(hook_name, *args, **kwargs)` | `script_context.py:85–92` | + `ordered_hooks` ordering (D-i4-6); keeps the two `debug` lines verbatim (levels unchanged) |
152	| `ordered_hooks` | new | pure; Kahn + registration-order ready queue |
153	| `validate_hooks()` | new | conditions 1–4 (§4 table below) over `sc.hooks` + `CONTRACT` |
154	| `HookDagError` + 4 subclasses | new | §4 table below |
155	| `CONTRACT` | new | §5 below |
156	| `stuff_traffic_contract`, `stuff_gather_contract` | extracted from `main()` (B28/B37 stuffing lines) | §5 below |
157	
158	`script_context.py` keeps: `hooks = {phase: [] for phase in PHASES}` (rebuilt from the
159	imported `PHASES`), and everything else it has today. The engine defs and the `PHASES`
160	literal are **deleted** from it (moved, not copied — one copy, PD's DRY preference).
161	
162	Module docstring MUST carry the D-i4-2 import-direction diagram (PD#8: the flow spans
163	`script_context` ↔ `psh.modules`, non-local by definition).
164	
165	## 4. Deliverable B — DAG validation (canonical fatal-condition table)
166	
167	Phase-position notation: `pos(phase)` = index in `PHASES`; a key's **owner phase** =
168	the phase where the registry lists it, or the phase of the hook that produces it.
169	
170	| # (§4) | Condition | Where enforced | Error (all in `psh.modules`) |
171	|---|---|---|---|
172	| 1 | a consumed key no registry phase and no hook produces | `validate_hooks()` | `UnproducedKeyError(HookDagError)` |
173	| 2 | two producers of one key — hook+hook, or hook producing a registry key | `validate_hooks()` | `DuplicateProducerError(HookDagError)` |
174	| 3 | cycle among same-phase hooks | `validate_hooks()` | `HookCycleError(HookDagError)` |
175	| 4 | consumed key's owner phase is later than the hook's phase | `validate_hooks()` | `LaterPhaseKeyError(HookDagError)` |
176	| 5 | missing/malformed declaration (incl. non-empty on dotted event) | `add_hook` | `console.print` + `sys.exit(1)` (house style of its sibling unknown-phase fatal, D-i4-4) |
177	
178	Every error message names the offending hook(s) by their `name` entry, the phase, and
179	the key(s) — the operator must be able to act without reading source (PD#1/#5).
180	Consuming a key owned by an **earlier** phase than the hook's is legal (the
181	`check.umich.cloudflare_cms` case: consumes `fqdns_behind_cloudflare`, owned by
182	`site_post_dns`, from `site_post_gather`).
183	
184	`main()` wiring (the only `_legacy.py` edits, all small): the `except HookDagError`
185	call site after B4 (D-i4-5); the B28/B37 stuffing lines replaced by the two stuffer
186	calls; `sc.invoke_hooks("run_finish")` opening `finish_run()`; the `find_modules` def
187	deleted and re-imported.
188	
189	## 5. Deliverable C — contract registry + stuffers
190	
191	```python
192	# psh/modules.py — authoritative machine-readable form of CLAUDE.md's per-phase table.
193	# Keys FIRST guaranteed at each phase; availability is cumulative (site_pre_render
194	# guarantees everything above it and adds nothing).
195	CONTRACT: dict[str, tuple[str, ...]] = {
196	    "setup": (),
197	    "site_pre": (),
198	    "site_post_traffic": ("traffic_rows", "start_date", "end_date"),
199	    "site_post_dns": (
200	        "domains", "custom_domains", "primary_domain", "main_fqdn",
201	        "fqdns_behind_cloudflare", "fqdns_not_behind_cloudflare", "not_in_dns",
202	        "behind_cloudflare_not_proxied", "proxied_in_multiple_zones", "dns_transient",
203	    ),
204	    "site_post_gather": (
205	        "framework", "site_url", "wordpress_version", "drupal_version",
206	        "wordpress_plugins", "drupal_modules",
207	    ),
208	    "site_pre_render": (),
209	    "run_finish": (),
210	}
211	```
212	
213	(Verbatim from CLAUDE.md's table per §4; the base `site`/`notices`/`sections`/
214	`attachments` keys are `SiteContext` construction, not contract keys, and hooks do not
215	declare them.)
216	
217	Stuffers (extracted so "core's stuffing code is checked against it in tests", §4 —
218	without them the only cover is the goldens, which cannot name a missing key):
219	
220	- `stuff_traffic_contract(site_context, traffic_rows, start_date, end_date)` — the
221	  three B28 assignments, verbatim.
222	- `stuff_gather_contract(site_context, framework, site_url, wordpress_version, plugins,
223	  drupal_version, mods)` — the six B37 assignments **including** the
224	  `isinstance(plugins, list)` / `isinstance(mods, dict)` normalizations and their
225	  comments, verbatim.
226	- `dns_classify.stuff_dns_contract` already exists and is NOT moved; a test pins its
227	  key set against `CONTRACT["site_post_dns"]`.
228	
229	Registry-vs-stuffer tests are registry-driven (`set(written keys) ==
230	set(CONTRACT[phase])`) so adding a key in one place and not the other goes red.
231	
232	## 6. Deliverable D — declaration retrofit (exhaustive; all 12 in-repo registrations)
233	
234	The implementer MUST re-verify each `consumes` list against the hook body before
235	writing it (spec-time verification below was by direct read on 2026-07-20; §7
236	obligation 4). `produces=[]` for every hook — **no in-repo hook publishes a contract
237	key today**, hence the edgeless DAG and unchanged invoke order (D-i4-6).
238	
239	| Registration (file) | Phase | `consumes` |
240	|---|---|---|
241	| `plugin/cloudflare/__init__.py` ips | `setup` | `[]` |
242	| `plugin/cloudflare/__init__.py` fqdns | `setup` | `[]` |
243	| `plugin/umich/__init__.py` portal | `setup` | `[]` |
244	| `check/cloudflare/__init__.py` egress | `setup` | `[]` |
245	| `check/cloudflare/__init__.py` cache | `site_post_dns` | `["fqdns_behind_cloudflare", "primary_domain"]` *(corrected during Task 3: the spec-time grep pattern `site_context[` missed the `.get("primary_domain")` read at `cache.py:233`; the implementer's mandated re-verification caught it — ledger-recorded)* |
246	| `check/dns/__init__.py` emit_dns_notices | `site_post_dns` | `["dns_transient", "fqdns_not_behind_cloudflare", "behind_cloudflare_not_proxied", "proxied_in_multiple_zones", "not_in_dns"]` |
247	| `check/pantheon_cdn_change/__init__.py` | `site_post_dns` | `["custom_domains"]` |
248	| `check/umich/__init__.py` sitelens setup | `setup.umich.portal` (dotted) | `[]` |
249	| `check/umich/__init__.py` sitelens urls | `site_pre` | `[]` |
250	| `check/umich/__init__.py` sitelens scores | `site_pre` | `[]` |
251	| `check/umich/__init__.py` cloudflare_cms | `site_post_gather` | `["fqdns_behind_cloudflare", "framework", "wordpress_plugins", "drupal_version", "drupal_modules"]` |
252	| *(no 12th `add_hook` — the 12th registration surface is `plugin/umich`'s `sc.substitutions.append`, which is not a hook and is untouched)* | | |
253	
254	Test-side registrations updated in the same change (condition 5 has no legacy mode):
255	`tests/integration/test_hooks_phases.py`, `tests/integration/test_terminus_seam.py`,
256	`tests/integration/test_plugin_cloudflare_init.py` (assertions only — the package's own
257	retrofitted declarations flow through its `_load_init`), and any other `add_hook`
258	caller a repo-wide grep finds at implementation time.
259	
260	## 7. Deliverable E — ratchet (§13)
261	
262	- `psh/modules.py`: born gated. `uvx ruff check --config ruff-broad.toml psh/modules.py`
263	  → clean; pyright standard (already `include=["psh"]`) → 0 errors.
264	- **Un-grandfather `script_context.py`**: delete its line (and its comment) from
265	  `ruff-broad.toml` `extend-exclude`. Findings measured 2026-07-20 on the current file:
266	  `I001` (import sort), 2× `SIM401` (`.get` for the `order` lookups in
267	  `add_notice`/`add_news_item`), 2× `PLR1714` (`order in ('prepend', 'first')` merges)
268	  — all mechanical and behavior-preserving; none touch the engine (which leaves the
269	  file anyway). Expected post-move additions: `F401` on the re-exported
270	  `add_hook`/`invoke_hooks` (noqa with re-export reason, exactly like line 9's
271	  `Severity` noqa). Disposition-corrections, if any, go in the ledger (I3 precedent).
272	- Expected out-of-gate minimal typing fix (I3 precedent, ledger-recorded):
273	  `script_context.hooks` gains the annotation `dict[str, list[dict[str, Any]]]` if
274	  pyright standard needs it to check `psh/modules.py`'s call-time access; nothing else
275	  in `script_context.py` is retyped.
276	- No `ruff-broad.toml` `ignore` additions (that would be a §13 amendment). `# noqa`
277	  only with inline reasons (`PLC0415` cycle note, `F401` re-exports, `S101` if pyright
278	  narrowing needs an assert — same set I3 sanctioned).
279	
280	## 8. Behavior bar & invariants applied (§8/§9 — what this increment may and may not change)
281	
282	- Goldens: byte-identical (Invariant 1). Nothing in this increment renders differently:
283	  declarations are inert metadata, the DAG is edgeless (order unchanged), stuffers are
284	  verbatim extractions, `run_finish` has no consumer, and `invoke_hooks`'s only output
285	  is pre-existing `debug` lines at unchanged levels.
286	- Artifact structure: unchanged (§8 row 2) — `run_finish` fires before writes and
287	  writes nothing.
288	- stdout MAY improve (§8): the new fatal messages are new output on new failure paths
289	  only.
290	- Contract: additions none; existing keys untouched (Invariant 2). `run_finish` is a
291	  phase addition, sanctioned by §4 explicitly.
292	- Invariants 4 (lifecycle), 6 (escape untrusted text in the new fatals), 9 (no `sc`
293	  name removed — `sc.PHASES`/`sc.add_hook`/`sc.invoke_hooks`/`sc.hooks` all keep
294	  resolving) hold by construction; the façade test pins them.
295	- Config keys: none added/changed (§5 of CAMPAIGN.md — `[Check.*]` starts at I8).
296	
297	## 9. Seams under test (named and agreed here — exhaustive; PD spec bar)
298	
299	| Behavior | Seam | Tier |
300	|---|---|---|
301	| `add_hook`/`invoke_hooks`/ordering/declaration fatals | `psh.modules` functions directly (pure state via `reset_sc`'s `sc.hooks`) | unit/integration (`test_hooks_phases.py` grows; SystemExit + `recording_console`) |
302	| Each DAG fatal condition 1–4 red | `psh.modules.validate_hooks` with synthetic `sc.hooks` contents | unit (`tests/unit/test_hook_dag_validation.py`, new) |
303	| Topo order + registration tie-break | `psh.modules.ordered_hooks` (pure) | unit (same file) |
304	| "future changes can never make the DAG impossible" (§4) | load ALL real check/plugin packages (checkload probe-package pattern + enabling config: `[UMich].enabled`, `[Cloudflare].enabled` + `[Cloudflare.cachecheck]` with `account_id`/`list_name`) then `validate_hooks()` | integration (`tests/integration/test_hook_dag.py`, new, permanent) |
305	| Registry ↔ stuffers agree | `psh.modules.stuff_traffic_contract`/`stuff_gather_contract`, `dns_classify.stuff_dns_contract` vs `CONTRACT` | unit (`tests/unit/test_contract_registry.py`, new) |
306	| `run_finish` fires before artifacts, on normal and abort paths | `finish_run()` in-process (existing `tests/integration/test_finish_run.py` harness; probe hook registered via `add_hook`) | integration |
307	| Retrofitted packages still register (with declarations) | existing per-package init tests (`test_plugin_cloudflare_init.py` etc.) | integration (updated) |
308	| Whole-program unchanged | the four e2e goldens | e2e (untouched, must stay green) |
309	
310	No new subprocess/network/DNS paths → no new shims. `find_modules` keeps its existing
311	behavior; its move is covered by the e2e tier (which fails loudly if module discovery
312	breaks — the `_CWD_ASSETS` lesson) plus a small unit test if one exists already
313	(implementer greps; none is required to be added for a verbatim move).
314	
315	Test-first applies to every new behavior (declaration fatals, each validator condition,
316	ordering, registry tests, `run_finish` firing); the moves themselves are
317	behavior-preserving relocations covered by the existing suite staying green.
318	
319	## 10. Documentation & memory obligations (same change, §7)
320	
321	- CLAUDE.md: hook-engine location (`psh/modules.py`, import-back + re-export mechanics),
322	  `add_hook` declaration requirement + fatal conditions, `run_finish` in the phase list,
323	  registry-is-authoritative line on the contract table ("the machine-readable copy in
324	  `psh/modules.py` `CONTRACT` is authoritative; this table is its prose rendering"),
325	  prose that this task obsoletes deleted (report the line-count delta).
326	- `ruff-broad.toml` comment for `script_context.py` removed with its exclude line.
327	- Memory: update `modularization-campaign.md` progress note; new/updated memory for the
328	  engine's new home + declaration requirement.
329	- `LEDGER.md`: the I4 entry with the seven ledger notes flagged above (D-i4-1, D-i4-3,
330	  D-i4-4, D-i4-6, D-i4-7, B2/B4 deferral, ratchet dispositions/corrections).
331	
332	## 11. Acceptance (commands run and output pasted into this file at close — never summarized)
333	
334	Run 2026-07-20 at increment close (HEAD = `1f2a6af`, base `d46f56d`):
335	
336	1. `./run-tests --fast --llm`:
337	
338	```
339	LLM_SUMMARY passed=780 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
340	27 snapshots passed.
341	```
342	
343	(Baseline at I3 close was 761 passed — I4 added 19 tests: run_finish probe + EXPECTED_PHASES,
344	2 declaration fatals, 6 contract-registry tests, 9 DAG-validation/ordering tests, plus the
345	permanent `test_hook_dag.py`, net of the `test_plugin_umich_portal.py` registration rework.)
346	
347	2. `./run-tests --llm` — **live tier ran** (Terminus token present in this environment):
348	
349	```
350	All checks passed!
351	All checks passed!
352	0 errors, 0 warnings, 0 informations
353	LLM_SUMMARY passed=782 failed=0 error=0 skipped=1 xfailed=0 xpassed=0
354	27 snapshots passed.
355	782 passed, 1 skipped in 36.53s
356	```
357	
358	(The 1 skip is `test_db_credentials.py`'s `importorskip("MySQLdb")` on this sqlite-only
359	install — same as I2.)
360	
361	3. `git diff d46f56d -- tests/e2e/__snapshots__/ | wc -l` → `0` (four goldens
362	byte-identical, Invariant 1).
363	
364	4. `uvx ruff check --config ruff-broad.toml psh/modules.py script_context.py` →
365	`All checks passed!`
366	
367	5. `uvx ruff check .` (narrow set, whole tree) → `All checks passed!`
368	
369	6. pyright via the `./run-tests` gate → `0 errors, 0 warnings, 0 informations` (line 3 of
370	the item-2 output above).
371	
372	7. Red-demonstration evidence for conditions 1–5: task reports
373	`.superpowers/sdd/task-3-report.md` (condition 5: two `DID NOT RAISE SystemExit` reds,
374	independently reproduced by the Task 3 reviewer) and `task-5-report.md` (conditions 1–4:
375	`AttributeError` red before `validate_hooks` existed, then per-condition
376	`pytest.raises(<named error>)` green; the Task 5 reviewer re-derived the reds from
377	`git show`). The Task 2 reviewer additionally mutation-tested the run_finish
378	before-artifacts probe (moved the invoke after the writes → `assert [True] == [False]`).
379
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "head -40 /workspace/psh/gateway.py; echo ====CONFIG====; head -30 /workspace/psh/configuration.py; echo ====ROUNDTRIP====; sed -n '1,50p' /workspace/tests/integration/test_db_roundtrip.py",
  "description": "Show gateway/configuration import patterns and roundtrip test head"
}
```

### ↳ Tool result

```
"""The gateway: every Terminus/WP-CLI/Drush subprocess flows through this module.

Increment I2 of the modularization campaign (development/2026-07-17-mod-I2-gateway/SPEC.md).
The eleven Terminus/WP/Drush subprocess-facing wrappers moved here from psh/_legacy.py, which
re-imports them so its call sites and the sc-exposure block keep resolving unchanged.  This is
the single seam through which the future Pantheon-API transport swap becomes a one-module change
(CAMPAIGN.md D1).

The in-process monkeypatch point for anything routed through the wrappers is
`psh.gateway.run_terminus`: terminus/wp/drush resolve run_terminus in THIS module's namespace, so
patching the remnant's imported binding would not intercept them (SPEC §Seams, PD#14).
"""
import html
import json
import re
import subprocess
import time
from typing import Any, NamedTuple

from rich.markup import escape

import script_context as sc


class GatewayResult(NamedTuple):
    result: Any
    errors: str
    fatal: bool


def run_terminus(command: list, input_data=None) -> GatewayResult:  # noqa: C901, PLR0912 -- moved verbatim; run_terminus's stderr/markup escaping is under-tested and refactoring is a review activity, not part of a behavior-preserving move (SPEC §Broad-ruff findings)

    command = ["terminus", "--no-ansi", "--no-interaction", *command]
    commandline = " ".join(
        [
            (("'" + arg.replace("'", "\\'") + "'") if len(arg.split()) > 1 else arg)
            for arg in command
        ]
    )

====CONFIG====
"""Configuration engine: <{ ... }> substitution (two-pass, with DEFER), section gating, news
loading, and the umich/cloudflare feature flags.  Moved from psh/_legacy.py at campaign I3; the
remnant re-imports these names so its call sites resolve unchanged (CAMPAIGN.md §3.1)."""
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import tomllib
from rich.markup import escape
from rich.pretty import pprint

import script_context as sc


def config_substitution(expr: str, path) -> str:  # noqa: C901, PLR0912, PLR0915 -- best-match scorer moved behavior-preserving; restructuring is a review activity, not part of a move (I2 run_terminus precedent). Covered by tests/unit/test_config_substitution.py.
    argv = list(shlex.shlex(expr, posix=True))
    argc = len(argv)
    if sc.options.verbose > 1:
        sc.debug(f"\nconfig_substitution: {path}")
        pprint(argv)
    if argc == 0:
        return ""

    # Figure out which substitution matches the expression most closely:
    best_match: dict[str, Any] | None = None
    best_match_score = 0
    best_match_args_map = {}
    for match in sc.substitutions:
====ROUNDTRIP====
"""Integration tests for the SQLAlchemy models against a temp sqlite DB (test-suite SPEC §7.3).

Covers the upsert/merge semantics main() relies on and the unique key that protects a
(site_id, date/month) from duplicating.
"""
import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from conftest import E2E_SITE_ID

pytestmark = pytest.mark.integration

DAY = datetime.date(2026, 3, 15)
MONTH = datetime.date(2026, 3, 1)


def _traffic(temp_db, visits):
    return temp_db.PantheonTraffic(
        site_id=E2E_SITE_ID,
        traffic_date=DAY,
        site_plan="Performance Small",
        visits=visits,
        pages_served=visits * 3,
        cache_hits=visits * 2,
    )


def test_traffic_merge_is_idempotent_upsert(temp_db):
    session = temp_db.session()
    session.merge(_traffic(temp_db, 1000))
    session.commit()
    session.merge(_traffic(temp_db, 2000))  # same PK (site_id, traffic_date) -> update, not insert
    session.commit()
    rows = session.query(temp_db.PantheonTraffic).all()
    assert len(rows) == 1
    assert rows[0].visits == 2000
    session.close()


def test_traffic_duplicate_insert_violates_unique_key(temp_db):
    session = temp_db.session()
    session.add(_traffic(temp_db, 10))
    session.commit()
    session.add(_traffic(temp_db, 20))  # duplicate (site_id, traffic_date)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "S=/tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad && mkdir -p $S && {\ncat <<'EOF'\n\"\"\"Database layer: ORM models, detached row types, resilience (db_retry), and engine args.\"\"\"\nimport datetime\nimport sys\nimport time\nfrom typing import NamedTuple\n\nfrom rich.markup import escape\nfrom sqlalchemy import (\n    Boolean,\n    Date,\n    Integer,\n    PrimaryKeyConstraint,\n    String,\n    UniqueConstraint,\n    insert,\n)\nfrom sqlalchemy.dialects.sqlite import insert as sqlite_insert\nfrom sqlalchemy.exc import DBAPIError, OperationalError\nfrom sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column\nfrom sqlalchemy.types import CHAR\n\nimport script_context as sc\n\nEOF\nsed -n '93,167p' psh/_legacy.py\necho\nsed -n '821,827p' psh/_legacy.py\necho\nsed -n '841,1061p' psh/_legacy.py | sed -e 's/record_db_reconnect(db_reconnect_failures_by_site/record_db_reconnect(sc.db_reconnect_failures_by_site/' -e 's/record_db_reconnect(db_reconnects_by_site/record_db_reconnect(sc.db_reconnects_by_site/'\necho\nsed -n '1079,1109p' psh/_legacy.py\n} > $S/db_scratch.py && uvx ruff check --config ruff-broad.toml --force-exclude $S/db_scratch.py 2>&1 | tail -40",
  "description": "Assemble scratch psh/db.py and run broad ruff on it"
}
```

### ↳ Tool result

```
help: Organize imports

ERA001 Found commented-out code
  --> /tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad/db_scratch.py:31:5
   |
29 |     __tablename__ = "pantheon_traffic"
30 |
31 |     # id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
   |     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
32 |     site_id: Mapped[str] = mapped_column(CHAR(36))
33 |     traffic_date: Mapped[datetime.date] = mapped_column(Date)
   |
help: Remove commented-out code

RUF013 PEP 484 prohibits implicit `Optional`
   --> /tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad/db_scratch.py:132:49
    |
132 | def db_retry(session, unit, *, what: str, site: str = None):
    |                                                 ^^^
133 |     """Run `unit()`; on a database failure, roll back and re-run it exactly once.
    |
help: Convert to `T | None`

DTZ007 Naive datetime constructed using `datetime.datetime.strptime()` without %z
   --> /tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad/db_scratch.py:213:24
    |
211 |       for e in metrics["timeseries"]:
212 |           entry = metrics["timeseries"][e]
213 |           traffic_date = datetime.datetime.strptime(
    |  ________________________^
214 | |             entry["datetime"], "%Y-%m-%dT%H:%M:%S"
215 | |         ).date()
    | |_________^
216 |           if traffic_date == end_date:
217 |               continue  # skip today's partial data
    |
help: Call `.replace(tzinfo=<timezone>)` or `.astimezone()` to convert to an aware datetime

Found 5 errors.
[*] 1 fixable with the `--fix` option (1 hidden fix can be enabled with the `--unsafe-fixes` option).
```

## Assistant

Ruff found 5 — the tail shows three; let me see the full list:

### ⚙ Tool call: `Bash`

```json
{
  "command": "S=/tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad && uvx ruff check --config ruff-broad.toml --force-exclude $S/db_scratch.py 2>&1 | grep -E '^[A-Z]+[0-9]+|-->' ",
  "description": "List all broad-ruff finding codes on the scratch file"
}
```

### ↳ Tool result

```
INP001 File `/tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad/db_scratch.py` is part of an implicit namespace package. Add an `__init__.py`.
--> /tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad/db_scratch.py:1:1
I001 [*] Import block is un-sorted or un-formatted
  --> /tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad/db_scratch.py:2:1
ERA001 Found commented-out code
  --> /tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad/db_scratch.py:31:5
RUF013 PEP 484 prohibits implicit `Optional`
   --> /tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad/db_scratch.py:132:49
DTZ007 Naive datetime constructed using `datetime.datetime.strptime()` without %z
   --> /tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad/db_scratch.py:213:24
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "grep -n 'pyright' /workspace/run-tests | head -5; S=/tmp/claude-501/-workspace/619f4b9f-4c42-4655-b464-a1c5448605c3/scratchpad; cp $S/db_scratch.py /workspace/psh/db.py && uvx pyright psh 2>&1 | tail -15; rm /workspace/psh/db.py; ls /workspace/psh/",
  "description": "Measure pyright on a temporary psh/db.py, then remove it"
}
```

### ↳ Tool result

```
36:def pyright_argv():
37:    """How to invoke pyright here, or None.  Same fallback pattern as ruff_argv()."""
38:    if shutil.which("pyright"):
39:        return ["pyright"]
41:        return ["uvx", "pyright"]
  /workspace/psh/db.py:19:6 - error: Import "sqlalchemy.orm" could not be resolved (reportMissingImports)
  /workspace/psh/db.py:20:6 - error: Import "sqlalchemy.types" could not be resolved (reportMissingImports)
  /workspace/psh/db.py:132:55 - error: Expression of type "None" cannot be assigned to parameter of type "str"
    "None" is not assignable to "str" (reportArgumentType)
  /workspace/psh/db.py:168:36 - error: "db_reconnect_failures_by_site" is not a known attribute of module "script_context" (reportAttributeAccessIssue)
  /workspace/psh/db.py:184:40 - error: "db_reconnect_failures_by_site" is not a known attribute of module "script_context" (reportAttributeAccessIssue)
  /workspace/psh/db.py:186:36 - error: "db_reconnect_failures_by_site" is not a known attribute of module "script_context" (reportAttributeAccessIssue)
  /workspace/psh/db.py:192:32 - error: "db_reconnects_by_site" is not a known attribute of module "script_context" (reportAttributeAccessIssue)
  /workspace/psh/db.py:330:40 - error: Tuple expression not allowed in type expression
    Use tuple[T1, ..., Tn] to indicate a tuple type or T1 | T2 to indicate a union type (reportInvalidTypeForm)
/workspace/psh/gateway.py
  /workspace/psh/gateway.py:20:6 - error: Import "rich.markup" could not be resolved (reportMissingImports)
/workspace/psh/modules.py
  /workspace/psh/modules.py:28:6 - error: Import "rich.markup" could not be resolved (reportMissingImports)
16 errors, 0 warnings, 0 informations
__init__.py
__pycache__
_legacy.py
cli.py
configuration.py
gateway.py
modules.py
notice.py
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "grep -n 'def temp_db' -A 25 /workspace/tests/conftest.py; echo ==house==; grep -n 'db_engine_args\\|db_reconnect' /workspace/tests/unit/test_house_rules.py; echo ==namedtuple==; grep -n 'NamedTuple' /workspace/psh/_legacy.py; echo ==sqlalchemy-orphan-check==; grep -n 'OperationalError\\|DBAPIError\\|sqlite_insert\\|DeclarativeBase\\|mapped_column\\|Mapped\\[\\|CHAR\\|PrimaryKeyConstraint\\|UniqueConstraint\\|Boolean\\|Date\\b\\|Integer\\|String(\\|insert(' /workspace/psh/_legacy.py | awk -F: '$1 > 1110 || $1 < 93' | head -30",
  "description": "Check temp_db fixture, house rules, and post-move import users in _legacy"
}
```

### ↳ Tool result

```
167:def temp_db(psh, tmp_path):
168-    """A temporary sqlite DB with the program's schema created; no repo DB is touched."""
169-    db = TempDB(psh, tmp_path / "test.db")
170-    yield db
171-    db.engine.dispose()
172-
173-
174-# ── Isolated working directory for subprocess (e2e) runs ────────────────────────────
175-def make_workdir(base):
176-    """Wire a temp CWD with the repo's static assets, an empty news/ dir, and a neutral
177-    fqdns.json, so a subprocess run of the program writes only under this dir."""
178-    work = Path(base) / "work"
179-    work.mkdir()
180-    for asset in _CWD_ASSETS:
181-        src = REPO_ROOT / asset
182-        if not src.exists():
183-            raise FixtureNotFoundError(f"expected repo asset missing: {src}")
184-        (work / asset).symlink_to(src)
185-    (work / "news").mkdir()
186-    # A neutral fqdns.json.  With the offline configs all Cloudflare-*disabled*, the cloudflare
187-    # plugin's fqdns setup hook never registers and the program never reads this file -- so it is
188-    # effectively vestigial today.  Kept as belt-and-suspenders: were a Cloudflare-enabled
189-    # subprocess config ever added, a fresh empty file makes decide_fqdns_update() return "skip"
190-    # (exists + fresh + single-site), so the run stays offline instead of hitting the real API.
191-    (work / "fqdns.json").write_text("{}\n")
192-    return work
==house==
160:# standalone)."  sc.db_engine_args is exposed in the same block (CLAUDE.md § Database).
163:                   "db_engine_args", "Notice", "Severity")
177:    above).  Red was demonstrated by temporarily commenting out `sc.db_engine_args =
178:    db_engine_args` in psh/_legacy.py, which made this test fail naming db_engine_args.
==namedtuple==
34:from typing import NamedTuple
137:class TrafficRow(NamedTuple):
154:class OverageProtectionRow(NamedTuple):
==sqlalchemy-orphan-check==
50:    Boolean,
51:    Date,
52:    Integer,
53:    PrimaryKeyConstraint,
55:    UniqueConstraint,
58:from sqlalchemy.dialects.sqlite import insert as sqlite_insert
59:from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
60:from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
61:from sqlalchemy.types import CHAR
1195:    # appends to a DBAPIError -- as a style tag and DELETES it, and an unmatched `[/x]` raises
1409:    A DBAPIError is a database abort only when it is one db_retry() would have retried
1411:    other non-retryable DBAPIError is a data bug and belongs on the fatal path, with its
1415:        isinstance(error, DBAPIError) and db_retryable(error)
1481:    # escape() every interpolated exception.  A SQLAlchemy DBAPIError's message ends with
3153:<td><div class="rt-data-header rt-plan">Date</div><div class="rt-data rt-plan">{update_release_date}</div></td>
3178:<thead><th class="rt-plan">Date</th><th class="rt-plan">Description</th><th class="rt-plan">Author</th></thead>
3216:<thead><th class="rt-plan">Date</th><th class="rt-plan">Description</th><th class="rt-plan">Author</th></thead>
3256:<thead><th class="rt-plan">Date</th><th class="rt-plan">Description</th><th class="rt-plan">Author</th></thead>
4007:                sorted_notices.insert(
4027:                sorted_notices.insert(
4138:            msg["Date"] = datetime.datetime.now(datetime.UTC).strftime("%a, %d %b %Y %T %z")
4183:                fields.insert(1, contacts)
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "mkdir -p /workspace/development/2026-07-20-mod-I5-db",
  "description": "Create the I5 dev folder"
}
```

### ↳ Tool result

```
(Bash completed with no output)
```

### ⚙ Tool call: `Write`

```json
{
  "file_path": "/workspace/development/2026-07-20-mod-I5-db/SPEC.md",
  "content": "# SPEC — Increment I5: `psh/db.py` (models, row types, resilience layer, engine args)\n\n**Campaign:** `development/2026-07-17-modularization-campaign/` — this spec cites\n`CAMPAIGN.md` by section number and re-derives nothing (CAMPAIGN.md preamble). Scope\nauthority: §11 row I5. Module map: §3.1 (`psh/db.py` row). Parallel-ready constraint:\n§3.4. Per-increment obligations: §7. Behavior bar: §8. Invariants: §9 (Invariant 5 is\nthis increment's center of gravity). Ratchet: §13.\n\n**Read first (per §7):** `CAMPAIGN.md`, `LEDGER.md` (through I4), `CLAUDE.md`\n(§ Database in full), `BLOCKMAP.md` (DB session touches: B10, B11, B23, B24, B26, B46,\nB47, B59, B60 — none of these *blocks* move; I5 moves module-level defs only),\n`prompts/directives.md`, `prompts/implementation-standards.md`,\n`development/2026-07-13-db-connection-resilience/SPEC.md` (the design the moved code\nimplements — its section numbers are cited throughout the moved docstrings and MUST keep\nresolving).\n\n## Glossary (delta over CAMPAIGN.md's)\n\n- **Counters** — the two run-scoped reconnect-attribution dicts,\n  `db_reconnects_by_site` (healed) and `db_reconnect_failures_by_site` (failed).\n- **Remnant readers** — `finish_run()`/`abort_run()` (staying in `psh/_legacy.py` until\n  I13), which read the counters at `_legacy.py:1210–1211` and `1296–1297`.\n- **Move set** — the defs Deliverable A enumerates; \"verbatim\" means byte-identical\n  bodies except the edits Deliverable A names per item.\n\n## 1. Scope (exhaustive) and non-scope\n\nIn scope (§11 row I5 — its \"95–178\" / \"1285–1575\" are a47418c line ranges, drifted per\nBLOCKMAP preamble; current-line equivalents below):\n\n1. **Move** into a new `psh/db.py` (gated from birth): `Base`, `PantheonTraffic`,\n   `PantheonOverageProtection`, `TrafficRow`, `OverageProtectionRow`\n   (`psh/_legacy.py:93–167`), `DatabaseUnavailableError` (821–826),\n   `record_db_reconnect` (841–844), `db_retryable` (847–862), `db_retry` (865–926),\n   `update_traffic_rows` (929–961), `insert_traffic_rows` (964–980),\n   `load_traffic_rows` (983–1021), `load_overage_protection_window` (1024–1061),\n   `db_engine_args` (1079–1109). This is exactly §3.1's `psh/db.py` row.\n2. **Move the counters to `script_context.py`** (D-i5-1) with their contract comments\n   (829–838) verbatim; wire `reset_sc` isolation for them.\n3. **Re-import** every moved name into `psh/_legacy.py` (I2/I3/I4 pattern) so its call\n   sites, the tests' `psh.<name>` references, and the `sc.db_engine_args` exposure\n   (`_legacy.py:1155`) resolve unchanged; repoint the remnant readers' four counter\n   reads to `sc.`; remove only the imports the move orphans (verified, not assumed —\n   LEDGER I3 precedent; pre-verified list in Deliverable C).\n4. **Repoint the DB test suites' counter seams to `sc`** (D-i5-3) — suites otherwise\n   intact (no assertion weakened, no test dropped; §11's \"relocated intact\" reading in\n   D-i5-3).\n5. **Ratchet** (§13): `psh/db.py` clean under broad ruff + pyright standard from birth;\n   measured findings + dispositions in §5.\n6. Docs/CLAUDE.md/memory/ledger updates (§7 obligations 6–8).\n\nNOT in scope: the resume helpers `ResumeSiteNotFoundError` (817–818),\n`sites_from_resume_point` (1064–1076), `merge_prior_results` (1112–1141) — §11 row I5\nnames them as staying for I13, even though they sit inside the moved region's line\nrange. B10/B11 (`db.create_engine`/sessionmaker/`create_all` in `main()`,\n`_legacy.py:1997–2011`) stay — §3.1 assigns no module for them and §11 row I5 lists\ndefs only; they move with `main()`'s final form (I13; **ledger note**).\n`build_traffic_table_rows`, `get_old_metrics` and the traffic flow → I6 (§3.1\n`psh/traffic.py`). `finish_run`/`abort_run`/`abort_reason` → I13. No test-file\nun-grandfathering (`tests/` stays wholesale in `ruff-broad.toml` `extend-exclude` —\nI2–I4 precedent; the repoints in Deliverable D don't constitute the \"cleaned alongside\ntheir code\" pass). No golden/fixture changes (Invariants 1, 10). No config keys, no\ncontract keys, no new `sc` façade *documentation* (the counters are shared state like\n`sc.hooks`, not check-facing API — they do NOT join the documented-façade-names test).\n\n## 2. Architecture decisions (each with why; deviations flagged for the ledger)\n\n### D-i5-1: the counters move to `script_context.py`, accessed as `sc.` attributes\n\n§3.1's `psh/db.py` row lists `record_db_reconnect` (the function) but names the two\ndicts nowhere; §3.4 bars new module-level mutable state in `psh/` (the rule that kept\n`sc.hooks` in `script_context.py` — LEDGER I4 deviation 1); §6 already schedules the\n\"reconnect counters\" into I13's `RunState`, so this is their scheduled interim home,\nnot a new permanent surface. The deciding defect class: the writer (`db_retry`, moving)\nand the remnant readers (`finish_run`/`abort_run`, staying until I13) would otherwise\nhold **separately rebindable bindings of the same name** across two modules — ~40\nexisting `monkeypatch.setattr(psh, \"db_reconnects_by_site\", {})` sites rebind, so any\ntwo-namespace aliasing scheme desyncs writer from readers the first time one side is\nrebound and not the other (the I2 `psh.gateway.run_terminus` seam lesson, PD#14). One\nowning namespace, attribute-accessed at call time by both sides, dissolves it:\n`script_context.py` defines `db_reconnects_by_site: dict[str, int] = {}` and\n`db_reconnect_failures_by_site: dict[str, int] = {}` (their 829–838 contract comments\nmoved verbatim); `db_retry` writes `sc.db_reconnect_failures_by_site` /\n`sc.db_reconnects_by_site`; the remnant readers read `sc.`. The pyright probe confirms\n`sc.`-access type-checks only with these module-level definitions (measured 2026-07-20).\n**Ledger note, not an amendment.**\n\n### D-i5-2: `psh/db.py` imports `script_context` at module level\n\n`import script_context as sc` at top of module — the `psh/gateway.py`/\n`psh/configuration.py` precedent. No cycle: `script_context` imports only\n`psh.modules`/`psh.notice` (I4's call-time-import constraint was specific to those two\nbeing imported *by* `script_context`; `psh.db` is not). Needed for `sc.console`,\n`sc.config` (`insert_traffic_rows`' backend switch), and the counters.\n\n### D-i5-3: test suites stay in place; only the counter seam repoints\n\n§11's \"DB test suites relocated intact\" is read as: the moved code's suites keep their\nfull coverage; their *targets* relocate, the files do not (they already live in\ntier-named homes: `tests/unit/test_db_resilience.py`,\n`tests/integration/test_db_roundtrip.py`, `tests/integration/test_db_credentials.py`).\n\"Intact\" = no assertion weakened, no test dropped, collected count preserved. The ONLY\nmandatory edit class is the counter seam: every\n`monkeypatch.setattr(psh, \"db_reconnect[s|_failures]_by_site\", …)` and every\n`psh.db_reconnect*` assertion retargets the `script_context` module (the namespace\n`db_retry` actually reads — patching the old `psh` binding would be the silent\nnon-intercepting patch of the I2 lesson, PD#14). Affected files (grep-verified\n2026-07-20): `test_db_resilience.py`, `test_db_credentials.py`, `test_abort_run.py`,\n`test_finish_run.py`, `test_traffic_table_rows.py`. Everything else keeps resolving\nthrough the `psh` fixture via the re-imports: `psh.db_retry`, `psh.db_engine_args`,\n`psh.TrafficRow`, `psh.PantheonTraffic`, … and `monkeypatch.setattr(psh.time, \"sleep\",\n…)` still intercepts (`time` is a shared module object — CLAUDE.md § mock seams).\n`tests/shims/pyshim/dbshim.py` patches `sqlalchemy.orm.Session.get` — location-independent,\nuntouched. `temp_db`/`TempDB` (conftest) resolves models via the `psh` fixture —\nimplementer verifies it needs no edit.\n\n### D-i5-4: `reset_sc` owns counter isolation\n\nThe counters join `_SC_ATTRS` and get clean-slate assignments (`= {}`) in `reset_sc` —\nthey are exactly the \"process-global mutable state\" that fixture exists to restore.\nThe per-test `monkeypatch` zeroings stay (repointed): they are now redundant but\nharmless, and deleting ~40 of them is churn \"intact\" forbids. (I13 collapses all of\nthis into `RunState`.)\n\n## 3. Deliverable A — `psh/db.py` (new file; gated from birth)\n\nModule docstring: names the module's role (every DB touch this program makes), cites\n`development/2026-07-13-db-connection-resilience/SPEC.md` as the governing design and\nCAMPAIGN.md I5 as the move, and carries the counter-location note (state in\n`script_context`, D-i5-1) — the flow is non-local, so the note is REQUIRED\n(implementation-standards § Directives 7).\n\n| Item | From (`_legacy.py`) | Edits allowed (exhaustive — else verbatim) |\n|---|---|---|\n| `Base` | 93–94 | — |\n| `PantheonTraffic` | 97–117 | delete the ERA001 commented-out `# id:` line (100) — dead schema remnant, §5 |\n| `PantheonOverageProtection` | 120–134 | — |\n| `TrafficRow` | 137–151 | — |\n| `OverageProtectionRow` | 154–166 | — |\n| `DatabaseUnavailableError` | 821–826 | — |\n| `record_db_reconnect` | 841–844 | — |\n| `db_retryable` | 847–862 | — |\n| `db_retry` | 865–926 | `site: str = None` → `site: str | None = None` (§5 RUF013/pyright); the four `record_db_reconnect(db_reconnect…` calls gain the `sc.` prefix (D-i5-1) |\n| `update_traffic_rows` | 929–961 | `# noqa: DTZ007` + inline reason on the `strptime` (§5) |\n| `insert_traffic_rows` | 964–980 | — (`sc.config` read already spelled `sc.`) |\n| `load_traffic_rows` | 983–1021 | — |\n| `load_overage_protection_window` | 1024–1061 | — |\n| `db_engine_args` | 1079–1109 | `-> (str, dict)` → `-> tuple[str, dict]` (§6 house-style replacement; pyright reportInvalidTypeForm) |\n\nImports (measured against the bodies): `datetime`, `sys`, `time`; `typing.NamedTuple`;\n`rich.markup.escape`; `sqlalchemy` (`Boolean`, `Date`, `Integer`,\n`PrimaryKeyConstraint`, `String`, `UniqueConstraint`, `insert`),\n`sqlalchemy.dialects.sqlite.insert as sqlite_insert`, `sqlalchemy.exc` (`DBAPIError`,\n`OperationalError`), `sqlalchemy.orm` (`DeclarativeBase`, `Mapped`, `mapped_column`),\n`sqlalchemy.types.CHAR`; `import script_context as sc` (D-i5-2).\n\nDocstrings move verbatim — every SPEC-section citation in them\n(`SPEC 2.2/3.3.1/3.3.2/3.3.3/3.6`, the `development/2026-07-13-…/SPEC.md 3.1, 3.3.2`\npointer, CLAUDE.md references) was verified still-resolving on 2026-07-20 (§7\nobligation 4). The \"MUST NOT be removed\" commit comments in the two loaders are part of\nInvariant 5 and move byte-for-byte.\n\n## 4. Deliverables B–D — the state move, the remnant, the tests\n\n**B — `script_context.py`** (un-grandfathered since I4 — edits must keep the broad gate\ngreen): add the two counter definitions with types (`dict[str, int]`) and the 829–838\ncomments verbatim, placed with the other mutable run state. No other change.\n\n**C — `psh/_legacy.py`:** delete the move set + counters; add\n`from psh.db import (…every moved name…)` in the import block (I2 pattern — all names,\nso `psh.<name>` test references keep resolving); repoint the four remnant-reader\ncounter reads (1210, 1211, 1296, 1297) to `sc.`; the `sc.db_engine_args = db_engine_args`\nexposure line (1155) stays — it resolves via the re-import, and the façade house-rule\ntest pins it (Invariant 9). Orphaned-import sweep, each removal verified by grep\n(pre-verified 2026-07-20, implementer re-verifies): orphaned — the seven-name\n`from sqlalchemy import (…)` block, `sqlite_insert`, `OperationalError`,\n`DeclarativeBase`/`Mapped`/`mapped_column`, `CHAR`, `NamedTuple`; NOT orphaned —\n`DBAPIError` (`abort_reason` 1409–1415), `SQLAlchemyError` (1199/1205/1463),\n`sqlalchemy as db` (B10, 1997/2007), `time`, `escape`. `db_retryable` is still called\nby `abort_reason` → covered by the re-import.\n\n**D — tests:** the counter-seam repoints of D-i5-3 (each file gains\n`import script_context as sc` if it lacks one; `monkeypatch.setattr(sc, …)` +\n`sc.db_reconnect…` assertions), plus conftest's `_SC_ATTRS`/`reset_sc` additions\n(D-i5-4). Nothing else — no new tests are owed: this increment adds no behavior, and\n\"behavior-preserving relocations [are] covered by the existing suite staying green\"\n(I4 SPEC §9 precedent, per implementation-standards § Test discipline's carve-out\nlogic — the moved code's seams are already the tested seams:\n`test_load_traffic_rows_releases_the_connection`, the `db_retry` contract suite, the\nroundtrip suite, `test_abort_e2e.py` through the real `main()`).\n\n## 5. Ratchet (§13) — measured findings and dispositions\n\nBroad ruff was run 2026-07-20 on a scratch assembly of the exact move (verbatim bodies\n+ final imports); pyright standard on the same content at `psh/db.py`. Findings\n(exhaustive — anything new at implementation time is disposed inline and\nledger-recorded, I3 precedent):\n\n| Finding | Where | Disposition |\n|---|---|---|\n| ERA001 commented-out code | `# id: Mapped[int]…` in `PantheonTraffic` | **delete the line** — a considered-and-rejected surrogate key, documented by the composite `PrimaryKeyConstraint` right below it; ratchet D2 (\"cleaned exactly once, as it moves\") |\n| RUF013 implicit Optional (+ pyright reportArgumentType) | `db_retry(…, site: str = None)` | `site: str | None = None` — §6's real-annotation replacement, behavior-preserving |\n| DTZ007 naive strptime | `update_traffic_rows` | `# noqa: DTZ007` + reason: Pantheon's `env:metrics` timestamps are naive date markers, only `.date()` is taken; attaching a tzinfo risks an off-by-one-day shift — a behavior change a move may not make |\n| pyright reportInvalidTypeForm | `db_engine_args -> (str, dict)` | `-> tuple[str, dict]` (§6 mandates this replacement per moved module) |\n| pyright reportAttributeAccessIssue on `sc.db_reconnect…` | `db_retry` | resolved by Deliverable B's typed module-level definitions (measured: errors vanish once defined) |\n\nNo `ruff-broad.toml` `ignore` additions (would be a §13 amendment). No\n`extend-exclude` deletion (the code lands in a fresh gated file — I2/I3 precedent;\n`_legacy.py` stays grandfathered).\n\n## 6. Behavior bar & invariants applied (§8/§9)\n\n- Four goldens byte-identical (Invariant 1): the move renders nothing differently —\n  same objects, same call graph, re-imports alias the same functions.\n- Invariant 5 holds by construction and by its named guard:\n  `test_load_traffic_rows_releases_the_connection` moves nothing and must stay green\n  unweakened; `db_retryable`'s predicate and `db_retry`'s unit-granularity move\n  byte-identically.\n- Invariant 4: `abort_reason`/`finish_run`/`abort_run` logic untouched — only their\n  counter reads re-spell to `sc.` (same dict objects at call time).\n- Artifact structure (§8): `-run.json`'s `reconnects_by_site`/\n  `reconnect_failures_by_site` blocks read the same dicts through the new spelling.\n- Invariant 9: no `sc` name removed; `sc.db_engine_args` keeps resolving (façade test).\n  New `sc` attributes (the counters) are additions — sanctioned by §3.5.\n- Invariant 7: no interlock change; no new subprocess/network paths (§ directives 6).\n- Exit codes/resume semantics/config keys: untouched.\n\n## 7. Task shape (for the plan)\n\nTask 1 — the move (Deliverables A–D in one atomic commit: the code, the state, the\nre-imports, the test repoints — partial application cannot be green). Gates: full\n`--fast` suite green with collected count unchanged (782 passed / 1 skipped baseline at\nI4 close; this increment adds/removes no tests), goldens diff empty, broad ruff clean\non `psh/db.py` + `script_context.py`, narrow ruff whole-tree clean, pyright 0 errors.\nTask 2 — docs/memory/ledger (CLAUDE.md § Database rewrite for the new home + seam\nnote; the models-\"near the top of the script\" line; memory update; LEDGER I5 entry;\nthis SPEC's acceptance section filled).\n\n## 8. Documentation & memory obligations (same change, §7)\n\n- CLAUDE.md: § Database gains the `psh/db.py` home (models, row types, resilience\n  layer, `db_engine_args` — re-imported by `_legacy`, same import-back pattern);\n  counter location + `sc.` access noted; the \"class defs near the top of the script\"\n  sentence corrected; test-seam guidance (counters patched at `script_context`, not\n  `psh`). Delete prose the move obsoletes; report the line-count delta\n  (implementation-standards § Definition of Done).\n- Memory: update `modularization-campaign.md` progress; extend `db-idle-connection-reaped.md`\n  (or add) with the new home + the counter-seam patching fact.\n- `LEDGER.md`: I5 entry with ledger notes D-i5-1 (counters), B10/B11 stay (I13), the\n  \"relocated intact\" reading (D-i5-3), ratchet dispositions, any finding-table\n  corrections.\n\n## 9. Acceptance (commands run and output pasted at close — never summarized)\n\n1. `./run-tests --fast --llm` — expect `passed=782 failed=0 error=0 skipped=1` (no\n   test count change), 27 snapshots.\n2. `./run-tests --llm` (live tier if credentials present; else `--fast` + ledger note).\n3. `git diff <base> -- tests/e2e/__snapshots__/ | wc -l` → 0 (Invariant 1).\n4. `uvx ruff check --config ruff-broad.toml psh/db.py script_context.py` → clean.\n5. `uvx ruff check .` (narrow set) → clean.\n6. pyright gate (via `./run-tests`) → 0 errors.\n"
}
```

### ↳ Tool result

```
File created successfully at: /workspace/development/2026-07-20-mod-I5-db/SPEC.md (file state is current in your context — no need to Read it back)
```

### ⚙ Tool call: `Skill`

```json
{
  "skill": "superpowers:writing-plans"
}
```

### ↳ Tool result

```
Launching skill: superpowers:writing-plans
```

## User

Base directory for this skill: /home/node/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/writing-plans

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Context:** If working in an isolated worktree, it should have been created via the `superpowers:using-git-worktrees` skill at execution time.

**Save plans to:** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`
- (User preferences for plan location override this default)

## Scope Check

If the spec covers multiple independent subsystems, it should have been broken into sub-project specs during brainstorming. If it wasn't, suggest breaking this into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## File Structure

Before defining tasks, map out which files will be created or modified and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file should have one clear responsibility.
- You reason best about code you can hold in context at once, and your edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together should live together. Split by responsibility, not by technical layer.
- In existing codebases, follow established patterns. If the codebase uses large files, don't unilaterally restructure - but if a file you're modifying has grown unwieldy, including a split in the plan is reasonable.

This structure informs the task decomposition. Each task should produce self-contained changes that make sense independently.

## Task Right-Sizing

A task is the smallest unit that carries its own test cycle and is worth a
fresh reviewer's gate. When drawing task boundaries: fold setup,
configuration, scaffolding, and documentation steps into the task whose
deliverable needs them; split only where a reviewer could meaningfully
reject one task while approving its neighbor. Each task ends with an
independently testable deliverable.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

## Global Constraints

[The spec's project-wide requirements — version floors, dependency limits,
naming and copy rules, platform requirements — one line each, with exact
values copied verbatim from the spec. Every task's requirements implicitly
include this section.]

---
```

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Interfaces:**
- Consumes: [what this task uses from earlier tasks — exact signatures]
- Produces: [what later tasks rely on — exact function names, parameter
  and return types. A task's implementer sees only their own task; this
  block is how they learn the names and types neighboring tasks use.]

- [ ] **Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

- [ ] **Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## No Placeholders

Every step must contain the actual content an engineer needs. These are **plan failures** — never write them:
- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" (without actual test code)
- "Similar to Task N" (repeat the code — the engineer may be reading tasks out of order)
- Steps that describe what to do without showing how (code blocks required for code steps)
- References to types, functions, or methods not defined in any task

## Remember
- Exact file paths always
- Complete code in every step — if a step changes code, show the code
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits

## Self-Review

After writing the complete plan, look at the spec with fresh eyes and check the plan against it. This is a checklist you run yourself — not a subagent dispatch.

**1. Spec coverage:** Skim each section/requirement in the spec. Can you point to a task that implements it? List any gaps.

**2. Placeholder scan:** Search your plan for red flags — any of the patterns from the "No Placeholders" section above. Fix them.

**3. Type consistency:** Do the types, method signatures, and property names you used in later tasks match what you defined in earlier tasks? A function called `clearLayers()` in Task 3 but `clearFullLayers()` in Task 7 is a bug.

If you find issues, fix them inline. No need to re-review — just fix and move on. If you find a spec requirement with no task, add the task.

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/superpowers/plans/<filename>.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?"**

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
- Fresh subagent per task + two-stage review

**If Inline Execution chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:executing-plans
- Batch execution with checkpoints for review

### ⚙ Tool call: `Bash`

```json
{
  "command": "ls /workspace/development/2026-07-20-mod-I4-hooks-dag/ /workspace/development/2026-07-17-mod-I2-gateway/; head -60 /workspace/development/2026-07-20-mod-I4-hooks-dag/PLAN.md 2>/dev/null",
  "description": "Check prior increments' dev-folder plan naming and shape"
}
```

### ↳ Tool result

```
/workspace/development/2026-07-17-mod-I2-gateway/:
PLAN.md
SPEC.md
analytics.md
statistics.md
transcript.md
transcript.raw.md
usage.raw.txt

/workspace/development/2026-07-20-mod-I4-hooks-dag/:
PLAN.md
SPEC.md
analytics.md
statistics.md
transcript.md
transcript.raw.md
usage.raw.txt
# I4 — Hook engine, DAG, contract registry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch
> every code-touching task as `psh-implementer`, every review as `psh-reviewer`; TDD via
> `mattpocock-skills:tdd` (NOT superpowers TDD). The authoritative design is `SPEC.md` in this
> folder — read it in full; this plan is the step sequence, the SPEC carries rationale,
> decisions (D-i4-1…7), and invariants.

**Goal:** Move `find_modules` + the hook engine into a new gated `psh/modules.py`, add the
`run_finish` phase, require `consumes`/`produces` on every hook, validate the per-phase hook
DAG fatally at startup, and ship the machine-readable contract registry — four e2e goldens
byte-identical throughout.

**Architecture:** Import-back move (I2/I3 precedent). Engine *functions* move; the mutable
`sc.hooks` dict STAYS in `script_context.py` (SPEC D-i4-1). `script_context.py` re-exports
`PHASES`/`add_hook`/`invoke_hooks` via a module-level from-import (I3 Notice precedent);
`psh/modules.py` therefore must NOT import `script_context` at module level — engine functions
use a function-level `import script_context as sc` (SPEC D-i4-2). The DAG is edgeless today
(no hook produces), so invoke order is observably unchanged.

**Tech Stack:** Python 3.12+, ruff (`ruff-broad.toml` `select=ALL`), pyright (standard),
pytest, syrupy.

## Global Constraints

- **Four e2e goldens byte-identical** (Invariant 1). `--update-goldens` FORBIDDEN. Verify
  `git diff d46f56d HEAD -- tests/e2e/__snapshots__/` is empty at each task end.
- **`psh/modules.py` passes the full gate from birth**: `uvx ruff check --config
  ruff-broad.toml psh/modules.py` → "All checks passed!"; pyright standard → 0 errors.
- **Run pyright via `./run-tests`, NOT `uv run pyright`** (uv.lock churn; `git checkout --
  uv.lock` if it shows modified).
- **No `sc` name removed** (Invariant 9): `sc.PHASES`, `sc.add_hook`, `sc.invoke_hooks`,
  `sc.hooks` must keep resolving. No config keys added. No contract keys added/renamed.
- **Safety interlock**: no `--all`/`--for-real`/live `--create-tables` in tests.
- **Escape untrusted text** in every new `console.print` interpolation (Invariant 6) —
  hook names/messages via `rich.markup.escape`.
- Clear stale `.superpowers/sdd/task-*-report.md` before each dispatch (LEDGER I1 note).
- Baseline commit (I4 start) = `d46f56d`.
- Every task report cites Spine directives by number with a verbatim quote (agent config).
- The inner loop is `./run-tests --fast --llm`; run it at every task end.

---

### Task 1: Pure move — `psh/modules.py` (engine + `find_modules`)

Behavior-preserving relocation; no new behavior, so no new tests — the existing suite
(`test_hooks_phases.py`, e2e goldens) is the guard and must stay green **unchanged**.

**Files:**
- Create: `psh/modules.py`
- Modify: `script_context.py` (delete `PHASES` literal + `_valid_hook_name`/`add_hook`/
  `invoke_hooks` defs; add the re-export import)
- Modify: `psh/_legacy.py` (delete `find_modules` def at lines 526–539; add re-import)

**Interfaces:**
- Produces: `psh.modules.PHASES` (tuple), `psh.modules.find_modules(module_type: str) ->
  list[str]`, `psh.modules.add_hook(hook_name: str, target: dict) -> None`,
  `psh.modules.invoke_hooks(hook_name: str, *args, **kwargs) -> None` — all re-exported as
  `sc.*`; later tasks extend this module.
```

## Assistant

I4's plan gives me the exact house shape. Writing the I5 plan to the increment folder (campaign convention overrides the skill's default location):

### ⚙ Tool call: `Write`

```json
{
  "file_path": "/workspace/development/2026-07-20-mod-I5-db/PLAN.md",
  "content": "# I5 — `psh/db.py` (DB layer move) — Implementation Plan\n\n> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to\n> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch\n> every code-touching task as `psh-implementer`, every review as `psh-reviewer`; TDD via\n> `mattpocock-skills:tdd` (NOT superpowers TDD). The authoritative design is `SPEC.md` in this\n> folder — read it in full; this plan is the step sequence, the SPEC carries rationale,\n> decisions (D-i5-1…4), and invariants.\n\n**Goal:** Move the ORM models, detached row types, connection-resilience layer, idempotent\nDB units of work, and `db_engine_args` into a new gated `psh/db.py`; move the two reconnect\ncounter dicts to `script_context.py`; four e2e goldens byte-identical throughout.\n\n**Architecture:** Import-back move (I2/I3/I4 precedent): `psh/_legacy.py` re-imports every\nmoved name so its call sites, the tests' `psh.<name>` references, and the\n`sc.db_engine_args` exposure resolve unchanged. The mutable counters do NOT live in\n`psh/db.py` (CAMPAIGN §3.4): they become `sc.db_reconnects_by_site` /\n`sc.db_reconnect_failures_by_site` — one owning namespace, attribute-accessed at call time\nby the writer (`db_retry`, moving) and the remnant readers (`finish_run`/`abort_run`,\nstaying until I13) — SPEC D-i5-1. `psh/db.py` imports `script_context` at module level\n(no cycle; `psh/gateway.py` precedent — SPEC D-i5-2).\n\n**Tech Stack:** Python 3.12+, SQLAlchemy 2.x, ruff (`ruff-broad.toml` `select=ALL`),\npyright (standard), pytest.\n\n## Global Constraints\n\n- **Four e2e goldens byte-identical** (Invariant 1). `--update-goldens` FORBIDDEN. Verify\n  `git diff 1cf37d3 HEAD -- tests/e2e/__snapshots__/` is empty at each task end.\n- **`psh/db.py` passes the full gate from birth**: `uvx ruff check --config ruff-broad.toml\n  psh/db.py script_context.py` → \"All checks passed!\"; pyright standard → 0 errors.\n  `script_context.py` is un-grandfathered (since I4) — its edits must stay clean too.\n- **Run pyright via `./run-tests`, NOT `uv run pyright`** (uv.lock churn; `git checkout --\n  uv.lock` if it shows modified).\n- **No `sc` name removed** (Invariant 9): `sc.db_engine_args` must keep resolving (the\n  façade house-rule test pins it). The counters are `sc` **additions** (§3.5 allows).\n- **Invariant 5**: the read-release commits in the two loaders and `db_retry`'s\n  unit-granularity move byte-identically; `test_load_traffic_rows_releases_the_connection`\n  must stay green **unweakened**.\n- **Moved bodies are verbatim** except the SPEC Deliverable-A named edits (repeated inline\n  below). The Task 1 report MUST paste the region diff proving the only differences are\n  those edits.\n- **No test dropped, no assertion weakened** (SPEC D-i5-3 \"intact\"): expected counts\n  unchanged from I4 close — `--fast` = 780 passed / 1 skipped; full (live tier) = 782 / 1.\n- **Safety interlock**: no `--all`/`--for-real`/live `--create-tables` in tests.\n- Clear stale `.superpowers/sdd/task-*-report.md` before each dispatch (LEDGER I1 note).\n- Baseline commit (I5 start) = `1cf37d3`.\n- Every task report cites Spine directives by number with a verbatim quote (agent config).\n- The inner loop is `./run-tests --fast --llm`; run it at every task end.\n\n---\n\n### Task 1: The move — `psh/db.py` + counters to `sc` + re-imports + test repoints\n\nOne atomic commit: the code, the state, the re-imports, and the test repoints — partial\napplication cannot be green. Behavior-preserving relocation; **no new tests are owed**\n(SPEC §4 Deliverable D) — the existing suites are the guard and must stay green unchanged\nin count.\n\n**Files:**\n- Create: `psh/db.py`\n- Modify: `script_context.py` (add the two counter dicts + their moved comments)\n- Modify: `psh/_legacy.py` (delete lines 93–167, 821–826, 829–838, 841–1061 **minus**\n  1064–1076 which stays, 1079–1109; add the re-import; repoint 4 counter reads; orphaned\n  imports)\n- Modify: `tests/conftest.py` (`_SC_ATTRS` + `reset_sc`)\n- Modify: `tests/unit/test_db_resilience.py`, `tests/unit/test_traffic_table_rows.py`,\n  `tests/integration/test_db_credentials.py`, `tests/integration/test_abort_run.py`,\n  `tests/integration/test_finish_run.py` (counter-seam repoints only)\n\n**Interfaces:**\n- Produces: `psh.db.{Base, PantheonTraffic, PantheonOverageProtection, TrafficRow,\n  OverageProtectionRow, DatabaseUnavailableError, record_db_reconnect, db_retryable,\n  db_retry, update_traffic_rows, insert_traffic_rows, load_traffic_rows,\n  load_overage_protection_window, db_engine_args}` — all re-imported by `psh._legacy`;\n  `sc.db_reconnects_by_site: dict[str, int]`, `sc.db_reconnect_failures_by_site:\n  dict[str, int]`.\n\n- [ ] **Step 1: Baseline green.** Run `./run-tests --fast --llm`; record the LLM_SUMMARY\n  line (expect `passed=780 … skipped=1`).\n\n- [ ] **Step 2: Create `psh/db.py`.** Header verbatim:\n\n```python\n\"\"\"The database layer: every table this program touches and every query it runs.\n\nORM models (PantheonTraffic, PantheonOverageProtection), their detached row types\n(TrafficRow, OverageProtectionRow), the connection-resilience layer (DatabaseUnavailableError /\nrecord_db_reconnect / db_retryable / db_retry), the idempotent units of work it protects\n(update_traffic_rows, insert_traffic_rows, load_traffic_rows, load_overage_protection_window),\nand db_engine_args -- the ONE engine builder, also exposed as sc.db_engine_args so\nplugin/umich/portal.py gets the same pool settings (CLAUDE.md § Database).\n\nMoved from psh/_legacy.py at campaign increment I5 (CAMPAIGN.md section 3.1;\ndevelopment/2026-07-20-mod-I5-db/SPEC.md).  The governing design is\ndevelopment/2026-07-13-db-connection-resilience/SPEC.md, which the docstrings below cite by\nbare section number.\n\nThe run-scoped reconnect counters (db_reconnects_by_site / db_reconnect_failures_by_site)\nlive in script_context, NOT here: CAMPAIGN.md section 3.4 bars module-level mutable state in\npsh/ modules, and the remnant's finish_run/abort_run read them until I13's RunState absorbs\nthem -- one owning namespace (sc), attribute-accessed at call time by the writer (db_retry,\nbelow) and the remnant readers (SPEC D-i5-1).\n\"\"\"\nimport datetime\nimport sys\nimport time\nfrom typing import NamedTuple\n\nfrom rich.markup import escape\nfrom sqlalchemy import (\n    Boolean,\n    Date,\n    Integer,\n    PrimaryKeyConstraint,\n    String,\n    UniqueConstraint,\n    insert,\n)\nfrom sqlalchemy.dialects.sqlite import insert as sqlite_insert\nfrom sqlalchemy.exc import DBAPIError, OperationalError\nfrom sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column\nfrom sqlalchemy.types import CHAR\n\nimport script_context as sc\n```\n\n  Then the bodies, moved **verbatim** from `psh/_legacy.py` in this order, with exactly\n  these edits (SPEC Deliverable A) and no others:\n\n  1. Lines 93–167 (`Base`, `PantheonTraffic`, `PantheonOverageProtection`, `TrafficRow`,\n     `OverageProtectionRow`). ONE edit — delete line 100:\n     `    # id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)`\n  2. Lines 821–826 (`DatabaseUnavailableError`). No edits.\n  3. Lines 841–926 (`record_db_reconnect`, `db_retryable`, `db_retry`). Edits in\n     `db_retry` only:\n     - signature: `def db_retry(session, unit, *, what: str, site: str | None = None):`\n     - the four counter calls gain the `sc.` prefix:\n       `record_db_reconnect(sc.db_reconnect_failures_by_site, site)` (3×, lines\n       901/917/919) and `record_db_reconnect(sc.db_reconnects_by_site, site)` (line 925).\n  4. Lines 929–961 (`update_traffic_rows`). ONE edit — the strptime line gains a noqa:\n\n```python\n        traffic_date = datetime.datetime.strptime(  # noqa: DTZ007 -- Pantheon env:metrics timestamps are naive date markers; only .date() is taken, and attaching a tzinfo risks an off-by-one-day shift (a behavior change a move may not make)\n            entry[\"datetime\"], \"%Y-%m-%dT%H:%M:%S\"\n        ).date()\n```\n\n  5. Lines 964–980 (`insert_traffic_rows`). No edits.\n  6. Lines 983–1021 (`load_traffic_rows`). No edits — including the\n     `session.commit()  # releases the connection …` line (Invariant 5).\n  7. Lines 1024–1061 (`load_overage_protection_window`). No edits — same commit rule.\n  8. Lines 1079–1109 (`db_engine_args`). ONE edit — signature:\n     `def db_engine_args(db_config: dict) -> tuple[str, dict]:`\n\n  Do NOT move lines 817–818 (`ResumeSiteNotFoundError`), 1064–1076\n  (`sites_from_resume_point`), 1112–1141 (`merge_prior_results`) — they stay for I13.\n\n- [ ] **Step 3: `script_context.py` gains the counters.** After the existing mutable-state\n  globals (`plugin_context` block), insert (comments verbatim from `_legacy.py:829–838`,\n  with the one named doc-accuracy edit: the bare `(SPEC 3.6)` becomes the full path, since\n  the comment leaves the file whose convention resolved it):\n\n```python\n# Reconnects HEALED by db_retry() -- the retry ran and succeeded -- attributed to the site that\n# caused them.  Counted only after the second attempt returns: counting the attempt instead would\n# let an aborted run report a reconnect it never actually made.\ndb_reconnects_by_site: dict[str, int] = {}\n\n# Connection losses db_retry() could NOT heal, attributed the same way: the retry failed, or the\n# rollback before it did.  The counterpart of the dict above, and the reason it can be trusted --\n# every lost connection lands in exactly one of the two, so \"0 healed\" never means \"nothing\n# happened\".  Both are reported on the console and in {ymd}-run.json\n# (development/2026-07-13-db-connection-resilience/SPEC.md 3.6).  Written by psh.db.db_retry;\n# read by finish_run/abort_run; absorbed into RunState at campaign I13.\ndb_reconnect_failures_by_site: dict[str, int] = {}\n```\n\n- [ ] **Step 4: `psh/_legacy.py` re-import + deletions + reader repoints.**\n  - Delete the moved regions (Step 2 list) AND the counter block (829–838).\n  - Next to the existing `from psh.gateway import …` / `from psh.configuration import …`\n    re-imports, add:\n\n```python\nfrom psh.db import (\n    Base,\n    DatabaseUnavailableError,\n    OverageProtectionRow,\n    PantheonOverageProtection,\n    PantheonTraffic,\n    TrafficRow,\n    db_engine_args,\n    db_retry,\n    db_retryable,\n    insert_traffic_rows,\n    load_overage_protection_window,\n    load_traffic_rows,\n    record_db_reconnect,\n    update_traffic_rows,\n)\n```\n\n  - Repoint the four remnant-reader counter reads (post-deletion line numbers will have\n    shifted; find by content):\n\n```python\n    reconnects = sum(sc.db_reconnects_by_site.values())\n    reconnect_failures = sum(sc.db_reconnect_failures_by_site.values())\n```\n\n```python\n                \"reconnects_by_site\": dict(sc.db_reconnects_by_site),\n                \"reconnect_failures_by_site\": dict(sc.db_reconnect_failures_by_site),\n```\n\n  - Remove ONLY the orphaned imports (SPEC Deliverable C, grep-verify each before\n    removing): the seven-name `from sqlalchemy import (Boolean, Date, Integer,\n    PrimaryKeyConstraint, String, UniqueConstraint, insert)` block, the `sqlite_insert`\n    line, `OperationalError` (keep `DBAPIError` and `SQLAlchemyError` on that line),\n    the `from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column` line, the\n    `CHAR` line, and `NamedTuple`. KEEP: `sqlalchemy as db`, `time`, `escape`,\n    `datetime`.\n  - The `sc.db_engine_args = db_engine_args` exposure line stays untouched.\n\n- [ ] **Step 5: conftest isolation.** In `tests/conftest.py`, extend `_SC_ATTRS`:\n\n```python\n_SC_ATTRS = (\n    \"options\",\n    \"config\",\n    \"news\",\n    \"hooks\",\n    \"substitutions\",\n    \"plugin\",\n    \"check\",\n    \"plugin_context\",\n    \"db_reconnects_by_site\",\n    \"db_reconnect_failures_by_site\",\n)\n```\n\n  and in `reset_sc`, after `sc.plugin_context = {}`:\n\n```python\n    sc.db_reconnects_by_site = {}\n    sc.db_reconnect_failures_by_site = {}\n```\n\n- [ ] **Step 6: test-seam repoints.** Find every site with\n  `grep -rn 'psh, \"db_reconnect\\|psh\\.db_reconnect' tests/`. In each of the five files,\n  add `import script_context as sc` if absent, then mechanically:\n  `monkeypatch.setattr(psh, \"db_reconnects_by_site\", X)` →\n  `monkeypatch.setattr(sc, \"db_reconnects_by_site\", X)` (same for `…_failures_…`), and\n  assertions `psh.db_reconnects_by_site` → `sc.db_reconnects_by_site` (same for failures).\n  Example (`test_db_resilience.py:74`):\n\n```python\n    monkeypatch.setattr(sc, \"db_reconnects_by_site\", {})  # never assign: sc is shared module state\n```\n\n  No other test edits. A missed site fails LOUD (`monkeypatch.setattr` raises\n  `AttributeError` on the now-missing `psh` attribute) — zero must remain.\n\n- [ ] **Step 7: byte-verification.** Paste into the task report the proof that the moved\n  bodies differ from baseline only by the named edits:\n\n```bash\ngit show 1cf37d3:psh/_legacy.py | sed -n '93,167p'   > /tmp/old_models.py\ngit show 1cf37d3:psh/_legacy.py | sed -n '821,826p'  > /tmp/old_dbexc.py\ngit show 1cf37d3:psh/_legacy.py | sed -n '841,1061p' > /tmp/old_defs.py\ngit show 1cf37d3:psh/_legacy.py | sed -n '1079,1109p' > /tmp/old_engine.py\n# diff each against the corresponding psh/db.py region; every hunk must be one of the\n# named edits (deleted ERA001 line, sc.-prefixed counter calls, the two signatures, the\n# DTZ007 noqa) or the excluded resume helpers. Paste the diffs.\n```\n\n- [ ] **Step 8: gates.** Run and paste output of each:\n  - `./run-tests --fast --llm` → `passed=780 failed=0 error=0 skipped=1`, 27 snapshots\n  - `git diff 1cf37d3 -- tests/e2e/__snapshots__/ | wc -l` → `0`\n  - `uvx ruff check --config ruff-broad.toml psh/db.py script_context.py` → clean\n  - `uvx ruff check .` → clean\n\n- [ ] **Step 9: Commit.**\n\n```bash\ngit add psh/db.py psh/_legacy.py script_context.py tests/conftest.py \\\n  tests/unit/test_db_resilience.py tests/unit/test_traffic_table_rows.py \\\n  tests/integration/test_db_credentials.py tests/integration/test_abort_run.py \\\n  tests/integration/test_finish_run.py\ngit commit -m \"refactor(campaign-I5): move the DB layer into psh/db.py\n\nModels, row types, db_retry/db_retryable, the idempotent units of work, and\ndb_engine_args move to a new gated psh/db.py (re-imported by _legacy, I2 pattern).\nThe reconnect counters move to script_context (sc.) -- one owning namespace for\nthe moving writer and the remnant readers (SPEC D-i5-1); test seams repoint.\n\nCo-Authored-By: Claude Fable 5 <noreply@anthropic.com>\"\n```\n\n---\n\n### Task 2: Docs, memory, ledger\n\n**Files:**\n- Modify: `CLAUDE.md` (§ Database + the two module-map mentions)\n- Modify: `/home/node/.claude/projects/-workspace/memory/db-idle-connection-reaped.md`,\n  `modularization-campaign.md`, `MEMORY.md` (if hooks change)\n- Modify: `development/2026-07-17-modularization-campaign/LEDGER.md` (append I5 entry)\n- Modify: `development/2026-07-20-mod-I5-db/SPEC.md` (paste acceptance outputs into §9)\n\n**Interfaces:** none (docs only).\n\n- [ ] **Step 1: CLAUDE.md.** In § Architecture's module list, add `psh/db.py` alongside\n  the gateway/configuration/notice/modules entries (models, row types, resilience layer,\n  `db_engine_args`; re-imported by `_legacy.py`, same import-back pattern; counters live\n  in `script_context.py` as `sc.` attributes until I13's `RunState`). In § Database,\n  correct \"(see class defs near the top of the script)\" to name `psh/db.py`, and note the\n  test seam: the counters are patched at the `script_context` module (patching the old\n  `psh` binding no longer exists — it fails loudly). In § Testing's mock-seam bullet, no\n  change (the `psh.time.sleep` guidance still holds). Delete any prose the move obsoletes;\n  report the line-count delta.\n\n- [ ] **Step 2: Memory.** Update `db-idle-connection-reaped.md`: the resilience layer now\n  lives in `psh/db.py`; counters are `sc.db_reconnects_by_site`/\n  `sc.db_reconnect_failures_by_site` (patch at `script_context`, not `psh`). Update\n  `modularization-campaign.md`: I5 complete, I6 (traffic) next.\n\n- [ ] **Step 3: LEDGER.md entry** (template per CAMPAIGN §12): Moved (the §3.1 psh/db.py\n  row, by name); Deviations: none expected — ledger notes D-i5-1 (counters to\n  `script_context`, why, RunState destination), D-i5-3 (\"relocated intact\" reading),\n  B10/B11 stay for I13; Contract/config/sc additions: the two `sc` counter attributes\n  (not façade-documented); Discovered tasks: whatever Task 1 surfaced; Open questions\n  for I6: per CAMPAIGN §11 row I6.\n\n- [ ] **Step 4: Acceptance.** Run `./run-tests --llm` (full; live tier if credentials\n  present — else `--fast` and note it in the ledger entry). Paste outputs into SPEC §9.\n\n- [ ] **Step 5: Commit.**\n\n```bash\ngit add CLAUDE.md development/2026-07-20-mod-I5-db/ \\\n  development/2026-07-17-modularization-campaign/LEDGER.md\ngit commit -m \"docs(campaign-I5): close the DB-layer increment\n\nCo-Authored-By: Claude Fable 5 <noreply@anthropic.com>\"\n```\n\n(The memory files live outside the repo — written, not committed.)\n\n---\n\n## Self-review (run against SPEC.md)\n\n- Spec coverage: SPEC §1 items 1–6 → Task 1 (items 1–5) + Task 2 (item 6). Deliverables\n  A/B/C/D → Task 1 Steps 2/3/4/5–6. Ratchet §5 → the named edits + Step 8 gates.\n  §8 docs/memory → Task 2. §9 acceptance → Task 2 Step 4. No gaps.\n- Placeholder scan: all edits shown concretely; the verbatim-move regions are specified by\n  exact baseline line ranges with a mandatory diff-verification step (Step 7) — the source\n  of truth for a move is the source file, not a re-typed copy.\n- Type consistency: `tuple[str, dict]` and `str | None` appear identically in SPEC\n  Deliverable A and Task 1 Step 2; the counter names are spelled identically in Steps 3–6.\n"
}
```

### ↳ Tool result

```
File created successfully at: /workspace/development/2026-07-20-mod-I5-db/PLAN.md (file state is current in your context — no need to Read it back)
```

### ⚙ Tool call: `Skill`

```json
{
  "skill": "superpowers:subagent-driven-development"
}
```

### ↳ Tool result

```
Launching skill: superpowers:subagent-driven-development
```

## User

Base directory for this skill: /home/node/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development

# Subagent-Driven Development

Execute plan by dispatching a fresh implementer subagent per task, a task review (spec compliance + code quality) after each, and a broad whole-branch review at the end.

**Why subagents:** You delegate tasks to specialized agents with isolated context. By precisely crafting their instructions and context, you ensure they stay focused and succeed at their task. They should never inherit your session's context or history — you construct exactly what they need. This also preserves your own context for coordination work.

**Core principle:** Fresh subagent per task + task review (spec + quality) + broad final review = high quality, fast iteration

**Narration:** between tool calls, narrate at most one short line — the
ledger and the tool results carry the record.

**Continuous execution:** Do not pause to check in with your human partner between tasks. Execute all tasks from the plan without stopping. The only reasons to stop are: BLOCKED status you cannot resolve, ambiguity that genuinely prevents progress, or all tasks complete. "Should I continue?" prompts and progress summaries waste their time — they asked you to execute the plan, so execute it.

## When to Use

```dot
digraph when_to_use {
    "Have implementation plan?" [shape=diamond];
    "Tasks mostly independent?" [shape=diamond];
    "Stay in this session?" [shape=diamond];
    "subagent-driven-development" [shape=box];
    "executing-plans" [shape=box];
    "Manual execution or brainstorm first" [shape=box];

    "Have implementation plan?" -> "Tasks mostly independent?" [label="yes"];
    "Have implementation plan?" -> "Manual execution or brainstorm first" [label="no"];
    "Tasks mostly independent?" -> "Stay in this session?" [label="yes"];
    "Tasks mostly independent?" -> "Manual execution or brainstorm first" [label="no - tightly coupled"];
    "Stay in this session?" -> "subagent-driven-development" [label="yes"];
    "Stay in this session?" -> "executing-plans" [label="no - parallel session"];
}
```

**vs. Executing Plans (parallel session):**
- Same session (no context switch)
- Fresh subagent per task (no context pollution)
- Review after each task (spec compliance + code quality), broad review at the end
- Faster iteration (no human-in-loop between tasks)

## The Process

```dot
digraph process {
    rankdir=TB;

    subgraph cluster_per_task {
        label="Per Task";
        "Dispatch implementer subagent (./implementer-prompt.md)" [shape=box];
        "Implementer subagent asks questions?" [shape=diamond];
        "Answer questions, provide context" [shape=box];
        "Implementer subagent implements, tests, commits, self-reviews" [shape=box];
        "Write diff file, dispatch task reviewer subagent (./task-reviewer-prompt.md)" [shape=box];
        "Task reviewer reports spec ✅ and quality approved?" [shape=diamond];
        "Dispatch fix subagent for Critical/Important findings" [shape=box];
        "Mark task complete in todo list and progress ledger" [shape=box];
    }

    "Read plan, note context and global constraints, create todos" [shape=box];
    "More tasks remain?" [shape=diamond];
    "Dispatch final code reviewer subagent (../requesting-code-review/code-reviewer.md)" [shape=box];
    "Use superpowers:finishing-a-development-branch" [shape=box style=filled fillcolor=lightgreen];

    "Read plan, note context and global constraints, create todos" -> "Dispatch implementer subagent (./implementer-prompt.md)";
    "Dispatch implementer subagent (./implementer-prompt.md)" -> "Implementer subagent asks questions?";
    "Implementer subagent asks questions?" -> "Answer questions, provide context" [label="yes"];
    "Answer questions, provide context" -> "Dispatch implementer subagent (./implementer-prompt.md)";
    "Implementer subagent asks questions?" -> "Implementer subagent implements, tests, commits, self-reviews" [label="no"];
    "Implementer subagent implements, tests, commits, self-reviews" -> "Write diff file, dispatch task reviewer subagent (./task-reviewer-prompt.md)";
    "Write diff file, dispatch task reviewer subagent (./task-reviewer-prompt.md)" -> "Task reviewer reports spec ✅ and quality approved?";
    "Task reviewer reports spec ✅ and quality approved?" -> "Dispatch fix subagent for Critical/Important findings" [label="no"];
    "Dispatch fix subagent for Critical/Important findings" -> "Write diff file, dispatch task reviewer subagent (./task-reviewer-prompt.md)" [label="re-review"];
    "Task reviewer reports spec ✅ and quality approved?" -> "Mark task complete in todo list and progress ledger" [label="yes"];
    "Mark task complete in todo list and progress ledger" -> "More tasks remain?";
    "More tasks remain?" -> "Dispatch implementer subagent (./implementer-prompt.md)" [label="yes"];
    "More tasks remain?" -> "Dispatch final code reviewer subagent (../requesting-code-review/code-reviewer.md)" [label="no"];
    "Dispatch final code reviewer subagent (../requesting-code-review/code-reviewer.md)" -> "Use superpowers:finishing-a-development-branch";
}
```

## Pre-Flight Plan Review

Before dispatching Task 1, scan the plan once for conflicts:

- tasks that contradict each other or the plan's Global Constraints
- anything the plan explicitly mandates that the review rubric treats as a
  defect (a test that asserts nothing, verbatim duplication of a logic block)

Present everything you find to your human partner as one batched question —
each finding beside the plan text that mandates it, asking which governs —
before execution begins, not one interrupt per discovery mid-plan. If the
scan is clean, proceed without comment. The review loop remains the net for
conflicts that only emerge from implementation.

## Model Selection

Use the least powerful model that can handle each role to conserve cost and increase speed.

**Mechanical implementation tasks** (isolated functions, clear specs, 1-2 files): use a fast, cheap model. Most implementation tasks are mechanical when the plan is well-specified.

**Integration and judgment tasks** (multi-file coordination, pattern matching, debugging): use a standard model.

**Architecture and design tasks**: use the most capable available model.
The final whole-branch review is one of these — dispatch it on the most
capable available model, not the session default.

**Review tasks**: choose the model with the same judgment, scaled to the
diff's size, complexity, and risk. A small mechanical diff does not need the
most capable model; a subtle concurrency change does.

**Always specify the model explicitly when dispatching a subagent.** An
omitted model inherits your session's model — often the most capable and
most expensive — which silently defeats this section.

**Turn count beats token price.** Wall-clock and context cost scale with how
many turns a subagent takes, and the cheapest models routinely take 2-3× the
turns on multi-step work — costing more overall. Use a mid-tier model as the
floor for reviewers and for implementers working from prose descriptions.
When the task's plan text contains the complete code to write, the
implementation is transcription plus testing: use the cheapest tier for
that implementer. Single-file mechanical fixes also take the cheapest tier.

**Task complexity signals (implementation tasks):**
- Touches 1-2 files with a complete spec → cheap model
- Touches multiple files with integration concerns → standard model
- Requires design judgment or broad codebase understanding → most capable model

## Handling Implementer Status

Implementer subagents report one of four statuses. Handle each appropriately:

**DONE:** Generate the review package (`scripts/review-package BASE HEAD`, from this skill's directory — it prints the unique file path it wrote; BASE is the commit you recorded before dispatching the implementer — never `HEAD~1`, which silently drops all but the last commit of a multi-commit task), then dispatch the task reviewer with the printed path.

**DONE_WITH_CONCERNS:** The implementer completed the work but flagged doubts. Read the concerns before proceeding. If the concerns are about correctness or scope, address them before review. If they're observations (e.g., "this file is getting large"), note them and proceed to review.

**NEEDS_CONTEXT:** The implementer needs information that wasn't provided. Provide the missing context and re-dispatch.

**BLOCKED:** The implementer cannot complete the task. Assess the blocker:
1. If it's a context problem, provide more context and re-dispatch with the same model
2. If the task requires more reasoning, re-dispatch with a more capable model
3. If the task is too large, break it into smaller pieces
4. If the plan itself is wrong, escalate to the human

**Never** ignore an escalation or force the same model to retry without changes. If the implementer said it's stuck, something needs to change.

## Handling Reviewer ⚠️ Items

The task reviewer may report "⚠️ Cannot verify from diff" items — requirements
that live in unchanged code or span tasks. These do not block the rest of the
review, but you must resolve each one yourself before marking the task
complete: you hold the plan and cross-task context the reviewer
lacks. If you confirm an item is a real gap, treat it as a failed spec
review — send it back to the implementer and re-review.

## Constructing Reviewer Prompts

Per-task reviews are task-scoped gates. The broad review happens once, at the
final whole-branch review. When you fill a reviewer template:

- Do not add open-ended directives like "check all uses" or "run race tests
  if useful" without a concrete, task-specific reason
- Do not ask a reviewer to re-run tests the implementer already ran on the
  same code — the implementer's report carries the test evidence
- Do not pre-judge findings for the reviewer — never instruct a reviewer to
  ignore or not flag a specific issue. If you believe a finding would be a
  false positive, let the reviewer raise it and adjudicate it in the review
  loop. If the prompt you are writing contains "do not flag," "don't treat X
  as a defect," "at most Minor," or "the plan chose" — stop: you are
  pre-judging, usually to spare yourself a review loop.
- The global-constraints block you hand the reviewer is its attention
  lens. Copy the binding requirements verbatim from the plan's Global
  Constraints section or the spec: exact values, exact formats, and the
  stated relationships between components ("same layout as X", "matches
  Y"). The reviewer's template already carries the process rules (YAGNI,
  test hygiene, review method) — the constraints block is for what THIS
  project's spec demands.
- Hand the reviewer its diff as a file: run this skill's
  `scripts/review-package BASE HEAD` and pass the reviewer the file path
  it prints (or, without bash: `git log --oneline`, `git diff --stat`,
  and `git diff -U10` for the range, redirected to one uniquely named
  file). The output never enters your own context, and the reviewer sees
  the commit list, stat summary, and full diff with context in one Read
  call. Use the BASE you recorded before dispatching the implementer —
  never `HEAD~1`, which silently truncates multi-commit tasks.
- A dispatch prompt describes one task, not the session's history. Do not
  paste accumulated prior-task summaries ("state after Tasks 1-3") into
  later dispatches — a real session's dispatch hit 42k chars of which 99%
  was pasted history. A fresh subagent needs its task, the interfaces it
  touches, and the global constraints. Nothing else.
- Dispatch fix subagents for Critical and Important findings. Record Minor
  findings in the progress ledger as you go, and point the final
  whole-branch review at that list so it can triage which must be fixed
  before merge. A roll-up nobody reads is a silent discard.
- A finding labeled plan-mandated — or any finding that conflicts with
  what the plan's text requires — is the human's decision, like any plan
  contradiction: present the finding and the plan text, ask which governs.
  Do not dismiss the finding because the plan mandates it, and do not
  dispatch a fix that contradicts the plan without asking.
- The final whole-branch review gets a package too: run
  `scripts/review-package MERGE_BASE HEAD` (MERGE_BASE = the commit the
  branch started from, e.g. `git merge-base main HEAD`) and include the
  printed path in the final review dispatch, so the final reviewer reads
  one file instead of re-deriving the branch diff with git commands.
- Every fix dispatch carries the implementer contract: the fix subagent
  re-runs the tests covering its change and reports the results. Name the
  covering test files in the dispatch — a one-line fix does not need the
  whole suite. Before re-dispatching the reviewer, confirm the fix report
  contains the covering tests, the command run, and the output; dispatch
  the re-review once all three are present.
- If the final whole-branch review returns findings, dispatch ONE fix
  subagent with the complete findings list — not one fixer per finding.
  Per-finding fixers each rebuild context and re-run suites; a real
  session's final-review fix wave cost more than all its tasks combined.

## File Handoffs

Everything you paste into a dispatch prompt — and everything a subagent
prints back — stays resident in your context for the rest of the session
and is re-read on every later turn. Hand artifacts over as files:

- **Task brief:** before dispatching an implementer, run this skill's
  `scripts/task-brief PLAN_FILE N` — it extracts the task's full text to a
  uniquely named file and prints the path. Compose the dispatch so the
  brief stays the single source of requirements. Your dispatch should
  contain: (1) one line on where this task fits in the project; (2) the
  brief path, introduced as "read this first — it is your requirements,
  with the exact values to use verbatim"; (3) interfaces and decisions
  from earlier tasks that the brief cannot know; (4) your resolution of
  any ambiguity you noticed in the brief; (5) the report-file path and
  report contract. Exact values (numbers, magic strings, signatures, test
  cases) appear only in the brief.
- **Report file:** name the implementer's report file after the brief
  (brief `…/task-N-brief.md` → report `…/task-N-report.md`) and put it in
  the dispatch prompt. The implementer writes the full report there and
  returns only status, commits, a one-line test summary, and concerns.
- **Reviewer inputs:** the task reviewer gets three paths — the same brief
  file, the report file, and the review package — plus the global
  constraints that bind the task.
- Fix dispatches append their fix report (with test results) to the same
  report file and return a short summary; re-reviews read the updated file.

## Durable Progress

Conversation memory does not survive compaction. In real sessions,
controllers that lost their place have re-dispatched entire completed task
sequences — the single most expensive failure observed. Track progress in
a ledger file, not only in todos.

- At skill start, check for a ledger:
  `cat "$(git rev-parse --show-toplevel)/.superpowers/sdd/progress.md"`. Tasks listed there
  as complete are DONE — do not re-dispatch them; resume at the first task
  not marked complete.
- When a task's review comes back clean, append one line to the ledger in
  the same message as your other bookkeeping:
  `Task N: complete (commits <base7>..<head7>, review clean)`.
- The ledger is your recovery map: the commits it names exist in git even
  when your context no longer remembers creating them. After compaction,
  trust the ledger and `git log` over your own recollection.
- `git clean -fdx` will destroy the ledger (it's git-ignored scratch); if
  that happens, recover from `git log`.

## Prompt Templates

- [implementer-prompt.md](implementer-prompt.md) - Dispatch implementer subagent
- [task-reviewer-prompt.md](task-reviewer-prompt.md) - Dispatch task reviewer subagent (spec compliance + code quality)
- Final whole-branch review: use superpowers:requesting-code-review's [code-reviewer.md](../requesting-code-review/code-reviewer.md)

## Example Workflow

```
You: I'm using Subagent-Driven Development to execute this plan.

[Read plan file once: docs/superpowers/plans/feature-plan.md]
[Create todos for all tasks]

Task 1: Hook installation script

[Run task-brief for Task 1; dispatch implementer with brief + report paths + context]

Implementer: "Before I begin - should the hook be installed at user or system level?"

You: "User level (~/.config/superpowers/hooks/)"

Implementer: "Got it. Implementing now..."
[Later] Implementer:
  - Implemented install-hook command
  - Added tests, 5/5 passing
  - Self-review: Found I missed --force flag, added it
  - Committed

[Run review-package, dispatch task reviewer with the printed path]
Task reviewer: Spec ✅ - all requirements met, nothing extra.
  Strengths: Good test coverage, clean. Issues: None. Task quality: Approved.

[Mark Task 1 complete]

Task 2: Recovery modes

[Run task-brief for Task 2; dispatch implementer with brief + report paths + context]

Implementer: [No questions, proceeds]
Implementer:
  - Added verify/repair modes
  - 8/8 tests passing
  - Self-review: All good
  - Committed

[Run review-package, dispatch task reviewer with the printed path]
Task reviewer: Spec ❌:
  - Missing: Progress reporting (spec says "report every 100 items")
  - Extra: Added --json flag (not requested)
  Issues (Important): Magic number (100)

[Dispatch fix subagent with all findings]
Fixer: Removed --json flag, added progress reporting, extracted PROGRESS_INTERVAL constant

[Task reviewer reviews again]
Task reviewer: Spec ✅. Task quality: Approved.

[Mark Task 2 complete]

...

[After all tasks]
[Dispatch final code-reviewer]
Final reviewer: All requirements met, ready to merge

Done!
```

## Advantages

**vs. Manual execution:**
- Subagents follow TDD naturally
- Fresh context per task (no confusion)
- Parallel-safe (subagents don't interfere)
- Subagent can ask questions (before AND during work)

**vs. Executing Plans:**
- Same session (no handoff)
- Continuous progress (no waiting)
- Review checkpoints automatic

**Efficiency gains:**
- Controller curates exactly what context is needed; bulk artifacts move
  as files, not pasted text
- Subagent gets complete information upfront
- Questions surfaced before work begins (not after)

**Quality gates:**
- Self-review catches issues before handoff
- Task review carries two verdicts: spec compliance and code quality
- Review loops ensure fixes actually work
- Spec compliance prevents over/under-building
- Code quality ensures implementation is well-built

**Cost:**
- More subagent invocations (implementer + reviewer per task)
- Controller does more prep work (extracting all tasks upfront)
- Review loops add iterations
- But catches issues early (cheaper than debugging later)

## Red Flags

**Never:**
- Start implementation on main/master branch without explicit user consent
- Skip task review, or accept a report missing either verdict (spec compliance AND task quality are both required)
- Proceed with unfixed issues
- Dispatch multiple implementation subagents in parallel (conflicts)
- Make a subagent read the whole plan file (hand it its task brief —
  `scripts/task-brief` — instead)
- Skip scene-setting context (subagent needs to understand where task fits)
- Ignore subagent questions (answer before letting them proceed)
- Accept "close enough" on spec compliance (reviewer found spec issues = not done)
- Skip review loops (reviewer found issues = implementer fixes = review again)
- Let implementer self-review replace actual review (both are needed)
- Tell a reviewer what not to flag, or pre-rate a finding's severity in the
  dispatch prompt ("treat it as Minor at most") — the plan's example code is
  a starting point, not evidence that its weaknesses were chosen
- Dispatch a task reviewer without a diff file — generate it first
  (`scripts/review-package BASE HEAD`) and name the printed path in the
  prompt
- Move to next task while the review has open Critical/Important issues
- Re-dispatch a task the progress ledger already marks complete — check
  the ledger (and `git log`) after any compaction or resume

**If subagent asks questions:**
- Answer clearly and completely
- Provide additional context if needed
- Don't rush them into implementation

**If reviewer finds issues:**
- Implementer (same subagent) fixes them
- Reviewer reviews again
- Repeat until approved
- Don't skip the re-review

**If subagent fails task:**
- Dispatch fix subagent with specific instructions
- Don't try to fix manually (context pollution)

## Integration

**Required workflow skills:**
- **superpowers:using-git-worktrees** - Ensures isolated workspace (creates one or verifies existing)
- **superpowers:writing-plans** - Creates the plan this skill executes
- **superpowers:requesting-code-review** - Code review template for the final whole-branch review
- **superpowers:finishing-a-development-branch** - Complete development after all tasks

**Subagents should use:**
- **superpowers:test-driven-development** - Subagents follow TDD for each task

**Alternative workflow:**
- **superpowers:executing-plans** - Use for parallel session instead of same-session execution

### ⚙ Tool call: `Bash`

```json
{
  "command": "cat .superpowers/sdd/progress.md 2>/dev/null; ls .superpowers/sdd/ 2>/dev/null; rm -f .superpowers/sdd/task-*-report.md .superpowers/sdd/task-*-brief.md .superpowers/sdd/review-package-*.md 2>/dev/null; mkdir -p .superpowers/sdd; head -8 .claude/agents/psh-implementer.md .claude/agents/psh-reviewer.md; git rev-parse --short HEAD",
  "description": "Check SDD ledger, purge stale reports, show agent frontmatter"
}
```

### ↳ Tool result

```
# I4 progress ledger (development/2026-07-20-mod-I4-hooks-dag/PLAN.md)
Base (I4 start): d46f56d
- Task 1: engine move -> psh/modules.py : complete (commit 82d62ff, review clean; Minor -> closing task: CLAUDE.md line ~117 add_hook/invoke_hooks attribution stale)
- Task 2: run_finish phase : complete (commit b610f60, review clean; note -> final review: abort-path run_finish coverage is indirect (single unconditional line, shared caller))
- Task 3: mandatory consumes/produces + retrofit : complete (commit 5da97b1, review clean; SPEC §6 cache row corrected mid-task: +primary_domain, code-verified cache.py:233 -> ledger; Low: report said 12 registrations, actual 11 add_hook calls; ⚠️ pre-existing: unknown-phase fatals interpolate hook_name unescaped -> fix folded into Task 5 dispatch)
- Task 4: CONTRACT registry + stuffers : complete (commit 4922c38, review clean; PLR0913 noqa on stuff_gather_contract, spec-pinned signature)
- Task 5: DAG validation + topo order : complete (commits 3b46cb7 + fix 32d3c9a, re-review approved; extras: checkload.py base= param (back-compat), test_plugin_umich_portal.py raw-hook-write fix (only instance repo-wide), unknown-phase fatals now escape hook_name (Invariant 6))
- Task 6: un-grandfather script_context.py : complete (commit 1f2a6af, review clean; findings exactly as pre-measured, no noqa additions)
- Whole-branch review (opus): PASS. I-1 (closing docs: CLAUDE.md 117/137-146/487 + LEDGER I4 + memory) = Task 7. M-1 main() HookDagError glue untested (inspection only) -> ledger. M-2 run_finish abort-path indirect -> ledger. M-3 runtime-registered hooks bypass conditions 1-4 (import-time model assumed) -> ledger note for I13.
progress-2026-07-13-db-connection-resilience.md
progress-2026-07-17-mod-I3.md
progress.md
review-32d3c9a..1f2a6af.diff
review-4922c38..3b46cb7.diff
review-5da97b1..4922c38.diff
review-82d62ff..b610f60.diff
review-b610f60..5da97b1.diff
review-d46f56d..1f2a6af.diff
review-d46f56d..82d62ff.diff
task-1-brief.md
task-1-report.md
task-2-brief.md
task-2-report.md
task-3-brief.md
task-3-report.md
task-4-brief.md
task-4-report.md
task-5-brief.md
task-5-report.md
task-6-brief.md
task-6-report.md
==> .claude/agents/psh-implementer.md <==
---
name: psh-implementer
description: Implementer for pantheon-sitehealth-emails. Carries this repo's standards and house style. Use for any task that writes or changes code in this repo, including fix-subagents applying review findings.
---

You are implementing a task in `pantheon-sitehealth-emails`, a Python CLI that emails
Pantheon site owners a monthly health report.


==> .claude/agents/psh-reviewer.md <==
---
name: psh-reviewer
description: Adversarial reviewer for pantheon-sitehealth-emails. Carries this repo's standards. Use for adversarial review of specs/plans, task review, and whole-branch review.
---

You are reviewing work in `pantheon-sitehealth-emails`, a Python CLI that emails Pantheon
site owners a monthly health report.

1cf37d3
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "mv .superpowers/sdd/progress.md .superpowers/sdd/progress-2026-07-20-mod-I4.md && rm -f .superpowers/sdd/review-*.diff && printf '# I5 progress ledger (development/2026-07-20-mod-I5-db/PLAN.md)\\nBase (I5 start): 1cf37d3\\n' > .superpowers/sdd/progress.md && /home/node/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/scripts/task-brief development/2026-07-20-mod-I5-db/PLAN.md 1",
  "description": "Archive I4 ledger, start I5 ledger, extract Task 1 brief"
}
```

### ↳ Tool result

```
wrote /workspace/.superpowers/sdd/task-1-brief.md: 249 lines
```

## Assistant

Dispatching the Task 1 implementer (`psh-implementer`, sonnet — multi-file move with a fully-specified plan):

### ⚙ Tool call: `Agent`

```json
{
  "description": "I5 Task 1: DB layer move",
  "subagent_type": "psh-implementer",
  "model": "sonnet",
  "run_in_background": false,
  "prompt": "You are implementing Task 1 of campaign increment I5 (DB-layer move) in /workspace — the modularization campaign's next increment after I4.\n\nRead this first — it is your requirements, with the exact values to use verbatim: /workspace/.superpowers/sdd/task-1-brief.md\n\nThen read IN FULL the authoritative design it implements: /workspace/development/2026-07-20-mod-I5-db/SPEC.md (especially Deliverables A–D and §5's measured ruff/pyright dispositions). The brief is the step sequence; the SPEC carries the rationale and the exhaustive edit list. Where they name line numbers, both refer to baseline commit 1cf37d3 (= current HEAD).\n\nProcess notes:\n- TDD for this repo is `mattpocock-skills:tdd`, NOT superpowers:test-driven-development. This task is a behavior-preserving relocation: no new tests are owed (SPEC §4 Deliverable D); the existing suites are the guard and must stay green with count unchanged (--fast: 780 passed / 1 skipped).\n- The move is atomic — one commit containing psh/db.py, script_context.py, psh/_legacy.py, tests/conftest.py, and the five test-file repoints. Partial application cannot be green, so verify everything before committing.\n- Moved bodies are verbatim except the named edits; Step 7's region-diff proof is mandatory and goes in your report.\n- Do not touch tests/e2e/__snapshots__/ (goldens byte-identical, `--update-goldens` forbidden).\n\nWrite your full report to /workspace/.superpowers/sdd/task-1-report.md: what you did, the Step 7 diffs, every gate command with pasted output, the Spine directives you applied by number with a verbatim quote from each, and any concerns. Return to me only: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED), commit sha(s), a one-line test summary, and concerns if any."
}
```

### ↳ Tool result

```
All verified. Task 1 is complete and committed.

## Summary

**Status:** DONE
**Commit:** `c291a26` — "refactor(campaign-I5): move the DB layer into psh/db.py"
**Test summary:** `passed=780 failed=0 error=0 skipped=1` (unchanged from baseline), 27 snapshots, both ruff gates clean, pyright 0 errors, e2e goldens byte-identical (`git diff 1cf37d3 -- tests/e2e/__snapshots__/ | wc -l` → 0).

Full report with every gate command's pasted output, the Step 7 region diffs proving the moved bodies differ from baseline only by the named edits, and the Spine citations is at `/workspace/.superpowers/sdd/task-1-report.md`.

**Concerns (documented in the report, not silent):**
1. One pyright finding not in SPEC §5's finding table: `record_db_reconnect`'s `site: str` parameter needed retyping to `str | None` once `db_retry`'s SPEC-mandated signature edit passed a `str | None` through it. Disposed the same way as the sibling edit (body already handled `None`). Flagged for Task 2's LEDGER.md as a finding-table correction.
2. Collapsed blank-line runs (up to 8 consecutive) that the brief's literal non-contiguous line-range deletions left behind in `psh/_legacy.py`, to the file's standard 2-blank-line convention — whitespace only, no code touched.

Files touched: `/workspace/psh/db.py` (new), `/workspace/psh/_legacy.py`, `/workspace/script_context.py`, `/workspace/tests/conftest.py`, `/workspace/tests/unit/test_db_resilience.py`, `/workspace/tests/unit/test_traffic_table_rows.py`, `/workspace/tests/integration/test_db_credentials.py`, `/workspace/tests/integration/test_abort_run.py`, `/workspace/tests/integration/test_finish_run.py`.
agentId: a98d43ef36f9974b5 (use SendMessage with to: 'a98d43ef36f9974b5', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 183347
tool_uses: 96
duration_ms: 668969</usage>
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "/home/node/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/scripts/review-package 1cf37d3 c291a26",
  "description": "Generate Task 1 review package"
}
```

### ↳ Tool result

```
wrote /workspace/.superpowers/sdd/review-1cf37d3..c291a26.diff: 1 commit(s), 80595 bytes
```

### ⚙ Tool call: `Agent`

```json
{
  "description": "I5 Task 1 review",
  "subagent_type": "psh-reviewer",
  "model": "opus",
  "run_in_background": false,
  "prompt": "Task review for Task 1 of campaign increment I5 (DB-layer move into psh/db.py) in /workspace.\n\nRead these three files:\n1. The task brief (requirements): /workspace/.superpowers/sdd/task-1-brief.md\n2. The implementer's report: /workspace/.superpowers/sdd/task-1-report.md\n3. The full diff (1 commit, 1cf37d3..c291a26): /workspace/.superpowers/sdd/review-1cf37d3..c291a26.diff\n\nThe authoritative design is /workspace/development/2026-07-20-mod-I5-db/SPEC.md (read in full; Deliverables A–D and §5 are what this task implements).\n\nGlobal constraints binding this task (verbatim from the plan):\n- \"Four e2e goldens byte-identical (Invariant 1). `--update-goldens` FORBIDDEN.\"\n- \"`psh/db.py` passes the full gate from birth: `uvx ruff check --config ruff-broad.toml psh/db.py script_context.py` → 'All checks passed!'; pyright standard → 0 errors.\" `script_context.py` is un-grandfathered and must stay clean.\n- \"No `sc` name removed (Invariant 9): `sc.db_engine_args` must keep resolving.\" The counters are sc additions.\n- \"Invariant 5: the read-release commits in the two loaders and `db_retry`'s unit-granularity move byte-identically; `test_load_traffic_rows_releases_the_connection` must stay green unweakened.\"\n- \"Moved bodies are verbatim except the SPEC Deliverable-A named edits\" — the named edits are, exhaustively: delete the ERA001 `# id:` line; `site: str | None = None` on db_retry; `sc.` prefix on the four record_db_reconnect calls; the DTZ007 noqa on the strptime; `-> tuple[str, dict]` on db_engine_args. Verify the report's region diffs and spot-check the actual diff yourself — a re-indent or content drift in moved bodies (including the docstrings and the two `session.commit()` release lines) is a Critical finding.\n- \"No test dropped, no assertion weakened (SPEC D-i5-3 'intact'): expected counts unchanged from I4 close — --fast = 780 passed / 1 skipped.\"\n- Deliberately NOT moved (staying for I13): `ResumeSiteNotFoundError`, `sites_from_resume_point`, `merge_prior_results`, the B10/B11 engine/sessionmaker/create_all code in main(), finish_run/abort_run (whose four counter reads must now read `sc.`).\n- The implementer's two reported concerns (record_db_reconnect `site: str | None` retyping beyond the SPEC table; blank-line collapse in `_legacy.py`) need your verdict: correct disposition or defect.\n\nReport two verdicts: spec compliance (✅/❌ with specifics) and task quality (Approved / issues by severity Critical/Important/Minor). List any \"⚠️ Cannot verify from diff\" items separately."
}
```

### ↳ Tool result

```
I have completed independent verification. Every load-bearing claim checks out. Here is my review.

---

## Task 1 review — I5 DB-layer move into `psh/db.py`

I read `prompts/directives.md`, `prompts/implementation-standards.md`, the SPEC, the brief, the report, and the full diff, then independently verified against the repo at `c291a26`.

### Verdict 1 — Spec compliance: ✅ PASS (with one SPEC-side documentation defect the implementer must carry into Task 2)

Everything the SPEC's Deliverables A–D and §5/§6 require is present and correct. Verified, not trusted:

- **Moved bodies verbatim modulo named edits** — I diffed every region against baseline `1cf37d3`:
  - Models (`git show 1cf37d3:…| sed -n '93,166p'` vs `psh/db.py`): sole difference is the deleted ERA001 `# id:` line. ✅
  - `DatabaseUnavailableError`: byte-identical (`diff` exit 0). ✅
  - `record_db_reconnect`…`load_overage_protection_window`: only the 4 `sc.` prefixes, `db_retry`'s `site: str | None = None`, the `record_db_reconnect` retype, and the DTZ007 noqa. The two `session.commit()  # releases the connection … MUST NOT be removed` lines are present byte-identical at `psh/db.py:306,346` (Invariant 5). ✅
  - `db_engine_args`: only `-> (str, dict)` → `-> tuple[str, dict]`. ✅
- **Orphaned-import sweep is correct.** All 12 removed names (`NamedTuple`, `Boolean`, `Integer`, `PrimaryKeyConstraint`, `String`, `UniqueConstraint`, `sqlite_insert`, `OperationalError`, `DeclarativeBase`, `Mapped`, `mapped_column`, `CHAR`) have **0** remaining uses in `_legacy.py`. I specifically chased the `grep -w "Date"` = 5 hits red flag: all five are string literals (HTML template `<div>Date</div>`, `msg["Date"]` header), not the sqlalchemy type — critical to check because `_legacy.py` is grandfathered from broad ruff *and* excluded from pyright, so a genuinely-undefined name there would slip every gate. `DBAPIError`/`SQLAlchemyError`/`db_retryable`/`sqlalchemy as db` confirmed still used and correctly kept. ✅
- **Counter move + repoints.** All four remnant reads at `_legacy.py:864,865,950,951` re-spelled to `sc.`; zero bare counter reads remain. `script_context.py` gains both typed dicts with verbatim comments (plus the named `(SPEC 3.6)` → full-path edit). `_SC_ATTRS`/`reset_sc` extended. ✅
- **Invariant 9 façade.** `sc.db_engine_args = db_engine_args` survives at `_legacy.py:809`; `test_documented_sc_facade_names_exist` passes; the counters correctly do **not** join it. ✅
- **Test-seam repoints complete.** `grep -rnE 'psh, "db_reconnect|psh\.db_reconnect' tests/` → zero hits; all 5 files import `sc`. ✅
- **Gates green (re-run by me, not taken on faith):** `--fast` → `passed=780 failed=0 error=0 skipped=1`, 27 snapshots; goldens diff = 0 lines (Invariant 1); broad ruff on `psh/db.py script_context.py` clean; narrow ruff whole-tree clean; pyright `0 errors`. Invariant-5 guard `test_load_traffic_rows_releases_the_connection` (+2 siblings) pass. ✅

**The one SPEC-side defect (PD#14):** The SPEC's acceptance criterion §9 #1 and §7 both assert the I4-close baseline is **`passed=782`**. Reality is **780**. I collected at both `1cf37d3` and `c291a26`: **783 tests collected on each side** (no test added or dropped), and in `--fast` that resolves to 780 passed / 1 skipped / 2 deselected — 782 passed is unreachable in `--fast`. The SPEC number was asserted from appearance, never run — exactly the failure PD#14 exists to catch (*"A green check is a claim, not evidence, until it has been shown capable of going red"*; the corollary the Spine draws for measurements). The brief corrected it to 780 and the implementer verified 780 against reality, which is the right disposition — but **Task 2 must correct the SPEC's §9 acceptance line and §7 to 780, not "fill in 782."** This is a documentation defect, not an implementation one; the implementation preserves the count exactly.

### Verdict 2 — Task quality: **Approved** (one Minor follow-up, already flagged by the implementer)

The implementer's two reported concerns — my verdict on each:

1. **`record_db_reconnect` retyped `site: str | None` beyond the SPEC table — CORRECT, not a defect (Minor: ledger follow-up owed).** This is *forced* by the pyright gate: `db_retry`'s SPEC-mandated `site: str | None = None` flows straight into `record_db_reconnect(counter, site)`, which declared `site: str`, producing `reportArgumentType` at all four call sites — and `psh/db.py` must reach 0 pyright errors "from birth." The fix is behavior-preserving (the body already does `key = site if site is not None else "(no site)"`). The SPEC's §5 table calls itself "exhaustive" but missed it, and Deliverable A lists `record_db_reconnect` edits as "—", so this is a genuine SPEC gap the implementer filled correctly and disclosed loudly, with red-first PD#14 discipline. It belongs in Task 2's LEDGER as a finding-table correction (SPEC §8 already mandates "any finding-table corrections") — the implementer said exactly this.

2. **Blank-line collapse in `_legacy.py` — CORRECT, not a defect.** It touches only leftover whitespace in the *remnant* between non-contiguous deletions, not the moved bodies (which are verbatim in `db.py`, verified). I enumerated every `_legacy.py` hunk: the complete set of added lines is the rewritten `sqlalchemy.exc` import, the `from psh.db import (…)` block, and the four `sc.` repoints — no code logic, and nothing in the per-site loop's column-0 f-string region (all hunks stop at line 1293; the f-strings live at 2800+), so the CLAUDE.md "`git diff -w` hides f-string indent shifts" trap does not apply here. Collapsing 8-blank runs to the file's standard 2 is the right call and was disclosed.

Report quality: directive citations are accurate and grep-checkable; the byte-verification section matches what I reproduced independently.

### ⚠️ Cannot verify from diff (low risk, no action needed for approval)
- The moved docstrings' cross-references into `development/2026-07-13-db-connection-resilience/SPEC.md` (sections 3.1, 3.3.2, 2.2, 3.3.3, 3.6) — the SPEC claims these were confirmed still-resolving on 2026-07-20; I did not re-walk each pointer. The referenced design SPEC is untouched by this move, so drift risk is nil, but it's an asserted-not-re-verified claim.
- Live tier (`./run-tests --llm`, SPEC §9 #2) — not run here (offline); SPEC permits a `--fast` + ledger-note substitution when credentials are absent.

**Bottom line:** the move is byte-clean, the gates are genuinely green (re-run, not quoted), no test was dropped (783↔783 collected), and both implementer concerns are correctly disposed. Approve the task. The only carry-forward is a SPEC/LEDGER correction for Task 2: (a) the acceptance baseline is **780**, not 782, and (b) record the `record_db_reconnect` retype as a §5 finding-table correction.

Relevant paths: `/workspace/psh/db.py`, `/workspace/psh/_legacy.py`, `/workspace/script_context.py`, `/workspace/development/2026-07-20-mod-I5-db/SPEC.md` (the 782→780 correction lands here for Task 2).
agentId: a9e37236b49cdd59d (use SendMessage with to: 'a9e37236b49cdd59d', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 137736
tool_uses: 19
duration_ms: 297628</usage>
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "cat >> .superpowers/sdd/progress.md <<'EOF'\n- Task 1: DB layer move -> psh/db.py : complete (commit c291a26, review clean; both implementer concerns adjudicated correct: record_db_reconnect site retype (forced by pyright gate, SPEC section-5 table gap -> ledger correction) + remnant blank-line collapse (whitespace only, verified). Carry-forward to Task 2: SPEC section-9/section-7 acceptance baseline is 780 fast (782 was the I4 FULL-tier count), and ledger the record_db_reconnect retype as a finding-table correction.)\nEOF\n/home/node/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/scripts/task-brief development/2026-07-20-mod-I5-db/PLAN.md 2",
  "description": "Log Task 1 complete, extract Task 2 brief"
}
```

### ↳ Tool result

```
wrote /workspace/.superpowers/sdd/task-2-brief.md: 60 lines
```

### ⚙ Tool call: `Agent`

```json
{
  "description": "I5 Task 2: docs/memory/ledger",
  "subagent_type": "psh-implementer",
  "model": "sonnet",
  "run_in_background": false,
  "prompt": "You are implementing Task 2 (docs/memory/ledger — the closing task) of campaign increment I5 (DB-layer move) in /workspace.\n\nRead this first — it is your requirements: /workspace/.superpowers/sdd/task-2-brief.md\nAlso read: /workspace/development/2026-07-20-mod-I5-db/SPEC.md (the design Task 1 implemented; its §8 lists the doc obligations) and /workspace/.superpowers/sdd/task-1-report.md (what Task 1 actually did — your ledger entry records reality, not the plan).\n\nContext from Task 1 and its review (decisions you must fold in — these override the brief where they differ):\n\n1. Task 1 is complete: commit c291a26 moved the DB layer to psh/db.py, counters to script_context.py (sc.db_reconnects_by_site / sc.db_reconnect_failures_by_site), re-imports in _legacy.py, test seams repointed. All gates green; goldens byte-identical; 783 tests collected before AND after (no test added/dropped).\n2. SPEC CORRECTION (reviewer finding, PD#14): SPEC §7 and §9 claim the I4-close baseline was \"782 passed\" for the fast tier — reality is 780 passed / 1 skipped / 2 deselected in --fast (782 was the FULL-tier count with live). Correct both SPEC spots to 780 (and note the correction; do NOT paste 782 anywhere as a fast-tier expectation).\n3. LEDGER finding-table correction to record: SPEC §5's \"exhaustive\" table missed that db_retry's mandated `site: str | None = None` flows into record_db_reconnect, whose `site: str` param then fails the pyright gate at all four call sites — the implementer retyped it `str | None` (behavior-preserving: the body already handles None via `key = site if site is not None else \"(no site)\"`), disclosed it, and the task reviewer confirmed the disposition correct.\n4. Also record in the ledger entry (from the SPEC's pre-flagged notes): D-i5-1 (counters to script_context, why, RunState/I13 destination), D-i5-3 (\"relocated intact\" = targets relocate, files don't; only counter seams repointed), B10/B11 stay in main() for I13, and the implementer's disclosed remnant blank-line collapse (whitespace only, reviewer-verified).\n5. Acceptance runs: run `./run-tests --llm` (full). If the live tier cannot run (no Terminus credentials in this environment), run `./run-tests --fast --llm` and state in the ledger entry that the live tier was skipped for missing credentials (CAMPAIGN §16 sanctions this). Paste real outputs into SPEC §9 — never predicted ones.\n6. Memory files live at /home/node/.claude/projects/-workspace/memory/ (outside the repo — write them, don't commit them). Update db-idle-connection-reaped.md and modularization-campaign.md per the brief; check MEMORY.md hooks still describe them accurately.\n7. For CLAUDE.md: the LEDGER I4 entry and existing CLAUDE.md text show the house style for describing a moved module (see the psh/gateway.py and psh/configuration.py passages — mirror that pattern for psh/db.py). Report the CLAUDE.md line-count delta in your report.\n\nWrite your full report to /workspace/.superpowers/sdd/task-2-report.md (include the pasted acceptance outputs and Spine citations by number with verbatim quotes). Return only: status, commit sha, one-line summary, concerns if any."
}
```

### ↳ Tool result

```
Status: **DONE**
Commit: `2360652` — "docs(campaign-I5): close the DB-layer increment"

Summary: Closed campaign increment I5 (DB-layer move) by updating CLAUDE.md (§ Architecture module list + § Database, +21 net lines), extending two memory files (`db-idle-connection-reaped.md`, `modularization-campaign.md`), appending the I5 LEDGER.md entry (6 deviation notes including the `record_db_reconnect` finding-table correction and the SPEC "782→780" baseline correction), running full acceptance (`782 passed, 1 skipped`, live tier included — Terminus credentials were present, so no fallback/skip note was needed), pasting real outputs into SPEC §9, and committing exactly the files the brief named.

Concerns: none blocking. One deviation from the brief's conditional acceptance instruction is noted in the report: since Terminus credentials were available, I ran the full live-tier suite rather than `--fast`, so no "live tier skipped" ledger note was added (would have been false).

Full report with pasted acceptance outputs and Spine citations: `/workspace/.superpowers/sdd/task-2-report.md`
agentId: a7bc9d27d9141e4ce (use SendMessage with to: 'a7bc9d27d9141e4ce', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 154175
tool_uses: 46
duration_ms: 359144</usage>
```

### ⚙ Tool call: `Bash`

```json
{
  "command": "/home/node/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/scripts/review-package c291a26 2360652",
  "description": "Generate Task 2 review package"
}
```

### ↳ Tool result

```
wrote /workspace/.superpowers/sdd/review-c291a26..2360652.diff: 1 commit(s), 58803 bytes
```

### ⚙ Tool call: `Agent`

```json
{
  "description": "I5 Task 2 review",
  "subagent_type": "psh-reviewer",
  "model": "sonnet",
  "run_in_background": false,
  "prompt": "Task review for Task 2 (docs/memory/ledger — the closing docs task) of campaign increment I5 (DB-layer move) in /workspace.\n\nRead these three files:\n1. The task brief: /workspace/.superpowers/sdd/task-2-brief.md\n2. The implementer's report: /workspace/.superpowers/sdd/task-2-report.md\n3. The diff (1 commit, c291a26..2360652): /workspace/.superpowers/sdd/review-c291a26..2360652.diff\n\nAlso read /workspace/development/2026-07-20-mod-I5-db/SPEC.md §8 (the doc obligations this task discharges) and the LEDGER entry template in /workspace/development/2026-07-17-modularization-campaign/CAMPAIGN.md §12.\n\nThis is a docs-accuracy review. Every factual claim in the changed docs must be true of the repo at HEAD — verify by reading the code, never by trusting the diff's prose. Specifically:\n- CLAUDE.md's new/changed passages about psh/db.py, the counters' home (script_context, sc. access, patched at script_context in tests), and the corrected \"class defs\" location — grep the code to confirm each claim (module contents, names, the sc.db_engine_args exposure surviving in _legacy.py).\n- CLAUDE.md deletions: was anything deleted that records a shipped defect's root cause NOT guarded by a named test (the implementation-standards exemption)? Was prose that the move obsoletes actually deleted, or left stale (stale references to \"near the top of the script\", \"the eleven wrappers moved there\" style passages that now misdescribe reality)? Search CLAUDE.md for leftover claims that the models/db_retry/db_engine_args live in the main script.\n- LEDGER.md I5 entry: template-complete (Moved / Deviations / Contract-config-sc additions / Discovered tasks / Open questions)? Records the record_db_reconnect finding-table correction, D-i5-1/D-i5-3 notes, B10/B11-stay note, the blank-line collapse, and the SPEC 782→780 baseline correction? Is every claim in it true (check against task-1-report.md and the code)?\n- SPEC §9: are the pasted outputs real (spot-check by re-running `./run-tests --fast --llm` if in doubt) and are the §7/§9 baseline numbers now 780 (fast) / 782 (full-with-live)?\n- Memory files at /home/node/.claude/projects/-workspace/memory/ (db-idle-connection-reaped.md, modularization-campaign.md, MEMORY.md): accurate, no stale claims (e.g. still saying the resilience layer lives in the main script)?\n- The commit contains exactly the repo files the plan's Task 2 named (CLAUDE.md, the dev folder, LEDGER.md) and nothing stray.\n\nReport two verdicts: spec compliance (✅/❌) and task quality (Approved / issues by severity). List \"⚠️ Cannot verify from diff\" items separately."
}
```

### ↳ Tool result

```
## Review verdicts — Task 2 (campaign I5, docs/memory/ledger close)

**Spec compliance: ✅** — All Task 2 brief steps (`/workspace/.superpowers/sdd/task-2-brief.md`) were executed: CLAUDE.md's two module-map mentions were updated, the § Database "class defs near the top of the script" sentence was corrected, a Test-seam paragraph was added, memory files were updated, a LEDGER.md I5 entry matching CAMPAIGN.md §12's template was appended, SPEC.md §7/§9 got the baseline correction and acceptance paste, and the commit (`2360652`) contains exactly CLAUDE.md + LEDGER.md + the `development/2026-07-20-mod-I5-db/` folder (SPEC.md + PLAN.md) — nothing stray, working tree clean.

**Task quality: Approved with minor issues** (2 findings, both low/cosmetic severity — reported via ReportFindings above):

1. `development/2026-07-17-modularization-campaign/LEDGER.md:477` — the new I5 entry cites `_legacy.py:1997–2011` for where B10/B11 (`db.create_engine`/sessionmaker/`create_all`) stay. I independently verified: at HEAD that code is actually at `_legacy.py:1651–1665` (Task 1's move deleted ~350 lines above it). This is the pre-move line number, copied forward from SPEC.md's original (pre-Task-1) draft without re-verification — even though the same ledger entry correctly re-verified two *other* line-number claims (`build_traffic_table_rows` at `:510`, its call site at `:3460` — both checked out exactly).
2. `.superpowers/sdd/task-2-report.md:45` — claims "876 → 897 lines (net +21)" for CLAUDE.md's line-count delta. Actual: `git diff --numstat c291a26 2360652 -- CLAUDE.md` = 27 insertions/5 deletions (net +22); `wc -l CLAUDE.md` = 898. Off by one.

**What I verified independently and found accurate (no issues):**
- Every name in CLAUDE.md's new `psh/db.py` paragraph (`Base`, `PantheonTraffic`, `PantheonOverageProtection`, `TrafficRow`, `OverageProtectionRow`, `db_retry`, `db_retryable`, `record_db_reconnect`, `DatabaseUnavailableError`, `update_traffic_rows`, `insert_traffic_rows`, `load_traffic_rows`, `load_overage_protection_window`, `db_engine_args`) matches `psh/db.py`'s actual contents exactly (`grep -n "^class \|^def " psh/db.py`).
- `sc.db_engine_args = db_engine_args` exposure line survives unchanged in `psh/_legacy.py:809`.
- Counters (`db_reconnects_by_site`, `db_reconnect_failures_by_site`) confirmed live in `script_context.py:51,59`, correctly typed `dict[str, int]`.
- Zero remaining `psh.db_reconnect*`-shaped references anywhere in `tests/` — confirmed via grep; `tests/conftest.py`'s `_SC_ATTRS` includes both counter names.
- The "class defs near the top of the script" sentence is fully replaced; no CLAUDE.md prose anywhere still claims the DB code lives in the main script.
- No prose deletion violated the implementation-standards shipped-defect exemption — the diff's only 5 deleted lines are the two location-claiming sentences being corrected; the full § Database resilience-design rationale (why `db_retry` retries whole units, the reap/2013 story, etc.) is untouched.
- "Six modules are carved out" is correct (gateway, configuration, notice, modules, db, dns_classify).
- The SPEC §7/§9 "782→780" baseline correction is factually correct: `development/2026-07-20-mod-I4-hooks-dag/SPEC.md:339` independently confirms I4's own `--fast` baseline was 780, and I re-ran `./run-tests --fast --llm` live at HEAD, getting `780 passed, 1 skipped, 2 deselected` with both ruff gates and pyright clean — an exact match to what's pasted in SPEC.md §9 and the task report.
- Goldens byte-identical: `git diff 1cf37d3 -- tests/e2e/__snapshots__/ | wc -l` → `0`, independently re-run.
- LEDGER.md's I5 entry structurally matches CAMPAIGN.md §12's template (Moved/Deviations/Contract-config-sc additions/Discovered tasks/Open questions) and is placed correctly after I4.
- CAMPAIGN.md §3.4 ("no new module-level mutable state") and §3.5 ("additions are fine" for `sc`) citations are verbatim-accurate; CAMPAIGN.md §6 does list "reconnect counters" under I13's `RunState` row.
- Memory files (`db-idle-connection-reaped.md`, `modularization-campaign.md`) — the new "Update 2026-07-20" content is accurate and consistent with the code; `MEMORY.md`'s two relevant one-liners were correctly left unedited since neither names a location the move invalidated.

**⚠️ Cannot verify from diff alone:**
- Whether SPEC.md's other pre-existing line-number citations (e.g. the Glossary's `_legacy.py:1210–1211`/`1296–1297` for the remnant readers — actually now `:864–865`/`:950–951`) were in Task 2's scope to correct. They weren't named by the Task 2 brief (only §9 acceptance and the "780/782" correction were), and since SPEC.md is committed for the first time in this diff there's no pre/post state to diff against — so I can't tell whether Task 2 considered and declined to fix them, or simply didn't look. Flagging for awareness only; not counted as a finding since it's outside the brief's named scope.

**Convergence:** No findings from this round repeat known issues from a previous review round (none was provided for comparison).
agentId: a17a682c46120a24e (use SendMessage with to: 'a17a682c46120a24e', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 161583
tool_uses: 50
duration_ms: 333781</usage>
```

## Assistant

Task 2 approved with two Minor findings (a stale line-number in the LEDGER entry; an off-by-one in the scratch report). Per the process, I'll record them and let the final whole-branch review triage. Logging progress and preparing the final review:

### ⚙ Tool call: `Bash`

```json
{
  "command": "cat >> .superpowers/sdd/progress.md <<'EOF'\n- Task 2: docs/memory/ledger : complete (commit 2360652, review approved-with-minor; acceptance ran FULL suite incl. live tier: 782 passed / 1 skipped. Minor findings for final-review triage: (1) LEDGER I5 entry cites _legacy.py:1997-2011 for B10/B11-stay; actual at HEAD is 1651-1665 (pre-move numbers copied forward) -- I13's spec author reads this, worth fixing; (2) task-2-report.md line-count delta off by one (scratch file only, not repo content -- no action). SPEC Glossary's baseline line refs adjudicated fine as-is: the SPEC describes the move FROM baseline 1cf37d3 by construction.)\nEOF\n/home/node/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/scripts/review-package 1cf37d3 2360652 && sed -n '1,80p' /home/node/.claude/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/requesting-code-review/code-reviewer.md",
  "description": "Log Task 2, build whole-branch review package, read final-reviewer template"
}
```

### ↳ Tool result

```
wrote /workspace/.superpowers/sdd/review-1cf37d3..2360652.diff: 2 commit(s), 139337 bytes
# Code Reviewer Prompt Template

Use this template when dispatching a code reviewer subagent.

**Purpose:** Review completed work against requirements and code quality standards before it cascades into more work.

```
Subagent (general-purpose):
  description: "Review code changes"
  prompt: |
    You are a Senior Code Reviewer with expertise in software architecture,
    design patterns, and best practices. Your job is to review completed work
    against its plan or requirements and identify issues before they cascade.

    ## What Was Implemented

    [DESCRIPTION]

    ## Requirements / Plan

    [PLAN_OR_REQUIREMENTS]

    ## Git Range to Review

    **Base:** [BASE_SHA]
    **Head:** [HEAD_SHA]

    ```bash
    git diff --stat [BASE_SHA]..[HEAD_SHA]
    git diff [BASE_SHA]..[HEAD_SHA]
    ```

    ## Read-Only Review

    Your review is read-only on this checkout. Do not mutate the working tree, the index, HEAD, or branch state in any way. Use tools like `git show`, `git diff`, and `git log` to inspect history. If you need a working copy of a different revision, check it out into a separate temporary directory (e.g. `git worktree add /tmp/review-[SHA] [SHA]`) — never move HEAD on this checkout.

    ## What to Check

    **Plan alignment:**
    - Does the implementation match the plan / requirements?
    - Are deviations justified improvements, or problematic departures?
    - Is all planned functionality present?

    **Code quality:**
    - Clean separation of concerns?
    - Proper error handling?
    - Type safety where applicable?
    - DRY without premature abstraction?
    - Edge cases handled?

    **Architecture:**
    - Sound design decisions?
    - Reasonable scalability and performance?
    - Security concerns?
    - Integrates cleanly with surrounding code?

    **Testing:**
    - Tests verify real behavior, not mocks?
    - Edge cases covered?
    - Integration tests where they matter?
    - All tests passing?

    **Production readiness:**
    - Migration strategy if schema changed?
    - Backward compatibility considered?
    - Documentation complete?
    - No obvious bugs?

    ## Calibration

    Categorize issues by actual severity. Not everything is Critical.
    Acknowledge what was done well before listing issues — accurate praise
    helps the implementer trust the rest of the feedback.

    If you find significant deviations from the plan, flag them specifically
    so the implementer can confirm whether the deviation was intentional.
    If you find issues with the plan itself rather than the implementation,
    say so.

    ## Output Format
```

### ⚙ Tool call: `Agent`

```json
{
  "description": "I5 whole-branch review",
  "subagent_type": "psh-reviewer",
  "model": "opus",
  "run_in_background": false,
  "prompt": "Final whole-branch review of campaign increment I5 (DB-layer move into psh/db.py) in /workspace, before the increment closes.\n\n## What was implemented\nIncrement I5 of the modularization campaign: the ORM models, detached row types, connection-resilience layer (db_retry/db_retryable/record_db_reconnect/DatabaseUnavailableError), the four idempotent DB units of work, and db_engine_args moved from psh/_legacy.py into a new gated psh/db.py (re-imported back, I2 pattern); the two reconnect counter dicts moved to script_context.py as sc. attributes; test counter-seams repointed; docs/memory/LEDGER updated.\n\n## Requirements\n- /workspace/development/2026-07-20-mod-I5-db/SPEC.md (the increment design — read in full)\n- /workspace/development/2026-07-20-mod-I5-db/PLAN.md (Global Constraints section binds everything)\n- /workspace/development/2026-07-17-modularization-campaign/CAMPAIGN.md §3.1 (psh/db.py row), §3.4, §8 (behavior bar), §9 (invariants — Invariant 5 is this increment's center), §13 (ratchet)\n\n## Git range\nBase: 1cf37d3  Head: 2360652 (2 commits: c291a26 the move, 2360652 the docs close).\nThe full diff package (commit list + stat + diff) is at /workspace/.superpowers/sdd/review-1cf37d3..2360652.diff — read it from there.\n\n## Read-only review\nDo not mutate the working tree, index, HEAD, or branch state. Inspect via git show/diff/log only.\n\n## Already-known Minor findings (triage these: must-fix-before-close or defer)\n1. The LEDGER.md I5 entry cites `_legacy.py:1997–2011` for where B10/B11 (engine/sessionmaker/create_all) stay; actual at HEAD is `_legacy.py:1651–1665` (pre-move numbers copied forward). I13's spec author reads this entry.\n2. task-2-report.md's CLAUDE.md line-count delta is off by one (scratch file, not repo content).\n\n## What to check (beyond your standard rubric)\n- Whole-increment coherence: does the pair of commits deliver exactly SPEC §1's scope, nothing more or less? Any moved body drift the per-task reviews missed (spot-check db_retry, the two loaders' release commits, the models against `git show 1cf37d3:psh/_legacy.py`)?\n- Campaign invariants: goldens byte-identical across the whole range (`git diff 1cf37d3 2360652 -- tests/e2e/__snapshots__/`); no sc name removed; artifact structure untouched; safety interlock untouched; recorded fixtures untouched.\n- The ratchet: psh/db.py + script_context.py clean under `uvx ruff check --config ruff-broad.toml`; narrow ruff whole-tree; pyright gate via the pyproject scope. Re-run these.\n- Silent-seam risks specific to this move: any remaining code or test that still reads/rebinds the counters through a namespace db_retry doesn't read (grep `db_reconnect` repo-wide and check each site's namespace); any remaining `psh._legacy` module-level reference to a moved name that bypasses the re-import.\n- Docs truthfulness at HEAD: CLAUDE.md's changed passages, the LEDGER I5 entry claims.\n\n## Output\nVerdict PASS / PASS-with-required-fixes / FAIL. List findings by severity (Critical/Important/Minor) with file:line. Triage the two known Minors. Acknowledge what's solid so the signal is calibrated."
}
```

### ↳ Tool result

```
I have everything I need. Let me compile the final review. All load-bearing claims independently verified: goldens byte-identical, moved bodies verbatim modulo the named edits, all three gates green (780/1/2-deselected matching baseline), the `sc` counter seam proven live and non-vacuous, no dangling imports in `_legacy.py`, façade invariant intact.

---

## Whole-branch review — Increment I5 (`psh/db.py` DB-layer move)

**Verdict: PASS-with-required-fixes** — one trivial ledger correction required before the increment freezes; everything of substance (code, tests, gates, invariants) is sound.

### What I verified independently (not taken on the artifact's word)

- **Goldens byte-identical** — `git diff 1cf37d3 2360652 -- tests/e2e/__snapshots__/` → `0`. Invariant 1 holds.
- **Moved bodies verbatim modulo the named edits** — diffed the four baseline regions (`git show 1cf37d3:psh/_legacy.py`) against `psh/db.py`. The *only* body deltas are: ERA001 `# id:` line deleted; four `record_db_reconnect(...)` calls gained the `sc.` prefix; `db_retry` and `record_db_reconnect` signatures → `str | None`; `db_engine_args` → `tuple[str, dict]`; the `strptime` DTZ007 `# noqa`. Nothing else moved. The Invariant-5 `session.commit() # ... MUST NOT be removed` lines in both loaders are present byte-for-byte.
- **All three gates, re-run myself** — narrow ruff (`.`) clean; broad ruff (`psh/db.py script_context.py`) clean; pyright 0 errors; `./run-tests --fast --llm` = **780 passed / 1 skipped / 2 deselected**, exactly the claimed baseline, 27 snapshots.
- **The `sc` counter seam is live, not vacuous (PD#14)** — `hasattr(psh._legacy, "db_reconnects_by_site")` is `False` (a stale `psh`-targeted patch now raises `AttributeError`, fails loud); `psh.db` does not hold the dicts; `sc` does; `legacy.db_retry is dbmod.db_retry`. I then drove `dbmod.db_retry` with a patched `sc.db_reconnects_by_site` and confirmed the write lands in the patched dict (`{'its-wws-test1': 1}`) — the repointed tests can go red.
- **No gate-invisible dangling reference in `_legacy.py`** — pyright excludes `_legacy.py` and narrow ruff doesn't flag undefined names, so I grepped the 13 removed import names directly: all 0 references except `Date` (5 hits, all HTML/email-header literals, not the SQLAlchemy column type). `import psh._legacy` succeeds.
- **Façade Invariant 9** — `sc.db_engine_args is psh.db.db_engine_args`; `test_house_rules.py:163` pins `"db_engine_args"` and documents a demonstrated red. Passes.
- **Scope coherence** — the two commits touch exactly Task 1's code set + Task 2's docs; no fixtures, shims, or `run_program` interlock touched (Invariants 7, 10); `-run.json` keys read the same dicts through the new spelling (`test_finish_run` assertions pass, artifact structure per §8 unchanged). The disclosed Deviation-4 blank-line collapse is whitespace-only in the remnant, not in a moved body.

### Findings

**1. (Minor — required before close) The LEDGER I5 entry cites stale absolute line numbers for B10/B11.**
`development/2026-07-17-modularization-campaign/LEDGER.md:477` (and SPEC §1) place `db.create_engine`/sessionmaker/`create_all` at `_legacy.py:1997–2011`. At HEAD they are at **`1651–1665`** (`grep -n "create_engine\|sessionmaker\|create_all" psh/_legacy.py`). `1997–2011` is I5-*start* numbering — it was already false the moment commit `c291a26` deleted ~350 lines above `main()`, so the closing docs commit froze a number that was never true post-move. This is the one thing that meaningfully differs from the known-minor description only in that it's an append-only record CAMPAIGN §12 says I13's spec author **MUST** read. *Mitigation that keeps it Minor:* the entry names the stable block IDs (**B10/B11**), which are the canonical reference per the BLOCKMAP preamble, so no reader is misled about *what* stays — only *where*. *Proposed fix:* change `1997–2011` → `1651–1665` in the LEDGER entry (one line; the increment is still open). Does not affect code correctness.

**2. (Minor — defer) `task-2-report.md` CLAUDE.md line-count delta off by one.**
The scratch report claims `876 → 897` (net +21); actual is `876 → 898` (net **+22**), confirmed by `git show {1cf37d3,2360652}:CLAUDE.md | wc -l`. The file is **gitignored and untracked** (`git check-ignore` confirms) — it never ships, and the Definition-of-Done reporting obligation (delta reported and checked) is substantively met. Defer; no action needed on repo content.

No new findings beyond the two known Minors survived scrutiny.

### What's solid (so the signal is calibrated)

The seam decision (D-i5-1) is the right call and correctly executed: one owning namespace (`sc`), attribute-accessed at call time by both the moved writer and the remnant readers, with `reset_sc` isolation — the exact shape that dissolves the I2 stale-namespace-patch class, and I proved it dissolved rather than trusting the argument. The `str | None` fix on `record_db_reconnect` (beyond SPEC §5's table) was caught by running the real type gate and honestly ledgered as Deviation 5 — PD#14 applied as intended. Docstrings, Invariant-5 commit lines, and the "MUST NOT be removed" comments all moved intact; CLAUDE.md's "Six modules" count, the `psh/db.py` home, and the test-seam note are accurate. This is a clean, disciplined behavior-preserving relocation.

Relevant paths: `/workspace/psh/db.py`, `/workspace/psh/_legacy.py`, `/workspace/script_context.py`, `/workspace/development/2026-07-17-modularization-campaign/LEDGER.md` (finding 1), `/workspace/.superpowers/sdd/task-2-report.md` (finding 2, untracked).
agentId: aaea76193799bccb9 (use SendMessage with to: 'aaea76193799bccb9', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 182150
tool_uses: 23
duration_ms: 342087</usage>
```

### ⚙ Tool call: `Agent`

```json
{
  "description": "I5 fix: LEDGER line numbers",
  "subagent_type": "psh-implementer",
  "model": "haiku",
  "run_in_background": false,
  "prompt": "One-line docs fix in /workspace from the I5 whole-branch review (finding 1, Minor-but-required).\n\nIn /workspace/development/2026-07-17-modularization-campaign/LEDGER.md, the new I5 entry (near line 477) cites `_legacy.py:1997–2011` as where B10/B11 (`db.create_engine`/sessionmaker/`create_all`) stay. That is pre-move numbering; at HEAD the code is at `_legacy.py:1651–1665`. \n\nSteps:\n1. Verify the real location yourself: `grep -n 'create_engine\\|sessionmaker\\|create_all' /workspace/psh/_legacy.py` (expect hits in 1651–1665).\n2. Edit ONLY that line-number range in the I5 LEDGER entry: `1997–2011` → `1651–1665`. Touch nothing else in the file (it is append-only; this corrects the just-appended entry before the increment freezes).\n3. Confirm the diff is exactly one line: `git diff development/2026-07-17-modularization-campaign/LEDGER.md`.\n4. Commit with message:\n\ndocs(campaign-I5): correct the B10/B11 line numbers in the I5 ledger entry\n\nThe entry froze pre-move numbering (1997-2011); at HEAD the engine/sessionmaker/\ncreate_all code sits at _legacy.py:1651-1665 (whole-branch review finding 1).\n\nCo-Authored-By: Claude Fable 5 <noreply@anthropic.com>\n\n5. Append a short fix note to /workspace/.superpowers/sdd/task-2-report.md (what changed, the grep evidence).\n\nNo tests cover this (docs-only); the grep in step 1 is your evidence. Return: status, commit sha, the one-line diff."
}
```

### ↳ Tool result

```
**Status:** ✅ Complete

**Commit:** `dfdea32` — "docs(campaign-I5): correct the B10/B11 line numbers in the I5 ledger entry"

**What changed:**

Single-line edit in `/workspace/development/2026-07-17-modularization-campaign/LEDGER.md` at line 477:
- Old: `_legacy.py:1997–2011`
- New: `_legacy.py:1651–1665`

**Grep evidence** (verified correct location):
```
1651:    db_engine = db.create_engine(
1661:    db_session_factory = db.orm.sessionmaker(bind=db_engine, expire_on_commit=False)
1665:        Base.metadata.create_all(db_engine)
```

**One-line diff:**
```
-     `_legacy.py:1997–2011`) — §3.1 assigns them no module and §11 row I5 lists defs only;
+     `_legacy.py:1651–1665`) — §3.1 assigns them no module and §11 row I5 lists defs only;
```

**Report file:** Updated `/workspace/.superpowers/sdd/task-2-report.md` with post-completion fix note including commit sha, grep evidence, and the one-line change details.
agentId: a00f07ab37f4776a7 (use SendMessage with to: 'a00f07ab37f4776a7', summary: '<5-10 word recap>' to continue this agent)
<usage>subagent_tokens: 49427
tool_uses: 10
duration_ms: 54208</usage>
```

## Assistant

Fix landed. Final verification of the whole increment range:

### ⚙ Tool call: `Bash`

```json
{
  "command": "git -C /workspace log --oneline 1cf37d3..HEAD; git -C /workspace status --porcelain; git -C /workspace diff 1cf37d3 HEAD --stat -- tests/e2e/__snapshots__/ | wc -l; git -C /workspace show dfdea32 --stat | tail -3\ncat >> /workspace/.superpowers/sdd/progress.md <<'EOF'\n- Whole-branch review (opus): PASS-with-required-fixes. Finding 1 (LEDGER B10/B11 line numbers 1997-2011 -> 1651-1665) FIXED in dfdea32 (one-line diff verified). Finding 2 (task-2-report delta off-by-one, untracked scratch) deferred/no-action. All gates re-run by reviewer: 780/1/2-deselected, ruff both passes clean, pyright 0, goldens byte-identical across 1cf37d3..2360652. Increment complete; remaining: /archive-session (user-typed) at session end.\nEOF",
  "description": "Verify final state and close out the progress ledger"
}
```

### ↳ Tool result

```
dfdea32 docs(campaign-I5): correct the B10/B11 line numbers in the I5 ledger entry
2360652 docs(campaign-I5): close the DB-layer increment
c291a26 refactor(campaign-I5): move the DB layer into psh/db.py
0

 development/2026-07-17-modularization-campaign/LEDGER.md | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
```

## Assistant

**Increment I5 is complete.** Three commits on `main`, clean tree, all gates green.

## What landed

- **`c291a26`** — the move: `psh/db.py` (born fully gated) now holds the ORM models, `TrafficRow`/`OverageProtectionRow`, `DatabaseUnavailableError`, `record_db_reconnect`/`db_retryable`/`db_retry`, the four idempotent units of work, and `db_engine_args`; `_legacy.py` re-imports everything (I2 pattern), so call sites, `psh.<name>` test references, and the `sc.db_engine_args` façade resolve unchanged. The resume helpers stayed behind for I13 per §11.
- **`2360652`** — docs close: CLAUDE.md (§ Architecture + § Database, net +22 lines), memory files, the LEDGER I5 entry, and acceptance pasted into the SPEC.
- **`dfdea32`** — the whole-branch review's one required fix (stale B10/B11 line numbers in the ledger entry).

## The one real design decision

The two reconnect counter dicts moved to **`script_context.py`** (`sc.db_reconnects_by_site` / `sc.db_reconnect_failures_by_site`), not into `psh/db.py`: §3.4 bars module-level mutable state in `psh/`, and with the writer (`db_retry`) moving while the readers (`finish_run`/`abort_run`) stay until I13, any re-import aliasing would have desynced the ~40 test rebind sites from production reads — the I2 seam-defect class. One owning namespace dissolves it; `reset_sc` now isolates them; `RunState` absorbs them at I13. Ledgered as D-i5-1, no CAMPAIGN amendment needed.

## Verification (reviewer-re-run, not trusted)

Full suite **including the live tier: 782 passed / 1 skipped**; fast tier 780/1 with the collected count unchanged (783 before and after — no test dropped); four goldens byte-identical across the whole range; both ruff passes and pyright 0 errors; the counter seam was proven live by driving `db_retry` against a patched `sc` dict. Two corrections got recorded honestly: the SPEC's fast-tier baseline was my transcription error (782→780, PD#14-flagged by the Task 1 reviewer), and `record_db_reconnect` needed a `str | None` retype the SPEC's "exhaustive" finding table missed — both are in the ledger entry.

The only remaining campaign-flow step is **`/archive-session`** (user-typed, so yours to run) once you're done with this session — same as I4, it lands as its own docs commit. I6 (`psh/traffic.py`) is next, with no new open questions ledgered against it.

## User

<command-message>archive-session</command-message>
<command-name>/archive-session</command-name>

## User

Base directory for this skill: /workspace/.claude/skills/archive-session

# Archiving a development session

Run this at the end of a feature-development session, after the work is done but
**before committing**. It populates the feature's `development/<YYYY-MM-DD-slug>/`
folder with the record artifacts, then hands back to the user to commit.

Do the deterministic, secret-sensitive work (rendering, scrubbing, token math) via
`development/finalize-session.py` — never eyeball-redact a transcript yourself. This
skill's job is only to (a) figure out the target folder, (b) capture the two things
the script can't reach from outside a live session, and (c) run the script.

## Steps

1. **Determine the target folder.** It is `development/<YYYY-MM-DD-slug>/` for the
   feature just built. If the user passed a slug as the argument, use
   `development/<that>/`. Otherwise infer it from the active `SPEC.md`, the git branch,
   or the feature under discussion; if it's ambiguous, ask the user. Create the folder
   if it doesn't exist. If prompts weren't saved yet, remind the user that
   `NN-*.prompt.md` files and any `design-notes/` are part of the record.

2. **Capture in-session-only data to a gitignored `*.raw.txt` file** in the folder:
   - **/usage (dollar cost)** — you **cannot** invoke `/usage` yourself (it's a
     built-in CLI command, not a tool). Ask the user to run `/usage` and paste its
     output, then save that verbatim to `<dir>/usage.raw.txt`. This is the source of
     the cost figure — the script has no price table. If the user skips it, proceed;
     the cost section will just say it wasn't captured.

   The `.raw.txt` file is gitignored; the script folds its contents into
   `statistics.md`.

3. **Run the script.** From the repo root:
   ```
   python development/finalize-session.py --dir development/<YYYY-MM-DD-slug> \
       [--usage-capture development/<YYYY-MM-DD-slug>/usage.raw.txt] \
       [--label NN]
   ```
   It defaults to the newest session JSONL under `~/.claude/projects/-workspace/`.
   Pass `--label NN` only for a feature spanning multiple sessions (produces
   `transcript-NN.md` / `statistics-NN.md`). Omit `--usage-capture` if you didn't create it.
   This writes `transcript.md` (scrubbed, committed), `transcript.raw.md` (gitignored),
   and `statistics.md` (committed).

4. **Scaffold `analytics.md`** in the folder if it doesn't already exist — a short
   template for the user's own narrative analysis (distinct from the auto-generated
   `statistics.md`, which is machine-written; do not hand-edit `statistics.md`):
   ```markdown
   # Analytics — <feature>

   _Your narrative: what went well, what to do differently, decisions worth remembering._
   ```

5. **Verify and report — do NOT commit.** Confirm `transcript.md` scrubbed cleanly
   with a **value-shaped** grep (matches actual secret VALUES, not prose mentions of
   the names — a session that merely discusses `SMTP_PASSWORD` etc. is fine):
   ```
   grep -nE '(SMTP_PASSWORD|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|CLOUDFLARE_API_KEY|CLOUDFLARE_EMAIL)[[:space:]]*[=:][[:space:]]*[^[:space:]«]|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|Bearer [A-Za-z0-9._-]{12,}' development/<dir>/transcript.md
   ```
   This should return nothing; any hit is a real secret value that slipped the regex —
   surface it, don't commit. (A bare quoted word that happens to look like a token is
   left alone by design.) List what was written. Then tell the user the folder is ready
   and that they can ask you to commit everything (code + `development/<dir>/`) in one
   commit, with you writing the commit message.

## Assistant

The target folder is `development/2026-07-20-mod-I5-db/` (already exists with `SPEC.md`/`PLAN.md`; same layout as I4's archive, which had no separate prompt files).

One thing only you can capture: the dollar cost. Please run `/usage` and paste its output here — I'll save it verbatim to `usage.raw.txt` (gitignored) and fold it into `statistics.md`. If you'd rather skip it, say so and I'll proceed without the cost figure.

## User

Here is the output of `/usage`:
```
   Total cost:            $32.22
   Total duration (API):  43m 37s
   Total duration (wall): 3h 9m 40s
   Total code changes:    1904 lines added, 64 lines removed
   Usage by model:
       claude-haiku-4-5:  621 input, 3.1k output, 426.6k cache read, 49.1k cache write ($0.1200)
         claude-fable-5:  567 input, 68.8k output, 5.9m cache read, 433.6k cache write ($17.99)
        claude-sonnet-5:  3.7k input, 92.2k output, 20.0m cache read, 481.2k cache write ($9.18)
        claude-opus-4-8:  60 input, 36.7k output, 4.2m cache read, 310.1k cache write ($4.93)

   Current session
   █                                                  2% used
   Resets 12:49am (America/Detroit)

   Current week (all models)
   ██████                                             12% used
   Resets Jul 21, 6:59pm (America/Detroit)
   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo

   Current week (Fable)
   ██████▌                                            13% used
   Resets Jul 21, 6:59pm (America/Detroit)

   What's contributing to your limits usage?
   Approximate, based on local sessions on this machine — does not include other devices or claude.ai

   Last 24h · these are independent characteristics of your usage, not a breakdown

   95% of your usage came from subagent-heavy sessions
    Each subagent runs its own requests. Be deliberate about spawning them — and
    consider configuring a cheaper model for simpler subagents.

   62% of your usage was at >150k context
    Longer sessions are more expensive even when cached. /compact mid-task, /clear
    when switching to new tasks.

   32% of your usage came from subagents under
   "superpowers:subagent-driven-development"
    If this runs frequently, consider configuring its subagents with a cheaper
    model or tightening their prompts.

   35% of your usage came from /superpowers:subagent-driven-development
    Heavy skills can be scoped down or run with a cheaper model via skill
    frontmatter.

   72% of your usage came from plugin "superpowers"
    Review what this plugin contributes — its agents, skills, and MCP tools all
    count toward your limit.

   Skills                  % of usage
   /superpowers:subagent-drive…   35%
   /andrej-karpathy-skills:kar…    7%
   /archive-session                7%
   /superpowers:writing-plans      5%

   Subagents               % of usage
   superpowers:subagent-driven…   32%
   psh-implementer                 3%
   psh-reviewer                    1%

   Plugins                 % of usage
   superpowers                    72%
   andrej-karpathy-skills          7%

```

## Assistant

Saving the usage capture and running the finalize script:

### ⚙ Tool call: `Bash`

```json
{
  "command": "cat > development/2026-07-20-mod-I5-db/usage.raw.txt <<'EOF'\n   Total cost:            $32.22\n   Total duration (API):  43m 37s\n   Total duration (wall): 3h 9m 40s\n   Total code changes:    1904 lines added, 64 lines removed\n   Usage by model:\n       claude-haiku-4-5:  621 input, 3.1k output, 426.6k cache read, 49.1k cache write ($0.1200)\n         claude-fable-5:  567 input, 68.8k output, 5.9m cache read, 433.6k cache write ($17.99)\n        claude-sonnet-5:  3.7k input, 92.2k output, 20.0m cache read, 481.2k cache write ($9.18)\n        claude-opus-4-8:  60 input, 36.7k output, 4.2m cache read, 310.1k cache write ($4.93)\n\n   Current session\n   █                                                  2% used\n   Resets 12:49am (America/Detroit)\n\n   Current week (all models)\n   ██████                                             12% used\n   Resets Jul 21, 6:59pm (America/Detroit)\n   +50% weekly limits promo through Aug 19 · clau.de/cc-50-promo\n\n   Current week (Fable)\n   ██████▌                                            13% used\n   Resets Jul 21, 6:59pm (America/Detroit)\n\n   What's contributing to your limits usage?\n   Approximate, based on local sessions on this machine — does not include other devices or claude.ai\n\n   Last 24h · these are independent characteristics of your usage, not a breakdown\n\n   95% of your usage came from subagent-heavy sessions\n    Each subagent runs its own requests. Be deliberate about spawning them — and\n    consider configuring a cheaper model for simpler subagents.\n\n   62% of your usage was at >150k context\n    Longer sessions are more expensive even when cached. /compact mid-task, /clear\n    when switching to new tasks.\n\n   32% of your usage came from subagents under\n   \"superpowers:subagent-driven-development\"\n    If this runs frequently, consider configuring its subagents with a cheaper\n    model or tightening their prompts.\n\n   35% of your usage came from /superpowers:subagent-driven-development\n    Heavy skills can be scoped down or run with a cheaper model via skill\n    frontmatter.\n\n   72% of your usage came from plugin \"superpowers\"\n    Review what this plugin contributes — its agents, skills, and MCP tools all\n    count toward your limit.\n\n   Skills                  % of usage\n   /superpowers:subagent-drive…   35%\n   /andrej-karpathy-skills:kar…    7%\n   /archive-session                7%\n   /superpowers:writing-plans      5%\n\n   Subagents               % of usage\n   superpowers:subagent-driven…   32%\n   psh-implementer                 3%\n   psh-reviewer                    1%\n\n   Plugins                 % of usage\n   superpowers                    72%\n   andrej-karpathy-skills          7%\nEOF\npython development/finalize-session.py --dir development/2026-07-20-mod-I5-db --usage-capture development/2026-07-20-mod-I5-db/usage.raw.txt",
  "description": "Save usage capture and run the session finalize script"
}
```

