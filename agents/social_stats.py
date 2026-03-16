import os
import requests

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
STATS_PAGE_ID = "324563ef9d0281c89ec9dcb673f48f85"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}


def fetch_social_stats() -> str:
    try:
        r = requests.get(
            f"https://api.notion.com/v1/blocks/{STATS_PAGE_ID}/children?page_size=50",
            headers=NOTION_HEADERS
        )
        blocks = r.json().get("results", [])
        lines = []
        for block in blocks:
            if block.get("type") == "bulleted_list_item":
                texts = block["bulleted_list_item"].get("rich_text", [])
                text = "".join(t.get("text", {}).get("content", "") for t in texts)
                if any(k in text for k in ["Followers", "Abonnés"]):
                    lines.append(text.strip())
        if not lines:
            return "Aucune stat disponible."
        return "\n".join(lines[:8])
    except Exception as e:
        return f"Erreur stats: {e}"
