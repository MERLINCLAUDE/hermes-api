import os
import requests

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Pages clés du workspace Lucas
WORKSPACE_PAGES = {
    "daily_plan_parent": "322563ef9d0281479c6aef4984219ca7",
    "stats": "324563ef9d0281c89ec9dcb673f48f85",
}


def _get_page_title(page_id: str) -> str:
    try:
        r = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=NOTION_HEADERS
        )
        props = r.json().get("properties", {})
        title_prop = props.get("title") or props.get("Name") or props.get("Titre") or {}
        titles = title_prop.get("title", [])
        return "".join(t.get("plain_text", "") for t in titles)
    except Exception:
        return ""


def _get_page_blocks(page_id: str, max_blocks: int = 30) -> list[str]:
    try:
        r = requests.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children?page_size={max_blocks}",
            headers=NOTION_HEADERS
        )
        blocks = r.json().get("results", [])
        lines = []
        for block in blocks:
            btype = block.get("type", "")
            content = block.get(btype, {})
            rich = content.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich)
            if text.strip():
                lines.append(text.strip())
        return lines
    except Exception:
        return []


def fetch_notion_context() -> str:
    """Retourne un résumé du workspace Notion de Lucas pour contextualiser les agents."""
    parts = []

    stats_blocks = _get_page_blocks(WORKSPACE_PAGES["stats"])
    if stats_blocks:
        parts.append("📊 Stats réseaux sociaux :\n" + "\n".join(f"- {l}" for l in stats_blocks[:8]))

    recent_plans = _get_recent_daily_plans()
    if recent_plans:
        parts.append("📅 Derniers plans du jour :\n" + "\n".join(f"- {p}" for p in recent_plans[:5]))

    if not parts:
        return "Aucun contexte Notion disponible."

    return "\n\n".join(parts)


def _get_recent_daily_plans() -> list[str]:
    try:
        r = requests.get(
            f"https://api.notion.com/v1/blocks/{WORKSPACE_PAGES['daily_plan_parent']}/children?page_size=10",
            headers=NOTION_HEADERS
        )
        blocks = r.json().get("results", [])
        titles = []
        for block in blocks:
            if block.get("type") == "child_page":
                title = block.get("child_page", {}).get("title", "")
                if title:
                    titles.append(title)
        return titles
    except Exception:
        return []
