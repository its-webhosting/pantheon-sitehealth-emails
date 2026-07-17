"""The gateway: every Terminus/WP-CLI/Drush subprocess flows through this module.

Increment I2 of the modularization campaign (development/2026-07-17-mod-I2-gateway/SPEC.md).
The eleven Terminus/WP/Drush subprocess-facing wrappers moved here from psh/_legacy.py, which
re-imports them so its call sites and the sc-exposure block keep resolving unchanged.  This is
the single seam through which the future Pantheon-API transport swap becomes a one-module change
(CAMPAIGN.md D1).

The in-process monkeypatch point for anything routed through the wrappers is
`psh.gateway.run_terminus`: terminus/wp/drush resolve run_terminus in THIS module's namespace, so
patching the remnant's imported binding would not intercept them (SPEC §Seams, PD#14).
"""
import html
import json
import re
import subprocess
import time
from typing import Any, NamedTuple

from rich.markup import escape

import script_context as sc


class GatewayResult(NamedTuple):
    result: Any
    errors: str
    fatal: bool


def run_terminus(command: list, input_data=None) -> GatewayResult:  # noqa: C901, PLR0912 -- moved verbatim; run_terminus's stderr/markup escaping is under-tested and refactoring is a review activity, not part of a behavior-preserving move (SPEC §Broad-ruff findings)

    command = ["terminus", "--no-ansi", "--no-interaction", *command]
    commandline = " ".join(
        [
            (("'" + arg.replace("'", "\\'") + "'") if len(arg.split()) > 1 else arg)
            for arg in command
        ]
    )

    sc.debug("Running Terminus command:\n", commandline)

    with sc.console.status(f"[bold green]Running: [bright_magenta]{commandline}"):
        p = subprocess.Popen(  # noqa: S603 -- command is a fixed ["terminus", ...] argv (no shell, no untrusted-input execution path); spawning it is the gateway's entire purpose
            command,
            stdin=(subprocess.PIPE if input_data is not None else None),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
        )
        try:
            data = None if input_data is None else input_data.encode("utf-8")
            stdout, stderr = p.communicate(input=data, timeout=300)
        except subprocess.TimeoutExpired:
            p.kill()
            stdout, stderr = p.communicate()
            output = stdout.decode("utf-8").strip()
            errors = stderr.decode("utf-8").strip()
            sc.console.print("[bold red]Terminus command timed out.")
            sc.console.print("===== stdout:\n" + escape(output))
            sc.console.print("===== stderr:\n" + escape(errors))
            errors += "\n[ERROR] Terminus command timed out.\n"
            return GatewayResult(output, errors, fatal=True)

    output = stdout.decode("utf-8").strip()
    errors = stderr.decode("utf-8").strip()

    if (
        command[3] in ("wp", "composer")
        and len(output) > 0
        and (p.returncode == 0 or command[3] == "composer")
    ):
        lines = output.split("\n")
        filtered_lines = []
        extra_errors = []
        for line in lines:
            if re.match(r"^\s*Cannot create cache directory\s+", line):
                continue
            if re.match(r"^\s*Warning:\s+", line):
                extra_errors.append(line)
            else:
                filtered_lines.append(line)
        output = "\n".join(filtered_lines)
        if command[3] == "composer":
            errors = ""
            p.returncode = 0
        else:
            errors = "\n".join(extra_errors) + "\n" + errors
    sc.debug("Terminus output:\n", escape(output), level=3)

    if len(errors) > 0 and p.returncode == 0:
        lines = errors.split("\n")
        filtered_lines = []
        for raw_line in lines:
            line = raw_line.strip()
            if (
                line != ""
                and not line.endswith("[Exit: 0] (Attempt 1/1)")
                and not line.startswith("[warning] There are no available updates")
                and "This environment is in read-only Git mode" not in line
                and not (
                    line.startswith("Warning: Permanently added")
                    and line.endswith("to the list of known hosts.")
                )
            ):
                filtered_lines.append(line)
        errors = "\n".join(filtered_lines)
    if len(errors) > 0:
        sc.console.print("Terminus errors:")
        sc.console.print(escape(errors))

    if p.returncode != 0:
        line = f"Terminus command failed with exit code {p.returncode}: {stderr}\n"
        sc.console.print(f"[bold red][ERROR] {escape(line)}")
        errors += "\n" + line
        return GatewayResult(output, errors, fatal=True)

    return GatewayResult(output, errors, fatal=False)


class TerminusError(RuntimeError):
    """
    A Terminus command failed at a call site that needs its data.

    Raised by terminus_data() when the command was fatal (timeout / non-zero exit) or its
    output could not be decoded.  Carries the command and captured stderr so the failure is
    reported with its real cause instead of a downstream TypeError far from the source (P3).
    """

    def __init__(self, command, errors: str):
        self.command = command
        self.errors = errors
        super().__init__(f"Terminus command {command!r} failed: {errors}")


