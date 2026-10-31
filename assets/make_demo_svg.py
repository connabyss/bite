"""Builds assets/bite-demo.svg: a short animated terminal clip of `bite --demo` (real output, trimmed)."""
from html import escape
import sys

W, LH, PAD, TOP = 860, 22, 18, 44
G, Y, R, D, T = "#7ee787", "#e3b341", "#ff7b72", "#8b949e", "#e6edf3"
# (delay seconds, [(text, colour, bold)])
LINES = [
    (0.3, [("$ ", G, 0), ("bite --demo", T, 1)]),
    (1.2, [("Two of its commits say they fixed something. One added a test for its fix, the other didn't.", D, 0)]),
    (1.6, [("Bite takes each fix back out and runs the tests, to see whether any test notices it's gone.", D, 0)]),
    (2.4, [("", T, 0)]),
    (2.4, [("  9661edcf ", D, 0), ("✅ noticed by test_discount_never_below_zero", G, 1)]),
    (2.4, [("           Fix discounts over 100% making the price negative", T, 0)]),
    (3.6, [("  e5c329ec ", D, 0), ("⚠️ NO TEST NOTICED", Y, 1)]),
    (3.6, [("           Fix totals showing long decimals like 0.30000000000000004", T, 0)]),
    (4.6, [("", T, 0)]),
    (4.6, [("No test noticed it was gone. If it breaks later, nothing warns you.", Y, 0)]),
    (5.2, [("Next: add a test that fails without it.", T, 1)]),
    (6.0, [("", T, 0)]),
    (6.0, [("0s, $0.00", D, 0)]),
]
LOOP = 11.0
H = TOP + LH * len(LINES) + PAD
out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">',
       "<title>bite --demo: one fix has a test that notices it, the other has none</title>",
       "<style>text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace;font-size:14px;white-space:pre}"
       f".l{{opacity:0;animation:show {LOOP}s infinite}}"]
for i, (d, _) in enumerate(LINES):
    out[-1] += f".d{i}{{animation-delay:0s;animation-name:s{i}}}"
    a = d / LOOP * 100
    out[-1] += f"@keyframes s{i}{{0%,{a:.2f}%{{opacity:0}}{a + 0.5:.2f}%,96%{{opacity:1}}100%{{opacity:0}}}}"
out[-1] += "</style>"
out += [f'<rect width="{W}" height="{H}" rx="10" fill="#0d1117"/>',
        '<circle cx="22" cy="20" r="6" fill="#ff5f57"/><circle cx="42" cy="20" r="6" fill="#febc2e"/><circle cx="62" cy="20" r="6" fill="#28c840"/>']
for i, (_, parts) in enumerate(LINES):
    spans = "".join(f'<tspan fill="{c}"{" font-weight=\"bold\"" if b else ""}>{escape(t)}</tspan>' for t, c, b in parts)
    out.append(f'<text class="l d{i}" x="{PAD}" y="{TOP + LH * i + 14}" xml:space="preserve">{spans}</text>')
out.append("</svg>")
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(out) + "\n")
