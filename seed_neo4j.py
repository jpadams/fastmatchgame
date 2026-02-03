"""
Load game deck (57 cards, projective plane) into Neo4j on startup if not already present.
Uses emoji names from symbols.EMOJI_NAMES (names of the actual 57 emojis).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from symbols import EMOJI_NAMES

if TYPE_CHECKING:
    from neo4j import Driver


def ensure_deck_loaded(driver: "Driver") -> str:
    """
    If no Card nodes exist, create the full graph (57 Points, 57 Cards, :ON edges).
    Returns "already_loaded" if data was present, "just_loaded" if we ran the seed.
    """
    with driver.session() as session:
        result = session.run("MATCH (c:Card) RETURN count(c) AS n")
        row = result.single()
        if row and row["n"] and row["n"] > 0:
            return "already_loaded"

    _seed_points(driver)
    _seed_cards(driver)
    _seed_incidence(driver)
    return "just_loaded"


def _seed_points(driver: "Driver") -> None:
    """Create 57 Point/Symbol nodes (pointId 1..57)."""
    with driver.session() as session:
        for pid in range(1, 58):
            name = EMOJI_NAMES[pid - 1]
            kind = "affine" if pid < 50 else "infinity"
            x = (pid - 1) // 7 if pid < 50 else None
            y = (pid - 1) % 7 if pid < 50 else None
            if pid == 57:
                slope = "vertical"
            elif 50 <= pid <= 56:
                slope = pid - 50
            else:
                slope = None
            session.run(
                """
                MERGE (p:Point:Symbol {pointId: $pid})
                SET p.name = $name, p.kind = $kind, p.x = $x, p.y = $y, p.slope = $slope
                """,
                pid=pid,
                name=name,
                kind=kind,
                x=x,
                y=y,
                slope=slope,
            )


def _seed_cards(driver: "Driver") -> None:
    """Create 57 Line/Card nodes (cardId 0..56)."""
    with driver.session() as session:
        for cid in range(57):
            if cid < 49:
                kind = "affine"
                m, b = cid // 7, cid % 7
                x_val = None
                label = f"y={m}x+{b}"
            elif cid < 56:
                kind = "vertical"
                m, b = None, None
                x_val = cid - 49
                label = f"x={x_val}"
            else:
                kind = "infinity"
                m, b, x_val = None, None, None
                label = "line_at_infinity"
            session.run(
                """
                MERGE (l:Line:Card {cardId: $cid})
                SET l.kind = $kind, l.m = $m, l.b = $b, l.x = $x_val, l.label = $label
                """,
                cid=cid,
                kind=kind,
                m=m,
                b=b,
                x_val=x_val,
                label=label,
            )


def _seed_incidence(driver: "Driver") -> None:
    """Create (:Point)-[:ON]->(:Card) edges (projective plane incidence)."""
    with driver.session() as session:
        # 3a) Affine lines: 7 affine points each
        session.run(
            """
            MATCH (l:Line:Card {kind: "affine"})
            WITH l, l.m AS m, l.b AS b
            UNWIND range(0, 6) AS x
            WITH l, m, b, x, (m * x + b) % 7 AS y
            MATCH (p:Point:Symbol {kind: "affine", x: x, y: y})
            MERGE (p)-[:ON]->(l)
            """
        )
        # 3b) Affine lines: slope infinity point
        session.run(
            """
            MATCH (l:Line:Card {kind: "affine"})
            WITH l, l.m AS m
            MATCH (inf:Point:Symbol {kind: "infinity", slope: m})
            MERGE (inf)-[:ON]->(l)
            """
        )
        # 3c) Vertical lines: 7 affine points each
        session.run(
            """
            MATCH (l:Line:Card {kind: "vertical"})
            WITH l, l.x AS c
            UNWIND range(0, 6) AS y
            WITH l, c, y
            MATCH (p:Point:Symbol {kind: "affine", x: c, y: y})
            MERGE (p)-[:ON]->(l)
            """
        )
        # 3d) Vertical lines: vertical infinity point
        session.run(
            """
            MATCH (l:Line:Card {kind: "vertical"})
            MATCH (inf:Point:Symbol {kind: "infinity", slope: "vertical"})
            MERGE (inf)-[:ON]->(l)
            """
        )
        # 3e) Line at infinity: all 8 infinity points
        session.run(
            """
            MATCH (l:Line:Card {kind: "infinity"})
            MATCH (inf:Point:Symbol {kind: "infinity"})
            MERGE (inf)-[:ON]->(l)
            """
        )
