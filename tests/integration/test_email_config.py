"""Integration tier: [Email]/[SMTP] config + the [UMich].enabled gate (P8a/P8b).

P8a moves sender identity / SMTP host to config with byte-identical U-M defaults; P8b gates the
fqdns-gated Cloudflare/doc-URL checks on umich_enabled().  The rendered-output side (headers +
msgid come from config, U-M doc URLs absent for a non-U-M run) is proven by the non-U-M golden
in tests/e2e/test_golden_nonumich.py; here we cover the seams directly.
"""
import pytest

pytestmark = pytest.mark.integration


class _FakeSMTP:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.logged_in_as = None

    def login(self, user, password):
        self.logged_in_as = user


def test_smtp_login_uses_config(psh, reset_sc, monkeypatch):
    captured = {}
    monkeypatch.setattr(psh, "SMTP_SSL", lambda host, port: captured.setdefault("c", _FakeSMTP(host, port)))
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    reset_sc.options.smtp_username = "someone"
    reset_sc.config = {"SMTP": {"host": "smtp.example.org", "port": 587}}

    psh.smtp_login()
    assert captured["c"].host == "smtp.example.org"
    assert captured["c"].port == 587


def test_smtp_login_defaults_to_umich(psh, reset_sc, monkeypatch):
    captured = {}
    monkeypatch.setattr(psh, "SMTP_SSL", lambda host, port: captured.setdefault("c", _FakeSMTP(host, port)))
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    reset_sc.options.smtp_username = "someone"
    reset_sc.config = {}  # no [SMTP] section

    psh.smtp_login()
    assert captured["c"].host == "smtp.mail.umich.edu"
    assert captured["c"].port == 465


@pytest.mark.parametrize(
    "config,expected",
    [
        ({}, False),
        ({"UMich": {}}, False),
        ({"UMich": {"enabled": False}}, False),
        ({"UMich": {"enabled": True}}, True),
    ],
)
def test_umich_enabled_gate(psh, reset_sc, config, expected):
    reset_sc.config = config
    assert psh.umich_enabled() is expected
