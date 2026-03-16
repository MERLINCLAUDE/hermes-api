import requests
import os
from datetime import datetime

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
CTO_INBOX_DB_ID = "8840e85e-5157-4670-b2e7-9bcf82b6233c"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}


def report_to_cto(agent: str, ticket_type: str, priority: str, context: str, error: str = "") -> bool:
    """
    Crée un ticket dans la CTO Inbox Notion.
    Archimède utilise cette fonction pour signaler des problèmes à Euclide.

    agent: archimede, daily_plan, social_stats, content_strategy, life_coach, security_monitor
    ticket_type: erreur, feature_request, bug, optimisation
    priority: critique, haute, moyenne, basse
    context: description du problème ou de la demande
    error: message d'erreur technique (optionnel)
    """
    try:
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        title = f"[{agent}] {context[:80]} — {now}"

        payload = {
            "parent": {"database_id": CTO_INBOX_DB_ID},
            "properties": {
                "Titre": {"title": [{"text": {"content": title}}]},
                "Agent": {"select": {"name": agent}},
                "Type": {"select": {"name": ticket_type}},
                "Priorité": {"select": {"name": priority}},
                "Statut": {"select": {"name": "ouvert"}},
                "Contexte": {"rich_text": [{"text": {"content": context[:2000]}}]},
                "Erreur": {"rich_text": [{"text": {"content": error[:2000]}}]}
            }
        }
        resp = requests.post(
            "https://api.notion.com/v1/pages",
            headers=NOTION_HEADERS,
            json=payload,
            timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False


def get_open_tickets() -> list:
    """
    Récupère tous les tickets ouverts de la CTO Inbox.
    Utilisé par Euclide pour checker les problèmes à résoudre.
    """
    try:
        payload = {
            "filter": {
                "property": "Statut",
                "select": {"equals": "ouvert"}
            },
            "sorts": [
                {"property": "Créé", "direction": "descending"}
            ]
        }
        resp = requests.post(
            f"https://api.notion.com/v1/databases/{CTO_INBOX_DB_ID}/query",
            headers=NOTION_HEADERS,
            json=payload,
            timeout=10
        )
        if resp.status_code != 200:
            return []

        results = resp.json().get("results", [])
        tickets = []
        for page in results:
            props = page.get("properties", {})
            tickets.append({
                "id": page["id"],
                "titre": _get_title(props.get("Titre", {})),
                "agent": _get_select(props.get("Agent", {})),
                "type": _get_select(props.get("Type", {})),
                "priorite": _get_select(props.get("Priorité", {})),
                "contexte": _get_text(props.get("Contexte", {})),
                "erreur": _get_text(props.get("Erreur", {})),
                "cree": props.get("Créé", {}).get("created_time", "")
            })
        return tickets
    except Exception:
        return []


def resolve_ticket(page_id: str, resolved_by: str = "euclide") -> bool:
    """Marque un ticket comme résolu."""
    try:
        payload = {
            "properties": {
                "Statut": {"select": {"name": "résolu"}},
                "Résolu par": {"select": {"name": resolved_by}}
            }
        }
        resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS,
            json=payload,
            timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False


def _get_title(prop: dict) -> str:
    items = prop.get("title", [])
    return items[0].get("text", {}).get("content", "") if items else ""


def _get_select(prop: dict) -> str:
    sel = prop.get("select")
    return sel.get("name", "") if sel else ""


def _get_text(prop: dict) -> str:
    items = prop.get("rich_text", [])
    return items[0].get("text", {}).get("content", "") if items else ""
