# Analytics — workflow & configuration consolidation

_Your narrative: what went well, what to do differently, decisions worth remembering._

---

## Prompts for your own review

Some things this session surfaced that you may or may not agree with — worth a line
each, since the Campaign starts from here.

- **The tier model was designed and then dropped** (PD#12). Was that right, or did the
  campaign framing just postpone a real problem? §1c remains only partially addressed.
- **`psh-implementer` shipped un-dogfooded.** §4 was implemented inline because the agent
  could not register mid-session. Its first real use is Campaign increment 1.
- **The `/usage` numbers are worth a decision**, not just a record (see `statistics.md`):
  83% of the last 24h came from subagent-heavy sessions and 71% at >150k context — and
  this session was both, at $48.28. The adversarial-review loop (3 rounds × a
  general-purpose subagent reading the whole repo) is where much of that went. It also
  caught 39 issues, four of which were PD#14 violations that would have shipped. Whether
  that trade is right at Campaign scale — N increments × 3 rounds — is a real question
  the spec doesn't answer.
- **`/grilling` cost 11% of the last 24h.** It was invoked once here, per
  `prompts/adversarial-review.md`'s mandate to interview rather than patch. Worth knowing
  the price of that mandate.
