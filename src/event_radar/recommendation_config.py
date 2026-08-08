from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringSignal:
    """
    A deterministic recommendation signal.

    Evidence strength is intentionally field-sensitive:

    - Structured source categories are strongest because the event source
      explicitly classified the event that way.
    - Title matches are also strong because the concept is likely central
      to the event.
    - Description matches are weaker because descriptions frequently mention
      secondary activities, performers, amenities, or contextual details that
      are not the event's actual purpose.

    The evaluator should award only the strongest matching evidence level for
    a given signal. A single signal must not stack category + title +
    description weights for the same event.
    """

    reason: str
    activity_type: str

    category_weight: int
    title_weight: int
    description_weight: int

    category_terms: tuple[str, ...]
    title_terms: tuple[str, ...]
    description_terms: tuple[str, ...]


SCORING_SIGNALS = (
    ScoringSignal(
        reason="festival or public celebration",
        activity_type="festival",
        category_weight=12,
        title_weight=12,
        description_weight=4,
        category_terms=(
            "festival",
            "fair",
            "carnival",
            "parade",
            "celebration",
            "public celebration",
        ),
        title_terms=(
            "festival",
            "fair",
            "carnival",
            "parade",
            "public celebration",
        ),
        description_terms=(
            "festival",
            "street fair",
            "community fair",
            "carnival",
            "parade",
            "public celebration",
        ),
    ),
    ScoringSignal(
        reason="live music",
        activity_type="live_music",
        category_weight=10,
        title_weight=10,
        description_weight=3,
        category_terms=(
            "music",
            "live music",
            "concert",
            "concerts",
            "jazz",
            "blues",
        ),
        title_terms=(
            "live music",
            "concert",
            "jazz",
            "blues",
            "symphony",
            "live band",
            "music festival",
            "live at",
            "in concert",
        ),
        description_terms=(
            "live music",
            "live band",
            "in concert",
            "music festival",
            "jazz performance",
            "blues performance",
        ),
    ),
    ScoringSignal(
        reason="nightlife or energetic evening social setting",
        activity_type="nightlife",
        category_weight=9,
        title_weight=9,
        description_weight=4,
        category_terms=(
            "nightlife",
            "night club",
            "nightclub",
            "dj",
            "dance party",
            "happy hour",
        ),
        title_terms=(
            "nightlife",
            "night club",
            "nightclub",
            "dance party",
            "dj night",
            "dj set",
            "after dark",
            "late night",
            "happy hour",
        ),
        description_terms=(
            "nightlife",
            "dance party",
            "dj night",
            "dj set",
            "after dark",
            "late night",
            "happy hour",
        ),
    ),
    ScoringSignal(
        reason="participatory dance or movement event",
        activity_type="dance",
        category_weight=8,
        title_weight=8,
        description_weight=4,
        category_terms=(
            "dance",
            "dancing",
            "salsa",
            "ballroom",
            "swing dance",
        ),
        title_terms=(
            "dance party",
            "dance night",
            "dance social",
            "salsa night",
            "salsa social",
            "swing dance",
            "ballroom dance",
            "ballroom social",
        ),
        description_terms=(
            "dance party",
            "dance floor",
            "social dancing",
            "salsa dancing",
            "swing dancing",
            "ballroom dancing",
        ),
    ),
    ScoringSignal(
        reason="public market or street gathering",
        activity_type="market",
        category_weight=8,
        title_weight=8,
        description_weight=3,
        category_terms=(
            "market",
            "farmers market",
            "night market",
            "maker market",
            "makers market",
            "craft market",
        ),
        title_terms=(
            "farmers market",
            "night market",
            "street market",
            "maker market",
            "makers market",
            "craft market",
            "public market",
        ),
        description_terms=(
            "farmers market",
            "night market",
            "street market",
            "maker market",
            "makers market",
            "craft market",
            "public market",
        ),
    ),
    ScoringSignal(
        reason="community gathering",
        activity_type="community",
        category_weight=7,
        title_weight=7,
        description_weight=3,
        category_terms=(
            "community",
            "community event",
            "community gathering",
            "block party",
            "street fair",
        ),
        title_terms=(
            "community event",
            "community gathering",
            "block party",
            "street fair",
            "open streets",
            "community festival",
        ),
        description_terms=(
            "community event",
            "community gathering",
            "block party",
            "street fair",
            "open streets",
            "community festival",
        ),
    ),
    ScoringSignal(
        reason="comedy or improv",
        activity_type="comedy",
        category_weight=7,
        title_weight=7,
        description_weight=3,
        category_terms=(
            "comedy",
            "improv",
        ),
        title_terms=(
            "comedy",
            "comedian",
            "stand up comedy",
            "standup comedy",
            "stand-up comedy",
            "improv",
        ),
        description_terms=(
            "comedy show",
            "stand up comedy",
            "standup comedy",
            "stand-up comedy",
            "improv show",
        ),
    ),
    ScoringSignal(
        reason="cultural event or performance",
        activity_type="culture",
        category_weight=7,
        title_weight=7,
        description_weight=2,
        category_terms=(
            "arts",
            "art",
            "culture",
            "cultural",
            "theatre",
            "theater",
            "film",
            "museum",
            "performing arts",
        ),
        title_terms=(
            "theatre",
            "theater",
            "musical",
            "opera",
            "ballet",
            "film festival",
            "film",
            "movie",
            "art walk",
            "exhibition",
            "museum",
            "performing arts",
        ),
        description_terms=(
            "theatre performance",
            "theater performance",
            "performing arts",
            "art exhibition",
            "film festival",
            "museum exhibition",
            "cultural performance",
        ),
    ),
    ScoringSignal(
        reason="active or outdoor activity",
        activity_type="outdoor",
        category_weight=7,
        title_weight=7,
        description_weight=3,
        category_terms=(
            "outdoor",
            "outdoors",
            "nature",
            "hiking",
            "cycling",
        ),
        title_terms=(
            "outdoor",
            "hike",
            "hiking",
            "nature walk",
            "trail walk",
            "bike ride",
            "cycling",
            "kayak",
            "paddle",
            "beach",
            "garden walk",
        ),
        description_terms=(
            "outdoor activity",
            "guided hike",
            "nature walk",
            "trail walk",
            "bike ride",
            "cycling",
            "kayaking",
            "paddling",
        ),
    ),
    ScoringSignal(
        reason="sports, fitness, or recreation",
        activity_type="sports",
        category_weight=6,
        title_weight=6,
        description_weight=3,
        category_terms=(
            "sports",
            "fitness",
            "recreation",
            "race",
            "yoga",
        ),
        title_terms=(
            "tournament",
            "race",
            "5k",
            "10k",
            "marathon",
            "fun run",
            "yoga",
            "fitness class",
        ),
        description_terms=(
            "tournament",
            "5k",
            "10k",
            "marathon",
            "fun run",
            "yoga class",
            "fitness class",
        ),
    ),
    ScoringSignal(
        reason="food-focused gathering",
        activity_type="food",
        category_weight=5,
        title_weight=5,
        description_weight=2,
        category_terms=(
            "food",
            "food & drink",
            "culinary",
            "dining",
        ),
        title_terms=(
            "food festival",
            "food truck",
            "culinary",
            "community dinner",
            "pop up dinner",
            "pop-up dinner",
            "barbecue",
            "bbq",
        ),
        description_terms=(
            "food festival",
            "food trucks",
            "community dinner",
            "pop up dinner",
            "pop-up dinner",
            "barbecue",
            "bbq",
        ),
    ),
    ScoringSignal(
        reason="adult-oriented setting",
        activity_type="adult_social",
        category_weight=4,
        title_weight=4,
        description_weight=2,
        category_terms=(
            "21+",
            "adult",
            "nightlife",
            "wine",
            "beer",
            "brewery",
        ),
        title_terms=(
            "adults only",
            "21+",
            "21 and over",
            "cocktail",
            "wine tasting",
            "beer tasting",
            "brewery",
            "taproom",
        ),
        description_terms=(
            "adults only",
            "21+",
            "21 and over",
            "cocktail",
            "wine tasting",
            "beer tasting",
        ),
    ),
    ScoringSignal(
        reason="distinctive or special event",
        activity_type="special",
        category_weight=3,
        title_weight=3,
        description_weight=1,
        category_terms=(
            "special event",
            "annual event",
            "premiere",
        ),
        title_terms=(
            "annual",
            "anniversary",
            "grand opening",
            "premiere",
            "debut",
            "special event",
            "showcase",
        ),
        description_terms=(
            "annual event",
            "anniversary",
            "grand opening",
            "premiere",
            "debut",
            "special event",
            "showcase",
        ),
    ),
)


