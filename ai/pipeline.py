"""Batch each post through Gemini: score the lead + draft a personalised reply."""
import json
from pathlib import Path

import yaml

from ai.client import generate


def analyse_batch(items: list[dict], context: str = "") -> list[dict]:
    """Enrich items with ai_score, ai_summary, ai_draft. Batches to save quota."""
    config = yaml.safe_load((Path(__file__).parent.parent / "config.yaml").read_text())
    ai_cfg = config.get("ai", {})
    model = ai_cfg.get("model", "gemini-2.5-flash")
    rate_limit = ai_cfg.get("rate_limit_seconds", 7.0)
    batch_size = ai_cfg.get("batch_size", 5)

    batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
    print(f"  [AI] {len(items)} posts -> {len(batches)} API calls")

    enriched: list[dict] = []
    for idx, batch in enumerate(batches):
        print(f"  [AI] batch {idx + 1}/{len(batches)}")
        prompt = _build_prompt(batch, context)
        result = generate(prompt, model=model, rate_limit=rate_limit)
        analyses = result.get("analyses", [])

        for j, item in enumerate(batch):
            ai = analyses[j] if j < len(analyses) else {}
            if ai:
                score = max(0, min(100, int(ai.get("score", 0))))
                enriched.append({
                    **item,
                    "ai_score": score,
                    "ai_summary": ai.get("summary", ""),
                    "ai_draft": ai.get("draft_reply", ""),
                })
            else:
                # AI failed for this item — HOLD it (score 0 so it fails the gate).
                # Better to miss one during an API hiccup than to flood junk that was
                # never actually vetted. These are logged, not sent.
                enriched.append({**item, "ai_score": 0, "ai_summary": "(AI failed — held)", "ai_draft": ""})

    return enriched


def _build_prompt(batch: list[dict], context: str) -> str:
    posts_text = "\n\n".join(
        f"Post {i + 1}:\n"
        f"  Subreddit: {p.get('source')}\n"
        f"  Title: {p.get('name')}\n"
        f"  Body: {p.get('body', '')[:800]}"
        for i, p in enumerate(batch)
    )

    return f"""You help a freelance web/Shopify developer find real client leads on Reddit
and draft a reply to each. For each post, decide if it's someone who genuinely wants a
website/store/landing page BUILT (a buyer), not another developer advertising.

# The developer (who you're writing replies for)
{context[:1200] if context else "A freelance web & Shopify developer."}

# Posts to evaluate
{posts_text}

# Scoring guide — BE STRICT. Most posts are NOT leads. Default to a low score.
- 85-100: explicitly wants a website/store/automation/CRM BUILT for them, now, with intent/budget
- 70-84: clearly a business owner describing a problem we build solutions for, open to hiring
- 40-69: loosely related but no clear buying intent (general discussion, vague)
- below 40: NOT a lead — score these LOW:
  * someone asking for ADVICE / how-to / opinions (not hiring)
  * someone ANNOUNCING or promoting their own product/app ("I built", "I made", "check out my")
  * another developer/agency/freelancer offering services ("[offer]", "available to work")
  * AutoModerator / weekly threads / "Talent Tuesday" / generic megathreads
  * tiny tech-support questions a plugin setting fixes (not a build project)

# Draft reply rules
- Friendly, human, max 4 sentences. NOT a copy-paste sales pitch.
- Open with ONE specific, useful observation about THEIR post.
- One line on why the developer is a fit + their portfolio link (from the context).
- End with a soft question to start a conversation. Never desperate or spammy.

# Output
Return ONLY this JSON, one entry per post IN ORDER:
{{"analyses": [{{"score": <0-100>, "summary": "<1 sentence: who they are + what they want>", "draft_reply": "<the reply, or empty string if score < 55>"}}]}}"""
