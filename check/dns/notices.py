"""PURE DNS notice builders (HTML + plaintext), U-M and generic variants.

Each builder returns a sc.Notice; SiteContext.notice_to_dict projects it onto the render dict
and fills `icon` from `severity`.  Every remotely-derived hostname is html.escape'd for display
and sc.escape_url'd for hrefs.  U-M variants link its.umich.edu / documentation.its.umich.edu;
generic variants use no U-M links.  csv codes: dns-lookup-failed, not-in-dns,
not-behind-cloudflare, behind-cloudflare-not-proxied, proxied-in-multiple-cloudflare-zones.

EMPTY-INPUT PRECONDITION (SPEC I14c §2.1, D-i14c-11), stated once here and referenced by each
builder: every builder takes a hostname list that its ONE caller guards against being empty
(check/dns/hook.py:26,30,33,36,40).  Pre-I14c the csv was f"{site},{code}," + ",".join(hostnames),
which left a trailing comma on an empty list; csv_extra=tuple(hostnames) leaves no trailing field.
The divergence is unreachable today and pinned by tests/unit/test_dns_notices.py.
"""
import html

import script_context as sc

# Notice codes registered at import; see CLAUDE.md § Notices vs. news.
NOTICE_DNS_LOOKUP_FAILED = sc.registry.register(
    "dns-lookup-failed", description="DNS lookup failed with a transient resolver error")
NOTICE_NOT_IN_DNS = sc.registry.register(
    "not-in-dns", description="custom domain has no DNS record")
NOTICE_NOT_BEHIND_CLOUDFLARE = sc.registry.register(
    "not-behind-cloudflare", description="custom domain does not resolve to Cloudflare")
NOTICE_BEHIND_CLOUDFLARE_NOT_PROXIED = sc.registry.register(
    "behind-cloudflare-not-proxied", description="Cloudflare proxying is off for the domain")
NOTICE_PROXIED_IN_MULTIPLE_ZONES = sc.registry.register(
    "proxied-in-multiple-cloudflare-zones",
    description="domain is proxied in more than one Cloudflare zone")


def _html_list(hostnames):
    return "\n".join(
        f'<li><a href="https://{sc.escape_url(n)}/">{html.escape(n)}</a></li>'
        for n in hostnames)


def _text_list(hostnames):
    return "\n".join(f"  * {n}" for n in hostnames)


def transient_notice(site_name, hostnames):  # noqa: ARG001 -- site_name is unused since I14c (the csv row's site field now comes from the SiteContext at projection time, SPEC I14c §2.2), but the five builders keep ONE uniform signature: check/dns/hook.py calls them all as f(site, hostnames)
    """Hostnames whose lookup failed transiently.  See the module docstring's empty-input
    precondition: csv_extra is the hostname list as separate csv fields."""
    return sc.Notice(
        severity=sc.Severity.WARNING,
        code=NOTICE_DNS_LOOKUP_FAILED,
        csv_extra=tuple(hostnames),
        short="DNS lookup failed (transient)",
        html=(
            "<p>The DNS lookup for the following domains failed with a transient resolver "
            "error, so their DNS status could not be checked. This does not necessarily mean "
            "they are misconfigured &mdash; re-run the report to retry.</p>\n"
            f'<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>'),
        text=(
            "The DNS lookup for the following domains failed with a transient resolver error,\n"
            "so their DNS status could not be checked. Re-run the report to retry.\n\n"
            f"{_text_list(hostnames)}\n"),
    )


def not_in_dns_notice(site_name, hostnames):
    """Hostnames with no DNS record.  See the module docstring's empty-input precondition:
    csv_extra is the hostname list as separate csv fields."""
    return sc.Notice(
        severity=sc.Severity.ALERT,
        code=NOTICE_NOT_IN_DNS,
        csv_extra=tuple(hostnames),
        short="add domains to DNS",
        html=(
            f"<p><strong>{html.escape(site_name)}</strong> has domains that are not in DNS.  "
            f"Please either remove these domains from the Pantheon live environment for "
            f"<strong>{html.escape(site_name)}</strong>, or add them to DNS.</p>\n"
            f'<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>'),
        text=(
            f"{site_name} has domains that are not in DNS.  Please either\n"
            f"remove these domains from the Pantheon live environment for\n"
            f"{site_name}, or add them to DNS.\n\n{_text_list(hostnames)}\n"),
    )


