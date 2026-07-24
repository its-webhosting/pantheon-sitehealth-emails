"""The Notice type and its code registry (CAMPAIGN.md §6).

A typed, frozen replacement for the ad-hoc notice dicts.  Pure: imports nothing from script_context,
so the sc facade and every psh/ module can import it without a cycle; checks/plugins reach
Notice/Severity via sc -- with one sanctioned exception, check/pantheon_cdn_change/notices.py,
whose purity test pins its imported-module set (CAMPAIGN.md §3.5 as amended at I14c).  Adoption was per-increment (CAMPAIGN.md §6) and completed at I14c: every
producer in psh/, check/ and plugin/ builds a Notice, SiteContext.add_notice accepts nothing else,
and this module's `csv_extra` field is that increment's CAMPAIGN.md §6 amendment.  The roster of
codes registered below is pinned by tests/integration/test_notice_roster.py.
"""
import dataclasses
from enum import StrEnum


class Severity(StrEnum):
    ALERT = "alert"
    WARNING = "warning"
    INFO = "info"


@dataclasses.dataclass(frozen=True)
class Notice:
    """One report notice.  `code` is the stable unique slug (registry-enforced) that maps to the
    notices-CSV code field; `html` is the report-body HTML, `text` its plaintext (empty -> derived by
    SiteContext.notice_to_dict via html2text); `short` is the one-line summary; `icon` empty ->
    filled from `severity` by that same projection; `order` places the notice ('prepend'/'first' ->
    front).  `csv_extra` holds the notices-CSV fields that follow `site,code` (CAMPAIGN.md §6 as
    amended at I14c); elements MUST already be strings -- the projection does not coerce, so a
    format spec like f"{savings:.2f}" stays visible at the producer."""

    severity: Severity
    code: str
    html: str
    short: str = ""
    text: str = ""
    icon: str = ""
    order: str = "append"
    csv_extra: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject a non-str csv_extra element AT THE PRODUCER, by name.

        VALIDATION, not coercion (SPEC I14c D-i14c-1 keeps the format spec at the producer).  Most
        producers live in check/, which pyright does not gate (pyproject [tool.pyright] includes
        only psh/), so a forgotten str() around an int csv field would otherwise surface much later
        as an anonymous `TypeError: sequence item 2: expected str instance, int found` from
        script_context's ",".join -- naming neither the notice nor the module (PD#2)."""
        bad = [x for x in self.csv_extra if not isinstance(x, str)]
        if bad:
            raise TypeError(
                f"Notice({self.code!r}).csv_extra elements must be str; got {bad!r}"
            )


class DuplicateNoticeCodeError(RuntimeError):
    """Raised when a notice code is registered twice.  A shared code across two notice types is the
    exact class of bug I1 fixed by hand (BLOCKMAP §Bugs 2/5); the registry makes it a loud
    import-time failure instead of a silent CSV collision."""


class NoticeRegistry:
    """Declare-once registry of notice codes.  Each notice type registers its code once at import; a
    re-used code raises DuplicateNoticeCodeError.  Registration is import-time metadata (like
    sc.substitutions/sc.hooks), not per-run/per-site state (CAMPAIGN.md §3.4)."""

    def __init__(self) -> None:
        self._codes: dict[str, str] = {}

    def register(self, code: str, *, description: str = "") -> str:
        if code in self._codes:
            raise DuplicateNoticeCodeError(
                f"notice code {code!r} is already registered "
                f"(existing: {self._codes[code]!r}); codes must be unique."
            )
        self._codes[code] = description
        return code

    def codes(self) -> frozenset[str]:
        return frozenset(self._codes)

    def snapshot(self) -> dict[str, str]:
        """Copy the registered codes.  TEST SEAM: tests/conftest.py's autouse reset_sc fixture
        snapshots before each test and restores after, because the suite loads check/ modules
        standalone once per test and a module body re-executing would otherwise re-register its
        codes and raise DuplicateNoticeCodeError.  Production imports each module once."""
        return dict(self._codes)

    def restore(self, snapshot: dict[str, str]) -> None:
        """Restore a snapshot() result.  See snapshot() for why this exists."""
        self._codes = dict(snapshot)


registry = NoticeRegistry()
