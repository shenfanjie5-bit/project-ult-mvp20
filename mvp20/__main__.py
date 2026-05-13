"""Allow ``python -m mvp20.cli`` invocation by dispatching to the click group.

Most users will prefer the installed ``mvp20`` console script (registered in
``pyproject.toml``), but the spec also documents ``python -m mvp20.cli ...``
so we ship a ``__main__.py`` for parity. Both routes call the same
``mvp20.cli.main`` group.
"""

from __future__ import annotations

from mvp20.cli import main


if __name__ == "__main__":
    main()
