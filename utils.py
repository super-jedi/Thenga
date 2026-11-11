import re
import os
from datetime import datetime
from typing import Optional, Any
import discord

ADMIN_USERS = [u.strip().lower() for u in os.getenv("ADMIN_USERS", "superjedi,superjedi.0257,haris_supran,harisupran").split(",") if u.strip()]
ADMIN_IDS = [i.strip() for i in os.getenv("ADMIN_IDS", "1567865230829035530").split(",") if i.strip()]

def is_admin_user(user: Any) -> bool:
    """
    Checks if a Discord user, member, or web session dict has admin/founder status.
    """
    if not user:
        return False
    
    if isinstance(user, dict):
        uname = str(user.get("username", "")).lower()
        uid = str(user.get("id", ""))
    else:
        uname = str(getattr(user, "name", "") or getattr(user, "display_name", "")).lower()
        uid = str(getattr(user, "id", ""))
    
    if any(adm in uname for adm in ADMIN_USERS) or uid in ADMIN_IDS:
        return True
    
    perms = getattr(user, "guild_permissions", None)
    if perms and perms.administrator:
        return True
    return False

def parse_amount(text: str) -> float:
    """
    Parses currency strings like '4.85M', '650k', '1.2B', '$100,000', '50000'.
    """
    clean = text.strip().replace("$", "").replace(",", "")
    match = re.match(r"^([0-9]*\.?[0-9]+)\s*([kKmMbB])?$", clean)
    if not match:
        raise ValueError(f"Invalid amount format: '{text}'. Use numbers, e.g. 500k, 4.85M, 100000.")
    
    val, suffix = match.groups()
    number = float(val)
    if suffix:
        s = suffix.lower()
        if s == "k":
            number *= 1_000
        elif s == "m":
            number *= 1_000_000
        elif s == "b":
            number *= 1_000_000_000
            
    return number

def format_money(amount: float) -> str:
    """
    Formats a number into a readable GTA cash string.
    e.g. 4850000 -> "$4,850,000 ($4.85M)"
    """
    abs_amt = abs(amount)
    if abs_amt >= 1_000_000_000:
        short = f"{amount / 1_000_000_000:.2f}B"
    elif abs_amt >= 1_000_000:
        short = f"{amount / 1_000_000:.2f}M"
    elif abs_amt >= 1_000:
        short = f"{amount / 1_000:.1f}k"
    else:
        short = f"{amount:,.0f}"

    return f"${amount:,.0f} ({short})"

def detect_server(interaction: discord.Interaction, explicit_server: Optional[str] = None) -> str:
    """
    Detects whether the action belongs to 'librarp' or 'grandrp'.
    Inspects explicit selection, channel name, or channel category.
    """
    if explicit_server:
        return explicit_server.lower()

    channel_name = getattr(interaction.channel, "name", "").lower()
    category_name = ""
    if hasattr(interaction.channel, "category") and interaction.channel.category:
        category_name = interaction.channel.category.name.lower()

    combined = f"{channel_name} {category_name}"

    if "grand" in combined or "en2" in combined or "thenga" in combined:
        return "grandrp"
    if "libra" in combined or "fedrix" in combined:
        return "librarp"

    # Default to librarp as per user's current activity
    return "librarp"

def discord_timestamp(dt: datetime, style: str = "R") -> str:
    """
    Returns a Discord dynamic timestamp string.
    Styles: 'R' (relative: in 2 hours), 'F' (full: Wednesday, November 11, 2026 6:00 AM), 't' (short time)
    """
    return f"<t:{int(dt.timestamp())}:{style}>"
