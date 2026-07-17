# Adversarial Review

A **standards overlay** for reviewing a spec or plan document. This file owns the *process*;
the *bar* lives in the Spine.

> **Read `prompts/directives.md` first** — the Posture, the 14 Prime Directives, the
> Engineering Preferences, and the spec quality bar, in one copy. This file does not restate
> them. It used to, and the copies **drifted**: PD#11 gained a `/domain-modeling` mandate in
> one file and not the other, with nothing saying which governed — and the reviewer read the
> stale one. Directives are cited here **by number**.

Use this for defects in a **document**. It is NOT for runtime failures: those go to
`prompts/debugging-standards.md` and `/diagnosing-bugs`, which gates on a command that goes
red on the bug's code path — something that cannot exist for a spec defect.

**Step 1: Dispatch reviewer subagent**

Dispatch with **`subagent_type: "psh-reviewer"`** (`.claude/agents/psh-reviewer.md`). That
agent carries the read list, so the standards reach the reviewer as configuration rather
than as prose you have to remember to paste. Its fresh context — seeing only the artifact,
never the brainstorming or writing-plans conversation — is what makes the review independent.

Give the subagent:

- The file path(s) of the document(s) just written: spec docs, plan docs, and my original
  brainstorming request.
- This instruction: *"Read the document(s), independently verify load-bearing claims (the
  facts the spec/plan rests on) rather than trusting them, and review on the **ten**
  dimensions below. For each dimension, note PASS or list specific issues with suggested
  fixes."*

**Dimensions — ten, exhaustive:**

1. **Correctness** — Are there any claims that did not verify? Gaps?
2. **Completeness** — Are all requirements addressed? Missing edge cases?
3. **Consistency** — Do parts of the document(s) agree with each other? Contradictions?
4. **Clarity** — Could an engineer implement this without asking questions? Ambiguous language?
5. **Feasibility** — Can this actually be built with the stated approach? Hidden complexity?
6. **Maintainability** — Will the spec/plan cause problems 6 months down the road? Excessive
   labor or costs?
7. **Robustness/fragility** — Are all edge cases solid? Is the spec/plan resilient to
   failures, and to evolution/changes in external systems?
8. **Security** — Is there anything that presents an opportunity to a threat actor? AuthN/
   AuthZ, TOCTOU, sanitization, injection, other?
9. **Testing** — Are all appropriate types of test present? **Has each acceptance criterion
   been run, and can it go red?** (PD#14.)
10. **Observability** — Is appropriate diagnostic information output at each verbosity level?
    Do output files contain appropriate/necessary information?

Evaluate against these factors using a **checklist backed by quoted evidence** — from the
Spine *and* from industry best practice — **not** a self-graded number. For each factor, note
how important it is relative to the others.

The subagent returns:

- **PASS** if no issues were identified.
- Otherwise a numbered list of issues with dimension, description, and proposed fix(es).

**Step 2: Fix and re-dispatch**

1. For each simple issue with an obvious, low-risk fix, fix it in the document on disk.
2. For every other issue — and **always** when the fix is not obvious, contradicts a
   previously made decision, or would create new problems for me or for users of the
   software — interview me with the `/grilling` skill until we reach a shared understanding.
   Present multiple options, and ask about technical implementation, expansion
   opportunities, edge cases, concerns, tradeoffs, and other potential oversights. Don't ask
   obvious questions; dig into the hard parts I might not have considered.

If no issues required interviewing me, end the review here. Otherwise re-dispatch the
reviewer with the updated document — **maximum 3 iterations total**.

**Before each re-dispatch, run the document's acceptance criteria and paste the real
output.** Fixes collide: one round's fix routinely breaks another round's criterion, and an
unrun criterion is exactly the instrument PD#14 forbids. This step is not optional and it is
the cheapest defect-catcher in the loop.

**Convergence guard:** if the reviewer returns the same issues on consecutive iterations (the
fix didn't resolve them, or the reviewer disagrees with the fix), stop the loop and persist
those issues as "Reviewer Concerns" in the document rather than looping further.

If the subagent fails, times out, or is unavailable — skip the review loop entirely. Tell me:
"Spec review unavailable — presenting unreviewed doc." The document is already written to
disk; the review is a quality bonus, not a gate.

**Step 3: Report**

After the loop completes (PASS, max iterations, or convergence guard):

1. Tell me the result:
   a. Summary: "Your doc survived N rounds of adversarial review. M issues caught and fixed.
      Quality score: X/10."
   b. Show the full reviewer output.
2. If issues remain after max iterations or convergence, add a **"## Reviewer Concerns"**
   section to the document listing each unresolved issue.

**Record the author's own corrected claims in the document**, not just the fixes. A spec that
had to correct its own load-bearing facts should say which ones and how they were caught —
that record is what teaches the next session where this project's verification actually
fails, and it is the evidence PD#14 is earned rather than asserted.
