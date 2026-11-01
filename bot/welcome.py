"""The bite-check app's welcome bot. Run once an hour by .github/workflows/bot.yml.

For every repo someone installed the bite-check app on, it opens one issue with an "Add Bite" link. The link opens
GitHub's own new-file page with the Bite check already filled in, so the owner adds it with one click on Commit.
The app itself only needs Issues: write. It never touches anyone's code or workflows.

Standard library only (plus the openssl command for signing), so nothing outside can change under it.
Key: BITE_APP_KEY (the app's private key). BITE_DRY_RUN=1 prints what it would post and posts nothing.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

APP_ID = "5545588"
APP_LOGIN = "bite-check[bot]"
MARK = "<!-- bite-welcome -->"
HOME = "connabyss/bite"
VERSION = "v0.9.0"
# An install on many repos at once (say "All repositories" on a big account) gets no issues at all, so the bot never
# floods anyone. They can install it again on the repos they want.
MAX_REPOS = 10
API = "https://api.github.com"

# What each language needs installed before its tests run. Bite installs itself; don't install the project as a
# package (pip install -e .), or every copy Bite makes would import this checkout's code instead of its own. The Python
# step installs what the project lists (pyproject.toml or setup.py), then uninstalls the project itself.
SETUP = {
    "Python": """      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      # Add what your tests need here.
      - run: |
          python -m pip install pytest
          if [ -f requirements.txt ]; then python -m pip install -r requirements.txt; fi
          # What pyproject.toml or setup.py lists, then the project itself comes out again.
          if [ -f pyproject.toml ] || [ -f setup.py ]; then
            if python -m pip install --report /tmp/deps.json .; then
              python -c "import json; print(*[i['metadata']['name'] for i in json.load(open('/tmp/deps.json'))['install'] if i.get('is_direct')])" | xargs -r python -m pip uninstall -y
            else
              echo "::warning::Couldn't install what this project lists; add it in the step above."
            fi
          fi
          # The test and dev lists in pyproject.toml (standard, dependency groups or Poetry's, which go by name only).
          if [ -f pyproject.toml ]; then
          python - <<'EOF'
          import subprocess, sys
          try:
              import tomllib
          except ImportError:  # Python 3.10 or older
              sys.exit(print("::warning::Reading pyproject.toml's test and dev lists needs Python 3.11 or newer."))
          d = tomllib.load(open("pyproject.toml", "rb"))
          keys = ("test", "tests", "testing", "dev")
          extra = d.get("project", {}).get("optional-dependencies", {})
          groups = d.get("dependency-groups", {})
          poetry = d.get("tool", {}).get("poetry", {})
          tables = [poetry.get("dev-dependencies", {})] + [poetry.get("group", {}).get(k, {}).get("dependencies", {}) for k in keys]
          names = [r for k in keys for r in extra.get(k, []) + groups.get(k, []) if isinstance(r, str)]
          names += [n for t in tables for n in t if n != "python"]
          if names and subprocess.run([sys.executable, "-m", "pip", "install", *names]).returncode:
              print("::warning::Couldn't install this project's test and dev lists; add them in the step above.")
          EOF
          fi""",
    "JavaScript": """      - uses: actions/setup-node@v4
        with:
          node-version: 22
      # Add what your tests need here.
      - run: npm ci || npm install""",
    "Go": """      - uses: actions/setup-go@v5
        with:
          go-version: stable""",
    "Rust": """      # Rust and cargo come with GitHub's Ubuntu machines.""",
    "C#": """      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: 8.0.x""",
    "Java": """      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'""",
}
SETUP["TypeScript"] = SETUP["JavaScript"]
SETUP["Kotlin"] = SETUP["Java"]  # Maven and Gradle come with GitHub's Ubuntu machines.
OTHER = """      # Install what your tests need here, e.g. actions/setup-python, then set test_command in a .bite.ini file
      # (see https://github.com/connabyss/bite)."""


def workflow(language):
    """The bite.yml the issue's link fills in, with the setup step for the repo's main language."""
    return f"""name: bite

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  bite:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.pull_request.head.sha }}}}
          fetch-depth: 0
{SETUP.get(language, OTHER)}
      - uses: {HOME}@{VERSION}
"""


def language(repo):
    """The repo's main language. A new repo or a fresh fork has none yet (GitHub works it out later), so guess
    Python, Bite's most common case, rather than leave the owner to write the setup themselves."""
    return repo.get("language") or "Python"


