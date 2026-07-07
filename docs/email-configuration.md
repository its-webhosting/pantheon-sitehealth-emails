# Configuring the report email sender and SMTP server

The monthly report emails' identity (who they appear to be from, who dry-run mail goes to,
which server sends them) is controlled by two optional sections in your
`pantheon-sitehealth-emails.toml` config file: `[Email]` and `[SMTP]`.

**Every key below is optional.** If you omit a key — or omit the whole section — the tool
falls back to the University of Michigan defaults it originally shipped with. If you run the
tool for a different institution, set these so your reports come from *your* addresses.

## `[Email]` — sender identity and addressing

```toml
[Email]
from        = "Example Web Team <webteam@example.edu>"   # the From: header
reply_to    = "webteam@example.edu"                       # the Reply-to: header
msgid_domain = "reports.example.edu"                      # domain used in inline-image IDs

# Sent only on a real run (with --for-real):
bcc         = "ops@example.edu"                            # the Bcc: header

# Dry-run addressing.  Without --for-real, ALL mail goes to the logged-in user instead of
# site owners.  These two keys control that dry-run To: line:
dry_run_to             = "ops@example.edu"                # an extra fixed dry-run recipient
dry_run_username_domain = "example.edu"                   # {smtp-username}@<this> is added too
```

| Key | Controls | Default (U-M) |
|-----|----------|---------------|
| `from` | `From:` header | `University of Michigan Webmaster Team <webmaster@umich.edu>` |
| `reply_to` | `Reply-to:` header | `webmaster@umich.edu` |
| `bcc` | `Bcc:` header (only with `--for-real`) | `januside@go.mail.umich.edu, its-webmaster@go.mail.umich.edu` |
| `dry_run_to` | fixed recipient on a dry run | `januside@go.mail.umich.edu` |
| `dry_run_username_domain` | domain appended to `--smtp-username` on a dry run | `umich.edu` |
| `msgid_domain` | domain in the inline images' `Content-ID` | `webservices.umich.edu` |

## `[SMTP]` — outgoing mail server

```toml
[SMTP]
enabled  = true
host     = "smtp.mail.umich.edu"
port     = 465
username = "<{env USER}"
password = "<{secret env SMTP_PASSWORD}"
```

| Key | Controls | Default (U-M) |
|-----|----------|---------------|
| `enabled` | whether the tool actually sends mail (see below) | *(unset → does not send)* |
| `host` | SMTP server hostname | `smtp.mail.umich.edu` |
| `port` | SMTP server port (SSL) | `465` |
| `username` | account used to log in and (on a dry run) receive a copy | *(none)* |
| `password` | account password | *(none)* |

**Sending is gated on `enabled`.** When `enabled = false` (or `[SMTP]` is omitted) the tool
writes the per-site `.eml` files but does **not** send anything. When `enabled = true` it sends
(to the dry-run addresses unless `--for-real` is given).

Keep the **password** out of the file by sourcing it from an environment variable with a
`<{secret env SMTP_PASSWORD}` substitution; the **username** defaults to `<{env USER}` and is
overridable at runtime with `--smtp-username`. See
[`env-and-smtp-configuration.md`](env-and-smtp-configuration.md) for the substitution forms.
Because a disabled section drops all its keys before those substitutions run, turning SMTP off
does **not** require `SMTP_PASSWORD` to be set.

## Safety reminder

Without `--for-real`, the tool sends **all** mail to the logged-in user (the dry-run
addressing above), never to site owners. Always do a dry run first. See the main
[README](../README.md) for the full run workflow.
