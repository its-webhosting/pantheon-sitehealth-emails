"""pantheon-sitehealth-emails core package.

Carved out of the legacy single-file script by the modularization campaign --
see development/2026-07-17-modularization-campaign/CAMPAIGN.md.  The orchestrator
(argparse + main()) lives in psh.cli; the gateway, config, db, traffic, plans,
gather, charts, render, mail, and lifecycle layers are sibling modules here.
"""
