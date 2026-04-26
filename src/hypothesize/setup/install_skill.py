"""Install the bundled Claude Code skill into the user's skill directory.

The canonical SKILL.md ships inside the wheel under
``hypothesize/skill/SKILL.md`` and is located via
:mod:`importlib.resources`. We deliberately do not use ``__file__``
arithmetic — that breaks when the package is installed from a wheel
(``importlib.resources`` works in both layouts).
"""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

SKILL_FILENAME = "SKILL.md"


def bundled_skill_path() -> Path:
    """Return a filesystem path to the bundled SKILL.md.

    Works in both editable installs (where the file lives in ``src/``)
    and wheel installs (where ``importlib.resources`` exposes it via the
    package data tree).
    """
    resource = resources.files("hypothesize.skill").joinpath(SKILL_FILENAME)
    # ``files()`` returns a Traversable; ``as_file`` would give a context
    # manager but we only need a stable Path because the file ships
    # uncompressed in the wheel. Falling back to str()/Path conversion
    # here works for the standard Hatch wheel layout.
    return Path(str(resource))


def is_installed(target_dir: Path) -> bool:
    """Return True iff ``target_dir/SKILL.md`` exists."""
    return (target_dir / SKILL_FILENAME).exists()


def install_skill(target_dir: Path) -> None:
    """Copy the bundled SKILL.md to ``target_dir/SKILL.md``.

    Creates ``target_dir`` (and parents) if missing. Overwrites any
    existing SKILL.md — the wizard collects the user's reinstall intent
    before calling this. Raises ``OSError`` (typically
    ``PermissionError``) on filesystem failures so the wizard can show
    a clear error.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    source = bundled_skill_path()
    destination = target_dir / SKILL_FILENAME
    shutil.copyfile(source, destination)