def terminus(*args) -> GatewayResult:
    """
    Run Terminus with the given arguments and return (result, errors, fatal).

    result is the parsed JSON on success, or None if the output could not be JSON-decoded.
    errors is the captured stderr (plus any decode detail), fatal is True when the underlying
    run_terminus reported a fatal condition (e.g. timeout).  On an expired-session error the
    call is retried once before returning.  Callers that index into result should either check
    fatal / `result is None` themselves or use terminus_data() (which raises TerminusError).
    """
    # args is a tuple (from *args); work with a list so the retry sentinel can be
    # added/removed without mutating a tuple (which previously crashed this path).
    args = list(args)
    retry = True
    if "pshe-no-retry" in args:
        args.remove("pshe-no-retry")
        retry = False
    command = [*args, "--format=json"]
    output, errors, fatal = run_terminus(command)
    try:
        result = json.loads(output)
    except json.JSONDecodeError as e:
        result = None
        errors += "\n" + output + "\n" + str(e)
    if errors != "":
        # escape(): terminus's stderr is untrusted text, and rich would parse a bracketed
        # lowercase-initial fragment in it as a style tag and DELETE it (or, on an unmatched
        # closing tag, raise MarkupError).  Same defect class as the abort-path prints.
        sc.console.print(f"[bold red]Terminus error: {escape(errors)}")
        if retry and "Invalid or expired session header: X-Pantheon-Session" in errors:
            sc.console.print("Sleeping for 5 seconds and then retrying...")
            time.sleep(5)
            args.append("pshe-no-retry")
            return terminus(*args)
    return GatewayResult(result, errors.strip(), fatal)


def terminus_data(*args) -> Any:
    """
    terminus() for call sites that index into the result and cannot proceed without it.

    Returns the parsed JSON, or raises TerminusError if the command was fatal or produced no
    decodable data.  Use this where a failure should abort (org-level calls, helper functions);
    inside the per-site loop, prefer checking fatal / `result is None` inline and skipping the
    site so one bad site does not kill the whole run.
    """
    result, errors, fatal = terminus(*args)
    if fatal or result is None:
        raise TerminusError(list(args), errors)
    return result


def wp(siteenv: str, *args) -> GatewayResult:
    """
    Run a "wp" command through Terminus and return the result as JSON.

    Returns a GatewayResult (result, errors, fatal); result is None on JSON-decode failure.
    """
    command = ["wp", siteenv, "--", *args, "--format=json"]
    output, errors, fatal = run_terminus(command)
    try:
        result = json.loads(output)
    except json.JSONDecodeError as e:
        result = None
        errors += "\n" + output + "\n" + str(e)
    return GatewayResult(result, errors.strip(), fatal)


def wp_eval(siteenv: str, *args) -> GatewayResult:
    """
    Run a "wp eval" command through Terminus and return the result as a string.

    Returns a GatewayResult (output, errors, fatal).
    """
    command = ["wp", siteenv, "--", "eval", *args]
    output, errors, fatal = run_terminus(command)
    return GatewayResult(output.strip(), errors.strip(), fatal)


def wp_error(site: str, code: str, message: str, errors: str) -> list[dict[str, str]]:
    html_message = message.replace(site, f"<strong>{site}</strong>")
    return [
        {
            "type": "alert",
            "icon": "&#x1F6A8;",  # police car light
            "csv": f"{site},wp-error,{code},{json.dumps(errors).replace(',', '\\,')}",
            "short": "fix WP CLI error",
            "message": f"""
<p>{html_message}
<code>wp</code> (WP CLI) returned the following error:</p>
<pre>{html.escape(errors)}</pre>
""",
            "text": f"""
{message}
"wp" (WP CLI) returned the following error:

----- START WP CLI ERROR -----
{errors}
----- END WP CLI ERROR -----

""",
        }
    ]


def fix_drush_output(output: str, errors: str) -> tuple[str, str]:
    """
    Move any error messages at the start of the output from a Drush command to the errors string.
    """
    if not isinstance(output, str) or output == "":
        return output, errors

    if output[0] != "{":
        lines = output.split("\n")
        linenum = 0
        while linenum < len(lines):
            if lines[linenum] and lines[linenum][0] == "{":
                break
            linenum += 1
        errors = "\n".join(lines[:linenum]) + errors
        output = "\n".join(lines[linenum:])

    sc.debug("Drush output:\n", escape(output), "\nDrush errors:\n", escape(errors), level=2)

    return output, errors


def drush(siteenv: str, *args) -> GatewayResult:
    """
    Run a "drush" command through Terminus and return the result as a JSON object.

    Returns a GatewayResult (result, errors, fatal); result is None on JSON-decode failure.
    """
    command = ["drush", siteenv, "--", *args, "--format=json"]
    output, errors, fatal = run_terminus(command)
    output, errors = fix_drush_output(output, errors)
    try:
        result = json.loads(output)
    except json.JSONDecodeError as e:
        result = None
        errors += "\n" + output + "\n" + str(e)
    return GatewayResult(result, errors.strip(), fatal)


def drush_php_script(siteenv: str, script: str) -> GatewayResult:
    """
    Run a "drush php:script" command through Terminus and return the result as a JSON object.

    Returns a GatewayResult (result, errors, fatal); result is None on JSON-decode failure.
    """
    command = ["drush", siteenv, "--", "php:script", "--format=json", "-"]
    output, errors, fatal = run_terminus(command, script)
    output, errors = fix_drush_output(output, errors)
    try:
        result = json.loads(output)
    except json.JSONDecodeError as e:
        result = None
        errors += "\n" + output + "\n" + str(e)
    return GatewayResult(result, errors.strip(), fatal)


def drush_error(site: str, code: str, message: str, errors: str) -> list[dict[str, str]]:
    html_message = message.replace(site, f"<strong>{site}</strong>")
    return [
        {
            "type": "alert",
            "icon": "&#x1F6A8;",  # police car light
            "csv": f"{site},drush-error,{code},{json.dumps(errors).replace(',', '\\,')}",
            "short": "fix drush error",
            "message": f"""
<p>{html_message}
<code>drush</code> returned the following error:</p>
<pre>{html.escape(errors)}</pre>
""",
            "text": f"""
{message}
drush returned the following error:

----- START DRUSH ERROR -----
{errors}
----- END ERROR -----

""",
        }
    ]
