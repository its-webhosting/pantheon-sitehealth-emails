"""import_packages seam (campaign I13, SPEC 2.5 -- the I4 deviation-6 discharge)."""
import pytest

import script_context as sc
from psh.modules import find_modules, import_packages
from tests.helpers.dnsfake import recording_console  # existing helper, width-defaulted


@pytest.mark.integration
def test_import_packages_returns_discovery_ordered_modules(psh, monkeypatch, reset_sc):
    console = recording_console(monkeypatch, reset_sc)
    loaded = import_packages("plugin")
    assert list(loaded) == find_modules("plugin")          # discovery order preserved
    assert all(m.__name__ == name for name, m in loaded.items())
    # The banner + per-module lines moved inside (byte-identical text, SPEC 2.5) --
    # visible only at -v; reset_sc's default namespace has verbose=0, so force it:
    sc.options.verbose = 1
    console2 = recording_console(monkeypatch, reset_sc)
    import_packages("plugin")
    out = console2.export_text()
    assert "=== Loading plugins:" in out and "Loading plugin: plugin.env" in out
