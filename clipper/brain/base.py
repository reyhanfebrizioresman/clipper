"""Antarmuka 'otak' pemilih klip: transkrip + campaign -> usulan klip."""
from dataclasses import dataclass
from typing import Protocol

from clipper.campaign import Campaign
from clipper.transcript import Segment


@dataclass
class Proposal:
    start: float
    end: float
    hook_title: str
    reason: str
    score: float


class Scorer(Protocol):
    def propose(self, segmen: list[Segment], c: Campaign, *,
                min_s: float, max_s: float) -> list[Proposal]: ...
