# Cloudflare proxied-FQDN data (`fqdns.json`)

When the `[Cloudflare]` section is **enabled**, the tool checks each site's custom domains
against the set of hostnames that are **proxied through Cloudflare**. That set is kept in a file
named `fqdns.json` at the top of the repo. You no longer generate this file by hand — the program
fetches it from the Cloudflare API and keeps it up to date for you.

## What's in the file

`fqdns.json` maps each proxied website FQDN to the Cloudflare zone it belongs to and its DNS
origins:

```json
{
    "academictechnology.umich.edu": {
        "zone_id": "1f3941c8aa44c353b2f10d2acaa5dc8e",
        "origins": [ "23.185.0.2", "2620:12a:8001::2", "2620:12a:8000::2" ]
    },
    "accessibility.engin.umich.edu": {
        "zone_id": "437c5deaee526832da03fd5b699a6497",
        "origins": [ "wp.wpenginepowered.com" ]
    }
}
```

The program uses only the **keys** (the FQDNs) to answer "is this hostname proxied?"; `zone_id`
and `origins` are stored for other tooling. (An older `fqdns.json` whose values were plain arrays
still works and is upgraded to this shape the next time the file is refreshed.)

## When the file is refreshed automatically

With `[Cloudflare]` enabled, the program refreshes `fqdns.json` before a run when **any** of
these is true:

- `fqdns.json` does not exist yet;
- `fqdns.json` is more than 24 hours old **and** you are processing multiple sites (`--all`, or
  more than one site named on the command line) **and** you did not pass
  `--no-update-cloudflare-fqdns`;
- you pass `--update-cloudflare-fqdns` (forces a refresh regardless of the above).

Otherwise the program just reads the existing file. Traffic-only runs (`--update` and
`--import-older-metrics`) never use `fqdns.json`, so they skip the refresh.

## The two flags

- `--update-cloudflare-fqdns` — force a refresh from Cloudflare before this run. Requires
  `[Cloudflare]` to be enabled (otherwise the program exits with a message). Cannot be combined
  with `--no-update-cloudflare-fqdns`.
- `--no-update-cloudflare-fqdns` — suppress the automatic 24-hour staleness refresh (use the file
  as-is even when running against many sites).

## What the refresh needs

The refresh uses the same `[Cloudflare]` credentials as the rest of the plugin (an `api_token`,
preferred, or `email` + `api_key`). The credentials need **DNS:Read** across the zones you want
covered. The program lists every account those credentials can see, then every zone in each
account, then each zone's proxied DNS records.

If the fetch returns **zero zones**, the program treats it as a **fatal error** — an
authenticated credential that sees no zones almost always means the token lacks DNS:Read scope, so
fixing the credential is better than writing an empty file that would flag every domain as "not
proxied." A fetch that finds zones but no proxied records is allowed (it just prints a warning).

Any Cloudflare API error during the refresh is fatal (the run stops with a clear message); your
existing `fqdns.json` is left untouched because the new file is written atomically.