def add_link(repo):
    """GitHub's new-file page for this repo, with .github/workflows/bite.yml already filled in."""
    query = urllib.parse.urlencode({"filename": ".github/workflows/bite.yml", "value": workflow(language(repo))},
                                   quote_via=urllib.parse.quote)
    return f"https://github.com/{repo['full_name']}/new/{urllib.parse.quote(repo['default_branch'])}?{query}"


def issue_body(repo):
    lang = language(repo)
    setup_note = ((f"The file installs what {lang} tests usually need. " if repo.get("language") else
                   "GitHub hasn't worked out this repo's language yet, so the file assumes Python tests. ")
                  + "If your tests need more, add it in the step marked \"Add what your tests need here\" before you commit."
                  if lang in SETUP else
                  "Bite couldn't tell how your tests run, so add your setup in the step marked in the file before "
                  "you commit.")
    return f"""{MARK}
Thanks for installing **bite-check**. One click left:

### [Add Bite to this repo]({add_link(repo)})

That link opens GitHub's own new-file page with the Bite check filled in. Read it, then click **Commit changes**.
From then on, every pull request gets one comment from Bite saying, per commit, whether any test notices when the
change is taken back out.

{setup_note}

- The check runs on GitHub's own machines in your repo, with your repo's own Actions minutes (free for public repos).
- This app can only open issues. It can't read or change your code or workflows.
- Already set up, or not for you? Close this issue; the app won't post again.

More: https://github.com/{HOME}
"""


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def app_jwt(key_pem, now=None):
    """The app's own short-lived login (a JWT signed with its private key), signed with the openssl command."""
    now = int(now if now is not None else time.time())
    head = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    body = b64(json.dumps({"iat": now - 60, "exp": now + 540, "iss": APP_ID}).encode())
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "key.pem")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key_pem)
        sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", path], input=f"{head}.{body}".encode(),
                             capture_output=True, check=True).stdout
    return f"{head}.{body}.{b64(sig)}"


def call(method, path, token, data=None, scheme="Bearer"):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(data).encode() if data else None,
                                 headers={"Authorization": f"{scheme} {token}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "bite-check-bot"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def pages(path, token, key=None):
    """Every item of a list endpoint, page by page."""
    sep = "&" if "?" in path else "?"
    page = 1
    while True:
        got = call("GET", f"{path}{sep}per_page=100&page={page}", token)
        items = got[key] if key else got
        yield from items
        if len(items) < 100:
            return
        page += 1


def welcomed(repo, token):
    """Whether the app already opened its issue here (open or closed)."""
    creator = urllib.parse.quote(APP_LOGIN)
    return any(MARK in (i.get("body") or "")
               for i in pages(f"/repos/{repo['full_name']}/issues?state=all&creator={creator}", token))


def wanted(repo):
    """Repos that get an issue: not Bite's own, not archived, with issues turned on."""
    return repo["full_name"] != HOME and not repo.get("archived") and repo.get("has_issues", True)


def run(key_pem, dry_run):
    jwt = app_jwt(key_pem)
    posted = 0
    for inst in pages("/app/installations", jwt):
        who = inst["account"]["login"]
        # Ask for an issues-only token, whatever else the app may be allowed, so this run can do nothing more.
        token = call("POST", f"/app/installations/{inst['id']}/access_tokens", jwt, {"permissions": {"issues": "write"}})["token"]
        repos = list(pages("/installation/repositories", token, key="repositories"))
        if len(repos) > MAX_REPOS:
            print(f"{who}: {len(repos)} repos, more than {MAX_REPOS}: skipped so nobody gets flooded")
            continue
        for repo in repos:
            name = repo["full_name"]
            try:
                if not wanted(repo) or welcomed(repo, token):
                    continue
                if dry_run:
                    print(f"{name}: would open the welcome issue ({language(repo)})")
                    continue
                call("POST", f"/repos/{name}/issues", token,
                     {"title": "Add Bite's free check (one click)", "body": issue_body(repo)})
                posted += 1
                print(f"{name}: opened the welcome issue")
            except urllib.error.HTTPError as e:  # one repo's trouble shouldn't stop the others
                print(f"{name}: skipped, GitHub said {e.code} {e.reason}")
    print(f"Done: {posted} new welcome issue(s).")


def main():
    key = os.environ.get("BITE_APP_KEY", "")
    if not key.strip():
        sys.exit("BITE_APP_KEY isn't set (it lives in the repo's 'bot' environment).")
    run(key, os.environ.get("BITE_DRY_RUN") == "1")


if __name__ == "__main__":
    main()
