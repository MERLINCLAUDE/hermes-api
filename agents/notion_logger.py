import requests
import os
from datetime import datetime

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
LOG_DB_ID = "4a33ba33-f8ae-486f-be39-9b6990d108c6"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}


def log_to_notion(agent: str, task: str, input_text: str, result: str, success: bool = True):
    try:
        today = datetime.now().strftime("%d/%m/%Y %H:%M")
        title = f"{agent} — {today}"
        payload = {
            "parent": {"database_id": LOG_DB_ID},
            "properties": {
                "Titre": {"title": [{"text": {"content": title}}]},
                "Agent": {"select": {"name": agent}},
                "Tâche": {"rich_text": [{"text": {"content": task[:200]}}]},
                "Input": {"rich_text": [{"text": {"content": input_text[:500]}}]},
                "Résultat": {"rich_text": [{"text": {"content": result[:500]}}]},
                "Statut": {"select": {"name": "✅ Succès" if success else "❌ Erreur"}}
            }
        }
        requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload)
    except Exception as e:
        print(f"[notion_logger] ERROR: {e}")  # Ne crashe pas le bot mais trace l'erreur
