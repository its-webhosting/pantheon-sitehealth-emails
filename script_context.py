
from rich.console import Console


options = {}  # the parsed command line options
config  = {}  # the parsed pantheon-sitehealth-emails.toml file
plugin  = {}  # imported plugins (Python modules)
news    = []  # list of news items to be displayed

console = Console()

substitutions = []

hooks = {
    'setup': [],
}

plugin_context = {}


def debug(*args, level: int = 1):
    if options.verbose >= level:
        console.log(*args, _stack_offset=2)
