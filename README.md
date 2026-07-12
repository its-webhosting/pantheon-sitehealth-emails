# pantheon-sitehealth-emails

Send emails to website owners letting them know what their Pantheon traffic has been and make recommendations about whether/how they should change their current plan or the configuration of their site.

This script is a temporary, standalone way to send reports to website owners via email.  The University of Michigan intends to eventually integrate this script into the ITS Web Hosting Services portal; this will make the reports available to website owners via the web on a daily basis, in addition to scheduled email reports.

Code contributions are gratefully accepted!


## Installation

Works with Python 3.13 and 3.12.  It should work with Python 3.11 but that has not been tested.  It will not work with Python 3.10 or earlier versions.

Running `brew install python@3.12` should work for macOS users.

Other requirements:
* PHP and Composer for the [Emogrifier CSS processor](https://packagist.org/packages/pelago/emogrifier). Any recent versions of PHP and Composer should work.
    ```
    brew unlink php
    brew install php@8.4
    brew link php@8.4
    ```
* MySQL client if you will use this script with a MySQL database instead of the default SQLite3 database. `pkg-config` is needed by `pip` to install the Python package `mysqlclient`.
    ```
    brew install pkgconf
    brew install mysql-client
    ```
    *  University of Michigan users: our web hosting services portal database requires MySQL 8 (versions 5.x and 9.x will not work):
        ```
        brew unlink mysql-client
        brew install mysql-client@8.4
        brew link mysql-client@8.4
        ```
* AWS CLI if you are using AWS resources with the script (for example, RDS databases or secrets)
    * `brew install awscli` should work for macOS users
    * Either run `aws configure --profile webhosting` or set the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables.

Install `uv` by running `brew install uv` or see https://docs.astral.sh/uv/getting-started/installation/

```bash
git clone git@github.com:its-webhosting/pantheon-sitehealth-emails.git
cd pantheon-sitehealth-emails

uv self update
uv python install --managed-python 3.13
uv python upgrade --managed-python 3.13 # in case it was already installed by another project, but out of date
uv venv --managed-python --python 3.13 --allow-existing
source .venv/bin/activate

which python  # make sure it's under .venv/
python -V     # make sure it's the version you expect

uv pip install .[mysql,aws,cloudflare]  # remove from the list the features you won't use

python -m playwright install --with-deps chromium # only if not already installed and working

composer install  # the CSS processor pantheon-sitehealth-emails needs is written in PHP
```

### AWS credentials

If you don't already have them, [create AWS credentials for the script](docs/aws-credentials.md) to use that are restricted to only what the script actually needs to do.

### Config file

Get a copy of your institution's `pantheon-sitehealth-emails.toml` file and put it in the same directory as the script.  If your institution does not have one, then follow the steps in the section [One-time per-institution setup](#one-time-per-institution-setup) below.  For University of Michigan users,
```bash
git clone git@github.com:its-webhosting/pantheon-sitehealth-emails-config.git  # private repo
ln -s pantheon-sitehealth-emails-config/pantheon-sitehealth-emails.toml .
```

Sender identity and the outgoing mail server are configured in the optional `[Email]` and
`[SMTP]` sections of the config (From/Reply-to/Bcc, the dry-run recipient, the inline-image
message-id domain, and the SMTP host/port).  If those sections are omitted the University of
Michigan defaults are used, so non-U-M deployments should set them — see
[`docs/email-configuration.md`](docs/email-configuration.md) and the annotated
`sample-pantheon-sitehealth-emails.toml`.

Any config value can be pulled from an environment variable with a `<{env NAME}` (or
`<{secret env NAME}`) substitution — this is how credentials such as `SMTP_PASSWORD` and the
Cloudflare keys reach the tool without being written into the file (see the exports in
[Usage](#usage) below).  Actually sending mail is gated on `[SMTP].enabled`; when it is `false`
the tool only writes the per-site `.eml` files.  See
[`docs/env-and-smtp-configuration.md`](docs/env-and-smtp-configuration.md) for the substitution
forms (including an optional default), the `[SMTP]` settings, and the Cloudflare credentials/token.


## Usage

```bash
git pull && \
    [ -d pantheon-sitehealth-emails-config ] && \
    ( cd pantheon-sitehealth-emails-config ; git pull ) # make sure you have the latest version


uv python upgrade --managed-python 3.13  # why each time? fix
source .venv/bin/activate  # if needed
ssh-add ~/.ssh/keys/pantheon-ecdsa256
export AWS_ACCESS_KEY_ID="AKIAVV6YMRGQX7XKC4DX"
export AWS_SECRET_ACCESS_KEY="xxx"

# export CLOUDFLARE_EMAIL="bjensen@umich.edu"  # set to your email address
# read -s -p "Paste your Cloudflare API Key here: " CLOUDFLARE_API_KEY \
#     && echo && export CLOUDFLARE_API_KEY

# If ${USER} is not your uniqname, you'll need add the options
# `--smtp-userame YOUR_UNIQNAME` whenever you run the `pantheon-sitehealth-emails` script.
read -s -p "SMTP password for ${USER}: " SMTP_PASSWORD \
    && echo && export SMTP_PASSWORD

# # ...or, if using 1Password:
# export CLOUDFLARE_EMAIL=$(op read "op://Private/ITS Cloudflare/username")
# export CLOUDFLARE_API_KEY=$(op read "op://Private/ITS Cloudflare/API key")
# export SMTP_PASSWORD=$(op read "op://Private/UMich Kerberos Password/password")
```

Run `pantheon-sitehealth-emails --help` for usage information.

Once per week, run the script manually to update the visitor counts:
```
./pantheon-sitehealth-emails --update --all
```

On the first of every month, send the reports:
```bash
# Make sure one site is correct so we don't bomb ourselves with errors.
# Date should be the last day of the previous month.
./pantheon-sitehealth-emails --date 20240731 its-wws-test1

# Run it for all sites, then check the emails for problems.
./pantheon-sitehealth-emails --date 20240731 --all

# Run it for real (sends emails to site owners).
./pantheon-sitehealth-emails --date 20240731 --all --for-real

# In both the webmaster@umich.edu and januside@umich.edu shared
# mailboxes, create a new label "Sent Pantheon traffic reports/${TODAYS_DATE}
# Move all of the bcc:'s of the email from Inbox to this new label.
```

If an `--all` run dies partway through or you interrupt it, `--resume-from SITE_NAME` restarts
the loop at that site, processing it and every site after it in the loop's sorted order:

```bash
./pantheon-sitehealth-emails --date 20240731 --all --resume-from its-wws-test1 --for-real
```

`--resume-from` requires `--all` (it is an error without it) and works with `--update`,
`--only-warn`, and `--import-older-metrics` as well. Naming a site that is not in the
organization is a fatal error before any site is processed. On a resumed run the two summary
artifacts, `YYYYMMDD-notices.csv` and `YYYYMMDD-results.json`, are appended to and merged into
rather than overwritten, so they accumulate across the original and resumed runs. See
[docs/resuming-interrupted-runs.md](docs/resuming-interrupted-runs.md).

When the `[Cloudflare]` section is enabled, the program fetches the set of Cloudflare-proxied
FQDNs (`fqdns.json`) directly from the Cloudflare API and refreshes it automatically (when it is
missing, or stale and you are processing multiple sites). Force a refresh with
`--update-cloudflare-fqdns`, or suppress the staleness refresh with `--no-update-cloudflare-fqdns`.
See [docs/cloudflare-fqdns.md](docs/cloudflare-fqdns.md) for details.

When `[Cloudflare.cachecheck]` is additionally enabled (opt-in), report runs also probe each
site's proxied FQDNs over HTTPS and report cache-configuration problems (missing/short
`Cache-Control`, cookies on public content, uncacheable `Cf-Cache-Status`, …) as a
"Cloudflare caching" notice.  Before the site loop, the program verifies its own egress IP
addresses appear in a configured Cloudflare IP list (skip with `--allow-any-source-ip`).
The `cloudflare` extra installs the needed `httpx` and `beautifulsoup4` packages.
See [docs/cloudflare-cachecheck.md](docs/cloudflare-cachecheck.md) for details.


## One-time per-institution setup

```bash
cp sample-pantheon-sitehealth-emails.toml pantheon-sitehealth-emails.toml
```

Edit `pantheon-sitehealth-emails.toml` and configure it correctly for your Pantheon account and your local environment.

### Create database tables

#### SQLite3

```bash
./pantheon-sitehealth-emails --create-tables
```

#### MySQL

For MySQL, first create the database,

```bash
mysql -h "${db_host}" -p -u "${db_user}" "${db_name}"
```

```sql
CREATE DATABASE traffic;
use traffic;
GRANT ALL ON traffic.* TO "${db_user}"@'%';
FLUSH PRIVILEGES;
quit
```

Then create the tables,

```bash
./pantheon-sitehealth-emails --create-tables
```

### Import data from Pantheon

Pantheon keeps daily traffic data for only 28 days; any new daily traffic data will be added to the sitehealth database each time the script runs.

But Pantheon also keeps weekly data for 12 weeks, and monthly data for 12 months.  Running the script with the `--import-older-metrics` option will add the average daily traffic for the weekly and monthly periods to the database.

Import the older (weekly and monthly) metrics for `--all` sites:

```bash
./pantheon-sitehealth-emails --import-older-metrics --all
```

## Testing

The project has a pytest-based test harness under `tests/`.  See
[`tests/README.md`](tests/README.md) for the full layout and how to add tests.

Install the test dependencies (once), plus the headless browser used by the render tier:

```bash
uv pip install .[test]
python -m playwright install --with-deps chromium   # needs sudo for the system libraries
```

Run the tests with the `./run-tests` wrapper (a thin front-end for pytest):

```bash
./run-tests              # everything, including the live tier (needs Terminus auth + network)
./run-tests --fast       # offline subset only: unit + integration + shim e2e + golden + render
./run-tests --llm        # terse, machine-parseable summary (for pasting failures into an assistant)
./run-tests --coverage   # report coverage (no gate; in-process tiers only)
./run-tests --update-goldens   # refresh the rendered-report snapshots after an intended change
./run-tests --record     # re-record the terminus fixtures from the live test site (read-only)
```

Any other arguments (`-k EXPR`, `-m MARK`, file paths) are passed straight through to pytest,
e.g. `./run-tests -m "e2e"` or `./run-tests tests/unit`.

Tiers are selected by pytest marks: `unit`, `integration`, `e2e`, `live`, `render`, `email`,
`slow`.  `--fast` excludes `live` and `slow`.  The `email` tier is a deferred, skipped scaffold
(it activates when email sending is re-enabled).  Two hard rules the harness enforces: tests
never run the program with `--all` or `--for-real` (a `run_program()` interlock refuses them),
and they use only the `its-wws-test1` / `its-wws-test2` test sites, read-only.

## TO DO

* git worktrees! (add to prompts to always use worktrees using Claude's `EnterWorktree` tool), https://code.claude.com/docs/en/worktrees
* assess memory system -- good enough, or install something new?
* update analyze-session skill based on new workflow
  * git rtk not worth it, after removing from analyze-session, uninstall
* add SendGrid API support as an alternative to SMTP
* finish implementing better secrets handling
    * Terminus machine token (filesystem for now, AWS Secrets Manager later?)
    * SSH and key (ssh-agent for now, something else later?)
    * UMich Kerberos password --> replace with SendGrid API key in AWS Secrets Manager
    * Cloudflare credentials (special read-only token from AWS Secrets Manager?)
    * [ok] AWS credentials (set in environment for now)
* rework everything from ~3,700 line script into a combination of checks (in the `checks` directory), plugins (where appropriate), and other Python files/packages
  * refactor the program to take the most advatage of the program's check framework,plugin framework, and configuration framework, moving checks, capabilities (such as fetching secrets from AWS versus another source), and other funtionality under `./checks` and `./plugins` wherever it is appropriate. Similarly, we will modify all parts of the program to modify the program's configuration framework. Document plugin system and config file as part of this.
  * possibly (check with Claude): expand the hooks/phases (possibly adding producer/consumer dependenencies for DAG ordering)
* Add ruff for linting+formatting, switch from "house styles" to best-practice/standard Python styles
* update dependencies
* Implement SMTP testing, GMail testing (see test harness prompt for requirements)
* Add % of traffic cached by _Cloudflare_ to traffic table (to show/maximize cost savings)
* switch to Pantheon API where possible
* parallelize where safe and possible, both within a single site (careful about data dependencies!) as well as handling a predefinied number of multiple sites in parallel (when run with `--all` or multiple sites explicitly specified)
* add everything to its-webhosting/terraform-infra repo that should be there

* Check Live environment (not Dev) for the version of PHP, Drupal/WordPress, and all the plugins/modules/themes and if everything is up to date there then skip asking Pantheon about updates pending in the Dev environment.  This way, site owners that are not using the Pantheon WebOps workflow won't be getting wrong information.

* Report on environment lock (no notice, just a report section)

* Send daily traffic alerts
  * A comparison of the site's month-to-date visits count compared to a prorated version of that site's monthly limit. If they are at or below zero at any point in the month, flag for extra visibility.
  * A comparison of the previous day's visits to the visits from the day before that. If the percentage increase is high AND the visits count is high enough, flag for extra visibility. This number is a bit less useful, as a very low-traffic site can see a 200-300% increase from day-to-day that is effectively meaningless (e.g. 60 visits instead of 20).
  * Monthly visits remaining on a prorated limit basis, calculated by the current day of the month
  * Query Cloudflare for a fuller traffic picture

* Move nightly traffic capture into portal app

* Add a notice for accessibility scores below a certain number given to us by the accessibility team.

* Measure PHP memory usage and factor that into plan recommendations

* Add security score to SiteLens.  Include Cloudflare Radar, SSL Labs, securityheaders.com / Mozilla Observatory API, pending updates, best practices, check internals of site (filesystem config, ...)

* Add a Cloudflare score to SiteLens: DNS, cache headers for pages/assets/api, check internals (SSL Full/Strict, WAF not disabled, ...)

* Attach data as CSV

* See if we can get a better recommendation by using AI -- either a customized LLM, or a specifically trained DNN


## Copyright and license information

Copyright (c) 2025 Regents of the University of Michigan.

This file is part of the pantheon-sitehealth-emails script source code.

pantheon-sitehealth-emails is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

pantheon-sitehealth-emails is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with pantheon-sitehealth-emails. If not, see <https://www.gnu.org/licenses/>.
