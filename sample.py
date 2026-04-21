
"""
sample.py — List all available Groq models for your API key.

Run this locally BEFORE starting Nexus to confirm which models
you can use and which model ID to put in your .env file.

Usage:
    python sample.py
    python sample.py --key gsk_your_key_here   (if no .env set up yet)
"""

import sys
import os

# ── Load .env if present ───────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass   # python-dotenv not installed — that's fine

# ── Allow key via CLI arg ──────────────────────────────────────────────────────
api_key = os.environ.get("GROQ_API_KEY", "")
for i, arg in enumerate(sys.argv[1:]):
    if arg in ("--key", "-k") and i + 1 < len(sys.argv) - 1:
        api_key = sys.argv[i + 2]
        break
    if arg.startswith("gsk_"):
        api_key = arg
        break

if not api_key:
    print("\n⚠  No API key found.")
    print("   Option 1 — set it in your .env file:  GROQ_API_KEY=gsk_...\n")
    print("   Option 2 — pass it as an argument:")
    print("              python sample.py --key gsk_your_key_here\n")
    print("   Get a free key at: https://console.groq.com/keys\n")
    sys.exit(1)

# ── Check groq is installed ────────────────────────────────────────────────────
try:
    from groq import Groq
except ImportError:
    print("\n⚠  groq package not installed.  Run:  pip install groq\n")
    sys.exit(1)

# ── Chat-capable model filter ──────────────────────────────────────────────────
# These model types are NOT chat-capable; skip them in the chat list
SKIP_PREFIXES = (
    "whisper",          # audio/transcription
    "distil-whisper",
    "playai",           # text-to-speech
    "llava",            # vision (separate API)
)
SKIP_KEYWORDS = ("guard", "safeguard", "embed")


def is_chat_model(model_id: str) -> bool:
    mid = model_id.lower()
    if any(mid.startswith(p) for p in SKIP_PREFIXES):
        return False
    if any(k in mid for k in SKIP_KEYWORDS):
        return False
    return True


# ── Fetch and display ──────────────────────────────────────────────────────────
print("\n" + "═" * 60)
print("  NEXUS — Groq Model Explorer")
print("═" * 60)
print(f"\n  Key: {api_key[:8]}{'•' * (len(api_key) - 12)}{api_key[-4:]}\n")

try:
    client = Groq(api_key=api_key)
    all_models = client.models.list().data
except Exception as e:
    print(f"\n✗  Could not connect to Groq API: {e}\n")
    print("   Check your key at: https://console.groq.com/keys\n")
    sys.exit(1)

# Sort: chat-capable first, then by id
chat_models  = [m for m in all_models if is_chat_model(m.id)]
other_models = [m for m in all_models if not is_chat_model(m.id)]

chat_models.sort(key=lambda m: m.id)
other_models.sort(key=lambda m: m.id)

# ── Recommended model ──────────────────────────────────────────────────────────
RECOMMENDED = "llama-3.3-70b-versatile"
rec = next((m for m in chat_models if m.id == RECOMMENDED), None)

if rec:
    print(f"  ✅  Recommended for Nexus:")
    print(f"      {RECOMMENDED}")
    print(f"\n  Add to your .env file:")
    print(f"      GROQ_MODEL={RECOMMENDED}")
else:
    # find best available fallback
    preferred = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "llama-3.3-70b-specdec",
        "mixtral-8x7b-32768",
    ]
    fallback = next((m for p in preferred for m in chat_models if p in m.id), None)
    if fallback:
        print(f"  ✅  Best available model for Nexus:")
        print(f"      {fallback.id}")
        print(f"\n  Add to your .env file:")
        print(f"      GROQ_MODEL={fallback.id}")

# ── Chat-capable models ────────────────────────────────────────────────────────
print(f"\n{'─' * 60}")
print(f"  💬  Chat-capable models ({len(chat_models)} found)")
print(f"{'─' * 60}")
for m in chat_models:
    marker = "  ★" if m.id == RECOMMENDED else "   "
    print(f"{marker}  {m.id}")

# ── Other models ───────────────────────────────────────────────────────────────
if other_models:
    print(f"\n{'─' * 60}")
    print(f"  🔇  Other models (audio / vision / guard) — not for chat")
    print(f"{'─' * 60}")
    for m in other_models:
        print(f"     {m.id}")

# ── Quick test ─────────────────────────────────────────────────────────────────
print(f"\n{'─' * 60}")
print("  🧪  Quick connection test …")
print(f"{'─' * 60}")

test_model = RECOMMENDED if rec else (chat_models[0].id if chat_models else None)

if test_model:
    try:
        resp = client.chat.completions.create(
            model=test_model,
            messages=[{"role": "user", "content": "Say 'Nexus is ready.' and nothing else."}],
            max_tokens=16,
        )
        reply = resp.choices[0].message.content.strip()
        print(f"\n  ✓  {test_model}")
        print(f"     Response: {reply}")
        print(f"\n  Your API key is valid and working. 🎉")
    except Exception as e:
        print(f"\n  ✗  Test failed: {e}")
else:
    print("\n  ✗  No chat-capable models found on this account.")

print(f"\n{'═' * 60}\n")

