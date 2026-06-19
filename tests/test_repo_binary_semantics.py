import py_compile
import sqlite3
from pathlib import Path

import numpy as np
from PIL import Image

from scripts import audit_repo_binary_semantics


def _item(path: str, *, ext: str, reason: str = "binary") -> dict:
    return {
        "path": path,
        "extension": ext,
        "bytes": 1,
        "reason": reason,
        "head_tail_sha256": "sha",
    }


def test_repo_binary_semantics_classifies_structured_skipped_files(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    con = sqlite3.connect(root / "data.sqlite")
    con.execute("CREATE TABLE example(id INTEGER PRIMARY KEY, name TEXT)")
    con.commit()
    con.close()

    source = root / "mod.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    pycache = root / "__pycache__"
    pycache.mkdir()
    pyc = pycache / "mod.cpython-314.pyc"
    py_compile.compile(str(source), cfile=str(pyc), doraise=True)

    np.savez(root / "arrays.npz", values=np.arange(3))

    image_path = root / "image.png"
    Image.new("RGB", (3, 4), "red").save(image_path)

    pickle_path = root / "payload.pkl"
    pickle_path.write_bytes(b"\x80\x04N.")

    large_text = root / "large.log"
    large_text.write_text("one\ntwo\n", encoding="utf-8")

    report = audit_repo_binary_semantics.build_report(
        root,
        root / "missing_repo_content.json",
    )
    assert report["summary"]["semantic_records"] == 0

    repo_content = {
        "skipped_file_fingerprints": [
            _item("data.sqlite", ext=".sqlite"),
            _item("__pycache__/mod.cpython-314.pyc", ext=".pyc"),
            _item("arrays.npz", ext=".npz"),
            _item("image.png", ext=".png"),
            _item("payload.pkl", ext=".pkl"),
            _item("large.log", ext=".log", reason="too_large_for_full_text_read"),
            _item("missing.pdf", ext=".pdf"),
        ]
    }
    content_path = root / "repo_content.json"
    content_path.write_text(__import__("json").dumps(repo_content), encoding="utf-8")

    report = audit_repo_binary_semantics.build_report(root, content_path)
    records = {row["path"]: row for row in report["records"]}

    assert report["summary"]["semantic_records"] == 7
    assert records["data.sqlite"]["semantic_kind"] == "sqlite_database"
    assert records["data.sqlite"]["details"]["object_counts"]["table"] == 1
    assert records["__pycache__/mod.cpython-314.pyc"]["semantic_kind"] == "python_bytecode"
    assert records["__pycache__/mod.cpython-314.pyc"]["details"]["source_exists"] is True
    assert records["arrays.npz"]["semantic_kind"] == "numpy_npz"
    assert records["arrays.npz"]["details"]["arrays"][0]["shape"] == [3]
    assert records["image.png"]["semantic_kind"] == "png_image"
    assert records["image.png"]["details"]["width"] == 3
    assert records["payload.pkl"]["semantic_kind"] == "pickle_payload"
    assert records["payload.pkl"]["details"]["loaded"] is False
    assert records["large.log"]["semantic_kind"] == "large_or_non_utf8_text"
    assert records["large.log"]["details"]["line_count"] == 2
    assert records["missing.pdf"]["semantic_kind"] == "missing_file"
    assert report["summary"]["missing_file_count"] == 1
