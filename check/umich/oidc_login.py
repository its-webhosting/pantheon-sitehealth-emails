"""The umich-oidc-login reinstall check (campaign I9, from B34; U-M-gated since I9).

A site_post_gather hook.  For a WordPress site with an active umich-oidc-login plugin at
version <= 1.2.99, advise a manual reinstall: 1.3.0 and later are hosted on GitHub, not on
wordpress.org, so WordPress can no longer auto-update the plugin.
"""

import semver


def check_oidc_login(site_context):
    if not site_context["framework"].startswith("wordpress"):
        return
    plugins = site_context["wordpress_plugins"]
    if plugins is None:
        return
    site = site_context["site"]
    for p in plugins:
        # Special check for umich-oidc-login upgrade, December 2025
        if p["name"] == "umich-oidc-login" and p["status"] != "inactive":  # noqa: SIM102 -- nesting moved verbatim from B34 (Invariant 8); keeps the notice-dict indentation byte-stable
            if semver.compare(p["version"], "1.2.99") <= 0:
                site_context.add_notice(
                    {
                        "type": "warning",
                        "icon": "&#x26A0;",  # warning sign
                        "csv": f"{site['name']},umich-oidc-login-reinstall",
                        "short": "Reinstall the UMich OIDC Login plugin to get the latest version",
                        "message": f"""
<p><strong>Please reinstall the UMich OIDC Login plugin to get the latest version.</strong></p>
<p>Versions 1.3.0 and later of the UMich OIDC Login plugin are hosted
<a href="https://github.com/its-webhosting/umich-oidc-login">on GitHub</a> rather than on wordpress.org.
{site["name"]} is using version {p["version"]}, so you will need to install version 1.3.0 or later by hand to get
future updates of this plugin through WordPress.  Please use one of the following three methods:
</p>
<ul>
    <li>
        (Simplest method, if you already have <a href="https://docs.pantheon.io/terminus">Terminus</a> set up <a href="https://docs.pantheon.io/terminus/install#ssh-authentication-optional-but-recommended">to work with WP CLI</a>): Run the command
        <pre>
terminus wp {site["name"]}.dev -- plugin install --force --activate https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip</pre>And then deploy from Dev to Test, and from Test to Live.<br /><br />
    </li>
    <li>
        Or, <a href="https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip">download the latest version</a>,
        upload the zip file through your WordPress admin dashboard using <code>Plugins -> Add New -> Upload Plugin</code>, then activate the plugin.<br /><br />
    </li>
    <li>
        Or, <a href="https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip">download the latest version</a>,
        unzip it on your local computer, upload the resulting <code>umich-oidc-login</code> folder to the <code>wp-content/plugins/</code> folder in your site
        (replacing any umich-oidc-login folder that is already there), then activate the plugin.
    </li>
</ul>
<p style="font-size: smaller;"><strong>NOTE:</strong> If your site uses any <code>[umich_oidc_button]</code> or <code>[umich_oidc_link]</code> shortcodes and uses an HTML
attribute (such as <code>class</code> or <code>style</code>) in those shortcodes, after you upgrade, the site will not look right and may
not function correctly unless you turn on the option <code>Settings -> UMich OIDC Login -> Shortcodes ->
Custom buttons and links -> Allow HTML attributes</code>.  This is safe to turn on as long as you trust any users with the
WordPress roles Contributor, Author, and Editor not to use Cross-Site Scripting to compromise an Administrator account
and gain Administrator access for themselves.  If you don't want to turn this option on, an alternative is to use a
child theme or a custom plugin to style the OIDC buttons/links.</p>
""",
                        "text": f"""
Please reinstall the UMich OIDC Login plugin
to get the latest version.

Versions 1.3.0 and later of the UMich OIDC Login plugin are hosted
on GitHub <https://github.com/its-webhosting/umich-oidc-login>
rather than on wordpress.org. {site["name"]} is using
version {p["version"]}, so you will need to install version 1.3.0
or later by hand to get future updates of this plugin through
WordPress.  Please use one of the following three methods:

* Simplest method, if you already have Terminus
<https://docs.pantheon.io/terminus> set up to work with WP CLI
<https://docs.pantheon.io/terminus/install#ssh-authentication-optional-but-recommended">
Run the command

terminus wp {site["name"]}.dev -- plugin install --force --activate https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip

And then deploy from Dev to Test, and from Test to Live.

* Or, download the latest version
<https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip>
upload the zip file through your WordPress admin dashboard using
Plugins -> Add New -> Upload Plugin, then activate the plugin.

* Or, download the latest version
<https://github.com/its-webhosting/umich-oidc-login/releases/latest/download/umich-oidc-login.zip>
unzip it on your local computer, upload the resulting
umich-oidc-login folder to the wp-content/plugins/ folder in your
site (replacing any umich-oidc-login folder that is already there),
then activate the plugin.

NOTE: If your site uses any [umich_oidc_button] or
[umich_oidc_link] shortcodes and uses an HTML attribute (such as
"class" or "style") in those shortcodes, after you upgrade, the
site will not look right and may not function correctly unless you
turn on the option Settings -> UMich OIDC Login -> Shortcodes ->
Custom buttons and links -> Allow HTML attributes.  This is safe
to turn on as long as you trust any users with the WordPress roles
Contributor, Author, and Editor not to use Cross-Site Scripting to
compromise an Administrator account and gain Administrator access
for themselves.  If you don't want to turn this option on, an
alternative is to use a child theme or a custom plugin to style
the OIDC buttons/links.
""",
                    }
                )
