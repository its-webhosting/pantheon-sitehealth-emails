
import sys

from rich.console import Console

import html2text


options     = {}  # the parsed command line options
config      = {}  # the parsed pantheon-sitehealth-emails.toml file
plugin      = {}  # imported plugins (Python modules)
check       = {}  # imported site checks (Python modules)
news        = []  # list of news items to be displayed


console = Console()

substitutions = []

hooks = {
    'setup': [],
    'check': [],
}

plugin_context = {}

icon = {
    'info': '&#x1F50E;',  # magnifying glass
    'warning': '&#x26A0;',  # warning sign
    'alert': '&#x1F6A8;',  # police car light
}


def debug(*args, level: int = 1) -> None:
    if options.verbose >= level:
        console.log(*args, _stack_offset=2)


def add_hook(hook_name: str, target: dict) -> None:
    if hook_name in hooks:
        hooks[hook_name].append(target)
    else:
        hooks[hook_name] = [target]


def invoke_hooks(hook_name: str, *args, **kwargs) -> None:
    debug(f'[bold magenta]=== Calling hooks for {hook_name}:')
    if hook_name in hooks:
        for hook in hooks[hook_name]:
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
