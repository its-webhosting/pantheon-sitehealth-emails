
import sys

from rich.console import Console

import html2text


options     = {}  # the parsed command line options
config      = {}  # the parsed pantheon-sitehealth-emails.toml file
plugin      = {}  # imported plugins (Python modules)
check       = {}  # imported site checks (Python modules)
news        = []  # list of news items to be displayed
sections    = []  # list of sections in the email
attachments = []  # list of attachments to be included in the email

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

def add_notice(notice: dict, site_context: dict) -> None:
    if 'message' not in notice:
        console.print(f'[bold red]ERROR: Notice is missing the "message" key: {notice}')
        sys.exit(1)
    if 'icon' not in notice:
        notice['icon'] = icon[notice['type']]
    if 'text' not in notice:
        notice['text'] = text_maker.handle(notice['message'])
    order = notice['order'] if 'order' in notice else 'append'
    if order == 'prepend' or order == 'first':
        site_context['notices'].insert(0, notice)
    else:
        site_context['notices'].append(notice)


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
