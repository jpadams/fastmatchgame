"""
Game API: rounds, symbols, validation, AI (Fast Match Finder).
"""
from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Load .env so NEO4J_* and OPENAI_API_KEY are set before graph/ai use them
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from game_logic import Round, new_round, symbols_for_round
from ai_player import ai_guess_shared_symbol, judge_answer
from symbols import emoji_for_name, emoji_for_point_id

# Optional image generation for cards
try:
    from render_cards import render_card_as_png_b64
    RENDER_AVAILABLE = True
except ImportError:
    RENDER_AVAILABLE = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    from graph import get_driver, connection_failure_reason
    driver = get_driver()
    if driver:
        from seed_neo4j import ensure_deck_loaded
        status = ensure_deck_loaded(driver)
        print("Neo4j: connected (graph is source of truth)")
        if status == "just_loaded":
            print("  → Deck loaded (57 cards, 57 symbols)")
    else:
        reason = connection_failure_reason()
        print("Neo4j: not connected (using built-in projective-plane fallback)")
        print(f"  → {reason}")
    yield
    from graph import close_driver
    close_driver()


app = FastAPI(title="Game API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory round store: round_id -> (Round, layout)
_rounds: dict[str, tuple[Round, dict]] = {}


def _min_dist_to_existing(x: float, y: float, existing: list[tuple[float, float]]) -> float:
    """Minimum distance from (x, y) to any existing point (Euclidean)."""
    if not existing:
        return float("inf")
    return min(((x - ex) ** 2 + (y - ey) ** 2) ** 0.5 for ex, ey in existing)


# Card center and max radius for placement (keep symbol centers well inside so symbols don't clip at edge)
_CARD_CENTER = 50.0
_CARD_RADIUS = 50.0
# Max placement radius 70% of card radius so symbol + margin stays inside circle (largest symbol ~12% radius)
_MAX_PLACEMENT_RADIUS_SQ = (_CARD_RADIUS * 0.70) ** 2  # 35^2


def _inside_placement_radius(x: float, y: float) -> bool:
    """True if (x, y) is within 70% of card radius from center (symbols stay fully inside circle)."""
    return (x - _CARD_CENTER) ** 2 + (y - _CARD_CENTER) ** 2 <= _MAX_PLACEMENT_RADIUS_SQ


def _pick_position_away_from(
    existing: list[tuple[float, float]],
    low: float = 18,
    high: float = 82,
    min_dist: float = 26,
) -> tuple[float, float]:
    """Pick (x, y) inside [low, high], within 95% radius, with at least min_dist from each existing point."""
    for _ in range(200):
        x = random.uniform(low, high)
        y = random.uniform(low, high)
        if not _inside_placement_radius(x, y):
            continue
        if all((x - ex) ** 2 + (y - ey) ** 2 >= min_dist ** 2 for ex, ey in existing):
            return (x, y)
    # Fallback: pick the position that maximizes distance to nearest existing, still within 95% radius
    best_x, best_y = random.uniform(low, high), random.uniform(low, high)
    if not _inside_placement_radius(best_x, best_y):
        best_x, best_y = _CARD_CENTER, _CARD_CENTER
    best_d = _min_dist_to_existing(best_x, best_y, existing)
    for _ in range(300):
        x = random.uniform(low, high)
        y = random.uniform(low, high)
        if not _inside_placement_radius(x, y):
            continue
        d = _min_dist_to_existing(x, y, existing)
        if d > best_d:
            best_x, best_y, best_d = x, y, d
    return (best_x, best_y)


def _layout_for_card(symbols: list[dict]) -> list[dict]:
    """Assign random position, rotation, size to each symbol; keep positions spaced. Mix: 3 large, 3 medium, 2 small per card."""
    size_pool = ["large"] * 3 + ["medium"] * 3 + ["small"] * 2
    random.shuffle(size_pool)
    out = []
    existing: list[tuple[float, float]] = []
    for i, s in enumerate(symbols):
        x, y = _pick_position_away_from(existing)
        existing.append((x, y))
        out.append({
            "pointId": s["pointId"],
            "name": s["name"],
            "emoji": emoji_for_point_id(s["pointId"]),
            "x": x,
            "y": y,
            "rotation": random.uniform(-40, 40),
            "size": size_pool[i],
        })
    return out


@app.post("/api/round")
def create_round() -> dict[str, Any]:
    """Create a new round: 3 distinct cards (target, ai, human). Returns round id and layout data."""
    r = new_round()
    symbols = symbols_for_round(r)
    # Unique round id (simple)
    import uuid
    round_id = str(uuid.uuid4())
    layout = {
        "target": _layout_for_card(symbols["target"]),
        "ai": _layout_for_card(symbols["ai"]),
        "human": _layout_for_card(symbols["human"]),
    }
    _rounds[round_id] = (r, layout)
    return {
        "roundId": round_id,
        "targetCardId": r.target_card_id,
        "aiCardId": r.ai_card_id,
        "humanCardId": r.human_card_id,
        "layout": layout,
        "allSymbolNames": sorted({s["name"] for syms in symbols.values() for s in syms}),
    }


@app.get("/api/round/{round_id}")
def get_round(round_id: str) -> dict[str, Any]:
    """Get round layout (no answers)."""
    if round_id not in _rounds:
        raise HTTPException(status_code=404, detail="Round not found")
    r, layout = _rounds[round_id]
    symbols = symbols_for_round(r)
    return {
        "roundId": round_id,
        "layout": layout,
        "allSymbolNames": sorted({s["name"] for syms in symbols.values() for s in syms}),
    }


@app.post("/api/round/{round_id}/validate")
def validate_answer(round_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Validate human's answer. Body: { "pointId": int? } or { "name": str }. Returns correct + expected."""
    if round_id not in _rounds:
        raise HTTPException(status_code=404, detail="Round not found")
    r, _ = _rounds[round_id]
    point_id = body.get("pointId")
    name = body.get("name")
    result = judge_answer(name, point_id, r, "human")
    debug = None
    from graph import get_driver, CYPHER_SHARED_SYMBOL
    if get_driver():
        debug = {
            "cypher": {
                "query": CYPHER_SHARED_SYMBOL.strip(),
                "params": {"yours": r.human_card_id, "target": r.target_card_id},
            },
            "output": result.get("expected"),
        }
    return {**result, "debug": debug}


@app.post("/api/round/{round_id}/ai-play")
async def ai_play(round_id: str) -> dict[str, Any]:
    """
    AI plays: we need images of AI card and target card.
    If render is available, we generate them and call vision model; else return instructions.
    """
    if round_id not in _rounds:
        raise HTTPException(status_code=404, detail="Round not found")
    r, _ = _rounds[round_id]
    if RENDER_AVAILABLE:
        symbols = symbols_for_round(r)
        ai_card_symbol_names = [s["name"] for s in symbols["ai"]]
        ai_b64 = render_card_as_png_b64(r.ai_card_id, round_id, "ai")
        target_b64 = render_card_as_png_b64(r.target_card_id, round_id, "target")
        guess = await asyncio.to_thread(ai_guess_shared_symbol, ai_b64, target_b64, ai_card_symbol_names)
        if guess.get("error"):
            return {"error": guess["error"], "correct": None, "expected": None, "usage": None, "debug": guess.get("debug")}
        verdict = judge_answer(guess.get("name"), guess.get("pointId"), r, "ai")
        name = guess.get("name")
        emoji = emoji_for_name(name) if name else None
        expected = verdict.get("expected")
        expected_emoji = emoji_for_name(expected.get("name")) if expected and expected.get("name") else None
        return {"name": name, "emoji": emoji, "expected_emoji": expected_emoji, "usage": guess.get("usage"), "token_cost_applicable": guess.get("token_cost_applicable", False), "debug": guess.get("debug"), **verdict}
    return {
        "error": "Card rendering not available; frontend must supply images or use symbol layout",
        "correct": None,
        "expected": None,
        "usage": None,
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Health and capabilities."""
    from graph import get_driver
    has_key = bool((os.environ.get("OPENAI_API_KEY") or "").strip())
    has_base = bool((os.environ.get("OPENAI_BASE_URL") or "").strip())
    ai_available = RENDER_AVAILABLE and (has_key or has_base)
    return {
        "status": "ok",
        "neo4j": "connected" if get_driver() else "disconnected",
        "render": "available" if RENDER_AVAILABLE else "unavailable",
        "ai_available": ai_available,
    }


# Serve static frontend
import os
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.isfile(path):
        with open(path, "r") as f:
            return f.read()
    return "<html><body><p>Game API. Serve static/ with index.html for the game UI.</p></body></html>"
