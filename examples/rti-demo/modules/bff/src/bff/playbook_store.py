# SPDX-FileCopyrightText: 2025 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Copyright 2025 Netbeheer Nederland
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Where the BFF keeps demo playbooks: built-in ones shipped with the repo
(examples/rti-demo/playbooks, read-only) and ones saved from the HMI
(recordings and uploads, on the config volume). A playbook's name is its file
name without the extension; a built-in name can't be saved over."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from bff.playbook import PlaybookError, dump_playbook, load_playbook, validate_playbook

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
# "run" would clash with /api/playbooks/run.
RESERVED = {"run"}
SUFFIXES = (".yaml", ".yml", ".json")


class PlaybookNameError(ValueError):
    """A name that can't be a playbook's (paths, odd characters, reserved)."""


class BuiltinPlaybookError(Exception):
    """A change to a built-in playbook."""


def check_name(name: str) -> str:
    if not NAME_RE.fullmatch(name or "") or name in RESERVED:
        raise PlaybookNameError(
            f"invalid playbook name {name!r} - use letters, digits, '_', '.' and '-' (at most 64), not 'run'"
        )
    return name


class PlaybookStore:
    def __init__(self, builtin_dir: str | Path, saved_dir: str | Path):
        self.builtin_dir = Path(builtin_dir)
        self.saved_dir = Path(saved_dir)

    @staticmethod
    def _files(
        directory: Path, suffixes: tuple[str, ...] = SUFFIXES
    ) -> dict[str, Path]:
        if not directory.is_dir():
            return {}
        found: dict[str, Path] = {}
        for path in sorted(directory.iterdir()):
            if (
                path.is_file()
                and path.suffix.lower() in suffixes
                and NAME_RE.fullmatch(path.stem)
                and path.stem not in RESERVED
            ):
                found.setdefault(path.stem, path)
        return found

    def _path(self, name: str) -> tuple[Path, bool]:
        check_name(name)
        builtin = self._files(self.builtin_dir)
        if name in builtin:
            return builtin[name], True
        saved = self.saved_dir / f"{name}.yaml"
        if saved.is_file():
            return saved, False
        raise KeyError(name)

    def list(self) -> list[dict[str, Any]]:
        builtin = self._files(self.builtin_dir)
        saved = {
            n: p
            for n, p in self._files(self.saved_dir, (".yaml",)).items()
            if n not in builtin
        }
        entries = []
        for is_builtin, files in ((True, builtin), (False, saved)):
            for name, path in files.items():
                entry: dict[str, Any] = {"name": name, "builtin": is_builtin}
                try:
                    playbook = load_playbook(path)
                    entry.update(
                        title=str(playbook.get("name") or name),
                        steps=len(playbook["steps"]),
                    )
                except (PlaybookError, OSError, ValueError) as exc:
                    entry.update(title=name, error=str(exc))
                entries.append(entry)
        return entries

    def get(self, name: str) -> tuple[dict[str, Any], bool]:
        path, builtin = self._path(name)
        return load_playbook(path), builtin

    def file(self, name: str) -> tuple[str, str]:
        path, _ = self._path(name)
        return path.read_text(encoding="utf-8"), path.name

    def save(self, name: str, playbook: dict[str, Any]) -> None:
        check_name(name)
        if name in self._files(self.builtin_dir):
            raise BuiltinPlaybookError(
                f"{name!r} is a built-in playbook - save under another name"
            )
        validate_playbook(playbook)
        self.saved_dir.mkdir(parents=True, exist_ok=True)
        # Temp file + rename in the same dir, as connections.json is saved.
        fd, tmp = tempfile.mkstemp(
            dir=self.saved_dir, prefix=f".{name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(dump_playbook(playbook))
            os.replace(tmp, self.saved_dir / f"{name}.yaml")
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def delete(self, name: str) -> None:
        path, builtin = self._path(name)
        if builtin:
            raise BuiltinPlaybookError(f"{name!r} is a built-in playbook")
        path.unlink()
