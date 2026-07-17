"""The Notice type and its code registry (CAMPAIGN.md §6).

A typed, frozen replacement for the ad-hoc notice dicts.  Pure: imports nothing from script_context,
so the sc facade and every psh/ module can import it without a cycle; checks/plugins reach
Notice/Severity via sc.  Adoption is per-increment (CAMPAIGN.md §6); the dict form is retired in I14.
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
    SiteContext.add_notice via html2text, as the dict form does); `short` is the one-line summary;
    `icon` empty -> filled from `severity`; `order` places the notice ('prepend'/'first' -> front)."""

    severity: Severity
    code: str
    html: str
    short: str = ""
    text: str = ""
    icon: str = ""
    order: str = "append"


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


registry = NoticeRegistry()
