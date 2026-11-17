"""Chat score for the radar catalog. Weights live in one dataclass so they can be tuned in one place."""
import math
from dataclasses import dataclass

ACTIVE_MIN_POSTS_PER_DAY = 1.0


@dataclass(frozen=True)
class ScoreWeights:
    activity: float = 40.0
    activity_cap_ppd: float = 20.0
    size: float = 25.0
    signals: float = 20.0
    signal_share_gain: float = 5.0
    language_bonus: float = 10.0
    location_bonus: float = 5.0
    ads_penalty: float = 15.0


def score_chat(
    posts_per_day_7d: float,
    members: int | None,
    signal_share: float,
    language: str | None,
    has_location: bool,
    ads_allowed: str,
    w: ScoreWeights = ScoreWeights(),
) -> float:
    activity = min(posts_per_day_7d, w.activity_cap_ppd) / w.activity_cap_ppd * w.activity
    size = min(math.log10((members or 0) + 1) / 5, 1) * w.size
    signal = min(signal_share * w.signal_share_gain, 1) * w.signals
    lang = w.language_bonus if language in ("uk", "ru") else 0
    loc = w.location_bonus if has_location else 0
    penalty = w.ads_penalty if ads_allowed == "no" else 0
    return round(max(0.0, min(100.0, activity + size + signal + lang + loc - penalty)), 1)
