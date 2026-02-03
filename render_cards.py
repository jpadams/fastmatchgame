"""
Render a game card as PNG: symbols at given positions/rotations/sizes.
Uses text labels (no image assets). Output base64 PNG for API/vision model.
"""
from __future__ import annotations

import base64
import io
import random
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from graph import get_symbols_on_card
from symbols import emoji_for_point_id

# Card dimensions for export
CARD_W = 400
CARD_H = 400
BG_COLOR = (255, 252, 240)
BORDER_COLOR = (80, 60, 40)
BORDER = 8


def _min_dist_to_existing(x: float, y: float, existing: list[tuple[float, float]]) -> float:
    """Minimum distance from (x, y) to any existing point (Euclidean)."""
    if not existing:
        return float("inf")
    return min(((x - ex) ** 2 + (y - ey) ** 2) ** 0.5 for ex, ey in existing)


# Card center and max radius for placement (keep symbol centers well inside so symbols don't clip at edge)
_CARD_CENTER = 0.5
_CARD_RADIUS = 0.5
# Max placement radius 70% of card radius so symbol + margin stays inside circle
_MAX_PLACEMENT_RADIUS_SQ = (_CARD_RADIUS * 0.70) ** 2  # 0.35^2


def _inside_placement_radius(x: float, y: float) -> bool:
    """True if (x, y) is within 70% of card radius from center (symbols stay fully inside circle)."""
    return (x - _CARD_CENTER) ** 2 + (y - _CARD_CENTER) ** 2 <= _MAX_PLACEMENT_RADIUS_SQ


def _pick_position_away_from(
    rng: random.Random,
    existing: list[tuple[float, float]],
    low: float = 0.18,
    high: float = 0.82,
    min_dist: float = 0.26,
) -> tuple[float, float]:
    """Pick (x, y) in [low, high], within 95% radius, with at least min_dist from each existing point."""
    for _ in range(200):
        x = rng.uniform(low, high)
        y = rng.uniform(low, high)
        if not _inside_placement_radius(x, y):
            continue
        if all((x - ex) ** 2 + (y - ey) ** 2 >= min_dist ** 2 for ex, ey in existing):
            return (x, y)
    # Fallback: pick the position that maximizes distance to nearest existing, still within 95% radius
    best_x, best_y = rng.uniform(low, high), rng.uniform(low, high)
    if not _inside_placement_radius(best_x, best_y):
        best_x, best_y = _CARD_CENTER, _CARD_CENTER
    best_d = _min_dist_to_existing(best_x, best_y, existing)
    for _ in range(300):
        x = rng.uniform(low, high)
        y = rng.uniform(low, high)
        if not _inside_placement_radius(x, y):
            continue
        d = _min_dist_to_existing(x, y, existing)
        if d > best_d:
            best_x, best_y, best_d = x, y, d
    return (best_x, best_y)


def _layout_symbols(symbols: list[dict], seed: Optional[int] = None) -> list[dict]:
    """Mix: 3 large, 3 medium, 2 small per card."""
    rng = random.Random(seed)
    size_pool = ["large"] * 3 + ["medium"] * 3 + ["small"] * 2
    rng.shuffle(size_pool)
    out = []
    existing: list[tuple[float, float]] = []
    for i, s in enumerate(symbols):
        pid = s["pointId"]
        x, y = _pick_position_away_from(rng, existing)
        existing.append((x, y))
        out.append({
            "pointId": pid,
            "name": s["name"],
            "emoji": emoji_for_point_id(pid),
            "x": x,
            "y": y,
            "rotation": rng.uniform(-40, 40),
            "size": size_pool[i],
        })
    return out


def _font_size_for_symbol(size: str, is_emoji: bool) -> int:
    """Larger sizes for emoji so they're visible (sizes ~15% larger for visibility)."""
    if is_emoji:
        return {"large": 55, "medium": 41, "small": 32}.get(size, 41)
    return {"large": 32, "medium": 23, "small": 16}.get(size, 23)


def render_card_image(
    card_id: int,
    layout: Optional[list[dict]] = None,
    *,
    seed: Optional[int] = None,
    width: int = CARD_W,
    height: int = CARD_H,
) -> Image.Image:
    """
    Draw one card: border + symbols (text) at positions/rotations/sizes.
    If layout is None, symbols come from get_symbols_on_card and we randomize layout.
    """
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    # Border
    for i in range(BORDER):
        draw.rectangle([i, i, width - 1 - i, height - 1 - i], outline=BORDER_COLOR)

    if layout is None:
        symbols = get_symbols_on_card(card_id)
        layout = _layout_symbols(symbols, seed=seed)

    def _get_font(size: str, is_emoji: bool):
        pt = _font_size_for_symbol(size, is_emoji)
        if is_emoji:
            for path in (
                "/System/Library/Fonts/Apple Color Emoji.ttc",
                "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
                "C:\\Windows\\Fonts\\seguiemj.ttf",
            ):
                try:
                    return ImageFont.truetype(path, pt)
                except OSError:
                    continue
        try:
            return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", pt)
        except OSError:
            pass
        return ImageFont.load_default()

    text_color = (40, 30, 20)

    for item in layout:
        emoji = item.get("emoji")
        name = item.get("name", "?")
        x = item.get("x", 0.5) * width
        y = item.get("y", 0.5) * height
        size = item.get("size", "medium")
        if emoji:
            font = _get_font(size, is_emoji=True)
            text = emoji
        else:
            font = _get_font(size, is_emoji=False)
            text = name[:14] + "…" if len(name) > 14 else name
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx, ty = x - tw / 2, y - th / 2
        draw.text((tx, ty), text, fill=text_color, font=font)

    return img


def render_card_as_png_b64(
    card_id: int,
    round_id: str,
    role: str,
    *,
    seed: Optional[int] = None,
) -> str:
    """
    Render card to PNG bytes, then base64. round_id + role used for deterministic seed if needed.
    """
    if seed is None:
        seed = hash((round_id, role, card_id)) % (2 ** 32)
    img = render_card_image(card_id, seed=seed)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")
