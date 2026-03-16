import os
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def _check_telegram_bot():
    if not TELEGRAM_TOKEN:
        return {"service": "Telegram Bot", "status": "❌", "detail": "TELEGRAM_TOKEN manquant"}
    try:
        resp = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe", timeout=10)
        data = resp.json()
        if data.get("ok"):
            return {"service": "Telegram Bot", "status": "✅", "detail": f"@{data['result'].get('username', '?')} en ligne"}
        return {"service": "Telegram Bot", "status": "❌", "detail": data.get("description", "Erreur")}
    except Exception as e:
        return {"service": "Telegram Bot", "status": "❌", "detail": str(e)[:100]}


def _check_notion_api():
    if not NOTION_TOKEN:
        return {"service": "Notion API", "status": "❌", "detail": "NOTION_TOKEN manquant"}
    try:
        resp = requests.get(
            "https://api.notion.com/v1/users/me",
            headers={"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28"},
            timeout=10
        )
        if resp.status_code == 200:
            return {"service": "Notion API", "status": "✅", "detail": f"Connecté ({resp.json().get('name', '?')})"}
        return {"service": "Notion API", "status": "❌", "detail": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"service": "Notion API", "status": "❌", "detail": str(e)[:100]}


def _check_anthropic_api():
    if not ANTHROPIC_API_KEY:
        return {"service": "Anthropic API", "status": "❌", "detail": "ANTHROPIC_API_KEY manquant"}
    try:
        resp = requests.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
            timeout=10
        )
        if resp.status_code == 200:
            return {"service": "Anthropic API", "status": "✅", "detail": "Clé valide"}
        return {"service": "Anthropic API", "status": "❌", "detail": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"service": "Anthropic API", "status": "❌", "detail": str(e)[:100]}


def _check_apify():
    if not APIFY_TOKEN:
        return {"service": "Apify", "status": "❌", "detail": "APIFY_TOKEN manquant"}
    try:
        resp = requests.get(f"https://api.apify.com/v2/users/me?token={APIFY_TOKEN}", timeout=10)
        if resp.status_code == 200:
            return {"service": "Apify", "status": "✅", "detail": f"@{resp.json().get('data', {}).get('username', '?')}"}
        return {"service": "Apify", "status": "❌", "detail": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"service": "Apify", "status": "❌", "detail": str(e)[:100]}


def run_security_monitor(mode: str = "full") -> str:
    required = ["ANTHROPIC_API_KEY", "TELEGRAM_TOKEN", "NOTION_TOKEN", "APIFY_TOKEN", "HERMES_API_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    env_check = {
        "service": "Variables d'env",
        "status": "❌" if missing else "✅",
        "detail": f"Manquantes : {', '.join(missing)}" if missing else "Toutes présentes"
    }

    checks = [env_check, _check_telegram_bot()]
    if mode == "full":
        checks += [_check_notion_api(), _check_anthropic_api(), _check_apify()]

    passed = sum(1 for c in checks if c["status"] == "✅")
    lines = [f"🔒 DIAGNOSTIC {'RAPIDE' if mode == 'quick' else 'COMPLET'} — {passed}/{len(checks)} OK\n"]
    for c in checks:
        lines.append(f"{c['status']} {c['service']} — {c['detail']}")
    lines.append(f"\n{'✅ Tous les systèmes opérationnels.' if passed == len(checks) else f'⚠️ {len(checks)-passed} problème(s) détecté(s).'}")
    return "\n".join(lines)
