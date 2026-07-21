"""The UMich Hummingbird fork check (campaign I9, from B34; U-M-gated since I9).

A site_post_gather hook.  Our fork of the Hummingbird performance plugin carries 'umich' in
its version string; it is unsupported and replaced by University of Michigan: Cloudflare
Cache.  Alert if it is active, advise deletion if it is merely installed.
"""

import html

import script_context as sc


def check_hummingbird_fork(site_context):
    if not site_context["framework"].startswith("wordpress"):
        return
    plugins = site_context["wordpress_plugins"]
    if plugins is None:
        return
    site = site_context["site"]
    # Special check for our fork of Hummingbird (version number contains 'umich')
    name = "hummingbird-performance"
    display_name = "UMich Hummingbird"
    url = "https://documentation.its.umich.edu/node/4243"
    url2 = "https://documentation.its.umich.edu/node/5114"
    reason = "UMich Hummingbird is unsupported and has been replaced by University of Michigan: Cloudflare Cache"
    installed = [
        p for p in plugins if p["name"] == name and "umich" in p["version"]
    ]
    if len(installed) != 0:
        plugin = installed[0]
        sc.console.print(
            f":exclamation: [bold red] ATTENTION: {site['name']} has {display_name} installed."
        )
        if "status" in plugin and plugin["status"] == "inactive":
            site_context.add_notice(
                {
                    "type": "info",
                    "icon": "&#x1F50E;",  # magnifying glass
                    "csv": f"{site['name']},unsupported-turned-off,{name}",
                    "short": f"delete inactive plugin {name}",
                    "message": f'<p>The <a href="{sc.escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin is inactive but should be deleted:</p><p>{html.escape(reason)}</p>',
                    "text": f"The {display_name} WordPress plugin\n<{url}>\nis inactive but should be deleted: {reason}",
                }
            )
        else:
            site_context.add_notice(
                {
                    "type": "alert",
                    "icon": "&#x1F6A8;",  # police car light
                    "csv": f"{site['name']},unsupported,{name}",
                    "short": f"replace plugin {name} with umich-cloudflare",
                    "message": f'''
<p>The <a href="{sc.escape_url(url)}">{html.escape(display_name)}</a> WordPress plugin needs to be replaced! It is unsupported and out of date.</p>
<p>Please install the <a href="{sc.escape_url(url2)}">University of Michigan: Cloudflare Cache</a> plugin and remove {html.escape(display_name)}.</p>
''',
                    "text": f"""
The {display_name} WordPress plugin\n<{url}>\nneeds to be replaced!
It is unsupported and out of date.

Please install the University of Michigan: Cloudflare Cache
<{url2}>
plugin and remove {display_name}.
""",
                }
            )
