"""The single HTTP seam for the per-site cache checks (SPEC §8.5).

`fetch` and `sleep` are module attributes so tests monkeypatch exactly one place and the
whole check stays offline-testable.  A fresh client per fetch: no cookies are ever sent
(no jar reuse), no environment proxies (trust_env=False), redirects handled manually.

Redirect decision per hop (max MAX_REDIRECTS follows per URL, D5):

    3xx + Location?
      ├─ no Location            → final response (battery flags the 3xx as http-error)
      ├─ classify 'follow'      → re-request (same-FQDN https, or identical-URL upgrade)
      ├─ hops exhausted         → error='too_many_redirects' (result item, D13)
      └─ classify 'cross'       → error='cross_fqdn_redirect' (console note, NO item)

`cf-mitigated: challenge` is checked on EVERY response, including redirect hops,
regardless of status code; it short-circuits everything else.
"""

import dataclasses
import ssl
import time
import urllib.parse

import httpx

from .pages import classify_redirect

MAX_REDIRECTS = 5


@dataclasses.dataclass
class FetchResult:
    url: str                      # originally requested URL
    final_url: str                # after followed redirects
    status_code: int | None       # None on transport failure
    headers: dict                 # lowercased keys; 'set-cookie' -> list[str]
    text: str
    error: str | None             # None | 'timeout' | 'cert' | 'challenge' | 'connection'
                                  #      | 'cross_fqdn_redirect' | 'too_many_redirects'
    redirect_chain: list          # URLs followed (empty when no redirects)
    insecure: bool = False        # True when this result came from a verify=False fetch
    error_detail: str = ""        # short reason text for 'connection' errors


def _headers_dict(response) -> dict:
    """Lowercased header dict; Set-Cookie kept as a list (folding cookies with commas
    would corrupt them), everything else comma-folded like httpx does."""
    headers = {}
    for key in {k.lower() for k in response.headers.keys()}:
        values = response.headers.get_list(key)
        headers[key] = values if key == "set-cookie" else ", ".join(values)
    return headers


def _is_cert_error(exc: Exception) -> bool:
    seen = set()
    cause = exc
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if isinstance(cause, ssl.SSLCertVerificationError):
            return True
        cause = cause.__cause__ or cause.__context__
    return "certificate verify failed" in str(exc).lower()


def _result(url, final_url, error, *, status=None, headers=None, text="", chain=None,
            insecure=False, detail=""):
    return FetchResult(url=url, final_url=final_url, status_code=status,
                       headers=headers or {}, text=text, error=error,
                       redirect_chain=chain or [], insecure=insecure, error_detail=detail)


def _make_client(timeout: float, user_agent: str, verify: bool) -> httpx.Client:
    return httpx.Client(follow_redirects=False, verify=verify, timeout=timeout,
                        headers={"user-agent": user_agent}, trust_env=False)


class ClientPool:
    """Per-FQDN connection reuse: one TCP+TLS handshake per FQDN (per verify mode)
    instead of one per URL.  The PROMPT's actual rule is "do not send any cookies":
    fetch() clears the jar before EVERY request (including redirect hops), so reuse never
    replays a Set-Cookie.  The verify=False client exists only for the invalid-cert
    diagnostic path and is created lazily.  Not itself a seam -- tests monkeypatch
    fetch/sleep, which makes the pool irrelevant to them."""

    def __init__(self, timeout: float, user_agent: str):
        self.timeout = timeout
        self.user_agent = user_agent
        self._clients = {}

    def client(self, verify: bool) -> httpx.Client:
        if verify not in self._clients:
            self._clients[verify] = _make_client(self.timeout, self.user_agent, verify)
        return self._clients[verify]

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _fetch(url: str, *, fqdn: str, timeout: float, user_agent: str,
           verify: bool = True, pool: "ClientPool | None" = None) -> FetchResult:
    chain = []
    current = url
    insecure = not verify
    if pool is not None:
        client = pool.client(verify)
        owns_client = False
    else:
        client = _make_client(timeout, user_agent, verify)
        owns_client = True
    try:
        for _hop in range(MAX_REDIRECTS + 1):
            client.cookies.clear()  # never send cookies -- not across URLs, not across hops
            response = client.get(current)
            headers = _headers_dict(response)
            # Challenge check on EVERY response, any status, including hops:
            if headers.get("cf-mitigated", "").lower() == "challenge":
                return _result(url, current, "challenge", status=response.status_code,
                               headers=headers, chain=chain, insecure=insecure)
            location = headers.get("location")
            if 300 <= response.status_code < 400 and location:
                target = urllib.parse.urljoin(current, location)
                if classify_redirect(current, target, fqdn) == "cross":
                    return _result(url, target, "cross_fqdn_redirect",
                                   status=response.status_code, headers=headers,
                                   chain=chain, insecure=insecure)
                chain.append(target)
                current = target
                continue
            return _result(url, current, None, status=response.status_code,
                           headers=headers, text=response.text, chain=chain,
                           insecure=insecure)
        return _result(url, current, "too_many_redirects", chain=chain,
                       insecure=insecure)
    except httpx.TimeoutException:
        return _result(url, current, "timeout", chain=chain, insecure=insecure)
    except httpx.ConnectError as e:
        if _is_cert_error(e):
            return _result(url, current, "cert", chain=chain, insecure=insecure,
                           detail=str(e))
        return _result(url, current, "connection", chain=chain, insecure=insecure,
                       detail=str(e))
    except httpx.HTTPError as e:  # remaining transport/protocol failures, named httpx base
        return _result(url, current, "connection", chain=chain, insecure=insecure,
                       detail=str(e))
    except httpx.InvalidURL as e:
        # NOT an HTTPError subclass: raised for URLs with non-printable characters or
        # absurd length that survived the pages.py filters (remote page content must
        # never be able to abort the whole run).
        return _result(url, current, "connection", chain=chain, insecure=insecure,
                       detail=f"invalid URL: {e}")
    finally:
        if owns_client:
            client.close()


fetch = _fetch      # THE monkeypatch seam for the per-site cache checks
sleep = time.sleep  # seam for the MISS-retry pauses (tests avoid real 2s waits)
