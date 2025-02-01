
from rich.console import Console


options = None  # the parsed command line options
config  = None  # the parsed pantheon-sitehealth-emails.toml file

console = Console()

def debug(*args, level: int = 1):
    if options.verbose >= level:
        console.log(*args, _stack_offset=2)
