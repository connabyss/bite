# Bite

**A proof of concept for an AI referee tool: it checks whether what a coding agent says is done is actually true.**

Bite turns an agent's "fixed" claim into a small test, runs the test itself, and shows a result only when a second, independent check agrees that the test is fair. It also hunts and fixes bugs in a throwaway copy of a project, and calls a fix "proven" only when a test fails without it and passes with it.

The code isn't public yet. This page shows what it has found so far.

## A real example: a fix that wasn't

In [fellowapp/prosemirror-py](https://github.com/fellowapp/prosemirror-py), commit `3614c96` (co-authored by Claude) says:

> fix: add weakref callback to clean up resolve cache entries
>
> The cache used dict keyed by id(doc) with no cleanup, causing a slow memory leak in long-running processes. Added a weakref finalizer callback that removes the cache entry when the doc is garbage collected.

Bite wrote this test of that claim and ran it:

```python
def test_cache_entry_removed_after_doc_gc():
    resolvedpos._resolve_cache.clear()
    d = doc(p("hello"))
    ResolvedPos.resolve_cached(d, 2)
    assert len(resolvedpos._resolve_cache) == 1
    del d
    gc.collect()
    assert len(resolvedpos._resolve_cache) == 0   # fails: 1 == 0
```

It fails on that commit and on today's code. The cache keeps each document alive through its cached positions, so the cleanup callback never runs. A standalone check on today's code found that after 20,000 documents are resolved and dropped, the cache still holds all 20,000, using 35 MB. Reported upstream with a repro ([prosemirror-py #335](https://github.com/fellowapp/prosemirror-py/issues/335)), and a tested fix is open as [#336](https://github.com/fellowapp/prosemirror-py/pull/336).

## Bugs it found in real open-source projects

Each one was reproduced with a standalone script in a clean environment before it was reported.

| Project | Report | What happened |
|---|---|---|
| prosemirror-py | [#335](https://github.com/fellowapp/prosemirror-py/issues/335) | The memory leak above. Fix sent as [#336](https://github.com/fellowapp/prosemirror-py/pull/336), waiting for review. |
| srptools | [#13](https://github.com/idlesign/srptools/issues/13) | 4 bugs. The maintainer fixed all 4 and closed it the same day. |
| pyclibrary | [#92](https://github.com/MatthieuDartiailh/pyclibrary/issues/92) | 7 bugs. The maintainer offered to review a PR for each one. 6 are reviewed and merged so far: [#93](https://github.com/MatthieuDartiailh/pyclibrary/pull/93), [#94](https://github.com/MatthieuDartiailh/pyclibrary/pull/94), [#95](https://github.com/MatthieuDartiailh/pyclibrary/pull/95), [#96](https://github.com/MatthieuDartiailh/pyclibrary/pull/96), [#97](https://github.com/MatthieuDartiailh/pyclibrary/pull/97), [#98](https://github.com/MatthieuDartiailh/pyclibrary/pull/98). |
| resolve-robotics-uri-py | [#26](https://github.com/ami-iit/resolve-robotics-uri-py/issues/26) | Reported, waiting for a reply. |
| mypy_boto3_builder | [#395](https://github.com/youtype/mypy_boto3_builder/issues/395) | Reported, waiting for a reply. |
| drf-pydantic | [#51](https://github.com/georgebv/drf-pydantic/issues/51) | Reported, waiting for a reply. |
| marshmallow-fastoneofschema | [#1](https://github.com/Kalepa/marshmallow-fastoneofschema/issues/1) | 3 bugs. Reported, waiting for a reply. |

## Limitations (honest numbers)

**Checking "fixed" claims.** Bite tested 76 claims from Claude-made commits in 9 open-source projects, all picked by a fixed rule. It showed 3 false "done" claims, and all 3 were real. One is the leak above. The other two were minor, and the projects' own next commits fixed exactly those bugs. 7 of the 9 projects had none: on well-reviewed code, the agents' claims mostly held. The second check threw out 10 failing tests that weren't fair.

**Hunting bugs overnight.** 10 projects, one night each, with two AI judges reading the claims blind:
- **Proven fixes: 21 of 22 were real bugs**, according to both judges. Neither judge rated any fix as wrong. The judges agreed on 93% of claims.
- **Weak spot:** each project had a bug its maintainers fixed soon after. Bite found only **1 of those 10**.

These are small samples. The judges are AI models that read the code without running it. The only human checks so far are the maintainers' fixes and merges above: 4 bugs fixed in srptools, 6 PRs merged in pyclibrary.

## Early access

Want to try Bite on your own project? [Open an issue](../../issues/new) and say a little about the project.
