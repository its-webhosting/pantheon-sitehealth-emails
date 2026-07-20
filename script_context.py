
import argparse
import sys
from typing import Any

import html2text
from rich.console import Console

from psh.modules import (  # noqa: F401 -- add_hook/invoke_hooks re-exported as sc.* for check/plugin packages
    PHASES,
    add_hook,
    invoke_hooks,
)
from psh.notice import (  # noqa: F401 -- Severity re-exported as sc.Severity for check/plugin packages
    Notice,
    Severity,
)

options: argparse.Namespace = argparse.Namespace()  # parsed CLI options; set by parse_args() caller
config: dict[str, Any] = {}                          # parsed pantheon-sitehealth-emails.toml
plugin      = {}  # imported plugins (Python modules)
check       = {}  # imported site checks (Python modules)
news        = []  # list of news items to be displayed


console = Console()


class ConfigSubstitutionError(Exception):
    """Raised by a config-substitution function (e.g. plugin.env.get_env) to abort the run
    with a helpful, config-path-annotated message.  Caught in config_substitution(), which
    prints the offending config path plus this message and exits."""


# Sentinel a substitution function returns to defer its resolution to the post-setup config pass
# (its backing data is populated by a `setup` hook that has not run yet -- e.g. plugin.umich's
# plan_info, which needs the portal DB).  config_substitution() re-emits a tagged marker that only
# the second pass re-resolves; see the two-pass note in main().
DEFER = object()


substitutions = []

hooks = {phase: [] for phase in PHASES}

plugin_context = {}

# Reconnects HEALED by db_retry() -- the retry ran and succeeded -- attributed to the site that
# caused them.  Counted only after the second attempt returns: counting the attempt instead would
# let an aborted run report a reconnect it never actually made.
db_reconnects_by_site: dict[str, int] = {}

# Connection losses db_retry() could NOT heal, attributed the same way: the retry failed, or the
# rollback before it did.  The counterpart of the dict above, and the reason it can be trusted --
# every lost connection lands in exactly one of the two, so "0 healed" never means "nothing
# happened".  Both are reported on the console and in {ymd}-run.json
# (development/2026-07-13-db-connection-resilience/SPEC.md 3.6).  Written by psh.db.db_retry;
# read by finish_run/abort_run; absorbed into RunState at campaign I13.
db_reconnect_failures_by_site: dict[str, int] = {}

icon = {
    'info': '&#x1F50E;',  # magnifying glass
    'warning': '&#x26A0;',  # warning sign
    'alert': '&#x1F6A8;',  # police car light
}


def debug(*args, level: int = 1) -> None:
    if options.verbose >= level:
        console.log(*args, _stack_offset=2)


def html_to_text(html: str) -> str:
    """Render notice/news HTML to the plaintext used in the text/plain email part.

    A FRESH HTML2Text per call, deliberately: the instance is stateful, and sharing one
    across calls made every notice render differently from its siblings -- the run's FIRST
    notice came out in a different link style from all the others, and html2text's reference
    counter climbed across the whole run instead of restarting.

    Links are reference-style, and html2text numbers them per handle() call.  An email body
    is many notices concatenated (email_template.txt loops over notice.text), so one message
    can contain several "[1]" labels -- one per notice.  That is an ACCEPTED trade-off, not an
    oversight: each notice's footnote definitions immediately follow its own block
    (links_after_para), so every label sits next to its URL and reads unambiguously.  The
    alternative -- inline links -- is worse in this content: with wrap_links=False any
    paragraph containing a link stops wrapping (250+ character lines in a plaintext email),
    and with wrap_links=True html2text splits long URLs mid-string and breaks them.
    `inline_links` is the flag html2text actually honors; `reference_links` alone only flips
    it during the first handle(), which is what made the first notice of a run come out in a
    different style from all the others.

    Equivalent to:
      html2text --protect-links --images-to-alt --unicode-snob --reference-links
                --no-wrap-links --links-after-para --wrap-list-items --pad-tables file.html
    """
    text_maker = html2text.HTML2Text()
    text_maker.protect_links    = True
    text_maker.images_to_alt    = True
    text_maker.unicode_snob     = True
    text_maker.reference_links  = True
    text_maker.inline_links     = False   # what reference_links=True actually needs; see above
    text_maker.wrap_links       = False
    text_maker.links_after_para = True
    text_maker.wrap_list_items  = True
    text_maker.pad_tables       = True
    return text_maker.handle(html)


