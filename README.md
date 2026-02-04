# Fast Match Finder

A timed perception game using a **57-card deck** represented in Neo4j as a projective plane graph. Three cards are drawn at random (target, AI, human). Players race to find the **one symbol shared** between their card and the target card. The graph is the source of truth for validation.

## Quickstart

```bash
uv run uvicorn main:app
```

Open http://localhost:8000

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** (Python 3.12+)
- **Neo4j** (optional): Used for graph-backed validation and symbol lookup. If not running, the game uses built-in projective-plane math (order 7).
- **OpenAI API key** (optional): For the AI opponent (vision model). Without it, you can still play; the "AI plays" button is just disabled or skips the vision call.

## Setup (after cloning)

```bash
# 1. Clone (if you haven’t already)
git clone <repo-url>
cd game

# 2. Install dependencies
uv sync

# 3. Copy env template and edit
cp .env.example .env
# Edit .env: set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD if using Neo4j;
# set OPENAI_API_KEY (and optionally OPENAI_BASE_URL for Ollama etc.) if you want the AI player.
```

**Neo4j (optional):** If you want graph-backed validation, run Neo4j (e.g. `docker run -p 7687:7687 -e NEO4J_AUTH=neo4j/your-password neo4j`) and set `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` in `.env`. The server seeds the deck on first run via `seed_neo4j.py`.

## Run

```bash
uv run uvicorn main:app --reload
```

Open http://localhost:8000 and click **New round**.

## How it works

- **Round**: 3 distinct card IDs in 0..56 are chosen (target, AI, human). The API returns a layout for each card: symbols with random **position** (%), **rotation** (degrees), and **size** (large/medium/small).
- **Frontend**: Renders the three cards with those layouts. You start the timer, find the symbol that appears on both **your card** and the **target card**, then submit (dropdown or type). The graph is queried to validate your answer.
- **AI player**: Optional. Set `OPENAI_API_KEY` in `.env` (and optionally `OPENAI_BASE_URL` for Ollama or other OpenAI-compatible endpoints). When you click **AI plays**, the server generates PNG images of the AI card and target card (same symbols, server-side layout), sends them to a vision model (e.g. GPT-4o or Ollama), and gets a symbol name. The **judge** uses the graph to check correctness (same validation as for the human).
- **Two-model design**: You can use one model as the game host (generating rounds and judging) and a separate model as the AI opponent by having the AI player call a different API or model.

## API

- `POST /api/round` — Create a new round; returns `roundId`, `layout` (target/ai/human), `allSymbolNames`.
- `GET /api/round/{roundId}` — Get layout for a round (no answers).
- `POST /api/round/{roundId}/validate` — Body: `{ "name": "Symbol name" }` or `{ "pointId": 1 }` (pointId 1..57). Returns `{ "correct": bool, "expected": { "pointId", "name" } }`.
- `POST /api/round/{roundId}/ai-play` — Run the AI player (vision model) and return its answer plus judge result.
- `GET /api/health` — Neo4j and render availability.

## Files

- `seed_neo4j.py` — Seeds Neo4j with 57 Points/Symbols, 57 Lines/Cards, and `(:Point)-[:ON]->(:Line)` incidence (projective plane order 7) on first run.
- `graph.py` — Neo4j queries: symbols on a card, shared symbol between two cards; fallback when DB is unavailable.
- `game_logic.py` — Round generation (3 random cards), validation against graph.
- `render_cards.py` — Renders a card as PNG (text labels, random layout) for the vision model.
- `ai_player.py` — Vision API call (OpenAI) and judge (graph-based validation).
- `main.py` — FastAPI app: round creation, layout, validate, ai-play, static frontend.
- `static/index.html` — Game UI: cards, timer, answer dropdown, submit, AI play.
