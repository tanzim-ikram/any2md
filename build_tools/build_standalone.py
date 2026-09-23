"""Automated build script for standalone Windows distribution of Any2MD."""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def build() -> None:
    print("=" * 60)
    print("Any2MD — Building Standalone Windows Application")
    print("=" * 60)

    # 1. Generate ICO if needed
    ico_path = ROOT_DIR / "Any2MD Logo.ico"
    if not ico_path.exists():
        print("[1/3] Generating multi-resolution Windows ICO...")
        from make_ico import generate_ico
        generate_ico()
    else:
        print("[1/3] Windows ICO ready.")

    # 2. Run PyInstaller
    print("[2/3] Compiling standalone package with PyInstaller...")
    spec_path = ROOT_DIR / "any2md.spec"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec_path)]
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))

    if result.returncode != 0:
        print("\nERROR: PyInstaller build failed!")
        sys.exit(result.returncode)

    # 3. Verify output
    dist_exe = ROOT_DIR / "dist" / "Any2MD" / "Any2MD.exe"
    if not dist_exe.exists():
        print(f"\nERROR: Expected output not found at {dist_exe}")
        sys.exit(1)

    size_mb = dist_exe.stat().st_size / (1024 * 1024)
    print(f"\n[3/3] Build succeeded!")
    print(f"Output executable: {dist_exe} ({size_mb:.2f} MB)")
    print(f"Standalone folder: {dist_exe.parent}")
    print("\nYou can distribute the entire 'dist/Any2MD' directory or package it with Inno Setup.")


if __name__ == "__main__":
    build()
