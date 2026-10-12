"""Shared fixtures: keep tests from reading or writing the user's real settings/history."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolated_user_state(tmp_path_factory, monkeypatch):
    from PyQt6.QtCore import QSettings

    import any2md.storage.history as history
    import any2md.storage.settings as settings

    state_dir: Path = tmp_path_factory.mktemp("user_state")
    ini = str(state_dir / "settings.ini")

    monkeypatch.setattr(
        settings, "QSettings", lambda *_a, **_k: QSettings(ini, QSettings.Format.IniFormat)
    )

    real_init = history.HistoryStore.__init__

    def init(self, data_dir=None):
        real_init(self, data_dir or state_dir)

    monkeypatch.setattr(history.HistoryStore, "__init__", init)


def test_default_output_is_same_as_source():
    """Fresh settings convert next to the source file, and stale folder values are reset."""
    from any2md.storage.settings import SettingsStore

    store = SettingsStore()
    assert store.load().default_output_dir == ""

    # Simulate a stored folder from before the settings version was introduced
    qs = store._qs
    qs.setValue("default_output_dir", "C:/custom_out")
    qs.remove("settings_version")
    qs.sync()
    assert SettingsStore().load().default_output_dir == ""
