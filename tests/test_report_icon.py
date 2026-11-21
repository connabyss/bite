import urllib.parse
from pathlib import Path

import recent


def test_cat_icon_data_uri():
    assert recent.CAT_ICON.startswith("data:image/svg+xml,")
    decoded = urllib.parse.unquote(recent.CAT_ICON.removeprefix("data:image/svg+xml,"))
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in decoded
    assert 'viewBox="20 14 160 166"' in decoded
    assert recent.CAT_SVG in decoded


def test_report_html_has_favicon(tmp_path: Path):
    path = recent.write_html(tmp_path, [], [], 1.0)
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    assert f'<link rel="icon" href="{recent.CAT_ICON}">' in content
