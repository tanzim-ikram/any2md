"""Unit tests for Windows Explorer Context Menu integration."""

import winreg
from pathlib import Path
from any2md.platform.windows_context_menu import (
    EXTENSION_TARGETS,
    is_context_menu_registered,
    register_context_menu,
    unregister_context_menu,
)


class TestContextMenuRegistry:
    def teardown_method(self) -> None:
        unregister_context_menu()

    def test_extension_targets_coverage(self) -> None:
        assert ".pdf" in EXTENSION_TARGETS
        assert ".docx" in EXTENSION_TARGETS
        assert ".md" in EXTENSION_TARGETS
        assert ".txt" in EXTENSION_TARGETS

        # Ensure same format is not offered
        pdf_targets = [t[0] for t in EXTENSION_TARGETS[".pdf"]]
        assert "pdf" not in pdf_targets
        assert "md" in pdf_targets
        assert "docx" in pdf_targets
        assert "html" in pdf_targets

        md_targets = [t[0] for t in EXTENSION_TARGETS[".md"]]
        assert "md" not in md_targets
        assert "pdf" in md_targets
        assert "docx" in md_targets

    def test_register_and_unregister_lifecycle(self) -> None:
        # Initially ensure unregistered
        unregister_context_menu()
        assert not is_context_menu_registered()

        # Register
        success = register_context_menu()
        assert success is True
        assert is_context_menu_registered() is True

        # Verify registry keys exist for .pdf
        pdf_key_path = r"Software\Classes\SystemFileAssociations\.pdf\shell\Any2MD"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, pdf_key_path) as k:
            verb, _ = winreg.QueryValueEx(k, "MUIVerb")
            assert verb == "Convert with Any2MD"

        # Verify sub-items exist
        to_md_path = pdf_key_path + r"\shell\to_md\command"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, to_md_path) as k:
            cmd = winreg.QueryValue(k, "")
            assert "--convert-to md" in cmd

        to_docx_path = pdf_key_path + r"\shell\to_docx\command"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, to_docx_path) as k:
            cmd = winreg.QueryValue(k, "")
            assert "--convert-to docx" in cmd

        open_gui_path = pdf_key_path + r"\shell\open_gui\command"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, open_gui_path) as k:
            cmd = winreg.QueryValue(k, "")
            assert "%1" in cmd

        # Unregister
        unreg_success = unregister_context_menu()
        assert unreg_success is True
        assert is_context_menu_registered() is False
