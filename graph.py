"""
Neo4j graph access for game deck (57 cards, projective plane).
Source of truth for card symbols and shared-symbol validation.
"""
from __future__ import annotations

import os
from typing import Optional

try:
    from neo4j import GraphDatabase, Driver
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    Driver = None  # type: ignore

# Default driver (lazy init)
_driver: Optional["Driver"] = None


def get_driver() -> Optional["Driver"]:
    global _driver
    if not NEO4J_AVAILABLE:
        return None
    if _driver is not None:
        return _driver
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "")
    if not password:
        return None
    try:
        _driver = GraphDatabase.driver(uri, auth=(user, password))
        _driver.verify_connectivity()
        return _driver
    except Exception:
        return None


def connection_failure_reason() -> str:
    """Return a short reason why Neo4j is not connected (for startup message)."""
    if not NEO4J_AVAILABLE:
        return "neo4j package not installed (run: uv sync)"
    if not os.environ.get("NEO4J_PASSWORD", "").strip():
        return "NEO4J_PASSWORD not set in .env"
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    try:
        driver = GraphDatabase.driver(
            uri,
            auth=(
                os.environ.get("NEO4J_USER", "neo4j"),
                os.environ.get("NEO4J_PASSWORD", ""),
            ),
        )
        driver.verify_connectivity()
        driver.close()
    except Exception as e:
        return f"connection failed: {e}"
    return "unknown"


def close_driver() -> None:
    global _driver
    if _driver:
        _driver.close()
        _driver = None


def get_symbols_on_card(card_id: int) -> list[dict]:
    """
    Return list of { pointId, name } for all symbols on the card with cardId = card_id.
    Name is always the emoji name from symbols (not the value stored in Neo4j).
    """
    from symbols import name_for_point_id

    driver = get_driver()
    if not driver:
        return _fallback_symbols_on_card(card_id)

    with driver.session() as session:
        result = session.run(
            """
            MATCH (s:Point:Symbol)-[:ON]->(c:Card {cardId: $card_id})
            RETURN s.pointId AS pointId
            ORDER BY s.pointId
            """,
            card_id=card_id,
        )
        return [{"pointId": r["pointId"], "name": name_for_point_id(r["pointId"])} for r in result]


# Exact Cypher used for shared-symbol lookup (for debug output).
CYPHER_SHARED_SYMBOL = """
WITH $yours AS a, $target AS b
MATCH 
  (:Card {cardId: a})
      <-[:ON]-
  (s:Point:Symbol)
      -[:ON]->
  (:Card {cardId: b})
RETURN s.name AS name, s.pointId AS pointId;
"""


def get_shared_symbol(card_id_a: int, card_id_b: int) -> Optional[dict]:
    """
    Return the single symbol shared by the two cards, or None if invalid.
    Name is always the emoji name from symbols.
    """
    from symbols import name_for_point_id

    driver = get_driver()
    if not driver:
        return _fallback_shared_symbol(card_id_a, card_id_b)

    with driver.session() as session:
        result = session.run(
            CYPHER_SHARED_SYMBOL,
            yours=card_id_a,
            target=card_id_b,
        )
        row = result.single()
        if not row:
            return None
        pid = row.get("pointId")
        if pid is None:
            pid = row.get("s.pointId")
        name = row.get("name")
        if name is None:
            name = row.get("s.name")
        if name is None and pid is not None:
            name = name_for_point_id(pid)
        return {"pointId": pid, "name": name}


def _fallback_symbols_on_card(card_id: int) -> list[dict]:
    """
    Fallback when Neo4j is not available: use projective plane math
    (order 7) and emoji names from symbols. Returns pointId 1..57.
    """
    from symbols import name_for_point_id

    if not 0 <= card_id <= 56:
        return []
    # Affine lines: cid 0..48 -> y = m*x + b, 7 affine points + slope point
    # Vertical: 49..55 -> x = c, 7 affine + vertical inf
    # Infinity line: 56 -> all 8 infinity points (indices 49..56 -> pointId 50..57)
    indices: list[int] = []
    if card_id < 49:
        m, b = card_id // 7, card_id % 7
        for x in range(7):
            y = (m * x + b) % 7
            indices.append(x * 7 + y)
        indices.append(49 + m)  # slope infinity
    elif card_id < 56:
        c = card_id - 49
        for y in range(7):
            indices.append(c * 7 + y)
        indices.append(56)  # vertical infinity
    else:
        indices = list(range(49, 57))
    return [{"pointId": i + 1, "name": name_for_point_id(i + 1)} for i in indices]


def _fallback_shared_symbol(card_id_a: int, card_id_b: int) -> Optional[dict]:
    """Compute shared symbol using same projective plane logic when DB unavailable. Returns pointId 1..57."""
    from symbols import name_for_point_id

    sa = {p["pointId"] for p in _fallback_symbols_on_card(card_id_a)}
    sb = {p["pointId"] for p in _fallback_symbols_on_card(card_id_b)}
    shared_ids = sa & sb
    if len(shared_ids) != 1:
        return None
    pid = shared_ids.pop()
    return {"pointId": pid, "name": name_for_point_id(pid)}
