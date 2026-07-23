"""Per-site report rendering (campaign I12, from main()'s B53/B54 regions).

escape_url lives here so psh/, check/ (via sc.escape_url), and the notice builders share
one URL-escaping rule.  render_report is CWD-relative (templates, inline-styles.php,
build/) like the rest of the program; a php inliner failure raises
subprocess.CalledProcessError into main()'s except-BaseException abort path, exactly as
the inline original did.
"""
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

from jinja2 import Template


def escape_url(url: str) -> str:
    return urllib.parse.quote(url, safe=":/?#&=", encoding="utf-8", errors="strict")


def render_report(site_name: str, template_dict: dict) -> tuple[str, str]:
    """Render build/{site}.html/.txt, inline CSS via php, add !important; return bodies.

    Returns (html_body, text_body): html_body is the build/{site}-inline2.html content --
    the HTML actually attached to the message (CLAUDE.md § Rendering); text_body is the
    rendered text template.
    """
    with Path("email_template.html").open(encoding="utf-8") as f:
        html_template = Template(f.read())
    html_body = html_template.render(**template_dict)
    # Write the results to a file for debugging.  Later, we'll use this file as input to the PHP script that
    # inlines the CSS. We're not piping the data to/from the script directly because the files are useful
    # for inspecting/debugging.
    with Path(f"build/{site_name}.html").open("w", encoding="utf-8") as f:
        f.write(html_body)

    with Path("email_template.txt").open(encoding="utf-8") as f:
        text_template = Template(f.read())
    text_body = text_template.render(**template_dict)
    with Path(f"build/{site_name}.txt").open("w", encoding="utf-8") as f:
        f.write(text_body)

    subprocess.run(  # noqa: S603 -- fixed ["php", "inline-styles.php", ...] argv, no shell, no untrusted-input execution path; the sanctioned non-gateway subprocess (the CSS inliner), moved verbatim from main() (SPEC I12 §2.4)
        [  # noqa: S607 -- "php" resolved via PATH is the documented runtime requirement (CLAUDE.md: php + composer must be on PATH); pinning an absolute path would break every install
            "php",
            "inline-styles.php",
            f"build/{site_name}.html",
            f"build/{site_name}-inline.html",
        ],
        stdout=sys.stdout,
        stderr=sys.stderr,
        check=True,
    )
    with Path(f"build/{site_name}-inline.html").open(encoding="utf-8") as f:
        html_body = f.read()

    style_elements = re.findall(r"(<style.*?</style>)", html_body, re.DOTALL)
    for style in style_elements:
        # Add !important to the end of each CSS attribute that doesn't already end with !important
        modified_style = re.sub(
            r"(?<!important);", " !important;", style, flags=re.DOTALL
        )
        html_body = html_body.replace(style, modified_style)

    with Path(f"build/{site_name}-inline2.html").open("w", encoding="utf-8") as f:
        f.write(html_body)

    return html_body, text_body
