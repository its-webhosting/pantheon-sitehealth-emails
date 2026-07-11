"""PURE DNS notice builders (HTML + plaintext), U-M and generic variants.

Each builder returns a notice dict with type/csv/short/message/text; add_notice fills `icon`
from `type`.  Every remotely-derived hostname is html.escape'd for display and sc.escape_url'd
for hrefs.  U-M variants link its.umich.edu / documentation.its.umich.edu; generic variants
use no U-M links.  csv codes: dns-lookup-failed, not-in-dns, not-behind-cloudflare,
behind-cloudflare-not-proxied, proxied-in-multiple-cloudflare-zones.
"""
import html

import script_context as sc


def _html_list(hostnames):
    return "\n".join(
        f'<li><a href="https://{sc.escape_url(n)}/">{html.escape(n)}</a></li>'
        for n in hostnames)


def _text_list(hostnames):
    return "\n".join(f"  * {n}" for n in hostnames)


def transient_notice(site_name, hostnames):
    return {
        "type": "warning",
        "csv": f"{site_name},dns-lookup-failed," + ",".join(hostnames),
        "short": "DNS lookup failed (transient)",
        "message": (
            "<p>The DNS lookup for the following domains failed with a transient resolver "
            "error, so their DNS status could not be checked. This does not necessarily mean "
            "they are misconfigured &mdash; re-run the report to retry.</p>\n"
            f'<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>'),
        "text": (
            "The DNS lookup for the following domains failed with a transient resolver error,\n"
            "so their DNS status could not be checked. Re-run the report to retry.\n\n"
            f"{_text_list(hostnames)}\n"),
    }


def not_in_dns_notice(site_name, hostnames):
    return {
        "type": "alert",
        "csv": f"{site_name},not-in-dns," + ",".join(hostnames),
        "short": "add domains to DNS",
        "message": (
            f"<p><strong>{html.escape(site_name)}</strong> has domains that are not in DNS.  "
            f"Please either remove these domains from the Pantheon live environment for "
            f"<strong>{html.escape(site_name)}</strong>, or add them to DNS.</p>\n"
            f'<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>'),
        "text": (
            f"{site_name} has domains that are not in DNS.  Please either\n"
            f"remove these domains from the Pantheon live environment for\n"
            f"{site_name}, or add them to DNS.\n\n{_text_list(hostnames)}\n"),
    }


def not_behind_cloudflare_notice(site_name, hostnames, *, umich):
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
    return {
        "type": "warning",
        "csv": f"{site_name},not-behind-cloudflare," + ",".join(hostnames),
        "short": "put domains behind Cloudflare",
        "message": f'{intro_html}\n<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>',
        "text": f"{intro_text}\n\n{_text_list(hostnames)}\n",
    }


def behind_cloudflare_not_proxied_notice(site_name, hostnames, *, umich):
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
    return {
        "type": "warning",
        "csv": f"{site_name},behind-cloudflare-not-proxied," + ",".join(hostnames),
        "short": "turn on Cloudflare proxying for domains",
        "message": f'{intro_html}\n<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>',
        "text": f"{intro_text}\n\n{_text_list(hostnames)}\n",   # bug #2 fix: lists THESE hosts
    }


def proxied_in_multiple_zones_notice(site_name, hostnames):
    return {
        "type": "warning",
        "csv": f"{site_name},proxied-in-multiple-cloudflare-zones," + ",".join(hostnames),
        "short": "domain in multiple Cloudflare zones",
        "message": (
            "<p>The following domains are configured (proxied) in more than one Cloudflare "
            "zone.  Serving a domain from multiple zones can cause inconsistent caching, TLS, "
            "and security settings.  Please consolidate each domain into a single Cloudflare "
            "zone.</p>\n"
            f'<ul style="list-style-type: none;">\n{_html_list(hostnames)}\n</ul>'),
        "text": (
            "The following domains are configured (proxied) in more than one\n"
            "Cloudflare zone.  Serving a domain from multiple zones can cause\n"
            "inconsistent caching, TLS, and security settings.  Please consolidate\n"
            f"each domain into a single Cloudflare zone.\n\n{_text_list(hostnames)}\n"),
    }
