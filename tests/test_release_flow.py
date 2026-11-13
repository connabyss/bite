"""Releases (2026-11-13): merging a version bump publishes the release and puts it on PyPI by itself.
These check the pieces fit together; the workflows themselves only run on GitHub. No key, no network."""
import importlib.util
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
WF = KIT / ".github" / "workflows"
spec = importlib.util.spec_from_file_location("release_lead", KIT / ".github" / "release_lead.py")
release_lead = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_lead)

LOG = """# Changelog

## Unreleased

- Something new.

## 1.0.9 (2026-11-20)

Thanks to @someone for the new skill.
It now has two lines.

- A change.

## 1.0.8 (2026-11-13)

- Only a list here.
"""


def test_the_lead_is_the_first_paragraph_of_that_versions_section():
    assert release_lead.lead(LOG, "1.0.9") == "Thanks to @someone for the new skill.\nIt now has two lines."


def test_no_lead_when_the_section_opens_with_a_list_or_is_missing():
    assert release_lead.lead(LOG, "1.0.8") == ""
    assert release_lead.lead(LOG, "2.0.0") == ""
    assert release_lead.lead(LOG, "1.0") == ""  # 1.0 is not 1.0.8 or 1.0.9


def test_a_new_version_publishes_the_draft_and_starts_pypi_on_its_tag():
    flow = (WF / "release-drafter.yml").read_text(encoding="utf-8")
    assert "publish: ${{ steps.new.outputs.release }}" in flow
    assert "header: ${{ steps.new.outputs.lead }}" in flow
    assert 'grep -q "HTTP 404"' in flow  # only "not found" means new; other errors stop
    assert 'gh workflow run publish.yml --repo "$GITHUB_REPOSITORY" --ref "v${{ needs.draft.outputs.version }}"' in flow


def test_publish_can_be_started_by_name_but_only_on_a_matching_tag():
    pub = (WF / "publish.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in pub and "types: [published]" in pub
    assert '[ "$GITHUB_REF_TYPE" != "tag" ] || [ "$version" != "$tag" ]' in pub
    assert "name: pypi" in pub and "id-token: write" in pub  # Trusted Publishing unchanged


def test_the_draft_has_no_write_this_before_publishing_placeholder():
    assert "before publishing" not in (KIT / ".github" / "release-drafter.yml").read_text(encoding="utf-8")
