# PROMPT

Verbatim user request that opened this session (2026-08-07):

> Fix the first TO DO item in `README.md`, which reads:
> ```
> * Add a `mutates` hook declaration to the DAG **(post-campaign)** — a third per-hook edge kind
>   (beside `consumes`/`produces`) that orders a `site_post_gather` smell-notice consumer *after* the
>   in-place `wp_smell`/`drush_smell` mutators (`check.wordpress.ocp`/`.favicon`,
>   `check.umich.drupal_ua`), which today are deliberately DAG-invisible (D-i9-3); declined in-campaign
>   at I10 (user decision) because it is engine surface no move needs, but it is what would let B48's
>   smell notices become a `check/addon_updates/` hook instead of staying an inline emission in `main()`
>   (LEDGER I10 amendment 1).
> ```
> If there are open questions, brainstorm this. When the work is done, delete that one TO DO item
> from `README.md`.

## Decisions taken in the brainstorm (both by explicit user selection)

1. **Scope — "Relocate only; no `mutates`."** The brainstorm established that the TODO's premise
   does not hold (SPEC §2): a `site_pre_render` hook dissolves every constraint the campaign cited,
   with no new engine surface. The user selected relocation without the `mutates` edge kind.
2. **Package — "New `check/smells/` package."** Rather than `check/addon_updates/`, which
   CAMPAIGN.md §3.2 named only because BLOCKMAP B48 and B39 were adjacent in the original `main()`.
   Reason: `[Check.addon_updates].enabled = false` would otherwise silence three unrelated notices.

The design was presented in five sections and approved with "yes, write the spec".
