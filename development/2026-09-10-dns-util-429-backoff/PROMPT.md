# PROMPT

Three turns, in a single session on 2026-09-10, in this order. Reproduced verbatim.

---

**1.**

> Look at `find-platform-domains-dns`. If the Pantheon API returns HTTP 429, does the script sleep
> and then retry the call, or does something else happen?

---

**2.** (with the output of a live organization sweep pasted in — reproduced in SPEC §3)

> What do you recommend in terms of the simplest, lowest-impact change to avoid this problem in
> **most** cases?

---

**3.**

> yes, implement it

---

**4.**

> write the SPEC amendment in a new development folder

---

## Note on ordering

The implementation preceded this spec, which inverts the usual
`prompts/new-feature-standards.md` flow (spec → plan → implement). It is recorded here rather
than smoothed over: turn 2 asked for a recommendation, the recommendation *was* the design, turn 3
approved it, and the spec was written afterwards at turn 4 to amend the archive. The
**tests** were still written first — see SPEC §8.
