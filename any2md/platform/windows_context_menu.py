"""Windows Explorer cascading context menu integration via HKCU registry.

Adds a "Convert with Any2MD" cascading right-click menu tailored to each document format:
- Right-clicking a PDF offers: Markdown (.md), Word Document (.docx), HTML (.html), Open in Any2MD
- Right-clicking DOCX offers: Markdown (.md), PDF (.pdf), HTML (.html), Open in Any2MD
- Right-clicking Markdown offers: PDF (.pdf), Word Document (.docx), HTML (.html), Open in Any2MD
- etc.

Stored under HKEY_CURRENT_USER\\Software\\Classes\\SystemFileAssociations\\<ext>\\shell\\Any2MD.
Requires zero administrator privileges.
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from any2md.ui.icons import get_app_logo_path

# Target conversion options per extension: (format_code, display_label)
EXTENSION_TARGETS: Dict[str, List[Tuple[str, str]]] = {
    ".pdf": [
        ("md", "Markdown (.md)"),
        ("docx", "Word Document (.docx)"),
        ("html", "HTML (.html)"),
    ],
    ".docx": [
        ("md", "Markdown (.md)"),
        ("pdf", "PDF (.pdf)"),
        ("html", "HTML (.html)"),
    ],
    ".xlsx": [
        ("md", "Markdown (.md)"),
    ],
    ".xls": [
        ("md", "Markdown (.md)"),
    ],
    ".pptx": [
        ("md", "Markdown (.md)"),
    ],
    ".ppt": [
        ("md", "Markdown (.md)"),
    ],
    ".txt": [
        ("md", "Markdown (.md)"),
        ("docx", "Word Document (.docx)"),
        ("pdf", "PDF (.pdf)"),
        ("html", "HTML (.html)"),
    ],
    ".csv": [
        ("md", "Markdown (.md)"),
    ],
    ".html": [
        ("md", "Markdown (.md)"),
        ("docx", "Word Document (.docx)"),
        ("pdf", "PDF (.pdf)"),
    ],
    ".htm": [
        ("md", "Markdown (.md)"),
        ("docx", "Word Document (.docx)"),
        ("pdf", "PDF (.pdf)"),
    ],
    ".md": [
        ("pdf", "PDF (.pdf)"),
        ("docx", "Word Document (.docx)"),
        ("html", "HTML (.html)"),
    ],
}


def _get_executable_and_icon() -> Tuple[str, str]:
    """Return the executable invocation prefix and icon path."""
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        exe_path = sys.executable
        icon_path = sys.executable
    else:
        # Use pythonw if available to avoid console flash
        py_exe = Path(sys.executable)
        pyw_exe = py_exe.with_name("pythonw.exe")
        exe_to_use = str(pyw_exe) if pyw_exe.exists() else sys.executable
        exe_path = f'"{exe_to_use}" -m any2md.main'
        icon_path = str(get_app_logo_path())

    return exe_path, icon_path


def _build_command_str(exe_prefix: str, format_code: Optional[str] = None) -> str:
    """Build the command string executed by Windows Explorer."""
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        if format_code:
            return f'"{exe_prefix}" --convert-to {format_code} "%1"'
        return f'"{exe_prefix}" "%1"'
    else:
        if format_code:
            return f'{exe_prefix} --convert-to {format_code} "%1"'
        return f'{exe_prefix} "%1"'


def _delete_key_recursive(hkey: int, subkey: str) -> None:
    """Recursively delete a Windows Registry key and all its subkeys."""
    try:
        with winreg.OpenKey(hkey, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                    _delete_key_recursive(hkey, f"{subkey}\\{child}")
                except OSError:
                    break
        winreg.DeleteKey(hkey, subkey)
    except FileNotFoundError:
        pass


def is_context_menu_registered() -> bool:
    """Check if Any2MD context menu is currently registered in HKCU."""
    try:
        test_key = r"Software\Classes\SystemFileAssociations\.pdf\shell\Any2MD"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, test_key, 0, winreg.KEY_READ):
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def register_context_menu(
    custom_exe_path: Optional[str] = None,
    custom_icon_path: Optional[str] = None,
) -> bool:
    """Register cascading 'Convert with Any2MD' context menu for all supported extensions."""
    exe_prefix, icon_path = _get_executable_and_icon()
    if custom_exe_path:
        exe_prefix = custom_exe_path
    if custom_icon_path:
        icon_path = custom_icon_path

    try:
        for ext, targets in EXTENSION_TARGETS.items():
            base_key_path = f"Software\\Classes\\SystemFileAssociations\\{ext}\\shell\\Any2MD"

            # Create base parent verb
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base_key_path) as base_key:
                winreg.SetValueEx(base_key, "MUIVerb", 0, winreg.REG_SZ, "Convert with Any2MD")
                winreg.SetValueEx(base_key, "SubCommands", 0, winreg.REG_SZ, "")
                if icon_path:
                    winreg.SetValueEx(base_key, "Icon", 0, winreg.REG_SZ, icon_path)

            shell_sub_path = f"{base_key_path}\\shell"

            # Sub-item: Each target format
            for fmt_code, fmt_label in targets:
                sub_item_path = f"{shell_sub_path}\\to_{fmt_code}"
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, sub_item_path) as sub_key:
                    winreg.SetValueEx(sub_key, "MUIVerb", 0, winreg.REG_SZ, fmt_label)

                cmd_path = f"{sub_item_path}\\command"
                cmd_str = _build_command_str(exe_prefix, fmt_code)
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, cmd_path) as cmd_key:
                    winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_str)

            # Sub-item: Open in Any2MD
            open_item_path = f"{shell_sub_path}\\open_gui"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, open_item_path) as open_key:
                winreg.SetValueEx(open_key, "MUIVerb", 0, winreg.REG_SZ, "Open in Any2MD...")

            open_cmd_path = f"{open_item_path}\\command"
            open_cmd_str = _build_command_str(exe_prefix, None)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, open_cmd_path) as open_cmd_key:
                winreg.SetValueEx(open_cmd_key, "", 0, winreg.REG_SZ, open_cmd_str)

        return True
    except Exception as exc:
        print(f"Failed to register context menu: {exc}", file=sys.stderr)
        return False


def unregister_context_menu() -> bool:
    """Remove Any2MD context menu from all supported extensions."""
    try:
        for ext in EXTENSION_TARGETS.keys():
            base_key_path = f"Software\\Classes\\SystemFileAssociations\\{ext}\\shell\\Any2MD"
            _delete_key_recursive(winreg.HKEY_CURRENT_USER, base_key_path)
        return True
    except Exception as exc:
        print(f"Failed to unregister context menu: {exc}", file=sys.stderr)
        return False
