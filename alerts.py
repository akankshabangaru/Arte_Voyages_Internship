"""Template-based alert text (no LLM) + Gmail sender."""
import os
from datetime import datetime

EMOJI = {"Green": "🟢", "Watch": "🟡", "Act": "🔴"}


def render_alert(trip_id: str, leg, tier: str, prev_tier: str, score: float, sigs: list[dict], monitored_at: datetime) -> str:
    top = max(sigs, key=lambda s: s["risk"]) if sigs else None
    title = top["title"][:80] if top else "no active signal"
    kind = top["kind"] if top else ""
    emoji = EMOJI.get(tier, "⚪")
    where = f"{kind} {title}" if kind else title
    link = top["url"] if top and top["url"] else ""
    action_map = {
        "Act": "Review now, consider buffer day / reroute, contact partners.",
        "Watch": "Monitor closely.",
        "Green": "No action.",
    }
    action = action_map.get(tier, "Monitor closely.")
    when = monitored_at.strftime("%d %b %Y %H:%M UTC")
    kind_word = "ACT" if tier == "Act" else tier.upper()
    return (
        f"{emoji} {kind_word} — {where} — Severity {score:.2f}\n"
        f"Trip: {trip_id} ({leg.country}, {leg.place}, {leg.start:%d %b}–{leg.end:%d %b}) | Leg risk: {score:.2f} -> {tier} (was {prev_tier})\n"
        f"Driver: {title}" + (f" ({kind})" if kind else "") + "\n"
        + (f"Source: {link}\n" if link else "")
        + f"Monitored: {when}\n"
        f"Action: {action}"
    )


def send_email(subject: str, body: str) -> None:
    user = os.environ.get("GMAIL_USER", "")
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "")
    to = os.environ.get("ALERT_TO", "")
    if not user or not pwd or not to:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD / ALERT_TO not set")
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
        s.starttls()
        s.login(user, pwd)
        s.send_message(msg)


def notify(alert: dict) -> None:
    text = alert.get("text", "")
    tier = alert.get("tier", "Watch")
    place = ""
    # Best effort: extract place from leg_id-less alert; monitor passes place in text already
    first = text.splitlines()[0] if text else ""
    subject = f"[{tier.upper()}] {first[:90]}"
    send_email(subject, text)
