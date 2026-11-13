---
description: Check the changes since the last commit with Bite (take them out, run the tests)
---

Run `bite live` in the project's folder with the Bash tool. It takes the changes since the last commit back out of
a copy of the project and runs the tests, so the user's files are never touched.

Tell the user the result in one or two plain sentences. If it says no test noticed the change, or that the new
tests don't notice it, offer to write a test that fails without the change and passes with it. If the `bite`
command wasn't found, try `python -m bite_check live`; if that fails too, tell the user to install Bite with
`pipx install bite-check` and run /bite again.
