"""The PHP end-of-life check (campaign I8, BLOCKMAP B41 + the I1-extracted builder):
warns/alerts when a site's live-environment PHP version is deprecated or below Pantheon's
supported floor.  SPEC D-i8-4 fixed two defects carried from I1 in this new home: the
lexicographic `php_version < "8.2"` string comparison (so "8.10" no longer false-alerts)
and the KeyError when envs["live"] has no php_version key (the hook now .get()s it and the
builder returns None for None/unparseable input)."""


def build_php_eol_notice(site_name, php_version):
    """Return the PHP-EOL notice dict for php_version, or None when no notice is needed."""
    if php_version in ("7.4", "8.1"):
        return {
            "type": "warning",
            "icon": "&#x26A0;",  # warning sign
            "csv": f"{site_name},php-eol-warning",
            "short": "Upgrade PHP",
            "message": f"""
<p><b>{site_name} is using PHP {php_version}.</b>
You may want to <a href="https://docs.pantheon.io/guides/php/php-versions">manually upgrade your site to PHP 8.2 or later</a>
since <a href="https://docs.pantheon.io/release-notes/2026/03/php-removal-schedule">Pantheon has announced they will no
longer offer PHP {php_version} soon</a>, likely sometime in 2027.</p>
""",
            "text": f"""
{site_name} is using PHP {php_version}.

You may want to manually upgrade your site to PHP 8.2 or later
<https://docs.pantheon.io/guides/php/php-versions>
since Pantheon has announced they will no longer offer PHP {php_version}
soon</a>, likely sometime in 2027.
<https://docs.pantheon.io/release-notes/2026/03/php-removal-schedule>
""",
        }
    try:
        parsed = tuple(int(part) for part in php_version.split("."))
    except (AttributeError, ValueError):
        return None
    if parsed < (8, 2):
        new_php = "7.4" if php_version.startswith("7") else "8.1"
        return {
            "type": "alert",
            "icon": "&#x1F6A8;",  # police car light
            "csv": f"{site_name},php-eol-alert",
            "short": "Upgrade PHP",
            "message": f"""
<p><b>{site_name} is using PHP {php_version}.  On September 30, 2026,
<a href="https://docs.pantheon.io/release-notes/2026/03/php-removal-schedule">Pantheon will move your site
to PHP {new_php}</a>, which may break your site.</b></p>
<p>Please <a href="https://docs.pantheon.io/guides/php/php-versions">manually upgrade your site to PHP 8.2 or later</a>
so you can fix any problems without affecting your site's visitors.  Although you can update
your site to use PHP {new_php} instead of 8.2, please note that Pantheon has already announced that they will also remove
PHP {new_php} sometime after September 30, 2026.</p>
""",
            "text": f"""
{site_name} is using PHP {php_version}.  On
September 30, 2026, Pantheon will move your site to PHP {new_php},
which may break your site.
<https://docs.pantheon.io/release-notes/2026/03/php-removal-schedule>

Please manually upgrade your site to PHP 8.2 or later so you can fix
any problems without affecting your site's visitors.
<https://docs.pantheon.io/guides/php/php-versions>

Although you can update your site to use PHP {new_php} instead of 8.2,
please note that Pantheon has already announced that they will also
remove PHP {new_php} sometime after September 30, 2026.
""",
        }
    return None


def check_php_eol(site_context):
    # April 2026 - September 2026:
    # Check to see if a PHP version upgrade is needed
    php_eol_notice = build_php_eol_notice(
        site_context["site"]["name"], site_context["envs"]["live"].get("php_version"))
    if php_eol_notice is not None:
        site_context.add_notice(php_eol_notice)
