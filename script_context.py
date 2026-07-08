
import sys

from rich.console import Console

import html2text


options     = {}  # the parsed command line options
config      = {}  # the parsed pantheon-sitehealth-emails.toml file
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

# Ordered lifecycle phases.  'setup' runs once per run (NOTE: including --create-tables,
# which exits later); the site_* phases run once per processed site, in this order, each
# receiving the SiteContext -- but a per-site fatal error (e.g. a domain:list failure) skips
# that site's remaining phases, so hooks must not assume a later phase always follows an
# earlier one.  Phases through site_post_gather run on full-report and --only-warn paths;
# site_pre_render only on the full-report path; --update and --import-older-metrics never
# reach any site_* phase.  Dotted names (e.g. 'setup.umich.portal') are plugin-defined
# events: allowed, not ordered here.  The per-phase site_context data contract lives in
# CLAUDE.md ("Per-site report pipeline").
PHASES = (
    'setup',
    'site_pre',            # first per-site seam (rename of the old 'check' seam; fires
                           # after the traffic gather, just before site_post_traffic --
                           # no per-phase keys guaranteed)
    'site_post_traffic',
    'site_post_dns',
    'site_post_gather',
    'site_pre_render',
)

hooks = {phase: [] for phase in PHASES}

plugin_context = {}

icon = {
    'info': '&#x1F50E;',  # magnifying glass
    'warning': '&#x26A0;',  # warning sign
    'alert': '&#x1F6A8;',  # police car light
}


def debug(*args, level: int = 1) -> None:
    if options.verbose >= level:
        console.log(*args, _stack_offset=2)


def _valid_hook_name(hook_name: str) -> bool:
    return hook_name in PHASES or '.' in hook_name


def add_hook(hook_name: str, target: dict) -> None:
    if not _valid_hook_name(hook_name):
        console.print(f'[bold red]ERROR: add_hook: unknown phase "{hook_name}" '
                      f'(known phases: {", ".join(PHASES)}; dotted names are plugin events)')
        sys.exit(1)
    hooks.setdefault(hook_name, []).append(target)


def invoke_hooks(hook_name: str, *args, **kwargs) -> None:
    if not _valid_hook_name(hook_name):
        console.print(f'[bold red]ERROR: invoke_hooks: unknown phase "{hook_name}"')
        sys.exit(1)
    debug(f'[bold magenta]=== Calling hooks for {hook_name}:')
    for hook in hooks.get(hook_name, []):
        debug(f'Invoking {hook_name} hook target {hook["name"]}')
        hook['func'](*args, **kwargs)


text_maker = html2text.HTML2Text()
# html2text --protect-links --images-to-alt --unicode-snob --reference-links --no-wrap-links --links-after-para --wrap-list-items --pad-tables file.html
text_maker.protect_links    = True
text_maker.images_to_alt    = True
text_maker.unicode_snob     = True
text_maker.reference_links  = True
text_maker.wrap_links       = False
text_maker.links_after_para = True
text_maker.wrap_list_items  = True
text_maker.pad_tables       = True

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

    def add_notice(self, notice: dict) -> None:
        """
        Add a notice, filling in the icon (from 'type'), the plaintext 'text' (via html2text),
        and honoring notice['order'] ('prepend'/'first' -> front of the list, else append).
        """
        if 'message' not in notice:
            console.print(f'[bold red]ERROR: Notice is missing the "message" key: {notice}')
            sys.exit(1)
        if 'icon' not in notice:
            notice['icon'] = icon[notice['type']]
        if 'text' not in notice:
            notice['text'] = text_maker.handle(notice['message'])
        order = notice['order'] if 'order' in notice else 'append'
        if order == 'prepend' or order == 'first':
            self['notices'].insert(0, notice)
        else:
            self['notices'].append(notice)

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
        news_item['text'] = text_maker.handle(news_item['message'])
    order = news_item['order'] if 'order' in news_item else 'append'
    if order == 'prepend' or order == 'first':
        news.insert(0, news_item)
    else:
        news.append(news_item)
