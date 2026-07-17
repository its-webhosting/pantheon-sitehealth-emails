# Pantheon Site-Health Emails

The domain glossary for this tool: monthly site-health and traffic reporting for
Pantheon-hosted websites, with plan-cost recommendations, run by a hosting service on
behalf of site owners. Vocabulary only — architecture and implementation live in
`CLAUDE.md`.

## Language

**Site**:
A Pantheon-hosted website in the organization's account, identified by its Pantheon
site name (e.g. `its-wws-test1`).

**Site owner**:
The person or group responsible for a site, and the recipient of its report.
_Avoid_: customer, client

**Report**:
The monthly site-health email generated for one site: traffic history, notices, news,
sections, and a plan recommendation.
_Avoid_: email (alone), summary

**Run**:
One execution of the tool over one or more sites for a given report date. A run can be
a dry run (mail addressed to the operator) or for-real (mail addressed to site owners).

**Notice**:
A per-site finding included in that site's report, with a severity of alert, warning,
or info and a stable machine-readable code.
_Avoid_: warning (as the generic term), alert (as the generic term), message

**News item**:
An organization-wide announcement included in every report in a run.
_Avoid_: notice (news is not per-site)

**Section**:
A standalone block of report content contributed by a check, distinct from notices
(which are findings) and news (which is org-wide).

**Check**:
A site-health inspection that contributes notices and/or sections to reports. Checks
are optional per institution.

**Integration plugin**:
A data-source or service integration package (AWS, Cloudflare, the U-M portal, env).
Always say "WordPress plugin" in full for the CMS concept — bare "plugin" is reserved
for integration plugins.
_Avoid_: plugin (bare, when the CMS concept is meant)

**Plan**:
A Pantheon hosting plan (Basic, Performance Small, …) with a monthly visit allowance
and price.

**Recommendation**:
The plan the report advises a site owner to move to, computed by the cost model from
the site's traffic history.

**Overage**:
Visits beyond a plan's allowance, billed in fixed-size blocks unless the site has
overage protection.

**Overage protection**:
The Pantheon feature that waives overage billing for a site during a given month.

**Framework**:
The CMS a site runs — WordPress (including a WordPress network) or Drupal — as reported
by Pantheon.
_Avoid_: platform (that word means Pantheon itself)
