# Sourcing config values from the environment (and configuring SMTP / Cloudflare)

Any string value in your `pantheon-sitehealth-emails.toml` can be filled in from an external
source at run time using a `<{ ... }>` marker, instead of being written into the file. This is
how secrets — your SMTP password, Cloudflare credentials — stay out of the config file.

## Substitution forms

| In the config file | Resolves to |
|--------------------|-------------|
| `"<{env NAME}"` | the value of environment variable `NAME` |
| `"<{secret env NAME}"` | the same thing (`secret` is an accepted prefix, to read like the AWS form) |
| `"<{env NAME default}"` | `NAME` if it is set, otherwise the literal `default` |
| `"<{secret env NAME default}"` | same, with the `secret` prefix |
| `"<{secret aws SECRET KEY}"` | a key from an AWS Secrets Manager secret (needs `[AWS]` enabled) |

Notes:

- **A referenced variable that is not set aborts the run** with an error that names both the
  config setting and the missing variable — *unless* you supplied a default.
- **Set-but-empty is not the same as unset.** If `NAME=""`, `<{env NAME}` yields an empty
  string; the default (if any) is only used when the variable is *absent*.
- **Defaults with spaces** must be quoted: `"<{env NAME \"two words\"}"`.

## Turning a section off

If a section has `enabled = false`, only `enabled` is kept — every other setting in that section
is dropped *before* substitutions run. So disabling a feature never requires that feature's
environment variables or secrets to exist. (A section with no `enabled` key, or `enabled = true`,
is processed normally.)

## Example: SMTP credentials from the environment

```toml
[SMTP]
enabled  = true
host     = "smtp.mail.umich.edu"
port     = 465
username = "<{env USER}"                    # override at runtime with --smtp-username
password = "<{secret env SMTP_PASSWORD}"    # required when enabled
```

Before running, make the password available in your shell (it is never stored in the file):

```bash
read -s -p "SMTP password for ${USER}: " SMTP_PASSWORD && echo && export SMTP_PASSWORD
```

If your login name is not your mail username, pass `--smtp-username YOUR_NAME` (it overrides the
`username` above). See [`email-configuration.md`](email-configuration.md) for the rest of the
`[SMTP]` and `[Email]` settings.

## Example: Cloudflare credentials

Cloudflare credentials come **entirely** from the `[Cloudflare]` section (there is no separate
"if the env var is set, use it" fallback). Use **either** an API token (preferred) **or** the
account email plus Global API Key:

```toml
[Cloudflare]
enabled = true
# Preferred — an API token:
api_token = "<{secret env CLOUDFLARE_API_TOKEN}"
# Or the email + Global API Key pair (used only when api_token is absent):
email   = "<{secret env CLOUDFLARE_EMAIL}"
api_key = "<{secret env CLOUDFLARE_API_KEY}"
```

When `api_token` is present and non-empty it is used and `email`/`api_key` are ignored. Whichever
values you reference must be available in the environment (or given as literals) when Cloudflare
is enabled, or the run stops with a clear error. Set them, for example, with:

```bash
export CLOUDFLARE_API_TOKEN=...            # preferred
# or:
export CLOUDFLARE_EMAIL="you@example.edu"
export CLOUDFLARE_API_KEY=...
```

See the main [README](../README.md) for the full run workflow.
