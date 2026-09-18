"""Set the local trial configuration without printing or overwriting API keys."""
from pathlib import Path
from dotenv import dotenv_values, set_key

root = Path(__file__).resolve().parent.parent
file = root / ".env"
if not file.exists():
    file.write_text((root / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
values = dotenv_values(file)
updates = {
    "KNOWLEDGE_BACKEND": "compiler",
    "COMPILER_URL": "http://127.0.0.1:8010",
    "COMPILER_QUERY_TIMEOUT_SECONDS": "180",
    "COMPILER_SYNC_TIMEOUT_SECONDS": "900",
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_MODEL": "deepseek-v4-flash",
    "MODEL_MODE": "openai",
    "MODEL_URL": "https://api.deepseek.com/chat/completions",
    "MODEL_NAME": "deepseek-v4-flash",
    "REQUEST_TIMEOUT_SECONDS": "90",
    "EXTERNAL_DEFAULT": "false",
}
for key, value in updates.items():
    set_key(str(file), key, value, quote_mode="never")
if "DEEPSEEK_API_KEY" not in values:
    set_key(str(file), "DEEPSEEK_API_KEY", "", quote_mode="never")
print("DeepSeek compiler trial configured. API key present:", bool(values.get("DEEPSEEK_API_KEY")))
