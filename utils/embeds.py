"""
utils/embeds.py — Reusable embed factory helpers.
All embeds use the Modern Security purple theme (0x7C3AED).
"""

import discord
from datetime import datetime, timezone

PURPLE = 0x7C3AED
RED    = 0xEF4444
GREEN  = 0x22C55E


def base_embed(
    title: str,
    description: str = "",
    color: int = PURPLE
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="Modern Security")
    return embed


def success_embed(description: str, title: str = "✅ Success") -> discord.Embed:
    return base_embed(title, description, PURPLE)


def error_embed(description: str, title: str = "❌ Error") -> discord.Embed:
    return base_embed(title, description, RED)


def mod_action_embed(
    action: str,
    emoji: str,
    user: discord.Member,
    moderator: discord.Member,
    reason: str,
    case_id: int,
    extra_fields: list[tuple[str, str, bool]] | None = None
) -> discord.Embed:
    embed = discord.Embed(
        title=f"{emoji} {action}",
        color=PURPLE,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="User",      value=f"{user.mention} (`{user.id}`)", inline=True)
    embed.add_field(name="Moderator", value=moderator.mention,               inline=True)
    embed.add_field(name="Reason",    value=reason,                          inline=False)
    embed.add_field(name="Case ID",   value=f"#{case_id}",                   inline=True)
    if extra_fields:
        for name, value, inline in extra_fields:
            embed.add_field(name=name, value=value, inline=inline)
    embed.set_footer(text="Modern Security • Moderation")
    return embed
