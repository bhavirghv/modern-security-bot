"""
cogs/trust.py — Modern Security Bot
/trust  — view any member's trust score with a visual progress bar.
/settrust — manually override a score (Admin only).
"""

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import PURPLE, error_embed


# ── Trust tier helpers ─────────────────────────────────────────────────────────

def get_tier(score: int) -> tuple[str, str]:
    """Return (tier_label, colour_indicator) for a trust score."""
    if score >= 90:
        return "⭐ Trusted",        "🟢"
    elif score >= 70:
        return "✅ Good Standing",  "🟡"
    elif score >= 50:
        return "⚠️ Moderate Risk",  "🟠"
    elif score >= 25:
        return "❗ High Risk",      "🔴"
    else:
        return "🚨 Dangerous",      "⛔"


def score_bar(score: int, width: int = 10) -> str:
    """Return a Unicode block progress bar."""
    filled = round((score / 100) * width)
    return "█" * filled + "░" * (width - filled)


class Trust(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /trust ────────────────────────────────────────────────────────

    @app_commands.command(name="trust", description="View a member's trust score")
    @app_commands.describe(user="Member to check (defaults to yourself)")
    async def trust(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
    ):
        target = user or interaction.user
        score  = await self.db.get_trust_score(target.id, interaction.guild_id)
        tier, indicator = get_tier(score)
        bar = score_bar(score)

        warnings = await self.db.get_warnings(target.id, interaction.guild_id)

        embed = discord.Embed(
            title=f"🛡️ Trust Score — {target.display_name}",
            color=PURPLE,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Score",    value=f"**{score} / 100** {indicator}", inline=True)
        embed.add_field(name="Status",   value=tier,                             inline=True)
        embed.add_field(name="Warnings", value=f"⚠️ {len(warnings)}",           inline=True)
        embed.add_field(
            name="Progress",
            value=f"`{bar}` {score}%",
            inline=False,
        )

        # Show a brief advice line
        if score >= 90:
            advice = "This member has an excellent standing."
        elif score >= 70:
            advice = "This member is in good standing."
        elif score >= 50:
            advice = "This member has some infractions — keep an eye on them."
        elif score >= 25:
            advice = "This member is considered high-risk."
        else:
            advice = "This member is flagged as dangerous."
        embed.add_field(name="Assessment", value=advice, inline=False)
        embed.set_footer(text=f"User ID: {target.id}  •  Modern Security")

        await interaction.response.send_message(embed=embed)

    # ── /settrust ─────────────────────────────────────────────────────

    @app_commands.command(name="settrust", description="Manually set a member's trust score (Admin only)")
    @app_commands.describe(
        user="Target member",
        score="New trust score (0–100)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def settrust(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        score: app_commands.Range[int, 0, 100],
    ):
        await self.db.set_trust_score(user.id, interaction.guild_id, score)
        tier, indicator = get_tier(score)

        embed = discord.Embed(
            title="✅ Trust Score Updated",
            description=(
                f"{user.mention}'s trust score has been manually set to "
                f"**{score}/100** {indicator}\n**Status:** {tier}"
            ),
            color=PURPLE,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Changed by {interaction.user}  •  Modern Security")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @settrust.error
    async def settrust_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=error_embed("❌ Administrator permission is required."),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Trust(bot))
