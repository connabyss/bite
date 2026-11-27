"""Builds assets/bite-catch.svg: Bite's prosemirror-py catch, replayed (see docs/track-record.md).

Every result in it is real output, rerun on commit 3614c96 of fellowapp/prosemirror-py. Lines appear at set times
and commands type themselves out, with SVG <animate> only, so it plays inside a plain <img> on GitHub.
Run: python assets/make_catch_svg.py assets/bite-catch.svg
"""
import sys
from html import escape

G, Y, D, T, R, B = "#7ee787", "#e3b341", "#8b949e", "#e6edf3", "#ff7b72", "#79c0ff"
LH, PAD, TOP, CW = 22, 18, 44, 8.4  # CW: one character's width at 14px monospace
TYPE_STEP = 0.045


def write(path, title, lines, loop, width=860):
    """lines: list of (t, parts) or (t, "$", command). parts = [(text, color, bold)]."""
    end = 0.985

    def k(t):
        return f"{t / loop:.4f}"

    def show(t_on, t_off=None):
        off = k(t_off) if t_off is not None else f"{end}"
        return (f'<animate attributeName="opacity" values="0;1;0" keyTimes="0;{k(t_on)};{off}" calcMode="discrete" '
                f'dur="{loop}s" repeatCount="indefinite"/>')

    def y(i):
        return TOP + LH * i + 14

    h = TOP + LH * len(lines) + PAD
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}" role="img">',
           f"<title>{escape(title)}</title>",
           "<style>text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace;"
           "font-size:14px;white-space:pre}</style>",
           f'<rect width="{width}" height="{h}" rx="10" fill="#0d1117"/>',
           '<circle cx="22" cy="20" r="6" fill="#ff5f57"/><circle cx="42" cy="20" r="6" fill="#febc2e"/>'
           '<circle cx="62" cy="20" r="6" fill="#28c840"/>']
    for i, line in enumerate(lines):
        t = line[0]
        if len(line) == 3:  # a typed command
            cmd = line[2]
            out.append(f'<text x="{PAD}" y="{y(i)}" fill="{G}" opacity="0">${show(t)}</text>')
            for j, ch in enumerate(cmd):
                if ch != " ":
                    out.append(f'<text x="{PAD + (j + 2) * CW:.1f}" y="{y(i)}" fill="{T}" font-weight="bold" '
                               f'opacity="0">{escape(ch)}{show(t + 0.25 + j * TYPE_STEP)}</text>')
            continue
        parts = line[1]
        if not parts:
            continue
        spans = "".join(f'<tspan fill="{c}"{" font-weight=&quot;bold&quot;" if b else ""}>{escape(s)}</tspan>'
                        .replace("&quot;", '"') for s, c, b in parts)
        out.append(f'<text x="{PAD}" y="{y(i)}" opacity="0" xml:space="preserve">{spans}{show(t)}</text>')
    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def typed_until(t, cmd):
    """When a command started at t has finished typing."""
    return t + 0.25 + len(cmd) * TYPE_STEP


c1 = "pytest -q"
c2 = "pytest -q test_claim.py"
L = [
    (0.0, [("# fellowapp/prosemirror-py, commit 3614c96, written with Claude. It says:", D, 0)]),
    (0.4, [('  "fix: add weakref callback to clean up resolve cache entries.', T, 0)]),
    (0.4, [('   The cache ... causing a slow memory leak in long-running processes."', T, 0)]),
    (0.4, []),
    (1.4, "$", c1),
    (typed_until(1.4, c1) + 0.6, [("466 passed", G, 1), (" in 0.57s        ", D, 0), ("# its own tests: all green", D, 0)]),
    (0.0, []),
    (3.4, [("# Bite's test of the claim: resolve a doc, drop it. Its cache entry should go too.", D, 0)]),
    (4.2, "$", c2),
    (typed_until(4.2, c2) + 0.4, [("FAILED", "#ff7b72", 1), (" test_cache_entry_removed_after_doc_gc - ", T, 0), ("assert 1 == 0", "#ff7b72", 1)]),
    (0.0, []),
    (6.9, [("The leak was still there. Drop 20,000 documents and all 20,000 stay in the cache.", Y, 1)]),
    (7.8, [("Reported as prosemirror-py #335. The tested fix, #336, was merged.", T, 0)]),
    (8.6, [("Rerun today on commit 3614c96: same result. Details: docs/track-record.md", D, 0)]),
]
write(sys.argv[1], "Bite's real catch: a Claude commit said it fixed a memory leak; its own tests passed, Bite's test of the claim failed", L, 20.0)
