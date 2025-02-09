# pantheon-sitehealth-emails

Send emails to website owners letting them know what their Pantheon traffic has been and make recommendations about whether/how they should change their current plan or the configuration of their site.

This script is a temporary, standalone way to send reports to website owners via email.  The University of Michigan intends to eventually integrate this script into the ITS Web Hosting Services portal; this will make the reports available to website owners via the web on a daily basis, in addition to scheduled email reports.

Code contributions are gratefully accepted!


## Installation

Works with Python 3.12.  It should work with Python 3.11 but that has not been tested.  It will not work with Python 3.10 or earlier versions.

Running `brew install python@3.12` should work for macOS users.

Other requirements:
* PHP and Composer for the [Emogrifier CSS processor](https://packagist.org/packages/pelago/emogrifier). Any recent versions of PHP and Composer should work, but note that as of January 2025, Pantheon's Terminus command does not work with PHP 8.4, so you should use PHP 8.3 or earlier with the sitehealth script since the sitehealth script also runs Terminus.
    ```
    brew unlink php
    brew install php@8.3
    brew link php@8.3
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

```bash
git clone git@github.com:its-webhosting/pantheon-sitehealth-emails.git
cd pantheon-sitehealth-emails

python3.12 -m venv venv   # change the version number if you're not using 3.12
source venv/bin/activate
which python  # make sure it's under venv/
python -V     # make sure it's the version you expect

ssh-add ~/.ssh/your-github-key-file  # required for installing umcloudflare package from private repo
pip install .[mysql,aws,cloudflare]  # remove from the list the features you won't use

composer install  # the CSS processor pantheon-sitehealth-emails needs is written in PHP
```

Get a copy of your institution's `pantheon-sitehealth-emails.toml` file and put it in the same directory as the script.  If your institution does not have one, then follow the steps in the section [One-time per-institution setup](#one-time-per-institution-setup) below.


## Usage

```bash
git pull  # make sure you have the latest version
source venv/bin/activate  # if you haven't already

export CLOUDFLARE_EMAIL="bjensen@umich.edu"  # set to your email address
read -s -p "Paste your Cloudflare API Key here: " CLOUDFLARE_API_KEY \
    && echo && export CLOUDFLARE_API_KEY

# If ${USER} is not your uniqname, you'll need add the options
# `--smtp-userame YOUR_UNIQNAME` whenever you run the `pantheon-sitehealth-emails` script.
read -s -p "SMTP password for ${USER}: " SMTP_PASSWORD \
    && echo && export SMTP_PASSWORD
```

Run `pantheon-sitehealth-emails --help` for usage information.

Once per week, run the script manually to update the visitor counts:
```
./pantheon-sitehealth-emails --update --all
```

On the first of every month, send the reports:
```
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

## TO DO

* Switch terminus() to returning tuple (output, errors, fatal) for better error handling

* Check for out-of-date WordPress Plugins, Drupal modules, and themes.

* Send daily traffic alerts
  * A comparison of the site's month-to-date visits count compared to a prorated version of that site's monthly limit. If they are at or below zero at any point in the month, flag for extra visibility.
  * A comparison of the previous day's visits to the visits from the day before that. If the percentage increase is high AND the visits count is high enough, flag for extra visibility. This number is a bit less useful, as a very low-traffic site can see a 200-300% increase from day-to-day that is effectively meaningless (e.g. 60 visits instead of 20).
  * Monthly visits remaining on a prorated limit basis, calculated by the current day of the month
  * Query Cloudflare for a fuller traffic picture

* Move nightly traffic capture into portal app

* Add a notice for accessibility scores below a certain number given to us by the accessibility team.

* Measure PHP memory usage and factor that into plan recommendations

* Add % of traffic cached by _Cloudflare_ to traffic table (to show/maximize cost savings)

* Add security score to SiteLens.  Include SSL Labs, securityheaders.com / Mozilla Observatory API, pending updates, best practices, check internals of site (filesystem config, ...)

* Add a Cloudflare score to SiteLens: DNS, cache headers for pages/assets/api, check internals (SSL Full/Strict, WAF not disabled, ...)

* Attach data as CSV

* See if we can get a better recommendation by using AI -- either a customized LLM, or a specifically trained DNN


## Copyright and license information

Copyright (c) 2025 Regents of the University of Michigan.

This file is part of the pantheon-sitehealth-emails script source code.

pantheon-sitehealth-emails is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

pantheon-sitehealth-emails is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with pantheon-sitehealth-emails. If not, see <https://www.gnu.org/licenses/>.

