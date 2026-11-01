"""
Bite in plain words: ask about a fix the way you'd ask a person, and get a plain answer.

    bite ask "is last week's login bug guarded?"
    bite ask "did the discount fix get a test?" --last 200
    bite ask "is the crash on empty carts guarded?" --free

Bite finds the commit(s) that match your words (and the time, if you name one: today, yesterday, this week,
last week, this month, last month, the last 10 days), then runs its usual free check on each: the change is
taken back out of a copy of the project and the tests are run. If a test fails, the fix is guarded.

Matching is free: Bite compares your words with each commit's message and the files it changed. Only when that
finds nothing clear, and you have an Anthropic API key (ANTHROPIC_API_KEY or key.txt), a small AI call picks
the matching commit instead (about a cent). --free never uses the key.

    --last N     how many recent commits to look through (default 100)
    --max N      how many matching commits to check (default 3)
    --free       never use the API key, word matching only
"""

import asyncio
import os
import re
import shutil
import sys
import textwrap
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bite  # noqa: E402
import recent  # noqa: E402
import repo  # noqa: E402

# Words that say what's being asked, not which fix: they'd match every commit.
QUIET = set("""
a an the is are was were be been being am do does did done has have had having will would can could should
i me my we our us you your it its this that these those there here what which who whom whose when where why how
of in on at to for from with by about into onto over under after before since until between of off out up down
and or but not no nor so if then than too very just only still really actually ever even also again any some
all every each one ones thing things stuff something anything bit
guard guarded guards guarding protect protected tested test tests testing covered cover coverage check checked
safe proven proof notice noticed catch caught
bug bugs fix fixes fixed fixing issue issues problem problems change changes changed commit commits patch
work works worked working broke broken break
last past this week weeks weekend today yesterday month months day days ago recent recently lately earlier
week's month's yesterday's today's
bite please tell know
""".split())
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "few": 3, "couple": 2}


def stem(word: str) -> str:
    """crash, crashes and crashed come out the same, and so do login and logins."""
    w = word.lower()
    for end in ("ing", "ed", "es", "s"):
        if w.endswith(end) and len(w) - len(end) >= 3:
            w = w[: -len(end)]
            break
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiou":
        w = w[:-1]  # logg(ed) -> log, stopp(ed) -> stop
    return w


def words(text: str) -> set:
    """Stemmed words, splitting snake_case, camelCase and paths, without the asking words."""
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    parts = re.findall(r"[A-Za-z][A-Za-z']*|\d+", text.replace("_", " "))
    out = set()
    for p in parts:
        p = p.lower().strip("'")
        if p.endswith("'s"):
            p = p[:-2]
        if p in QUIET or len(p) < 2:
            continue
        out.add(stem(p))
    return out


