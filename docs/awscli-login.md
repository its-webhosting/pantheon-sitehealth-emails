
We used to run pantheon-sitehealth-emails using IAM users associated with
people. Now, we are using per-person credentials that **only** have access
to what the program needs to access.

Here is the older way to configure things to use awscli-login, though.

# Install awscli-login

https://pypi.org/project/awscli-login/

```bash
direnv allow .  # sets AWS_CONFIG to point to ./aws-config
brew install awscli  # unless you already have it via another method
uv pip install --upgrade setuptools
uv pip install awscli-login
aws configure set plugins.login awscli_login

aws configure set plugins.cli_legacy_plugin_path \
    $(uv pip show awscli-login | sed -nr 's/^Location: (.*)/\1/p')

aws login configure
# ECP Endpoint URL [None]: https://weblogin.umich.edu/idp/profile/SAML2/SOAP/ECP
# Username [None]: markmont
# Enable Keyring [False]:
# Duo Factor [None]: push
# Role ARN [None]:
```

### Log in to AWS

* Log in to AWS at https://aws.it.umich.edu/
* Select the role and account `its-wws-admin`

Also log in via the command line:

```bash
aws login
```
