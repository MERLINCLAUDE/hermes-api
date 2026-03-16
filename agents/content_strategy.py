import anthropic

client = anthropic.Anthropic()

TASKS = {
    "strategy": {
        "label": "Social Media Strategy Planner",
        "prompt": """Act as an elite social media strategist. Based on the following details about this creator, build a clear strategy for growth. Include positioning, content angles, and the best opportunities to stand out.

Creator profile:
- Name: Lucas Zulfikarpasic (alias Merlin)
- Business: 344 Productions (filmmaker) + MZSpell344 (music producer)
- Location: Montréal
- Platforms: TikTok @enzo.babine, Instagram @merlinzsp, YouTube @MZSpell344

Additional context: {context}

Respond in French. Be specific and actionable."""
    },
    "pillars": {
        "label": "Content Pillar Generator",
        "prompt": """Build 5 strong content pillars for this creator's brand based on their niche, knowledge, and target audience.
For each pillar, give multiple post ideas that either educate, entertain, or inspire.

Creator: Lucas Zulfikarpasic — filmmaker (344 Productions) + music producer (MZSpell344), Montréal.
Additional context: {context}

Respond in French. Be specific."""
    },
    "planner": {
        "label": "30-Day Content Planner",
        "prompt": """Create a 30-day content plan for this creator. Include daily post ideas, the best format for each one (reel, carousel, thread, etc.), and the purpose of each post (reach, engagement, or leads).

Creator: Lucas Zulfikarpasic — filmmaker + music producer, Montréal. Platforms: TikTok, Instagram, YouTube.
Additional context: {context}

Respond in French. Format as a table or numbered list."""
    },
    "post": {
        "label": "High-Engagement Post Writer",
        "prompt": """Write a high-engagement social media post about this topic: {context}

Rules:
- Start with a strong hook that grabs attention
- Keep the message simple and valuable
- Finish with a call-to-action that drives comments or shares
- Tone: authentic, direct, not salesy

Creator voice: Lucas Zulfikarpasic — filmmaker & music producer, Montréal.
Respond in French."""
    },
    "script": {
        "label": "Short-Form Video Script",
        "prompt": """Write a short-form video script for Instagram Reels / TikTok / YouTube Shorts about this topic: {context}

Structure:
- Hook (0-3s): curiosity-driven opening line
- Value (3-45s): fast, punchy delivery
- CTA (last 5s): strong call-to-action

Creator: Lucas Zulfikarpasic — filmmaker & music producer, Montréal.
Respond in French. Format clearly with timestamps."""
    },
    "engagement": {
        "label": "Engagement Growth Strategist",
        "prompt": """Create a strategy to increase engagement on social media for this creator.
Suggest better conversation starters, comment hooks, storytelling ideas, and community-building tactics.

Creator: Lucas Zulfikarpasic — filmmaker (344 Productions) + music producer (MZSpell344), Montréal.
Additional context: {context}

Respond in French. Be specific and actionable."""
    },
    "analyzer": {
        "label": "Content Performance Analyzer",
        "prompt": """Review this creator's current social media situation and identify what is performing best, what is underperforming, and what specific changes to make to improve reach, engagement, and conversions.

Creator: Lucas Zulfikarpasic — filmmaker + music producer, Montréal.
Platforms: TikTok @enzo.babine, Instagram @merlinzsp @344prod, YouTube @MZSpell344.
Additional context: {context}

Respond in French. Be direct and actionable."""
    }
}


def run_content_strategy(task: str, context: str = "") -> str:
    if task not in TASKS:
        return f"❌ Tâche inconnue. Disponibles : {', '.join(TASKS.keys())}"
    task_info = TASKS[task]
    prompt = task_info["prompt"].format(context=context or "Aucun contexte supplémentaire.")
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return f"❌ Erreur content_strategy: {str(e)[:200]}"
