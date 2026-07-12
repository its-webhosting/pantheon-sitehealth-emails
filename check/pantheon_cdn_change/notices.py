"""The single owner-facing notice for the Pantheon CDN-change check (SPEC §8).

PURE: Findings in, one notice dict out.  Imports ONLY html + .model -- never detect/chain/
pantheon, so this module pulls in neither dnspython nor terminus.  Four copy variants from two
independent booleans -- umich (terminology) x before_cutoff (who does the work).  The notice
states ONLY what the owner must change; it deliberately does not explain Pantheon's migration,
Orange-to-Orange, or Pantheon-versus-our-Cloudflare.

Every hostname and address here is remotely derived -> html.escape on every text node.  The one
href is the constant DOCS_URL, so sc.escape_url is not needed; if a per-domain link is ever added
it MUST go through sc.escape_url (the check/dns/notices.py convention).

The HTML table reuses the markup the core's existing notices use (pantheon-sitehealth-emails
:2521), so it inherits email_template.html's mobile-stacking styles and survives the Emogrifier +
!important passes.  Plaintext uses an indented block per domain rather than an ASCII table --
three addresses per row do not survive a text table legibly.

ONE row per affected FQDN: the addresses are Pantheon's per-domain required records, so they are
correct for the DNS record and the Cloudflare record alike (SPEC §4.1).
"""
import html

from .model import Finding    # noqa: F401  -- re-exported for callers/tests; model is pure

DOCS_URL = "https://docs.pantheon.io/guides/global-cdn/global-cdn-beta#setup"

INTRO_HTML = (
    '<p>Pantheon is <a href="{docs}">making a change to their CDN</a>, from the legacy '
    "Pantheon GCDN (Fastly) to the new Pantheon GCDN Beta (Pantheon Cloudflare).  Before "
    "<strong>{site}</strong> can move to the new GCDN Beta, each of its custom domains must "
    "resolve through A and AAAA records instead of a CNAME record.</p>\n"
    "<p>These domains for <strong>{site}</strong> still use a CNAME record:</p>")

INTRO_TEXT = (
    "Pantheon is making a change to their CDN <{docs}>, from the legacy Pantheon\n"
    "GCDN (Fastly) to the new Pantheon GCDN Beta (Pantheon Cloudflare).  Before\n"
    "{site} can move to the new GCDN Beta, each of its custom domains must resolve\n"
    "through A and AAAA records instead of a CNAME record.\n\n"
    "These domains for {site} still use a CNAME record:")

MAINTENANCE_HTML = (
    "<p>ITS will make these changes for you during an upcoming maintenance, which we will "
    "schedule and announce.  If you would rather make the changes yourself before then, you "
    "are welcome to.</p>")

MAINTENANCE_TEXT = (
    "ITS will make these changes for you during an upcoming maintenance, which we\n"
    "will schedule and announce.  If you would rather make the changes yourself\n"
    "before then, you are welcome to.")

SELF_SERVE_HTML = (
    "<p>Please replace each CNAME record above with the A and AAAA records shown.</p>")

SELF_SERVE_TEXT = (
    "Please replace each CNAME record above with the A and AAAA records shown.")


def _cloudflare_label(umich: bool) -> str:
    return "U-M Cloudflare" if umich else "our (non-Pantheon) Cloudflare"


def where_label(where: str, *, umich: bool) -> str:
    """The 'Change it in' cell.  `where` is a Finding's machine value (SPEC §8).

    Raises ValueError on anything else: a silent fall-through would print a wrong instruction to
    a site owner, which is the class of failure this feature exists to prevent.
    """
    if where == "dns":
        return "DNS"
    if where == "cloudflare":
        return _cloudflare_label(umich)
    if where == "both":
        return f"DNS and {_cloudflare_label(umich)}"
    raise ValueError(f"unknown Finding.where: {where!r}")


def _records(finding) -> list:
    """[(rrtype, value)] -- Pantheon's required records for this domain, in Pantheon's order.

    Normally A/AAAA.  A CNAME appears only for a site already on the new GCDN Beta (F14), whose
    domain:dns answer has no A/AAAA at all -- that is an ANSWER, and it must be shown rather than
    reported as "unavailable".
    """
    return ([("A", ip) for ip in finding.a]
            + [("AAAA", ip) for ip in finding.aaaa]
            + [("CNAME", name) for name in finding.cname])


def _records_html(finding, umich: bool) -> str:
    records = _records(finding)
    if not records:      # F4: no answer at all
        return "unavailable &mdash; please contact us" if umich else "unavailable"
    return "<br>".join(f"{rrtype} {html.escape(value)}" for rrtype, value in records)


def _records_text(finding, umich: bool) -> str:
    records = _records(finding)
    if not records:
        return "      unavailable -- please contact us" if umich else "      unavailable"
    return "\n".join(f"      {rrtype:<6s} {value}" for rrtype, value in records)


def cdn_change_notice(site_name: str, findings: list, *, umich: bool, before_cutoff: bool) -> dict:
    """ONE info notice covering every affected custom domain for the site."""
    site = html.escape(site_name)
    rows = "\n".join(
        f"<tr><td>{html.escape(f.fqdn)}</td>"
        f"<td>{html.escape(where_label(f.where, umich=umich))}</td>"
        f"<td>{_records_html(f, umich)}</td></tr>"
        for f in findings)
    blocks = "\n\n".join(
        f"  {f.fqdn}  (change it in {where_label(f.where, umich=umich)})\n"
        f"{_records_text(f, umich)}"
        for f in findings)

    closing_html = MAINTENANCE_HTML if (umich and before_cutoff) else SELF_SERVE_HTML
    closing_text = MAINTENANCE_TEXT if (umich and before_cutoff) else SELF_SERVE_TEXT

    message = (
        f"{INTRO_HTML.format(docs=DOCS_URL, site=site)}\n"
        '<div class="container">\n'
        '<table class="responsive-table site-updates">\n'
        '<thead><th class="rt-plan">Domain</th><th class="rt-plan">Change it in</th>'
        '<th class="rt-plan">Replace the CNAME record with</th></thead>\n'
        f"<tbody>\n{rows}\n</tbody>\n"
        "</table>\n"
        "</div>\n"
        f"{closing_html}")

    text = (
        f"{INTRO_TEXT.format(docs=DOCS_URL, site=site_name)}\n\n"
        f"{blocks}\n\n"
        f"{closing_text}\n")

    return {
        "type": "info",
        "csv": f"{site_name},pantheon-cdn-change," + ",".join(f.fqdn for f in findings),
        "short": "Pantheon CDN change: replace CNAME records",
        "message": message,
        "text": text,
    }
