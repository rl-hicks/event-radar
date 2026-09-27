import re
import subprocess
from pathlib import Path

import pytest

import event_radar.main as main_module
from event_radar.services.personal_context import (
    PersonalContextStage,
    PersonalExperienceContextError,
    PersonalExperienceContextRepository,
)
from tests.curation_helpers import (
    example_user_context,
    personal_context_markdown,
)


def _without_section(markdown: str, heading: str) -> str:
    pattern = rf"\n# \d+\. {re.escape(heading)}\n.*?(?=\n# \d+\.|\Z)"
    updated, count = re.subn(pattern, "", markdown, flags=re.DOTALL)
    assert count == 1
    return updated


def test_current_unversioned_personal_context_contract_loads_successfully(
    tmp_path: Path,
) -> None:
    path = tmp_path / "personal.md"
    path.write_text(personal_context_markdown(), encoding="utf-8")

    context = PersonalExperienceContextRepository(path).load()

    assert context.source_path == path
    assert context.context_version == 1
    assert context.version_explicit is False
    assert len(context.sections) == 29
    assert context.canonical_markdown.startswith(
        "# PERSONAL EXPERIENCE PREFERENCE CONTEXT — EVENT RADAR"
    )


def test_explicit_supported_context_version_loads(tmp_path: Path) -> None:
    path = tmp_path / "personal.md"
    path.write_text(personal_context_markdown(include_version=True), encoding="utf-8")

    context = PersonalExperienceContextRepository(path).load()

    assert context.context_version == 1
    assert context.version_explicit is True


@pytest.mark.asyncio
async def test_missing_required_personal_context_fails_before_pipeline_or_ai(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pipeline_called = False
    user_context = example_user_context()

    async def forbidden_pipeline(**kwargs: object) -> object:
        nonlocal pipeline_called
        pipeline_called = True
        raise AssertionError("Pipeline and AI work must not start without private context.")

    monkeypatch.setattr(
        main_module.settings,
        "personal_experience_context_path",
        tmp_path / "missing.md",
    )
    monkeypatch.setattr(
        main_module.UserContextRepository,
        "load",
        lambda self: user_context,
    )
    monkeypatch.setattr(main_module, "build_recommendation_pipeline", forbidden_pipeline)

    with pytest.raises(PersonalExperienceContextError, match="was not found"):
        await main_module._build_current_pipeline()

    assert pipeline_called is False


def test_nonrequired_section_changes_do_not_break_validation(tmp_path: Path) -> None:
    base = personal_context_markdown()
    variants = [
        base + "\n# 29. OPTIONAL FUTURE SECTION\n\nAdditional policy.\n",
        _without_section(base, "VOLUNTEERING"),
        base.replace("# 12. VOLUNTEERING", "# 112. VOLUNTEERING"),
    ]

    for index, markdown in enumerate(variants):
        path = tmp_path / f"variant-{index}.md"
        path.write_text(markdown, encoding="utf-8")
        context = PersonalExperienceContextRepository(path).load()
        assert context.context_version == 1


def test_missing_required_semantic_section_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "missing-required.md"
    path.write_text(
        _without_section(personal_context_markdown(), "DISCOVERY POSTURE"),
        encoding="utf-8",
    )

    with pytest.raises(
        PersonalExperienceContextError,
        match="missing required semantic sections: discovery posture",
    ):
        PersonalExperienceContextRepository(path).load()


def test_unsupported_context_version_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "unsupported.md"
    path.write_text(
        personal_context_markdown(include_version=True).replace(
            "Context-Version: 1",
            "Context-Version: 99",
        ),
        encoding="utf-8",
    )

    with pytest.raises(PersonalExperienceContextError, match="unsupported Context-Version: 99"):
        PersonalExperienceContextRepository(path).load()


def test_stage_projections_are_deterministic_and_stage_appropriate(tmp_path: Path) -> None:
    path = tmp_path / "personal.md"
    path.write_text(personal_context_markdown(), encoding="utf-8")
    context = PersonalExperienceContextRepository(path).load()

    ai1_first = context.projection(PersonalContextStage.SCRAPED_EVENT_ANALYSIS)
    ai1_second = context.projection(PersonalContextStage.SCRAPED_EVENT_ANALYSIS)
    ai2 = context.projection(PersonalContextStage.WEB_EVENT_DISCOVERY)
    ai3 = context.projection(PersonalContextStage.FINAL_CURATION)

    assert ai1_first == ai1_second
    assert "Worth surfacing is a lower threshold than likely to attend." in ai1_first
    assert "workshop with desirable participation" in ai1_first
    assert "Favor broad discovery" in ai2
    assert "Generic crafts and generic workshops have weak pull." in ai2
    assert ai3 == context.canonical_markdown
    assert "# 27. PACKET COMPOSITION" in ai3


def test_projection_selection_survives_nonrequired_renumbering(tmp_path: Path) -> None:
    path = tmp_path / "renumbered.md"
    path.write_text(
        personal_context_markdown().replace("# 15. WEAK-PULL", "# 115. WEAK-PULL"),
        encoding="utf-8",
    )
    context = PersonalExperienceContextRepository(path).load()

    projection = context.projection(PersonalContextStage.SCRAPED_EVENT_ANALYSIS)

    assert "# 115. WEAK-PULL CATEGORIES" in projection
    assert "Generic crafts and generic workshops have weak pull." in projection


def test_private_personal_context_is_ignored_and_not_tracked() -> None:
    path = "config/personal_experience_preference_context.md"
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", path],
        check=False,
    )
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        check=False,
        capture_output=True,
    )

    assert ignored.returncode == 0
    assert tracked.returncode != 0