class SiteContext(dict):
    """
    Per-site report context.

    A dict subclass so that `site_context['notices' | 'sections' | 'attachments' | 'site']`
    access is unchanged throughout the code and the Jinja templates, while the object also owns
    the mutators for its collections (`add_notice`/`add_notices`/`add_section`/`add_attachment`).
    Constructed once per processed site; notices/sections/attachments accumulate through the
    per-site pipeline (including `check` hooks) and are consumed by the template render.
    """

    def __init__(self, site: dict):
        super().__init__(site=site, notices=[], sections=[], attachments=[])

    def add_notice(self, notice) -> None:      # notice: Notice | dict
        """Add a notice (Notice or legacy dict), filling icon (from 'type'), plaintext 'text' (via
        html2text), and honoring order ('prepend'/'first' -> front).  A Notice is projected to the
        legacy dict first (dict form retired in I14, CAMPAIGN.md §6)."""
        if isinstance(notice, Notice):
            notice = self._notice_to_dict(notice)
        if 'message' not in notice:
            console.print(f'[bold red]ERROR: Notice is missing the "message" key: {notice}')
            sys.exit(1)
        if 'icon' not in notice:
            notice['icon'] = icon[notice['type']]
        if 'text' not in notice:
            notice['text'] = html_to_text(notice['message'])
        order = notice.get('order', 'append')
        if order in ('prepend', 'first'):
            self['notices'].insert(0, notice)
        else:
            self['notices'].append(notice)

    def _notice_to_dict(self, notice: Notice) -> dict:
        """Project a Notice onto the legacy notice dict.  csv is built from the site name + code (the
        two-field form; extra-csv-field notices stay dicts until their adopting increment).  icon /
        text / non-default order are set only when present so the stored dict is byte-identical to the
        legacy one and add_notice's fill logic supplies icon/text identically."""
        d = {
            "type": str(notice.severity),
            "csv": f"{self['site']['name']},{notice.code}",
            "short": notice.short,
            "message": notice.html,
        }
        if notice.icon:
            d["icon"] = notice.icon
        if notice.text:
            d["text"] = notice.text
        if notice.order != "append":
            d["order"] = notice.order
        return d

    def add_notices(self, notices: list) -> None:
        """Add each notice dict returned by a builder (wp_error/drush_error/check_*module)."""
        for notice in notices:
            self.add_notice(notice)

    def add_section(self, section: dict) -> None:
        """Add a report section (rendered into the email body)."""
        self['sections'].append(section)

    def add_attachment(self, attachment: dict) -> None:
        """Add an attachment (e.g. an inline image referenced by cid)."""
        self['attachments'].append(attachment)


def msgid_domain() -> str:
    """
    The domain used for inline-image Content-IDs (make_msgid), from [Email].msgid_domain.
    Single source of the default so the core script and the umich check package don't each
    hard-code it.
    """
    return config.get('Email', {}).get('msgid_domain', 'webservices.umich.edu')


def smtp_username() -> str:
    """
    The effective SMTP / dry-run username: the --smtp-username option if given, else
    [SMTP].username (which is dropped when [SMTP] is disabled, per the section-gating rule),
    else the empty string.  Used both for SMTP login and for the dry-run To: operator copy.
    """
    if options.smtp_username is not None:
        return options.smtp_username
    return config.get('SMTP', {}).get('username', '') or ''


def add_news_item(news_item: dict, from_where: str = 'check') -> None:
    if 'message' not in news_item:
        console.print(f'ERROR: News item in {from_where} is missing the "message" key: {news_item}')
        sys.exit(1)
    if 'icon' not in news_item:
        news_item['icon'] = icon[news_item['type']]
    if 'text' not in news_item:
        news_item['text'] = html_to_text(news_item['message'])
    order = news_item.get('order', 'append')
    if order in ('prepend', 'first'):
        news.insert(0, news_item)
    else:
        news.append(news_item)
