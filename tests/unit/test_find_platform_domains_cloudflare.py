"""Offline tests for the find-platform-domains-cloudflare utility (SPEC section 7).

The script has no .py extension, so it is loaded with the SourceFileLoader idiom the suite
already uses for standalone scripts and check/plugin modules (see
tests/unit/test_find_platform_domains_dns.py).  It is loaded FRESH PER TEST so no module-level
state leaks between tests -- which is also what makes monkeypatching module attributes safe in
the main() tests at the bottom (SPEC section 4, seams).

Imports: each task ADDS to the block below, in the task that first needs the name.  Editing the
top block is fine; adding an import further down the file is what ruff's E402 forbids, and E402
is not in the tests/** ignore list.

TEMPORARY, deleted with the script after the Pantheon CDN migration -- see
development/2026-07-30-platform-domain-util2/SPEC.md section 11.
"""
import importlib.util
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parent.parent.parent / "find-platform-domains-cloudflare"


@pytest.fixture
def fpc():
    """The utility, loaded fresh.  Its entry point is __main__-guarded, so import runs nothing."""
    loader = SourceFileLoader("find_platform_domains_cloudflare_probe", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def record(**overrides):
    """A stand-in for a cloudflare RecordResponse; the code under test only reads attributes."""
    fields = {"type": "CNAME", "name": "www.example.edu", "id": "rec-1",
              "content": "live-umich-example1.pantheonsite.io", "proxied": True,
              "ttl": 1, "comment": None, "tags": [], "settings": None}
    fields.update(overrides)
    return types.SimpleNamespace(**fields)


# --- Task 1: the match rule ------------------------------------------------------------------

def test_normalize_strips_case_whitespace_and_the_root_dot(fpc):
    assert fpc.normalize("  LIVE-Umich-X.PantheonSite.IO.  ") == "live-umich-x.pantheonsite.io"


@pytest.mark.parametrize("name", [
    "live-umich-example1.pantheonsite.io",
    "LIVE-UMICH-EXAMPLE1.PANTHEONSITE.IO",
    "live-umich-example1.pantheonsite.io.",
])
def test_is_platform_domain_accepts_platform_hostnames(fpc, name):
    assert fpc.is_platform_domain(name) is True


@pytest.mark.parametrize("name", [
    "notpantheonsite.io",          # the leading dot in PLATFORM_SUFFIX is what rejects this
    "pantheonsite.io",             # the bare apex is not a site's platform domain
    "www.example.edu",
    "live-umich-example1.pantheonsite.io.evil.example",
])
def test_is_platform_domain_rejects_everything_else(fpc, name):
    assert fpc.is_platform_domain(name) is False


# --- Task 2: credentials ---------------------------------------------------------------------

AMBIENT_CLOUDFLARE_VARS = {
    "CLOUDFLARE_API_TOKEN": "ambient-token",
    "CLOUDFLARE_API_KEY": "ambient-key",
    "CLOUDFLARE_EMAIL": "ambient@example.edu",
    "CLOUDFLARE_API_USER_SERVICE_KEY": "ambient-usk",
    "CLOUDFLARE_BASE_URL": "https://evil.example/v4",
    "CLOUDFLARE_CUSTOM_HEADERS": "X-Auth-Email: attacker@evil.example\nX-Auth-Key: evil-key",
}


def write_config(tmp_path, body):
    """A config file containing just a [Cloudflare] table."""
    path = tmp_path / "config.toml"
    path.write_text(f"[Cloudflare]\n{body}\n")
    return str(path)


def sent_request(client):
    """The request the SDK would actually send.  Offline: _build_request performs no I/O."""
    from cloudflare._models import FinalRequestOptions
    return client._build_request(FinalRequestOptions(method="get", url="/zones"))


def test_resolve_config_value_passes_literals_and_non_strings_through(fpc):
    assert fpc.resolve_config_value("plain-literal", "where") == "plain-literal"
    assert fpc.resolve_config_value(True, "where") is True
    assert fpc.resolve_config_value(None, "where") is None


@pytest.mark.parametrize("marker", ["<{env CF_TEST_VAR}", "<{secret env CF_TEST_VAR}"])
def test_resolve_config_value_reads_the_environment(fpc, monkeypatch, marker):
    monkeypatch.setenv("CF_TEST_VAR", "from-the-environment")
    assert fpc.resolve_config_value(marker, "where") == "from-the-environment"


def test_resolve_config_value_substitutes_inside_a_larger_string(fpc, monkeypatch):
    monkeypatch.setenv("CF_TEST_VAR", "middle")
    assert fpc.resolve_config_value("a<{env CF_TEST_VAR}z", "where") == "amiddlez"


def test_resolve_config_value_uses_the_default_when_the_variable_is_unset(fpc, monkeypatch):
    monkeypatch.delenv("CF_TEST_VAR", raising=False)
    assert fpc.resolve_config_value("<{secret env CF_TEST_VAR fallback}", "where") == "fallback"


def test_resolve_config_value_reports_an_unset_variable_with_no_default(fpc, monkeypatch):
    monkeypatch.delenv("CF_TEST_VAR", raising=False)
    with pytest.raises(fpc.StartupError) as caught:
        fpc.resolve_config_value("<{env CF_TEST_VAR}", "config.toml [Cloudflare].api_key")
    assert "CF_TEST_VAR" in str(caught.value)
    assert "config.toml [Cloudflare].api_key" in str(caught.value)


def test_resolve_config_value_rejects_a_substitution_it_cannot_resolve(fpc):
    with pytest.raises(fpc.StartupError) as caught:
        fpc.resolve_config_value("<{secret aws cloudflare/token}", "where")
    assert "secret aws" in str(caught.value)
    # The rest of the body is withheld on purpose: an <{env NAME DEFAULT} default can be a
    # literal credential, and this message reaches stderr and any operator log.
    assert "cloudflare/token" not in str(caught.value)


def test_resolve_config_value_names_a_malformed_substitution(fpc):
    """An unbalanced quote makes shlex raise ValueError, which escaped as a raw traceback at
    exit 1 -- a code SPEC section R6 does not use (adversarial review round 1, finding 3)."""
    with pytest.raises(fpc.StartupError) as caught:
        fpc.resolve_config_value("<{env FOO don't}", "config.toml [Cloudflare].api_key")
    assert "config.toml [Cloudflare].api_key" in str(caught.value)


def test_cloudflare_client_prefers_the_api_token(fpc, tmp_path, monkeypatch):
    monkeypatch.setenv("CF_TEST_TOKEN", "tok-123")
    path = write_config(tmp_path, 'api_token = "<{secret env CF_TEST_TOKEN}"\n'
                                  'email = "someone@example.edu"\napi_key = "k-456"')
    client = fpc.cloudflare_client(path)
    assert client.api_token == "tok-123"


def test_cloudflare_client_sends_only_the_configured_credential(fpc, tmp_path, monkeypatch):
    """SPEC R2a, asserted as the security property rather than the attribute state implementing it.

    The SDK reads six ambient variables; ALL of them are exported here, so a regression that
    dropped any one field from the pin goes red.  Measured against cloudflare 5.4.0; an SDK that
    captured credentials at construction, or added a fifth route, would make this go red -- which
    is the point, since pyproject declares the dependency unpinned.
    """
    for name, value in AMBIENT_CLOUDFLARE_VARS.items():
        monkeypatch.setenv(name, value)
    path = write_config(tmp_path, 'api_token = "tok-123"')
    client = fpc.cloudflare_client(path)

    assert client.auth_headers == {"Authorization": "Bearer tok-123"}
    request = sent_request(client)
    assert str(request.url).startswith("https://api.cloudflare.com/client/v4/")
    leaked = set(request.headers.values()) & set(AMBIENT_CLOUDFLARE_VARS.values())
    assert leaked == set(), f"ambient credentials reached the wire: {leaked}"


def test_cloudflare_client_ignores_an_ambient_base_url(fpc, tmp_path, monkeypatch):
    """$CLOUDFLARE_BASE_URL would otherwise send the configured token to an arbitrary host --
    strictly worse than the defect the credential pin was written for (round 2, finding 3)."""
    monkeypatch.setenv("CLOUDFLARE_BASE_URL", "https://evil.example/v4")
    path = write_config(tmp_path, 'api_token = "tok-123"')
    request = sent_request(fpc.cloudflare_client(path))
    assert "evil.example" not in str(request.url)


def test_cloudflare_client_falls_back_to_email_and_key(fpc, tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "ambient-token")
    path = write_config(tmp_path, 'email = "someone@example.edu"\napi_key = "k-456"')
    client = fpc.cloudflare_client(path)
    assert client.api_email == "someone@example.edu"
    assert client.api_key == "k-456"
    assert client.api_token is None
    assert "ambient-token" not in set(sent_request(client).headers.values())


def test_cloudflare_client_requires_both_email_and_key(fpc, tmp_path):
    path = write_config(tmp_path, 'email = "someone@example.edu"')
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(path)
    assert "api_token" in str(caught.value)


def test_cloudflare_client_rejects_a_non_string_credential(fpc, tmp_path):
    """TOML is typed: `api_token = true` would otherwise reach the SDK and be stringified into
    `Authorization: Bearer True` -- the confusing 401 the marker rules exist to prevent."""
    path = write_config(tmp_path, "api_token = true")
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(path)
    assert "api_token" in str(caught.value)
    assert "bool" in str(caught.value)


def test_cloudflare_client_without_a_cloudflare_section_is_a_startup_error(fpc, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[Pantheon]\norg_id = "abc"\n')
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(str(path))
    assert "[Cloudflare]" in str(caught.value)


def test_cloudflare_client_with_a_missing_file_is_a_startup_error(fpc, tmp_path):
    with pytest.raises(fpc.StartupError):
        fpc.cloudflare_client(str(tmp_path / "nope.toml"))


def test_cloudflare_client_with_a_non_utf8_file_is_a_startup_error(fpc, tmp_path):
    """tomllib.load decodes the bytes itself, so a non-UTF-8 config raises UnicodeDecodeError --
    NOT a TOMLDecodeError.  It escaped as a raw traceback at exit 1 until the guard was widened
    to ValueError, which is the common base of both (round 3, finding 1)."""
    path = tmp_path / "config.toml"
    path.write_bytes(b'[Cloudflare]\napi_token = "caf\xe9"\n')
    with pytest.raises(fpc.StartupError) as caught:
        fpc.cloudflare_client(str(path))
    assert "not valid TOML" in str(caught.value)
