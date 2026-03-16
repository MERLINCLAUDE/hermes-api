import requests
import os
from datetime import datetime, timedelta
import imaplib
import email
from email.header import decode_header
import json

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
NOTION_PAGE_ID = "322563ef9d0281479c6aef4984219ca7"
STATS_PAGE_ID = "324563ef9d0281c89ec9dcb673f48f85"
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

SECTION_COLORS = {
    "📌": "gray_background",
    "🌅": "orange_background",
    "💼": "blue_background",
    "🎵": "purple_background",
    "🏃": "green_background",
}


def rt(text):
    return [{"type": "text", "text": {"content": str(text)}}]


def fetch_social_stats():
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
        return lines[:4]
    except:
        return []


def fetch_emails():
    if not GMAIL_APP_PASSWORD:
        return []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        mail.select("inbox")
        since_date = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
        _, message_ids = mail.search(None, f'(SINCE "{since_date}")')
        emails = []
        skip = ["noreply@linkedin", "noreply@github", "promotions", "newsletter",
                "unsubscribe", "deliveroo", "uber", "doordash", "notification"]
        for msg_id in message_ids[0].split()[-20:]:
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            sender = msg.get("From", "")
            if any(k in sender.lower() for k in skip):
                continue
            subject = decode_header(msg["Subject"] or "")[0]
            subject = subject[0].decode(subject[1] or "utf-8") if isinstance(subject[0], bytes) else subject[0]
            emails.append({"from": sender, "subject": subject})
        mail.logout()
        return emails[:10]
    except:
        return []


def run_daily_plan(client, imessage_context=""):
    """Génère le plan du jour et le publie sur Notion. Retourne l'URL de la page."""
    emails = fetch_emails()
    email_context = ""
    if emails:
        emails_text = "\n".join([f"- {e['from']}: {e['subject']}" for e in emails])
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=300,
            messages=[{"role": "user", "content": f"Emails de Lucas (filmmaker Montréal):\n{emails_text}\n\nUniquement ceux nécessitant une action réelle (pas delivery, promo). Une ligne par email : '- [emoji] expéditeur : action'. Si aucun, réponds 'aucun'."}]
        )
        result = resp.content[0].text.strip()
        if result.lower() != "aucun":
            email_context = result

    context_block = ""
    if email_context:
        context_block += f"\nEmails avec action :\n{email_context}"
    if imessage_context:
        context_block += f"\niMessages d'hier :\n{imessage_context}"

    PROMPT = f"""Tu es Archimède, l'assistant de Lucas Zulfikarpasic (filmmaker/producteur, 344 Productions / MZSpell344, Montréal).

Règles :
- Rappels UNIQUEMENT basés sur contexte réel. Sinon : "Rien d'urgent aujourd'hui."
- Ne mentionne jamais Make/Integromat.
{context_block}

Génère le plan en suivant EXACTEMENT ce format :

CALLOUT: [phrase motivante courte]

## 📌 Rappels du jour
- [rappel réel ou "Rien d'urgent aujourd'hui."]

## 🌅 Tournage & Montage — 8h à 12h
- [emoji] [horaire] : [tâche]
- [emoji] [horaire] : [tâche]
- [emoji] [horaire] : [tâche]

## 💼 Admin 344 Productions — 12h à 14h
- [emoji] [horaire] : [tâche]
- [emoji] [horaire] : [tâche]

## 🎵 MZSpell344 — 14h à 16h
- [emoji] [horaire] : [tâche]
- [emoji] [horaire] : [tâche]

## 🏃 Temps libre — 16h à 18h
- [emoji] Choix libre

Sans ** ou *. Concis et actionnable."""

    message = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=1024,
        messages=[{"role": "user", "content": PROMPT}]
    )
    plan_text = message.content[0].text
    today = datetime.now().strftime("%d/%m/%Y")

    children = [{
        "object": "block", "type": "callout",
        "callout": {"rich_text": rt(f"Généré via Archimède · {today}"), "icon": {"type": "emoji", "emoji": "⚡"}, "color": "gray_background"}
    }, {"object": "block", "type": "divider", "divider": {}}]

    for line in plan_text.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("CALLOUT:"):
            children.append({"object": "block", "type": "callout", "callout": {"rich_text": rt(s[8:].strip()), "icon": {"type": "emoji", "emoji": "💡"}, "color": "yellow_background"}})
        elif s.startswith("## "):
            title = s[3:]
            color = next((v for k, v in SECTION_COLORS.items() if title.startswith(k)), "default")
            children.append({"object": "block", "type": "divider", "divider": {}})
            children.append({"object": "block", "type": "heading_2", "heading_2": {"rich_text": rt(title), "color": color}})
        elif s.startswith("- "):
            children.append({"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": rt(s[2:])}})
        else:
            children.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": rt(s)}})

    stats = fetch_social_stats()
    if stats:
        children.append({"object": "block", "type": "divider", "divider": {}})
        children.append({"object": "block", "type": "callout", "callout": {"rich_text": rt("  ·  ".join(stats)), "icon": {"type": "emoji", "emoji": "📈"}, "color": "blue_background"}})

    payload = {
        "parent": {"page_id": NOTION_PAGE_ID},
        "icon": {"type": "emoji", "emoji": "🎬"},
        "properties": {"title": [{"text": {"content": f"📅 Plan du jour — {today}"}}]},
        "children": children
    }
    r = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=payload)
    if r.status_code == 200:
        return f"✅ Plan publié sur Notion : {r.json().get('url')}"
    return f"❌ Erreur Notion : {r.status_code}"
