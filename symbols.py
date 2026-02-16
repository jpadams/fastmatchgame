"""
57 emojis and their display names for game symbols (symbolId 0..56).
Names describe the actual emoji used.
"""
from __future__ import annotations

# One emoji per symbol (symbolId 0..56; index = symbolId)
POINT_ID_TO_EMOJI: list[str] = [
    "⚓",   # 0  Anchor
    "🍎",   # 1  Apple
    "🍼",   # 2  Baby bottle
    "💣",   # 3  Bomb
    "🌵",   # 4  Cactus
    "🕯️",   # 5  Candle
    "🚕",   # 6  Taxi
    "🥕",   # 7  Carrot
    "♞",   # 8  Knight
    "🕐",   # 9  Clock
    "🤡",   # 10 Clown
    "🌼",   # 11 Daisy
    "🦕",   # 12 Dinosaur
    "🐬",   # 13 Dolphin
    "🐉",   # 14 Dragon
    "❗",   # 15 Exclamation
    "👁️",   # 16 Eye
    "🔥",   # 17 Fire
    "🍀",   # 18 Clover
    "👻",   # 19 Ghost
    "💚",   # 20 Green heart
    "🔨",   # 21 Hammer
    "❤️",   # 22 Heart
    "🧊",   # 23 Ice
    "⛺",   # 24 Tent
    "🔑",   # 25 Key
    "🐞",   # 26 Ladybug
    "💡",   # 27 Light bulb
    "⚡",   # 28 Lightning
    "🔒",   # 29 Lock
    "🍁",   # 30 Maple leaf
    "🌙",   # 31 Moon
    "🚫",   # 32 Prohibited
    "🎃",   # 33 Pumpkin
    "✏️",   # 34 Pencil
    "🐦",   # 35 Bird
    "🐱",   # 36 Cat
    "👋",   # 37 Hand wave
    "💋",   # 38 Lips
    "✂️",   # 39 Scissors
    "💀",   # 40 Skull
    "❄️",   # 41 Snowflake
    "☃️",   # 42 Snowman
    "🕷️",   # 43 Spider
    "🕸️",   # 44 Spider web
    "☀️",   # 45 Sun
    "🕶️",   # 46 Sunglasses
    "🎯",   # 47 Target
    "🐢",   # 48 Tortoise
    "🎵",   # 49 Music notes
    "🌲",   # 50 Tree
    "💧",   # 51 Drop
    "🐕",   # 52 Dog
    "☯️",   # 53 Yin yang
    "🦓",   # 54 Zebra
    "❓",   # 55 Question mark
    "🧀",   # 56 Cheese
]

# Display name for each symbol (matches the emoji above; used in graph, API, validation, AI prompt)
EMOJI_NAMES: list[str] = [
    "Anchor", "Apple", "Baby bottle", "Bomb", "Cactus", "Candle", "Taxi",
    "Carrot", "Knight", "Clock", "Clown", "Daisy", "Dinosaur", "Dolphin", "Dragon",
    "Exclamation", "Eye", "Fire", "Clover", "Ghost", "Green heart", "Hammer", "Heart",
    "Ice", "Tent", "Key", "Ladybug", "Light bulb", "Lightning", "Lock", "Maple leaf",
    "Moon", "Prohibited", "Pumpkin", "Pencil", "Bird", "Cat", "Hand wave", "Lips",
    "Scissors", "Skull", "Snowflake", "Snowman", "Spider", "Spider web", "Sun",
    "Sunglasses", "Target", "Tortoise", "Music notes", "Tree", "Drop", "Dog",
    "Yin yang", "Zebra", "Question mark", "Cheese",
]


def emoji_for_symbol_id(symbol_id: int) -> str:
    """Return the emoji for a symbol (symbolId 0..56)."""
    if 0 <= symbol_id <= 56:
        return POINT_ID_TO_EMOJI[symbol_id]
    return "?"


def name_for_symbol_id(symbol_id: int) -> str:
    """Return the display name for a symbol (symbolId 0..56)."""
    if 0 <= symbol_id <= 56:
        return EMOJI_NAMES[symbol_id]
    return "?"


def emoji_for_name(name: str) -> str | None:
    """Return the emoji for a symbol by display name (case-insensitive), or None if not found."""
    if not name or not name.strip():
        return None
    n = name.strip()
    for i, label in enumerate(EMOJI_NAMES):
        if label.lower() == n.lower():
            return POINT_ID_TO_EMOJI[i]
    return None
