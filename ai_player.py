"""
AI player: receives images of AI card + target card, returns the shared symbol.
Uses GPT-4o mini for vision. Judge uses the graph (Neo4j) for validation, not an LLM.
"""
from __future__ import annotations

import os
import re
from typing import Optional

# Optional: call vision API when OPENAI_API_KEY is set
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


def _parse_final_symbol(text: str, valid_names: list[str]) -> Optional[str]:
    """Extract the single symbol name from model output (reasoning + final answer)."""
    if not text:
        return None
    text = text.strip()
    # Look for explicit "Final answer: X" or "ANSWER: X"
    for pattern in (r"(?:Final answer|ANSWER|answer):\s*([^\n.]+)", r"^(?:The )?shared symbol is[:\s]+([^\n.]+)", r"^([^\n.]+)\s*$"):
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if m:
            candidate = m.group(1).strip()
            for name in valid_names:
                if name.lower() == candidate.lower():
                    return name
    # Check last non-empty line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for name in valid_names:
        if lines and name.lower() == lines[-1].lower():
            return name
    # Any line that is exactly a valid name
    for line in reversed(lines):
        for name in valid_names:
            if name.lower() == line.lower():
                return name
    return None


def ai_guess_shared_symbol(
    ai_card_image_b64: str,
    target_card_image_b64: str,
    ai_card_symbol_names: list[str],
    *,
    model: str = "gpt-4o-mini",
) -> dict:
    """
    Send both card images and the list of symbols on the AI's card; ask for the shared symbol.
    Model is prompted to reason step by step, then give one final answer. Single attempt.
    Returns { "name": str | None, "symbolId": int | None, "error": str | None }.
    name can be None when the model returns empty content, wrong format, or no matching symbol
    (e.g. content filter, max_tokens cut-off before "Final answer:", or a typo in the answer).
    """
    env_model = (os.environ.get("OPENAI_DEFAULT_MODEL") or os.environ.get("MODEL") or "").strip()
    if env_model:
        model = env_model
    try:
        max_tokens = int((os.environ.get("OPENAI_MAX_TOKENS") or "800").strip() or "800")
        max_tokens = max(1, min(max_tokens, 128000))
    except (ValueError, TypeError):
        max_tokens = 800
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    raw_base = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip().rstrip("/")
    use_ollama_native = "11434" in raw_base
    if use_ollama_native:
        base_url = raw_base.replace("/v1", "").rstrip("/") or "http://localhost:11434"
    else:
        base_url = raw_base
        if base_url != "https://api.openai.com/v1" and not base_url.endswith("/v1"):
            base_url = base_url + "/v1"
    if not HTTPX_AVAILABLE:
        return {"name": None, "symbolId": None, "error": "AI not configured (httpx not installed; run: uv sync)"}
    if not api_key and (not use_ollama_native and base_url == "https://api.openai.com/v1"):
        return {"name": None, "symbolId": None, "error": "AI not configured (set OPENAI_API_KEY in .env)"}

    from symbols import EMOJI_NAMES

    ai_list = ", ".join(ai_card_symbol_names) if ai_card_symbol_names else "(unknown)"
    prompt = (
        "You are playing Fast Match Finder. You have TWO card images:\n"
        "1. First image = YOUR card (the AI's card).\n"
        "2. Second image = the TARGET card.\n\n"
        f"The symbols on YOUR card are exactly these 8 names: {ai_list}.\n"
        "Exactly ONE symbol appears on BOTH cards. Your job is to find that shared symbol.\n\n"
        "Think step by step internally, but do not narrate your full chain of thought. "
        "Reason briefly (or silently), then output only your final answer in this exact format:\n"
        "Final answer: <symbol name>\n\n"
        f"Your answer must be one of the 8 symbol names from your card above, spelled exactly: {ai_list}."
    )
    # OpenAI-style payload (for OpenAI API and for Ollama /v1/chat/completions fallback)
    payload_openai = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{ai_card_image_b64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{target_card_image_b64}"}},
                ],
            }
        ],
        "max_tokens": max_tokens,
    }
    debug_request_openai = {
        "url": f"{base_url}/v1/chat/completions" if use_ollama_native else f"{base_url}/chat/completions",
        "method": "POST",
        "body": {
            "model": payload_openai["model"],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"[image/png base64, {len(ai_card_image_b64)} chars]"}},
                        {"type": "image_url", "image_url": {"url": f"[image/png base64, {len(target_card_image_b64)} chars]"}},
                    ],
                }
            ],
            "max_tokens": payload_openai["max_tokens"],
        },
    }
    if use_ollama_native:
        img1 = (ai_card_image_b64 or "").replace("\n", "").strip()
        img2 = (target_card_image_b64 or "").replace("\n", "").strip()
        payload_native = {
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [img1, img2]}],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        api_url_native = f"{base_url}/api/chat"
        debug_request = {
            "url": api_url_native,
            "method": "POST",
            "body": {
                "model": payload_native["model"],
                "messages": [{"role": "user", "content": prompt, "images": [f"[base64, {len(img1)} chars]", f"[base64, {len(img2)} chars]"]}],
                "stream": False,
                "options": payload_native["options"],
            },
        }
    else:
        api_url_openai = f"{base_url}/chat/completions"
        debug_request = {**debug_request_openai, "url": api_url_openai}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = 120.0 if use_ollama_native else 60.0
    try:
        with httpx.Client(timeout=timeout) as client:
            if use_ollama_native:
                r = client.post(api_url_native, headers=headers, json=payload_native)
                if r.status_code == 404:
                    # Fallback: Ollama OpenAI-compatible endpoint (e.g. /v1/chat/completions)
                    api_url_openai = f"{base_url}/v1/chat/completions"
                    debug_request = {**debug_request_openai, "url": api_url_openai}
                    r = client.post(api_url_openai, headers=headers, json=payload_openai)
                try:
                    r.raise_for_status()
                except httpx.HTTPStatusError as err:
                    body = getattr(err.response, "text", "") or ""
                    raise RuntimeError(f"{err}: {body[:500]}") from err
                data = r.json()
                if "message" in data and "choices" not in data:
                    msg = data.get("message") or {}
                    text = (msg.get("content") or "").strip()
                    if not text and msg.get("thinking"):
                        text = (msg.get("thinking") or "").strip()
                else:
                    text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
            else:
                r = client.post(api_url_openai, headers=headers, json=payload_openai)
                try:
                    r.raise_for_status()
                except httpx.HTTPStatusError as err:
                    body = getattr(err.response, "text", "") or ""
                    raise RuntimeError(f"{err}: {body[:500]}") from err
                data = r.json()
                text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
            name = _parse_final_symbol(text or "", list(EMOJI_NAMES))
            if name is None and text:
                name = _parse_final_symbol(text, ai_card_symbol_names)
            if not (name and name.strip()):
                name = None
            token_cost_applicable = not use_ollama_native and base_url == "https://api.openai.com/v1" and model == "gpt-4o-mini"
            usage = data.get("usage") if token_cost_applicable else None
            debug_response = {"status_code": r.status_code, "body": data}
            return {"name": name, "symbolId": None, "error": None, "usage": usage, "token_cost_applicable": token_cost_applicable, "debug": {"request": debug_request, "response": debug_response}}
    except Exception as e:
        token_cost_applicable = not use_ollama_native and base_url == "https://api.openai.com/v1" and model == "gpt-4o-mini"
        return {"name": None, "symbolId": None, "error": str(e), "usage": None, "token_cost_applicable": token_cost_applicable, "debug": {"request": debug_request, "response": None, "error": str(e)}}


def judge_answer(
    claimed_name: str | None,
    claimed_symbol_id: int | None,
    round_obj: "Round",
    role: str,
) -> dict:
    """
    Judge a claimed answer (human or AI) using the graph as source of truth.
    role in ("human", "ai"). Returns { "correct": bool, "expected": { "symbolId", "name" } | None }.
    """
    if role == "human":
        truth = round_obj.human_target_shared()
        valid = round_obj.validate_human_answer(claimed_symbol_id, claimed_name or "")
    else:
        truth = round_obj.ai_target_shared()
        valid = round_obj.validate_ai_answer(claimed_symbol_id, claimed_name or "")
    return {"correct": valid, "expected": truth}
