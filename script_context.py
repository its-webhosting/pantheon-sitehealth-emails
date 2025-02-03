
from rich.console import Console


options = {}  # the parsed command line options
config  = {}  # the parsed pantheon-sitehealth-emails.toml file
plugin  = {}  # imported plugins (Python modules)

console = Console()

substitutions = []

hooks = {
    'setup': [],
}

def debug(*args, level: int = 1):
    if options.verbose >= level:
        console.log(*args, _stack_offset=2)
