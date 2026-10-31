"""Builds assets/bite-demo.svg: a short animated terminal clip of `bite --demo` (real output, trimmed).

The command types itself out, a spinner turns while the tests run, then the results appear. All timing uses
SVG <animate> on one shared loop, so it plays inside a plain <img> on GitHub with no script.
Run: python assets/make_demo_svg.py assets/bite-demo.svg
"""
from html import escape
import sys

W, LH, PAD, TOP, CW = 860, 22, 18, 44, 8.4  # CW: one character's width at 14px monospace
G, Y, D, T = "#7ee787", "#e3b341", "#8b949e", "#e6edf3"
LOOP = 19.0  # results are all up by ~6s, then held ~12s so they can be read
CMD, TYPE_AT, TYPE_STEP = "bite --demo", 0.6, 0.09
RUN_FROM, RUN_TO = 2.3, 4.0  # spinner turns while the tests run
# (appears at, [(text, colour, bold)]) - one entry per line; line 0 is the prompt, typed separately
LINES = [
    (0.0, []),
    (1.8, [("Two of its commits say they fixed something. One added a test for its fix, the other didn't.", D, 0)]),
    (2.0, [("Bite takes each fix back out and runs the tests, to see whether any test notices it's gone.", D, 0)]),
    (2.3, [("  free check of 2: each runs the tests twice (with and without the change)", D, 0)]),
    (3.2, [("  9661edcf ", D, 0), ("✅ noticed by test_discount_never_below_zero", G, 1)]),
    (3.2, [("           Fix discounts over 100% making the price negative", T, 0)]),
    (4.0, [("  e5c329ec ", D, 0), ("⚠️ NO TEST NOTICED", Y, 1)]),
    (4.0, [("           Fix totals showing long decimals like 0.30000000000000004", T, 0)]),
    (4.0, []),
    (4.9, [("No test noticed it was gone. If it breaks later, nothing warns you.", Y, 0)]),
    (5.5, [("Next: add a test that fails without it.", T, 1)]),
    (5.5, []),
    (6.2, [("0s, $0.00", D, 0)]),
]
SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
END = 0.985  # everything clears just before the loop restarts


def k(t):
    return f"{t / LOOP:.4f}"


def show(t_on, t_off=None):
    """Discrete opacity animation: hidden, visible from t_on until t_off (or the loop's end), hidden."""
    off = k(t_off) if t_off is not None else f"{END}"
    return (f'<animate attributeName="opacity" values="0;1;0" keyTimes="0;{k(t_on)};{off}" calcMode="discrete" '
            f'dur="{LOOP}s" repeatCount="indefinite"/>')


def y(i):
    return TOP + LH * i + 14


H = TOP + LH * len(LINES) + PAD
out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">',
       "<title>bite --demo: one fix has a test that notices it, the other has none</title>",
       "<style>text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace;"
       "font-size:14px;white-space:pre}</style>",
       f'<rect width="{W}" height="{H}" rx="10" fill="#0d1117"/>',
       '<circle cx="22" cy="20" r="6" fill="#ff5f57"/><circle cx="42" cy="20" r="6" fill="#febc2e"/>'
       '<circle cx="62" cy="20" r="6" fill="#28c840"/>']

# Prompt, then the command typed one character at a time (each at a fixed x, so the cursor lines up).
out.append(f'<text x="{PAD}" y="{y(0)}" fill="{G}">$</text>')
for i, ch in enumerate(CMD):
    if ch != " ":
        out.append(f'<text x="{PAD + (i + 2) * CW:.1f}" y="{y(0)}" fill="{T}" font-weight="bold" opacity="0">'
                   f'{escape(ch)}{show(TYPE_AT + i * TYPE_STEP)}</text>')
# Cursor: steps along with the typing, blinks before and after, gone once the output starts.
xs = [PAD + (i + 2) * CW for i in range(len(CMD) + 1)]
TYPED = TYPE_AT + len(CMD) * TYPE_STEP  # when the last character appears
times = [0.0] + [TYPE_AT + i * TYPE_STEP for i in range(1, len(CMD) + 1)]
out.append(f'<rect y="{y(0) - 12}" width="{CW:.1f}" height="16" fill="{T}" x="{xs[0]:.1f}">'
           f'<animate attributeName="x" values="{";".join(f"{x:.1f}" for x in xs)}" '
           f'keyTimes="{";".join(k(t) for t in times)}" calcMode="discrete" dur="{LOOP}s" repeatCount="indefinite"/>'
           f'<animate attributeName="opacity" values="1;0;1;0;1;0" '
           f'keyTimes="0;{k(0.3)};{k(TYPE_AT)};{k(TYPED + 0.3)};{k(TYPED + 0.6)};{k(RUN_FROM)}" '
           f'calcMode="discrete" dur="{LOOP}s" repeatCount="indefinite"/></rect>')

for i, (t, parts) in enumerate(LINES):
    if not parts:
        continue
    spans = "".join(f'<tspan fill="{c}"{" font-weight=\"bold\"" if b else ""}>{escape(s)}</tspan>' for s, c, b in parts)
    out.append(f'<text x="{PAD}" y="{y(i)}" opacity="0" xml:space="preserve">{spans}{show(t)}</text>')

# Spinner at the end of the "free check" line while the tests run.
sx = PAD + (len(LINES[3][1][0][0]) + 1) * CW
n = int((RUN_TO - RUN_FROM) / 0.1)
for f in range(n):
    t0 = RUN_FROM + f * 0.1
    out.append(f'<text x="{sx:.1f}" y="{y(3)}" fill="{Y}" opacity="0">{SPIN[f % len(SPIN)]}{show(t0, t0 + 0.1)}</text>')

out.append("</svg>")
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    fh.write("\n".join(out) + "\n")
