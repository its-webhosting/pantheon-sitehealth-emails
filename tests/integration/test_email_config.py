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
        self.logged_in_password = None

    def login(self, user, password):
        self.logged_in_as = user
        self.logged_in_password = password


def test_smtp_login_uses_config(psh, reset_sc, monkeypatch):
    """Host/port and BOTH credentials come from the [SMTP] config section, not the environment."""
    captured = {}
    monkeypatch.setattr(psh, "SMTP_SSL", lambda host, port: captured.setdefault("c", _FakeSMTP(host, port)))
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)  # must NOT be read from the environment
    reset_sc.options.smtp_username = None
    reset_sc.config = {"SMTP": {"host": "smtp.example.org", "port": 587,
                                "username": "config_user", "password": "config_pw"}}

    psh.smtp_login()
    assert captured["c"].host == "smtp.example.org"
    assert captured["c"].port == 587
    assert captured["c"].logged_in_as == "config_user"
    assert captured["c"].logged_in_password == "config_pw"


def test_smtp_login_cli_username_overrides_config(psh, reset_sc, monkeypatch):
    captured = {}
    monkeypatch.setattr(psh, "SMTP_SSL", lambda host, port: captured.setdefault("c", _FakeSMTP(host, port)))
    reset_sc.options.smtp_username = "cli_user"
    reset_sc.config = {"SMTP": {"username": "config_user", "password": "config_pw"}}

    psh.smtp_login()
    assert captured["c"].logged_in_as == "cli_user"


def test_smtp_login_defaults_to_umich_host(psh, reset_sc, monkeypatch):
    captured = {}
    monkeypatch.setattr(psh, "SMTP_SSL", lambda host, port: captured.setdefault("c", _FakeSMTP(host, port)))
    reset_sc.options.smtp_username = "someone"
    reset_sc.config = {"SMTP": {"password": "pw"}}  # host/port omitted -> U-M defaults

    psh.smtp_login()
    assert captured["c"].host == "smtp.mail.umich.edu"
    assert captured["c"].port == 465


def test_smtp_login_missing_password_exits(psh, reset_sc, monkeypatch):
    """No password configured -> a clear exit, never a silent send with empty credentials."""
    monkeypatch.setattr(psh, "SMTP_SSL", lambda host, port: pytest.fail("must not connect"))
    reset_sc.options.smtp_username = "someone"
    reset_sc.config = {"SMTP": {}}  # no password
    with pytest.raises(SystemExit):
        psh.smtp_login()


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
