from __future__ import annotations

import importlib
import os
import pathlib
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from importlib.metadata import EntryPoint


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


@contextmanager
def prepend_src_path() -> Iterator[None]:
    sys.path.insert(0, str(SRC_DIR))
    try:
        yield
    finally:
        sys.path.remove(str(SRC_DIR))


def import_contract_module(module_name: str) -> object:
    with prepend_src_path():
        return importlib.import_module(module_name)


def src_pythonpath_env(
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC_DIR)
    if extra is not None:
        environment.update(extra)

    return environment


def load_console_script(name: str, value: str) -> object:
    with prepend_src_path():
        return EntryPoint(name=name, value=value, group="console_scripts").load()
