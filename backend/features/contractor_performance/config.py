"""Methodology parameters, versioned. Changing any value means adding a new version key,
so stored rankings stay reproducible (rows are keyed by methodology_version)."""
from dataclasses import asdict, dataclass

DEFAULT_VERSION = "v1"


@dataclass(frozen=True)
class Methodology:
    version: str
    cost_tolerance: float  # +/- share around the rate-card benchmark treated as ordinary variation
    min_sample: int        # minimum known values in a contractor-month for that metric to be ranked
    min_cohort: int        # minimum valid jobs in a (month, repair_method) cohort for speed normalization
    rank_decimals: int     # metric values are rounded to this many decimals before tie comparison

    def params(self) -> dict:
        return asdict(self)


METHODOLOGIES = {
    "v1": Methodology(version="v1", cost_tolerance=0.30, min_sample=5, min_cohort=3, rank_decimals=6),
}

# IMD categories at or above "Heavy" (64.5 mm/day per IMD); taken from the rainfall table's own labels.
HEAVY_RAIN_CATEGORIES = ("Heavy", "Very heavy", "Extremely heavy")


def get_methodology(version: str) -> Methodology:
    try:
        return METHODOLOGIES[version]
    except KeyError:
        raise KeyError(f"unknown methodology_version {version!r}; known: {sorted(METHODOLOGIES)}") from None