def when(question: str, now: datetime):
    """(start, end, words for it) for the time the question names, or (None, None, "") when it names none."""
    q = question.lower()
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = day - timedelta(days=day.weekday())
    first = day.replace(day=1)
    m = re.search(r"\b(?:last|past)\s+(\d+|a|an|one|two|three|four|five|six|seven|few|couple(?: of)?)\s+(day|week|month)s?\b", q)
    if m:
        n = NUMBER_WORDS.get(m.group(1).split()[0], None) or int(m.group(1))
        span = {"day": timedelta(days=n), "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[m.group(2)]
        return now - span, now, f"in the last {n} {m.group(2)}{'s' if n != 1 else ''}"
    m = re.search(r"\b(\d+|a|an|one|two|three|four|five|six|seven|few|couple(?: of)?)\s+(day|week|month)s?\s+ago\b", q)
    if m:
        n = NUMBER_WORDS.get(m.group(1).split()[0], None) or int(m.group(1))
        span = {"day": timedelta(days=n), "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[m.group(2)]
        unit = {"day": timedelta(days=1), "week": timedelta(weeks=1), "month": timedelta(days=30)}[m.group(2)]
        return day - span, day - span + unit, f"about {n} {m.group(2)}{'s' if n != 1 else ''} ago"
    if re.search(r"\btoday\b|\btoday's\b", q):
        return day, now, "today"
    if re.search(r"\byesterday", q):
        return day - timedelta(days=1), day, "yesterday"
    if re.search(r"\bthis week", q):
        return monday, now, "this week"
    if re.search(r"\blast week", q):
        # People mean "a week or so ago", not strictly Monday to Sunday: look back to the Monday before last.
        return monday - timedelta(days=7), now, "last week"
    if re.search(r"\bthis month", q):
        return first, now, "this month"
    if re.search(r"\blast month", q):
        prev = (first - timedelta(days=1)).replace(day=1)
        return prev, now, "last month"
    return None, None, ""


def history(root: Path, last: int) -> list:
    """Recent commits, newest first, with when they were made."""
    raw = repo.git(root, "log", f"-n{last}", "--no-merges", "--format=%H%x1f%ct%x1f%s%x1f%b%x1e") or ""
    out = []
    for rec in raw.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        parts += [""] * (4 - len(parts))
        if not parts[0]:
            continue
        sha, ct, subject, body = parts
        out.append({"sha": sha, "time": int(ct or 0), "subject": subject.strip(), "body": body.strip()})
    return out


def match(question: str, cs: list) -> list:
    """Commits that share words with the question, best first: [(score, commit)]. A word in the commit's title
    counts twice; the body, the changed files' names and the functions it changed once."""
    want = words(question)
    if not want:
        return []
    found = []
    for c in cs:
        title = words(c["subject"])
        rest = words(re.sub(r"(?im)^[\w-]+-by:.*$", "", c["body"])) | words(" ".join(c.get("code", []) + c.get("tests", [])
                                                                                   + c.get("names", [])))
        score = 2 * len(want & title) + len((want - title) & rest)
        if score:
            score += 1 if c.get("claims") else 0  # a commit that says it fixed something is the likelier answer
            found.append((score, c))
    found.sort(key=lambda sc: -sc[0])  # stable: equal scores stay newest first
    return found


def clear(found: list, question: str) -> bool:
    """The word match found something worth checking: at least one asked-about word in the title, or two anywhere."""
    return bool(found) and found[0][0] >= 2


def has_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        return bite.KEY_FILE.exists() and bool(bite.clean_key(bite.KEY_FILE.read_text(encoding="utf-8-sig")))
    except OSError:
        return False


PICK_PROMPT = """Someone asked about a fix in their project: "{question}"

Here are the project's recent commits that changed code (short id, date, title):
{lines}

Which commits is the question about? Pick at most {n}, best first. If none fits, pick none.
Reply with one line of JSON only: {{"shas": ["<short id>", ...]}}"""


def ai_pick(cfg, question: str, cs: list, n: int) -> list:
    """The commits a small AI call says the question is about (the person's own API key, a cent or so)."""
    from claude_agent_sdk import ClaudeAgentOptions

    async def nothing(*a):
        from claude_agent_sdk import PermissionResultDeny
        return PermissionResultDeny(message="No tools: answer from what you were given.")
    lines = "\n".join(f"{c['sha'][:10]} {day_of(c)} {c['subject'][:120]}" for c in cs[:80])
    opts = ClaudeAgentOptions(model=cfg.judge_model, max_turns=1, max_budget_usd=0.05, allowed_tools=[],
                              can_use_tool=nothing, permission_mode="default", setting_sources=[],
                              env={"ANTHROPIC_API_KEY": bite.load_key()},
                              system_prompt="You match a question to commits. Pick none when unsure.")
    text, _ = asyncio.run(recent._agent(opts, PICK_PROMPT.format(question=question[:500], lines=lines, n=n)))
    picked = [str(s).strip() for s in (recent.last_json(text).get("shas") or []) if str(s).strip()]
    out = []
    for s in picked:
        c = next((c for c in cs if c["sha"].startswith(s.lower()) and len(s) >= 7), None)
        if c and c not in out:
            out.append(c)
    return out[:n]


def day_of(c: dict) -> str:
    d = datetime.fromtimestamp(c["time"])
    return f"{d:%b} {d.day}"


def verdict(c: dict) -> tuple:
    """(kind, label, one plain sentence) for one checked commit. kind is held, gap or cant; the gap labels are
    the names the rest of Bite uses for those results."""
    u, caught = c.get("undo", ""), c.get("caught", "")
    by = c.get("undone_by") or {}
    who = f"commit {by['sha'][:8]} (\"{by['subject']}\")" if by else "a later commit"
    if u == "undone since":
        return "gap", "🔁 UNDONE BY A LATER COMMIT", f"It's gone from today's code: {who} put the old code back."
    if u == "reverted since":
        return "cant", "➖ REVERTED ON PURPOSE", f"{who[0].upper() + who[1:]} reverted it on purpose, so there's nothing left to guard."
    if u.startswith("closed since"):
        return "held", "✅ YES, A LATER TEST NOTICES", "A test added in a later commit fails with it taken out."
    if u.startswith("guarded"):
        one = caught and " more" not in caught
        how = f"{caught.replace('`', '')} fails" if one else (
            f"the tests {caught.replace('`', '')} fail" if caught else "your tests fail")
        return "held", "✅ YES, A TEST NOTICED", f"With it taken out, {how}."
    if u == "TEST GUARDS NOTHING":
        mine = ", ".join(c.get("test_code", [])[:3])
        return "gap", "⚠️ ITS TESTS DIDN'T NOTICE", (f"It came with tests ({mine}), but they still pass with its code "
                                                     "taken out, so they check something else.")
    if u == "guard gone since":
        return "gap", "⚠️ ITS TEST IS GONE", (f"A test noticed it when it was made, but {', '.join(c.get('gone', [])[:3]) or 'its test'} "
                                             "was deleted later, and today's tests don't notice it.")
    if u == "unguarded: part":
        return "gap", "⚠️ PART NOT NOTICED", (f"A test noticed part of it, but not {c.get('part', 'all of it').replace('`', '')}: "
                                              "with only that part taken out, every test still passes.")
    if u.startswith("unguarded"):
        return "gap", "⚠️ NO TEST NOTICED", "With it taken out, every test still passes." + (
            f" ({c['flaky'].replace('`', '')} failed once without it, then passed: it fails now and then.)" if c.get("flaky") else "")
    if u.startswith("not flagged: "):
        return "cant", "❓ NOT CHECKED", f"{u[len('not flagged: '):]}."
    why = f" ({c['why']})" if c.get("why") else ""
    return "cant", "❓ BITE COULDN'T CHECK IT", f"{u}{why}."


def wrap(text: str, width: int, indent: str = "") -> str:
    """Wrapped at spaces only, so a long word or number is never cut in two."""
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent,
                         break_long_words=False, break_on_hyphens=False)


def block(c: dict, width: int, emoji: bool) -> str:
    """One commit's answer, a few short lines: the result, the commit's title, its id and day, and why."""
    _, label, why = verdict(c)
    if not emoji:
        label = label.split(" ", 1)[1]
    return "\n".join([label, wrap(recent.short(c["subject"]), width, "   "), f"   {c['sha'][:7]}, {day_of(c)}",
                      wrap(why, width, "   ")])


def opening(kinds: list) -> str:
    """The answer in a few words, before the details."""
    n, held, gaps = len(kinds), kinds.count("held"), kinds.count("gap")
    if n == 1:
        return {"held": "Yes, it's guarded.", "gap": "No, nothing guards it."}.get(kinds[0], "Bite couldn't check it.")
    if held == n:
        return f"Yes, a test noticed all {n} matching fixes."
    if held and gaps:
        return f"Partly: a test noticed {held} of the {n} matching fixes."
    if gaps:
        return (f"No, no test noticed any of the {n} matching fixes." if gaps == n
                else "No, as far as Bite could check: no test noticed the fixes it could check.")
    if held:
        return "Yes, as far as Bite could check: a test noticed every fix it could check."
    return "Bite couldn't check them."


def answer(checked: list, width: int = 88, emoji: bool = True) -> str:
    """The plain answer: an opening line, then a short block per commit, then what to do next."""
    if not checked:
        return "Bite couldn't tell."
    kinds = [verdict(c)[0] for c in checked]
    parts = [wrap(opening(kinds), width)] + [block(c, width, emoji) for c in checked]
    if "gap" in kinds:
        parts.append(wrap("Next: add a test that fails without that change, then ask again.", width))
    return "\n\n".join(parts)


def look() -> tuple:
    """(width, emoji) for this terminal: its width up to 88, and emoji only where they can show (not piped, and
    a console that can write them; old Windows consoles can't)."""
    width = max(40, min(88, shutil.get_terminal_size((88, 24)).columns - 1))
    try:
        "✅⚠️❓".encode(sys.stdout.encoding or "ascii")
        emoji = sys.stdout.isatty()
    except (UnicodeError, LookupError, AttributeError, ValueError):
        emoji = False
    return width, emoji


def ask(root: Path, question: str, last: int = 100, most: int = 3, free: bool = False, now=None,
        log=print, width: int = 88, emoji: bool = True) -> dict:
    """Find the commit(s) the question is about and check each. {"text", "status", "checked"}; status is held,
    gap, mixed, cant or none (nothing matched)."""
    question = (question or "").strip()
    if not question:
        return {"status": "cant", "checked": [], "text": "Bite: ask a question, like bite ask \"is the login fix guarded?\""}
    try:
        cfg = repo.load_cfg(root)
    except repo.ConfigError as e:
        return {"status": "cant", "checked": [], "text": f"Bite: {e}"}
    covers = recent.extras(root, cfg)  # also reads free_test_command and the rest of Bite's own settings
    if not cfg.test_cmd:
        return {"status": "cant", "checked": [], "text": "Bite found no test command; set test_command in .bite.ini"}
    missing = recent.preflight(cfg)
    if missing:
        return {"status": "cant", "checked": [], "text": f"Bite: {missing}"}
    now = now or datetime.now()
    start, end, said_when = when(question, now)
    cs = history(root, last)
    if start is not None:
        cs = [c for c in cs if start.timestamp() <= c["time"] <= end.timestamp()]
    for c in cs:
        recent.files_of(root, c, cfg)
    cs = [c for c in cs if c["code"]]
    for c in cs:  # "is the make_metavar fix guarded?": people name the function more often than the commit says it
        c["names"] = recent.changed_names(root, c)
    if covers:
        import fnmatch
        cs = [c for c in cs if any(fnmatch.fnmatch(f, g) for f in c["code"] for g in covers)]
    span = f" {said_when}" if said_when else f" in the last {last} commits"
    if not cs:
        return {"status": "none", "checked": [], "text": f"Bite found no commit that changed code your tests run{span}."
                + (f" {repo.SHALLOW}" if repo.shallow(root) else " Try a longer time." if said_when else " Try a larger --last.")}
    found = match(question, cs)
    picked = [c for _, c in found[:most]] if clear(found, question) else []
    how = "words"
    if not picked and not free and has_key():
        try:
            log("Bite: your words didn't clearly match a commit, so a small AI call is picking (your API key).")
            picked, how = ai_pick(cfg, question, cs, most), "ai"
        except Exception as e:  # no SDK, no network: say so and fall back to the word match
            log(f"Bite: the AI pick didn't work ({type(e).__name__}), so word matching only.")
    if not picked and found:
        picked = [c for _, c in found[:most]]  # weak matches are still better than nothing: say they're weak
        how = "weak"
    if not picked:
        hint = "" if free or has_key() else " (With an API key, Bite can also match vaguer questions.)"
        return {"status": "none", "checked": [], "text": f"Bite found no commit{span} that matches your words. Try "
                f"words from the commit message, or a function or file name it changed.{hint}"}
    log(f"Bite: checking {len(picked)} matching commit(s): each runs your tests twice (with and without the change)...")
    t0 = time.time()
    for c in picked:
        c["undo"] = recent.undo_check(root, c, cfg)
    kinds = {verdict(c)[0] for c in picked}
    text = answer(picked, width, emoji)
    if how == "weak":
        text += "\n\n" + wrap("(These only loosely match your words. If it's the wrong commit, use words from its "
                              "message.)", width)
    status = ("held" if kinds == {"held"} else "gap" if kinds <= {"gap", "cant"} and "gap" in kinds
              else "mixed" if "gap" in kinds else "held" if "held" in kinds else "cant")
    return {"status": status, "checked": picked, "text": text, "how": how, "seconds": time.time() - t0}


def main(argv: list) -> int:
    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    opts, words_ = {"--last": 100, "--max": 3}, []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in opts and i + 1 < len(argv):
            try:
                opts[a] = max(1, int(argv[i + 1]))
            except ValueError:
                print(f"Bite: {a} needs a whole number, got {argv[i + 1]!r}.")
                return 1
            i += 2
            continue
        if a != "--free":
            words_.append(a)
        i += 1
    root = repo.repo_root(os.getcwd())
    if root is None:
        print("Bite: not inside a git repository.")
        return 1
    width, emoji = look()
    r = ask(root, " ".join(words_), opts["--last"], opts["--max"], free="--free" in argv,
            log=lambda s: print(s, flush=True), width=width, emoji=emoji)
    print(r["text"])
    return 1 if r["status"] in ("gap", "mixed") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
