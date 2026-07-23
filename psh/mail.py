"""Per-site mail: recipient resolution, MIME assembly, and the SMTP login (campaign I12).

Carved from main()'s B49 (recipient/contact resolution), B55 (EmailMessage assembly +
build/{site}.eml write), and the top-level smtp_login().  All bodies moved verbatim except
the named-parameter substitutions the extraction requires (SPEC I12 §2.5, Invariant 8).

The B57 send block -- smtp_login() ... send_message() ... quit() -- deliberately does NOT
move here (SPEC D-i12-4).  Its five statements interleave the B14 accumulator writes
(emails_sent += 1; site_emailed = True) between send_message() and quit(); relocating them
into a function would put those counter updates after quit() returns, reopening the
documented Ctrl-C-during-quit() duplicate-email window (Invariant 4; CLAUDE.md § Database,
the notices-before-send paragraph).  main() keeps calling the re-imported smtp_login().
"""
import datetime
import sys
from email.message import EmailMessage
from email.policy import SMTP
from smtplib import SMTP_SSL

from rich.markup import escape

import script_context as sc
from psh.configuration import umich_enabled
from psh.gateway import terminus


def smtp_login() -> SMTP_SSL:
    smtp_cfg = sc.config.get("SMTP", {})
    host = smtp_cfg.get("host", "smtp.mail.umich.edu")
    port = smtp_cfg.get("port", 465)
    username = sc.smtp_username()
    password = smtp_cfg.get("password")
    if not username or not password:
        sys.exit(
            "SMTP is enabled but the username or password is not configured "
            "(set [SMTP].username / [SMTP].password, or pass --smtp-username)."
        )
    smtp_connection = SMTP_SSL(host, port=port)
    smtp_connection.login(username, password)
    return smtp_connection


def resolve_recipients(site: dict, site_id: str) -> tuple[str, str] | None:
    """Resolve (recipients, contacts) for a site; None on a fatal generic team fetch.

    The None return is the D-i6-1 pattern: main() does `if resolved is None: continue`.
    """
    if umich_enabled():
        r = sc.config["UMich"]["portal"]["sites"][site["name"]]["owner_group"]
        r = r.replace(" ", ".")
        recipients = f"{r}@umich.edu, {r}-owners@umich.edu"
        if site["name"] in ("lsa-disko-project", "umma-inside-wp"):
            # special case, see TDx 10112051, 10165816
            recipients = f"{r}@umich.edu"
        contacts = f"{r}@umich.edu"
    else:
        site_team, errors, fatal = terminus("site:team:list", site_id)
        if fatal or site_team is None:
            sc.console.print(
                f":exclamation: [bold red] ERROR: could not fetch team for {site['name']}: {escape(errors)}"
            )
            return None
        recipients = ", ".join(
            [site_team[team_member]["email"] for team_member in site_team]
        )
        contacts = recipients.replace(",", "")
    return recipients, contacts


def assemble_message(  # noqa: PLR0913 -- pinned MIME-assembly signature (11 args): banner/chart CIDs, both images, both bodies, subject, recipients, attachments, site_name, end_date all thread from main()'s per-site tail; the I6/I11 pinned-signature precedent (a dict would just re-spread the same locals)
    subject: str,
    recipients: str,
    text_body: str,
    html_body: str,
    wordmark_image: bytes,
    chart_image: bytes,
    banner_cid: str,
    chart_cid: str,
    attachments: list,
    site_name: str,
    end_date: datetime.date,
) -> EmailMessage:
    """Build the per-site EmailMessage and write build/{site_name}.eml; return the message."""
    msg = EmailMessage()
    # Sender identity + dry-run addressing come from the [Email] config section; the
    # defaults reproduce the historical U-M literals byte-for-byte so an institution that
    # does not set [Email] gets the same output (P8a).
    email_cfg = sc.config.get("Email", {})
    msg["From"] = email_cfg.get(
        "from", "University of Michigan Webmaster Team <webmaster@umich.edu>"
    )
    if sc.options.for_real:
        msg["To"] = recipients
        msg["Bcc"] = email_cfg.get(
            "bcc", "januside@go.mail.umich.edu, its-webmaster@go.mail.umich.edu"
        )
    else:
        dry_run_to = email_cfg.get("dry_run_to", "januside@go.mail.umich.edu")
        dry_run_domain = email_cfg.get("dry_run_username_domain", "umich.edu")
        # Address the dry run to the configured dry_run_to plus, when a username is
        # resolvable (--smtp-username or [SMTP].username), an operator copy.  When no
        # username is available (e.g. SMTP disabled and no --smtp-username), the operator
        # copy is omitted rather than reading USER from the environment directly.
        username = sc.smtp_username()
        parts = [dry_run_to]
        if username:
            parts.append(f"{username}@{dry_run_domain}")
        msg["To"] = ", ".join(p for p in parts if p)
    msg["Reply-to"] = email_cfg.get("reply_to", "webmaster@umich.edu")
    msg["Date"] = datetime.datetime.now(datetime.UTC).strftime("%a, %d %b %Y %T %z")
    msg["Subject"] = subject

    msg.set_content(text_body, subtype="plain", charset="utf-8")
    msg.add_alternative(html_body, subtype="html", charset="utf-8")

    msg.get_payload()[1].add_related(  # pyright: ignore[reportAttributeAccessIssue, reportArgumentType] -- get_payload()'s union return includes str; on this multipart message [1] is the html alternative part (an EmailMessage) and add_related is valid at runtime; verbatim from main()'s B55
        wordmark_image,
        maintype="image",
        subtype="png",
        filename="pantheon-traffic-email-banner.png",
        cid=banner_cid,
        disposition="inline",
    )

    msg.get_payload()[1].add_related(  # pyright: ignore[reportAttributeAccessIssue, reportArgumentType] -- get_payload()'s union return includes str; on this multipart message [1] is the html alternative part (an EmailMessage) and add_related is valid at runtime; verbatim from main()'s B55
        chart_image,
        maintype="image",
        subtype="png",
        filename=f"pantheon-traffic_{site_name}_{end_date.strftime('%Y%m%d')}.png",
        cid=chart_cid,
        disposition="inline",
    )

    for attachment in attachments:
        msg.get_payload()[1].add_related(  # pyright: ignore[reportAttributeAccessIssue, reportArgumentType] -- get_payload()'s union return includes str; on this multipart message [1] is the html alternative part (an EmailMessage) and add_related is valid at runtime; verbatim from main()'s B55
            attachment["data"],
            maintype=attachment["maintype"],
            subtype=attachment["subtype"],
            filename=attachment["filename"],
            cid=attachment["cid"],
            disposition=attachment["disposition"],
        )

    with open(f"build/{site_name}.eml", "wb") as f:  # noqa: PTH123 -- verbatim from main()'s B55 (Invariant 8, byte-identical .eml write); a Path.open() rewrite would be an un-mandated edit to a moved-verbatim block
        f.write(msg.as_bytes(policy=SMTP))

    return msg
