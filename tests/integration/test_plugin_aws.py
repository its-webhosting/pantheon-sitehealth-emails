"""Integration tests for plugin/aws/get_secret.py (test-suite SPEC §7.4).

No live AWS: boto3.session.Session is monkeypatched to return a fake Secrets Manager client.
The module is loaded fresh per test so its module-level cache (`secrets`) starts empty.
"""
import base64
import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


class FakeClient:
    def __init__(self, response, calls):
        self._response = response
        self._calls = calls

    def get_secret_value(self, SecretId):
        self._calls.append(SecretId)
        return self._response


class FakeSession:
    def __init__(self, client):
        self._client = client

    def client(self, service_name, region_name=None):
        return self._client


@pytest.fixture
def load_get_secret(psh, monkeypatch):
    """Load a fresh copy of the module with boto3 stubbed to return `response`."""

    def _load(response):
        calls = []
        path = Path(psh.__file__).parent / "plugin" / "aws" / "get_secret.py"
        loader = SourceFileLoader("aws_get_secret_probe", str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        client = FakeClient(response, calls)
        monkeypatch.setattr(module.boto3.session, "Session", lambda *a, **k: FakeSession(client))
        return module, calls

    return _load


def test_secret_string_json_and_key_lookup(load_get_secret):
    module, calls = load_get_secret({"SecretString": json.dumps({"user": "u", "pass": "p"})})
    assert module.get_secret("app/creds", "user") == "u"
    assert module.get_secret("app/creds", "pass") == "p"


def test_secret_binary_is_base64_decoded(load_get_secret):
    payload = base64.b64encode(json.dumps({"k": "v"}).encode())
    module, _ = load_get_secret({"SecretBinary": payload})
    assert module.get_secret("app/bin", "k") == "v"


def test_whole_secret_returned_when_no_key(load_get_secret):
    module, _ = load_get_secret({"SecretString": json.dumps({"a": 1, "b": 2})})
    assert module.get_secret("app/all") == {"a": 1, "b": 2}


def test_secret_is_cached_after_first_fetch(load_get_secret):
    module, calls = load_get_secret({"SecretString": json.dumps({"x": "y"})})
    module.get_secret("app/cache", "x")
    module.get_secret("app/cache", "x")  # second call must hit the cache, not the API
    assert calls == ["app/cache"]


def test_missing_key_raises_keyerror(load_get_secret):
    module, _ = load_get_secret({"SecretString": json.dumps({"present": 1})})
    with pytest.raises(KeyError):
        module.get_secret("app/creds", "absent")
