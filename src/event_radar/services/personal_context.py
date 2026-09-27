import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_TOP_LEVEL_HEADING = re.compile(r"^# (?:\d+\.\s*)?(?P<title>.+?)\s*$")
_PURPOSE_HEADING = re.compile(r"^##\s+Purpose\s*$", re.IGNORECASE)
_VERSION_MARKER = re.compile(r"^Context-Version:\s*(?P<version>\d+)\s*$", re.IGNORECASE)
_SUPPORTED_CONTEXT_VERSIONS = frozenset({1})
_REQUIRED_HEADINGS = frozenset(
    {
        "purpose",
        "primary weekend objective",
        "inclusion threshold",
        "discovery posture",
        "the would i actually care test",
        "final curation principle",
    }
)


class PersonalContextStage(StrEnum):
    SCRAPED_EVENT_ANALYSIS = "ai1"
    WEB_EVENT_DISCOVERY = "ai2"
    FINAL_CURATION = "ai3"


_STAGE_SECTION_HEADINGS: dict[PersonalContextStage, tuple[str, ...]] = {
    PersonalContextStage.SCRAPED_EVENT_ANALYSIS: (
        "purpose",
        "primary weekend objective",
        "demographic and social fit",
        "social architecture",
        "how social value interacts with experience value",
        "inclusion threshold",
        "core experience pull",
        "weak pull categories",
        "adult life stage fit",
        "friend vs solo assumptions",
        "experience multipliers",
        "experience penalties",
        "cost and friction",
        "discovery posture",
        "do not confuse these pairs",
        "the would i actually care test",
        "final curation principle",
    ),
    PersonalContextStage.WEB_EVENT_DISCOVERY: (
        "purpose",
        "primary weekend objective",
        "social architecture",
        "how social value interacts with experience value",
        "inclusion threshold",
        "core experience pull",
        "music",
        "food events",
        "festivals markets and open events",
        "comedy",
        "local weirdness and traditions",
        "volunteering",
        "wellness and fitness events",
        "dance",
        "weak pull categories",
        "adult life stage fit",
        "atmosphere",
        "friend vs solo assumptions",
        "experience multipliers",
        "experience penalties",
        "cost and friction",
        "discovery posture",
        "do not confuse these pairs",
        "the would i actually care test",
        "packet composition",
        "final curation principle",
    ),
}


class PersonalExperienceContextError(RuntimeError):
    """Raised when the required private personal-experience policy cannot be loaded."""


@dataclass(frozen=True)
class PersonalContextSection:
    heading: str
    normalized_heading: str
    markdown: str


@dataclass(frozen=True)
class PersonalExperienceContext:
    source_path: Path
    context_version: int
    version_explicit: bool
    canonical_markdown: str
    sections: tuple[PersonalContextSection, ...]

    @classmethod
    def from_markdown(
        cls,
        markdown: str,
        *,
        source_path: Path,
    ) -> "PersonalExperienceContext":
        canonical = markdown.strip()
        if not canonical:
            raise PersonalExperienceContextError(
                f"Personal experience preference context at {source_path} is empty."
            )
        first_line = canonical.splitlines()[0].strip()
        if first_line != "# PERSONAL EXPERIENCE PREFERENCE CONTEXT — EVENT RADAR":
            raise PersonalExperienceContextError(
                f"Personal experience preference context at {source_path} has an invalid title."
            )

        context_version, version_explicit = _context_version(canonical, source_path)
        sections = _parse_sections(canonical)
        headings = [section.normalized_heading for section in sections]
        if len(headings) != len(set(headings)):
            raise PersonalExperienceContextError(
                f"Personal experience preference context at {source_path} has duplicate "
                "semantic headings."
            )
        missing = sorted(_REQUIRED_HEADINGS - set(headings))
        if missing:
            raise PersonalExperienceContextError(
                f"Personal experience preference context at {source_path} is missing required "
                "semantic sections: " + ", ".join(missing) + "."
            )
        return cls(
            source_path=source_path,
            context_version=context_version,
            version_explicit=version_explicit,
            canonical_markdown=canonical + "\n",
            sections=sections,
        )

    def projection(self, stage: PersonalContextStage) -> str:
        if stage is PersonalContextStage.FINAL_CURATION:
            return self.canonical_markdown

        by_heading = {section.normalized_heading: section for section in self.sections}
        selected = [
            by_heading[heading].markdown
            for heading in _STAGE_SECTION_HEADINGS[stage]
            if heading in by_heading
        ]
        stage_label = {
            PersonalContextStage.SCRAPED_EVENT_ANALYSIS: "AI #1 recall-oriented projection",
            PersonalContextStage.WEB_EVENT_DISCOVERY: "AI #2 discovery-oriented projection",
        }[stage]
        return (
            "# PERSONAL EXPERIENCE PREFERENCE CONTEXT — EVENT RADAR\n\n"
            f"> Deterministic {stage_label} from the canonical private document.\n\n"
            + "\n\n---\n\n".join(selected)
            + "\n"
        )


class PersonalExperienceContextRepository:
    def __init__(
        self,
        path: Path = Path("config/personal_experience_preference_context.md"),
    ) -> None:
        self._path = path

    def load(self) -> PersonalExperienceContext:
        try:
            markdown = self._path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise PersonalExperienceContextError(
                f"Required personal experience preference context was not found at {self._path}."
            ) from exc
        except OSError as exc:
            raise PersonalExperienceContextError(
                f"Could not read personal experience preference context at {self._path}."
            ) from exc
        return PersonalExperienceContext.from_markdown(markdown, source_path=self._path)


def _parse_sections(markdown: str) -> tuple[PersonalContextSection, ...]:
    sections: list[PersonalContextSection] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def finish() -> None:
        if current_heading is not None:
            sections.append(
                PersonalContextSection(
                    heading=current_heading,
                    normalized_heading=_normalize_heading(current_heading),
                    markdown="\n".join(current_lines).strip(),
                )
            )

    for line in markdown.splitlines()[1:]:
        heading: str | None = None
        if _PURPOSE_HEADING.match(line):
            heading = "Purpose"
        else:
            match = _TOP_LEVEL_HEADING.match(line)
            if match is not None:
                heading = match.group("title")
        if heading is not None:
            finish()
            current_heading = heading
            current_lines = [line]
        elif current_heading is not None:
            current_lines.append(line)
    finish()
    return tuple(sections)


def _context_version(markdown: str, source_path: Path) -> tuple[int, bool]:
    versions = [
        int(match.group("version"))
        for line in markdown.splitlines()[1:]
        if (match := _VERSION_MARKER.match(line.strip())) is not None
    ]
    if len(versions) > 1:
        raise PersonalExperienceContextError(
            f"Personal experience preference context at {source_path} has multiple version markers."
        )
    version = versions[0] if versions else 1
    if version not in _SUPPORTED_CONTEXT_VERSIONS:
        raise PersonalExperienceContextError(
            f"Personal experience preference context at {source_path} uses unsupported "
            f"Context-Version: {version}."
        )
    return version, bool(versions)


def _normalize_heading(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized).split())