@dataclass(frozen=True)
class RecommendationScoringConfig:
    """
    Configuration for deterministic event compression.

    This layer is intentionally a coarse filter/ranker rather than the final
    recommendation engine. Nuanced preference interpretation belongs to the
    later LLM synthesis stage.
    """

    # Candidate-set controls.
    maximum_candidates: int = 22
    minimum_score: int = 5

    # Light diversity controls.
    diversity_soft_cap_per_type: int = 6
    diversity_soft_cap_per_title: int = 1

    # Evidence policy.
    #
    # If a signal matches multiple evidence locations, the evaluator should
    # award only the strongest applicable weight:
    #
    # category > title > description
    #
    # Do not add all three together.
    highest_evidence_only_per_signal: bool = True

    # Description-only semantic matches are deliberately capped so a verbose
    # marketing description cannot accumulate a large score simply because it
    # mentions many secondary activities.
    description_signal_score_cap: int = 8

    # Small secondary signals.
    #
    # Description substance is only a weak confidence/information-quality
    # signal. It should not materially change whether an event is desirable.
    description_substance_boost: int = 1
    description_substance_minimum_characters: int = 120

    evening_event_boost: int = 2
    practical_duration_boost: int = 1
    free_event_boost: int = 2

    # Negative signals.
    child_focused_penalty: int = -5
    administrative_event_penalty: int = -12
    generic_recurring_penalty: int = -3

    # Hard exclusion terms.
    #
    # These should remain conservative. Family-friendly does not mean
    # child-only; ordinary business-adjacent events do not automatically mean
    # professional-only.
    child_only_terms: tuple[str, ...] = (
        "children only",
        "child only",
        "kids only",
        "youth only",
        "for toddlers",
        "toddler time",
        "preschool storytime",
        "preschool class",
    )

    professional_only_terms: tuple[str, ...] = (
        "business networking",
        "professional networking",
        "b2b networking",
        "industry networking",
        "professional development seminar",
        "business leads group",
    )

    # Soft negative terms.
    child_focused_terms: tuple[str, ...] = (
        "kids and family",
        "childrens activities",
        "children s activities",
        "for kids",
        "family activity",
    )

    administrative_terms: tuple[str, ...] = (
        "board meeting",
        "commission meeting",
        "committee meeting",
        "council meeting",
        "public hearing",
        "administrative meeting",
    )

    generic_recurring_terms: tuple[str, ...] = (
        "weekly",
        "every week",
        "every friday",
        "every saturday",
        "every sunday",
        "monthly meeting",
        "ongoing series",
    )

    scoring_signals: tuple[ScoringSignal, ...] = SCORING_SIGNALS


DEFAULT_RECOMMENDATION_CONFIG = RecommendationScoringConfig()
