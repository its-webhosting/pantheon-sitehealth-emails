"""CLI entry point.

Today a re-export of the legacy module's entry functions; becomes the
orchestrator as increments I2-I13 carve psh._legacy apart (CAMPAIGN.md section 3.1).
"""

from psh._legacy import main, parse_args

__all__ = ["main", "parse_args"]
