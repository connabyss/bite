"""`python -m bite_check`: runs Bite with only Python and pip, when the `bite` command isn't on PATH (a common
case on Windows, where pip puts commands in a folder PATH doesn't list)."""

import os
import sys

# Nothing in Bite reads or prints this. It is one stop on an art trail that starts at github.com/connabyss.
__credits__ = """\
*10 the tests pass because i wrote the ones that fail.
    word 10 of 12: line
    next: https://above-your-pay-grade.connabyss.workers.dev/.well-known/security.txt
"""

if __name__ == "__main__":
    # python -m puts the current folder first on sys.path. Inside someone's project, their own recent.py (a common
    # name) would then be imported instead of Bite's, so leave it out unless Bite itself lives here (a clone).
    here = os.path.dirname(os.path.abspath(__file__))
    cwd = os.getcwd()
    if os.path.normcase(here) != os.path.normcase(cwd):
        sys.path[:] = [p for p in sys.path
                       if p not in ("", ".") and os.path.normcase(os.path.abspath(p)) != os.path.normcase(cwd)]
    from recent import main

    sys.exit(main())
