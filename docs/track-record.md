# Bite's track record

[← Back to the README](https://github.com/connabyss/bite#readme)

## Famous repos Bite has checked

| Project | Language | Changes checked | Noticed by a test | Real gaps |
|---|---|---|---|---|
| [Rich](https://github.com/Textualize/rich) | Python | 37 | 15 | 1 small: [`<kbd>` keys in Markdown](https://github.com/Textualize/rich/commit/a9c4aaba) |
| [Click](https://github.com/pallets/click) | Python | 37 | 30 | 1 small: [`help` on custom setting types](https://github.com/pallets/click/commit/405a5481) |
| [qs](https://github.com/ljharb/qs) | JavaScript | 40 | 40 | none ✅ |
| [chi](https://github.com/go-chi/chi) | Go | 27 | 21 | 2 small: [a test that only works in a terminal](https://github.com/go-chi/chi/commit/878fe71f), [XML compression](https://github.com/go-chi/chi/commit/d7b767bc) |
| [serde_json](https://github.com/serde-rs/json) | Rust | 16 | 12 | none ✅ |
| [FluentValidation](https://github.com/FluentValidation/FluentValidation) | C# | 9 | 5 | none ✅ |

Checked Oct 30-31, 2026 with `bite --free`. Every bug fix Bite could check had a test (one of chi's only works in a terminal). We read each unnoticed change
by hand. Apart from the gaps above, they were things a test can't catch, like type hints, speed-ups, Windows-only
code or rewrites that work the same.

**[The full scoreboard](https://github.com/connabyss/bite/blob/main/SCOREBOARD.md)** has 20 projects in 5 languages, with a link to every gap.

## The catch that shows what it's for

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

It fails on that commit and on today's code. The cache keeps each document alive through its cached positions, so the cleanup never runs. After 20,000 documents are resolved and dropped, the cache still holds all 20,000, using 35 MB. The commit looked right, read right, and passed its own tests. Reported with a repro in [#335](https://github.com/fellowapp/prosemirror-py/issues/335); the tested fix, [#336](https://github.com/fellowapp/prosemirror-py/pull/336), was merged.

## Fixed or merged upstream

Each bug was reproduced with a standalone script in a clean environment before it was reported.

| Project | What happened |
|---|---|
| pyclibrary | 7 bugs reported in [#92](https://github.com/MatthieuDartiailh/pyclibrary/issues/92). All 7 fixes reviewed and merged: [#93](https://github.com/MatthieuDartiailh/pyclibrary/pull/93), [#94](https://github.com/MatthieuDartiailh/pyclibrary/pull/94), [#95](https://github.com/MatthieuDartiailh/pyclibrary/pull/95), [#96](https://github.com/MatthieuDartiailh/pyclibrary/pull/96), [#97](https://github.com/MatthieuDartiailh/pyclibrary/pull/97), [#98](https://github.com/MatthieuDartiailh/pyclibrary/pull/98), [#99](https://github.com/MatthieuDartiailh/pyclibrary/pull/99). The maintainer [wrote](https://github.com/MatthieuDartiailh/pyclibrary/issues/92): "Thanks for the small and focused PR very nice to review." |
| django-tailwind-cli | With one stylesheet, `tailwind watch` hid rebuild messages and build errors. Fix [#232](https://github.com/django-commons/django-tailwind-cli/pull/232) merged and released in [4.8.2](https://github.com/django-commons/django-tailwind-cli/releases/tag/v4.8.2). The maintainer [wrote](https://github.com/django-commons/django-tailwind-cli/pull/232): "Just about to release 4.8.2 with the fix included. Thanks for the contribution." |
| srptools | 4 bugs reported in [#13](https://github.com/idlesign/srptools/issues/13). The maintainer fixed all 4 and closed it the same day. |
| resolve-robotics-uri-py | URI lookup depended on the hash seed ([#26](https://github.com/gbionics/resolve-robotics-uri-py/issues/26)). Fixed by the maintainers in [#27](https://github.com/gbionics/resolve-robotics-uri-py/pull/27). The maintainer [wrote](https://github.com/gbionics/resolve-robotics-uri-py/issues/26): "Thanks a lot for the detailed issue report!" |
| text-to-cad | A Claude commit added a Python 3.11 syntax check that can't catch the exact bug it was written for (nested same-quote f-strings). Bite sent a test that does catch it, [#708](https://github.com/earthtojake/text-to-cad/pull/708), was merged and released in [0.8.2](https://github.com/earthtojake/text-to-cad/releases/tag/v0.8.2); the maintainer then closed the remaining gaps in [#712](https://github.com/earthtojake/text-to-cad/pull/712). |
| west | Loading a manifest from data with a reserved project name crashed. Fix [#1013](https://github.com/zephyrproject-rtos/west/pull/1013) approved by two maintainers and merged. |
| midea-lan | A message encoder got the frame length wrong when no padding was needed. Fix [#251](https://github.com/wuwentao/midea-lan/pull/251) merged. The maintainer [wrote](https://github.com/wuwentao/midea-lan/pull/251): "Thank you @connabyss for submitting this PR and for finding and fixing the 8370 framing bug." |
| mizani | Number labels picked too few decimals when values were close together (`[0, 10, 10.5]` showed as `10, 10`). Fix [#90](https://github.com/has2k1/mizani/pull/90) merged. The maintainer [wrote](https://github.com/has2k1/mizani/pull/90): "@connabyss, thank you." |
| pamqp | Bite's free check found three past fixes that no test would notice breaking, including one where `Basic.Reject(requeue=False)` was flipped back to `True`. Tests for all three ([#86](https://github.com/gmr/pamqp/pull/86)) merged. |
| prosemirror-py | The memory leak above ([#335](https://github.com/fellowapp/prosemirror-py/issues/335)): fix [#336](https://github.com/fellowapp/prosemirror-py/pull/336) merged. A second Claude commit (`1e3339e`) let `Mapping` change a list the caller still owned: fix [#337](https://github.com/fellowapp/prosemirror-py/pull/337) merged. |
| drf-pydantic | Reported in [#51](https://github.com/georgebv/drf-pydantic/issues/51). 5 fixes merged: [#52](https://github.com/georgebv/drf-pydantic/pull/52), [#53](https://github.com/georgebv/drf-pydantic/pull/53), [#54](https://github.com/georgebv/drf-pydantic/pull/54), [#55](https://github.com/georgebv/drf-pydantic/pull/55), [#56](https://github.com/georgebv/drf-pydantic/pull/56). |
| claude-seo | A Claude commit's `--release` check let a value with a trailing newline through. Fix [#392](https://github.com/AgriciDaniel/claude-seo/pull/392) merged. |

## Sent, waiting for review

| Project | Link | What happened |
|---|---|---|
| python-vcr-tests | [#18](https://github.com/keboola/python-vcr-tests/issues/18), [#19](https://github.com/keboola/python-vcr-tests/pull/19) | A Claude commit said its database recorder captures every query; only the last per cursor is saved. |
| ChatSBOM | [#217](https://github.com/WangYihang/ChatSBOM/issues/217) | A Claude commit's stale-result guard is reset on every walk page, so a repo can be collected twice. |
| llm | [#1828](https://github.com/simonw/llm/pull/1828) | A Claude commit fixed per-turn tool ids in `llm logs`, but its test never made a tool call, so it passed even with the bug. |
| treg | [#1237](https://github.com/superdesigndev/treg/pull/1237) | A Claude commit's test for an org header passes even with the fix removed, so it guards nothing. |
| marshmallow-fastoneofschema | [#1](https://github.com/Kalepa/marshmallow-fastoneofschema/issues/1), [#2](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/2), [#3](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/3), [#4](https://github.com/Kalepa/marshmallow-fastoneofschema/pull/4) | 3 bugs, one fix each. |
| django-modeltranslation | [#831](https://github.com/deschler/django-modeltranslation/pull/831) | Nested `auto_populate()` and `fallbacks()` blocks reset the setting to nothing on exit instead of restoring it. |
| mypy_boto3_builder | [#395](https://github.com/youtype/mypy_boto3_builder/issues/395) | Reported, no reply yet. |
