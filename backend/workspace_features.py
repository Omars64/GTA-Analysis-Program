"""Private, opt-in profile data and deterministic weekly planning helpers."""
from __future__ import annotations

import re
import time

from storage import store

DEFAULT = {
    "garage": [],
    "wishlist": [],
    "businesses": [],
    "platform": "PC",
    "play_style": "Solo",
    "available_hours": 4,
    "checklist": [],
    "crew": {"name": "", "date": "", "notes": "", "discord_url": ""},
    "notifications": {"email_enabled": False, "email_recipients": [], "discord_enabled": False, "discord_webhook": ""},
}


def get_workspace():
    saved = store.get("workspace", "private") or {}
    return {**DEFAULT, **saved, "crew": {**DEFAULT["crew"], **(saved.get("crew") or {})}, "notifications": {**DEFAULT["notifications"], **(saved.get("notifications") or {})}}


def _clean_list(values, limit=100):
    if not isinstance(values, list):
        raise ValueError("This field must be a list.")
    result = []
    for value in values[:limit]:
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            continue
        clean = re.sub(r"\s+", " ", value.strip())
        if clean not in result:
            result.append(clean)
    return result


def save_workspace(payload):
    if not isinstance(payload, dict):
        raise ValueError("Workspace data must be an object.")
    current = get_workspace()
    clean = {**current}
    for key in ("garage", "wishlist", "businesses", "checklist"):
        if key in payload:
            clean[key] = _clean_list(payload[key])
    if "platform" in payload:
        if payload["platform"] not in {"PC", "PlayStation", "Xbox"}:
            raise ValueError("Choose PC, PlayStation or Xbox.")
        clean["platform"] = payload["platform"]
    if "play_style" in payload:
        if payload["play_style"] not in {"Solo", "Crew"}:
            raise ValueError("Choose Solo or Crew play style.")
        clean["play_style"] = payload["play_style"]
    if "available_hours" in payload:
        if type(payload["available_hours"]) not in {int, float} or not 1 <= payload["available_hours"] <= 24:
            raise ValueError("Available hours must be between 1 and 24.")
        clean["available_hours"] = payload["available_hours"]
    for section in ("crew", "notifications"):
        if section in payload:
            if not isinstance(payload[section], dict):
                raise ValueError(f"{section} must be an object.")
            clean[section] = {**current[section], **payload[section]}
    notifications = clean["notifications"]
    recipients = notifications.get("email_recipients", [])
    if isinstance(recipients, str):
        recipients = [item.strip() for item in recipients.split(",") if item.strip()]
    notifications["email_recipients"] = _clean_list(recipients, 10)
    for addr in notifications["email_recipients"]:
        if "@" not in addr or "\n" in addr or "\r" in addr:
            raise ValueError("Enter valid notification email recipients.")
    webhook = notifications.get("discord_webhook", "") or ""
    if not webhook and current["notifications"].get("discord_webhook"):
        webhook = current["notifications"]["discord_webhook"]
    if not isinstance(webhook, str) or (webhook and not re.match(r"^https://(?:discord(?:app)?\.com)/api/webhooks/", webhook)):
        raise ValueError("Discord webhook must be a discord.com webhook URL.")
    notifications["discord_webhook"] = webhook
    # Webhook secrets are never returned by the API, but are stored only when
    # the user explicitly opts in. This private app is not a public account system.
    return store.put("workspace", "private", clean)


def weekly_plan(workspace, snapshot=None):
    sections = (snapshot or {}).get("sections", {}) if snapshot else {}
    discounts = sections.get("Discounts", [])
    bonuses = sections.get("Bonuses", [])
    tasks = []
    if discounts:
        tasks.append({"title": "Use this week's discounts", "details": f"Review {len(discounts)} discounted item(s) before the weekly reset.", "source": "Latest saved scan"})
        wishlist_hits = [row.get("item", "") for row in discounts if any(token and token.lower() in (row.get("item", "") or "").lower() for token in workspace.get("wishlist", []))]
        if wishlist_hits:
            tasks.append({"title": "Wishlist discount alert", "details": ", ".join(wishlist_hits[:4]), "source": "Latest saved scan"})
    if bonuses:
        tasks.append({"title": "Run the highest-signal bonus activity", "details": bonuses[0].get("details") or bonuses[0].get("item", "Bonus activity"), "source": "Latest saved scan"})
    if workspace.get("businesses"):
        tasks.append({"title": "Collect and resupply businesses", "details": ", ".join(workspace["businesses"][:4]), "source": "Your profile"})
    if workspace.get("wishlist"):
        tasks.append({"title": "Watch your wishlist", "details": ", ".join(workspace["wishlist"][:3]), "source": "Your wishlist"})
    if not tasks:
        tasks.append({"title": "Run a fresh weekly scan", "details": "Fetch the current GTA Online week to build a grounded plan.", "source": "GTA Intelligence"})
    tasks = tasks[:max(2, min(6, int(workspace.get("available_hours", 4))))]
    return {"tasks": tasks, "hours": workspace.get("available_hours", 4), "play_style": workspace.get("play_style", "Solo"), "note": "Suggestions are based on your saved profile and the latest report; no earnings are estimated without sourced values."}