def not_behind_cloudflare_notice(site_name, hostnames, *, umich):  # noqa: ARG001 -- see transient_notice
    """Hostnames that do not resolve to Cloudflare.  See the module docstring's empty-input
    precondition: csv_extra is the hostname list as separate csv fields."""
    if umich:
        intro_html = (
            "<p>ITS strongly recommends you put the following domains behind Cloudflare to "
            "reduce Pantheon traffic and improve security.  Please refer to the "
            '<a href="https://its.umich.edu/computing/web-mobile/cloudflare/getting-started">'
            "Cloudflare at U-M documentation</a>.</p>")
        intro_text = (
            "ITS strongly recommends you put the following domains behind\n"
            "Cloudflare to reduce Pantheon traffic and improve security.\n"
            "Please refer to the Cloudflare at U-M documentation\n"
            "<https://its.umich.edu/computing/web-mobile/cloudflare/getting-started>")
    else:
        intro_html = (
            "<p>We strongly recommend you put the following domains behind Cloudflare to "
            "reduce origin traffic and improve security.</p>")
        intro_text = (
            "We strongly recommend you put the following domains behind Cloudflare\n"
            "to reduce origin traffic and improve security.")
    return sc.Notice(
        severity=sc.Severity.WARNING,
        code=NOTICE_NOT_BEHIND_CLOUDFLARE,
        csv_extra=tuple(hostnames),
        short="put domains behind Cloudflare",
        html=f'{intro_html}\n<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>',
        text=f"{intro_text}\n\n{_text_list(hostnames)}\n",
    )


def behind_cloudflare_not_proxied_notice(site_name, hostnames, *, umich):  # noqa: ARG001 -- see transient_notice
    """Hostnames behind Cloudflare with proxying turned off.  See the module docstring's
    empty-input precondition: csv_extra is the hostname list as separate csv fields."""
    if umich:
        intro_html = (
            "<p>The following domains point to Cloudflare but are not benefitting from "
            "Cloudflare's caching and security features because proxying for these FQDNs is "
            "turned off in Cloudflare.  Please follow steps 3 and 4 of the "
            '<a href="https://documentation.its.umich.edu/node/4237">U-M Cloudflare: Website '
            "Migration Steps</a> to ensure the site is configured to work with Cloudflare and "
            "to turn on proxying.</p>")
        intro_text = (
            "The following domains point to Cloudflare but are not benefitting from\n"
            "Cloudflare's caching and security features because proxying for these\n"
            "FQDNs is turned off in Cloudflare.\n\n"
            "Please follow steps 3 and 4 of the U-M Cloudflare: Website Migration\n"
            "Steps <https://documentation.its.umich.edu/node/4237> to ensure the\n"
            "site is configured to work with Cloudflare and to turn on proxying.")
    else:
        intro_html = (
            "<p>The following domains point to Cloudflare but are not benefitting from "
            "Cloudflare's caching and security features because proxying (the orange cloud) is "
            "turned off for these DNS records.  Turn on proxying for these records in your "
            "Cloudflare dashboard.</p>")
        intro_text = (
            "The following domains point to Cloudflare but are not benefitting from\n"
            "Cloudflare's caching and security features because proxying (the orange\n"
            "cloud) is turned off for these DNS records.  Turn on proxying for these\n"
            "records in your Cloudflare dashboard.")
    return sc.Notice(
        severity=sc.Severity.WARNING,
        code=NOTICE_BEHIND_CLOUDFLARE_NOT_PROXIED,
        csv_extra=tuple(hostnames),
        short="turn on Cloudflare proxying for domains",
        html=f'{intro_html}\n<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>',
        text=f"{intro_text}\n\n{_text_list(hostnames)}\n",   # bug #2 fix: lists THESE hosts
    )


def proxied_in_multiple_zones_notice(site_name, hostnames):  # noqa: ARG001 -- see transient_notice
    """Hostnames proxied in more than one Cloudflare zone.  See the module docstring's
    empty-input precondition: csv_extra is the hostname list as separate csv fields."""
    return sc.Notice(
        severity=sc.Severity.WARNING,
        code=NOTICE_PROXIED_IN_MULTIPLE_ZONES,
        csv_extra=tuple(hostnames),
        short="domain in multiple Cloudflare zones",
        html=(
            "<p>The following domains are configured (proxied) in more than one Cloudflare "
            "zone.  Serving a domain from multiple zones can cause inconsistent caching, TLS, "
            "and security settings.  Please consolidate each domain into a single Cloudflare "
            "zone.</p>\n"
            f'<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>'),
        text=(
            "The following domains are configured (proxied) in more than one\n"
            "Cloudflare zone.  Serving a domain from multiple zones can cause\n"
            "inconsistent caching, TLS, and security settings.  Please consolidate\n"
            f"each domain into a single Cloudflare zone.\n\n{_text_list(hostnames)}\n"),
    )
