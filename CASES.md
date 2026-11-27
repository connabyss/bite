# Cases

Bite makes claims: that a fix holds, that no test notices a change, that a test it wrote is fair. Each one should hold up when someone else checks it. This page tracks claims made by Bite, or about it, that anyone can rerun.

## How it works

1. **Open a case** with the [Reproduce or refute](https://github.com/connabyss/bite/issues/new?template=reproduce-or-refute.yml)
   form: one claim, the exact steps, what should happen, what did happen, and where you ran it.
2. **Rerun someone else's case.** Follow its steps on your own machine and post what you got, same or different,
   with your environment. A different result is as useful as a match.
3. **Close it** with what came of it: a fix, a new result written up, or a refutation. Everyone who opened or reran
   the case is credited in the list below.

Nothing here counts on the word of the person who opened it, including connabyss. Claims Bite makes about other people's code are checked against their code, at the commit named, never against a summary.

## The counts

**Open 1 · Reproduced 0 · Resolved 0 · Confirmed 0**

- **Open**: the case is still being worked on.
- **Reproduced**: someone other than the person who opened it followed the steps and got the reported behavior or result.
- **Resolved**: the case is closed, with a fix, a written-up result, or a clear refutation.
- **Confirmed**: the original claim held up after that independent check.

The counts are not mutually exclusive. One case can be Reproduced and Confirmed, and still Open until it is written up.
A rerun that gets a different result refutes the claim: that case is never counted as Reproduced or Confirmed, and it
closes as Resolved once the reason is written down.

## The list

| Case | Claim | Opened by | Reproduced by | Status |
|---|---|---|---|---|
| [#?](https://github.com/connabyss/bite/issues) | Commit `3614c96` of fellowapp/prosemirror-py does not fix the memory leak it says it fixes: Bite's test of the claim fails there while the commit's own 466 tests pass. | connabyss | waiting for a rerun | Open. Upstream fix [#336](https://github.com/fellowapp/prosemirror-py/pull/336) merged. |
