"""
Script to compile .po files to .mo files for gettext.

Compiles all translation files in locales directory.

Run from apps/api directory:
    python scripts/compile_translations.py
"""

import subprocess
from pathlib import Path


def compile_po_file(po_file: Path) -> bool:
    """Compile a .po file to .mo using msgfmt (or Python fallback)."""
    mo_file = po_file.with_suffix(".mo")

    try:
        # Try using msgfmt command (faster, standard tool)
        subprocess.run(
            ["msgfmt", str(po_file), "-o", str(mo_file)],
            check=True,
            capture_output=True,
        )
        print(f"  Compiled: {po_file.parent.parent.name}/{po_file.stem}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to Python polib library
        try:
            import polib

            po = polib.pofile(str(po_file))
            po.save_as_mofile(str(mo_file))
            print(f"  Compiled (polib): {po_file.parent.parent.name}/{po_file.stem}")
            return True
        except ImportError:
            print(
                f"  ERROR: Cannot compile {po_file}. " "Install msgfmt or polib: pip install polib"
            )
            return False
        except Exception as e:
            print(f"  ERROR compiling {po_file}: {e}")
            return False


def main():
    """Compile all .po files in locales directory."""
    # Get locales directory
    locales_dir = Path(__file__).parent.parent / "locales"

    if not locales_dir.exists():
        print(f"ERROR: Locales directory not found: {locales_dir}")
        return

    # Find all .po files
    po_files = list(locales_dir.glob("*/LC_MESSAGES/messages.po"))

    if not po_files:
        print("No .po files found in locales directory")
        return

    print(f"Found {len(po_files)} .po files to compile\n")

    success_count = 0
    for po_file in po_files:
        if compile_po_file(po_file):
            success_count += 1

    print(f"\nCompiled {success_count}/{len(po_files)} translation files successfully!")

    if success_count < len(po_files):
        print("\nTo install compilation tools:")
        print("  - Windows: pip install polib")
        print("  - Linux/Mac: sudo apt-get install gettext (or brew install gettext)")


if __name__ == "__main__":
    main()
