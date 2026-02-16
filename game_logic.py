"""
Game round: 3 distinct cards (target, AI, human), validation via graph.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from graph import get_symbols_on_card, get_shared_symbol


@dataclass
class Round:
    """One round: 3 card IDs and their roles."""
    target_card_id: int
    ai_card_id: int
    human_card_id: int

    def card_ids(self) -> list[int]:
        return [self.target_card_id, self.ai_card_id, self.human_card_id]

    def human_target_shared(self) -> dict | None:
        """Symbol shared by human's card and target (ground truth)."""
        return get_shared_symbol(self.human_card_id, self.target_card_id)

    def ai_target_shared(self) -> dict | None:
        """Symbol shared by AI's card and target (ground truth)."""
        return get_shared_symbol(self.ai_card_id, self.target_card_id)

    def validate_human_answer(self, symbol_id: int | None, name: str | None) -> bool:
        """Check human's answer against graph. Accept symbolId or name."""
        truth = self.human_target_shared()
        if not truth:
            return False
        if symbol_id is not None and truth["symbolId"] == symbol_id:
            return True
        if name is not None and truth["name"].strip().lower() == name.strip().lower():
            return True
        return False

    def validate_ai_answer(self, symbol_id: int | None, name: str | None) -> bool:
        """Check AI's answer against graph."""
        truth = self.ai_target_shared()
        if not truth:
            return False
        if symbol_id is not None and truth["symbolId"] == symbol_id:
            return True
        if name is not None and truth["name"].strip().lower() == name.strip().lower():
            return True
        return False


def new_round() -> Round:
    """Pick 3 distinct card IDs in 0..56; assign target, AI, human."""
    ids = random.sample(range(57), 3)
    return Round(
        target_card_id=ids[0],
        ai_card_id=ids[1],
        human_card_id=ids[2],
    )


def symbols_for_round(round_obj: Round) -> dict[str, list[dict]]:
    """
    Return symbols on each card for rendering.
    Keys: "target", "ai", "human"; values: list of { symbolId, name }.
    """
    return {
        "target": get_symbols_on_card(round_obj.target_card_id),
        "ai": get_symbols_on_card(round_obj.ai_card_id),
        "human": get_symbols_on_card(round_obj.human_card_id),
    }
