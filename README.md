# pantheon-sitehealth-emails

Send emails to website owners letting them know what their Pantheon traffic has been and make recommendations about whether/how they should change their current plan or the configuration of their site.

This is a standalone script that is intended to be a temporary first implementation to get reports to website owners earlier.  It should be rewritten and added to the `mgmt` app.

`pantheon-sitehealth-emails` currently works only in the prod portal and Pantheon environments.


## Installation

Works with Python 3.12.  It should work with Python 3.11 but that has not been tested.  It will not work with Python 3.10 or earlier versions.
* `brew install python@3.12` will hopefully work.

Other requirements:
* PHP and Composer for the [Emogrifier CSS processor](https://packagist.org/packages/pelago/emogrifier). Any recent versions of PHP and Composer should work.
    * `brew unlink php ; brew install php@8.3 ; brew link php@8.3`
* MySQL 8 client.  Versions 5.x and 9.x are not compatible with the portal database.
    * `brew install pkgconf`
    * `brew install mysql-client@8.4`
    * `brew link mysql-client@8.4`  # makes `mysql_config` and `pkg-config` available, which are needed by `pip`
* AWS CLI (`brew install awscli` should work)
    * Either run `aws configure --profile webhosting` or set the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables.

```bash
git clone git@github.com:its-webhosting/pantheon-sitehealth-emails.git
cd pantheon-sitehealth-emails

python3.12 -m venv venv   # change version number if you're not using 3.12
source venv/bin/activate
which python  # make sure it's under venv/
python -V     # make sure it's the version you expect

ssh-add ~/.ssh/your-github-key-file  # required for installing umcloudflare package from private repo
pip install .

composer install  # the CSS processor pantheon-sitehealth-emails needs is written in PHP

cp pantheon-sitehealth-emails.ini.sample pantheon-sitehealth-emails.ini

```

Edit `pantheon-sitehealth-emails.ini` and configure it correctly for your Pantheon account.  University of Michigan staff should get a copy of this file configured for the U-M environment from Dropbox.


## Usage

```bash
git pull  # make sure you have the latest version
source venv/bin/activate  # if you haven't already

export AWS_PROFILE=webhosting  # set to whatever profile name you chose for the account aws-webhosting-admin
export AWS_DEFAULT_REGION=us-east-1

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


## One-time setup

### Database

```bash
mysql -h "${db_host}" -p -u "${db_user}" "${db_name}"
```

```sql
CREATE DATABASE traffic;
use traffic;
GRANT ALL ON traffic.* TO 'webinfoprod'@'%';
FLUSH PRIVILEGES;
```

```bash
./pantheon-sitehealth-emails --create-tables
```

## TO DO

* Switch terminus() to returning tuple (output, errors, fatal) for better error handling

* Send daily traffic alerts
  * A comparison of the site's month-to-date visits count compared to a prorated version of that site's monthly limit. If they are at or below zero at any point in the month, flag for extra visibility.
  * A comparison of the previous day's visits to the visits from the day before that. If the percentage increase is high AND the visits count is high enough, flag for extra visibility. This number is a bit less useful, as a very low-traffic site can see a 200-300% increase from day-to-day that is effectively meaningless (e.g. 60 visits instead of 20).
  * Monthly visits remaining on a prorated limit basis, calculated by the current day of the month
  * Query Cloudflare for a fuller traffic picture

* Move nightly traffic capture into portal app

* Add a notice for accessibility scores below a certain number given to us by the accessibility team.

* Measure PHP memory usage and factor that into plan recommendations

* Add % of traffic cached by _Cloudflare_ to traffic table (to show/maximize cost savings)

* Attach data as CSV

* See if we can get a better recommendation by using AI -- either a customized LLM, or a specifically trained DNN


## Copyright and license information

Copyright (c) 2025 Regents of the University of Michigan.

This file is part of the pantheon-sitehealth-emails script source code.

pantheon-sitehealth-emails is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

pantheon-sitehealth-emails is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with pantheon-sitehealth-emails. If not, see <https://www.gnu.org/licenses/>.

