"""Pattern matching for auto-actions — skip the AI for obvious stuff."""

from __future__ import annotations

import re
from dataclasses import dataclass

NOISE_PATTERNS = [
    (r"noreply@", "archive", "noreply sender"),
    (r"no-reply@", "archive", "noreply sender"),
    (r"notifications?@", "archive", "notification sender"),
    (r"newsletter@", "archive", "newsletter"),
    (r"marketing@", "archive", "marketing"),
    (r"promo(tions)?@", "archive", "promotional"),
    (r"unsubscribe", "archive", "has unsubscribe link"),
    (r"receipt\s+(for|from)", "archive", "receipt"),
    (r"order\s+confirm", "archive", "order confirmation"),
    (r"shipping\s+(confirm|notif|update)", "archive", "shipping notification"),
    (r"delivery\s+(confirm|notif|update)", "archive", "delivery notification"),
    (r"your\s+package", "archive", "package notification"),
    (r"has\s+shipped", "archive", "shipping notification"),
    (r"out\s+for\s+delivery", "archive", "delivery notification"),
    (r"password\s+reset", "flag", "security - password reset"),
    (r"verify\s+your\s+(email|account)", "flag", "security - verification"),
    (r"sign[- ]?in\s+(attempt|from)", "flag", "security - sign in alert"),
    (r"suspicious\s+activity", "flag", "security alert"),
    (r"@linkedin\.com", "archive", "linkedin"),
    (r"@facebookmail\.com", "archive", "facebook"),
    (r"@twitter\.com", "archive", "twitter/x"),
    (r"@github\.com", "archive", "github notification"),
    (r"digest@", "archive", "digest email"),
    (r"weekly\s+update", "archive", "weekly update"),
    (r"daily\s+digest", "archive", "daily digest"),
]

URGENCY_PATTERNS = [
    (r"\bURGENT\b", 0.9, "marked urgent"),
    (r"\bASAP\b", 0.8, "marked asap"),
    (r"\bEOD\b", 0.7, "end of day deadline"),
    (r"\bby\s+(today|tomorrow|monday|tuesday|wednesday|thursday|friday)", 0.7, "has deadline"),
    (r"\bdeadline\b", 0.6, "mentions deadline"),
    (r"\btime[- ]?sensitive\b", 0.8, "time sensitive"),
    (r"\bimmediate(ly)?\b", 0.7, "immediate action"),
    (r"\baction\s+required\b", 0.6, "action required"),
    (r"\bplease\s+respond\b", 0.5, "requests response"),
    (r"\bwaiting\s+(for|on)\s+(your|a)\s+response\b", 0.6, "waiting for response"),
]


@dataclass
class PatternMatch:
    action: str
    reason: str
    confidence: float


def match_noise(sender: str, subject: str, preview: str) -> PatternMatch | None:
    text = f"{sender} {subject} {preview}".lower()

    for pattern, action, reason in NOISE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return PatternMatch(action=action, reason=reason, confidence=0.95)

    return None


def detect_urgency(subject: str, preview: str) -> tuple[float, str]:
    text = f"{subject} {preview}"
    max_score = 0.0
    reasons = []

    for pattern, score, reason in URGENCY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if score > max_score:
                max_score = score
            reasons.append(reason)

    return max_score, ", ".join(reasons) if reasons else ""


def should_skip_triage(sender: str, subject: str, preview: str) -> PatternMatch | None:
    return match_noise(sender, subject, preview)
