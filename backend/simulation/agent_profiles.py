"""Serialization for the offline agent's paired opponent models."""
from dataclasses import asdict, dataclass, field

from solver.showdown import ShowdownModel

from .opponent_model import OpponentModel, OpponentStats, SizedStats, SizingProfile


@dataclass
class OrientationProfile:
    models: dict[str, OpponentModel] = field(default_factory=lambda: {seat: OpponentModel(seat) for seat in ("a", "b")})
    showdowns: dict[str, ShowdownModel] = field(default_factory=dict)


def _restore_model(data):
    return OpponentModel(
        player=data["player"],
        hands_observed=data["hands_observed"],
        decisions_observed=data["decisions_observed"],
        stats={key: OpponentStats(**value) for key, value in data["stats"].items()},
        street_stats={street: {key: OpponentStats(**value) for key, value in stats.items()}
                      for street, stats in data["street_stats"].items()},
        sizing=SizingProfile(**data["sizing"]),
        street_sizing={street: SizingProfile(**value) for street, value in data["street_sizing"].items()},
        sized_stats={key: SizedStats(**value) for key, value in data["sized_stats"].items()},
    )


def restore_profiles(data) -> dict[str, OrientationProfile]:
    if data is None:
        return {seat: OrientationProfile() for seat in ("a", "b")}
    profiles = {}
    for orientation in ("a", "b"):
        record = data[orientation]
        profiles[orientation] = OrientationProfile(
            models={seat: _restore_model(record["models"][seat]) for seat in ("a", "b")},
            showdowns={seat: ShowdownModel(**value) for seat, value in record["showdowns"].items()},
        )
    return profiles


def encode_profiles(profiles) -> dict:
    return {orientation: asdict(profile) for orientation, profile in profiles.items()}


def opponent_hands(profiles) -> dict[str, int]:
    if profiles is None:
        return {"a": 0, "b": 0}
    return {seat: profiles[seat]["models"][other]["hands_observed"] for seat, other in (("a", "b"), ("b", "a"))}
