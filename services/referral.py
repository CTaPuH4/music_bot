from typing import Any, Dict, List, Optional

# Referral tiers: starts at 2%, increases by 2% up to 20%
# Required invites follow a geometric progression (1, 2, 4, 8, 16, 32, 64, 128, 256)
REFERRAL_TIERS: List[Dict[str, Any]] = [
    {"level": 1, "min_referrals": 0, "percent": 2, "title": "Новичок 🥉"},
    {"level": 2, "min_referrals": 1, "percent": 4, "title": "Любитель 🥈"},
    {"level": 3, "min_referrals": 2, "percent": 6, "title": "Активист 🥇"},
    {"level": 4, "min_referrals": 4, "percent": 8, "title": "Партнёр 🌟"},
    {"level": 5, "min_referrals": 8, "percent": 10, "title": "Мастер 💎"},
    {"level": 6, "min_referrals": 16, "percent": 12, "title": "Эксперт ⚡"},
    {"level": 7, "min_referrals": 32, "percent": 14, "title": "Амбассадор 🚀"},
    {"level": 8, "min_referrals": 64, "percent": 16, "title": "Босс 👑"},
    {"level": 9, "min_referrals": 128, "percent": 18, "title": "Легенда 🏆"},
    {"level": 10, "min_referrals": 256, "percent": 20, "title": "Олимп 🔥"},
]


def get_referral_tier(referrals_count: int) -> Dict[str, Any]:
    """
    Determines user's current referral tier and info about next tier.
    """
    current_tier = REFERRAL_TIERS[0]
    next_tier: Optional[Dict[str, Any]] = None

    for i, tier in enumerate(REFERRAL_TIERS):
        if referrals_count >= tier["min_referrals"]:
            current_tier = tier
            next_tier = REFERRAL_TIERS[i + 1] if i + 1 < len(REFERRAL_TIERS) else None
        else:
            break

    needed_for_next = (
        (next_tier["min_referrals"] - referrals_count) if next_tier else 0
    )

    return {
        "level": current_tier["level"],
        "title": current_tier["title"],
        "percent": current_tier["percent"],
        "min_referrals": current_tier["min_referrals"],
        "next_tier": next_tier,
        "needed_for_next": needed_for_next,
    }


def calculate_referral_reward(credits_bought: int, percent: int) -> float:
    """
    Calculates exact fractional referral reward earned from a referral purchase.
    e.g. 5 credits * 2% = 0.1 generations.
    """
    return round(credits_bought * (percent / 100.0), 2)


def format_referral_tiers_table(current_level: int) -> str:
    """
    Renders formatted list of tiers highlighting user's active tier.
    """
    lines = []
    for tier in REFERRAL_TIERS:
        mark = "👉 " if tier["level"] == current_level else "• "
        req = f"от {tier['min_referrals']} чел." if tier["min_referrals"] > 0 else "старт"
        lines.append(
            f"{mark}<b>Ур. {tier['level']}: {tier['title']}</b> ({req}) — <b>{tier['percent']}%</b>"
        )
    return "\n".join(lines)
