"""
cogs/reports.py — Modern Security Bot
/report  — opens a 🚨 Report User button that spawns a Modal.
/reports — mod-only view of recent reports in this server.
Every report is stored in the DB and forwarded to the log channel.
"""

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import PURPLE, error_embed


# ──────────────────────────────────────────────────────────────────────────────
# Report Modal
# ──────────────────────────────────────────────────────────────────────────────

class ReportModal(discord.ui.Modal, title="🚨 Report a User"):
    reason = discord.ui.TextInput(
        label="Reason for Report",
        style=discord.TextStyle.long,
        placeholder="Describe why you are reporting this user in detail…",
        min_length=15,
        max_length=500,
        required=True,
    )

    def __init__(self, target: discord.Member, db):
        super().__init__()
        self.target = target
        self.db = db

    async def on_submit(self, interaction: discord.Interaction):
        report_id = await self.db.add_report(
            interaction.user.id,
            self.target.id,
            interaction.guild_id,
            self.reason.value,
        )
        await self.db.update_trust_score(self.target.id, interaction.guild_id, -5)

        # ── Confirm to reporter ────────────────────────────────────────
        confirm_embed = discord.Embed(
            title="✅ Report Submitted",
            description=(
                f"Your report against {self.target.mention} has been submitted "
                f"and will be reviewed by the moderation team."
            ),
            color=PURPLE,
            timestamp=datetime.now(timezone.utc),
        )
        confirm_embed.add_field(name="Report ID", value=f"#{report_id}", inline=True)
        confirm_embed.add_field(name="Status",    value="🔍 Under Review",  inline=True)
        confirm_embed.set_footer(text="False reports may result in punishment • Modern Security")
        await interaction.response.send_message(embed=confirm_embed, ephemeral=True)

        # ── Forward to log channel ─────────────────────────────────────
        config = await self.db.get_config(interaction.guild_id)
        if config and config.get("log_channel_id"):
            log_channel = interaction.guild.get_channel(config["log_channel_id"])
            if log_channel:
                log_embed = discord.Embed(
                    title="🚨 New User Report",
                    color=0xEF4444,
                    timestamp=datetime.now(timezone.utc),
                )
                log_embed.set_thumbnail(url=self.target.display_avatar.url)
                log_embed.add_field(
                    name="Reporter",
                    value=f"{interaction.user.mention} (`{interaction.user.id}`)",
                    inline=True,
                )
                log_embed.add_field(
                    name="Target",
                    value=f"{self.target.mention} (`{self.target.id}`)",
                    inline=True,
                )
                log_embed.add_field(name="Reason",    value=self.reason.value, inline=False)
                log_embed.add_field(name="Report ID", value=f"#{report_id}",   inline=True)
                log_embed.set_footer(text="Modern Security • Report System")
                try:
                    await log_channel.send(embed=log_embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            embed=error_embed("Something went wrong. Please try again."),
            ephemeral=True,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Report Button View
# ──────────────────────────────────────────────────────────────────────────────

class ReportView(discord.ui.View):
    """Persistent (timeout=None) view that holds the 🚨 Report button."""

    def __init__(self, target: discord.Member, db):
        super().__init__(timeout=None)
        self.target = target
        self.db = db

    @discord.ui.button(
        label="🚨 Report User",
        style=discord.ButtonStyle.danger,
        custom_id="modern_security:report_button",
    )
    async def report_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if interaction.user == self.target:
            return await interaction.response.send_message(
                embed=error_embed("You cannot report yourself."), ephemeral=True
            )
        if self.target.bot:
            return await interaction.response.send_message(
                embed=error_embed("You cannot report bots."), ephemeral=True
            )
        await interaction.response.send_modal(ReportModal(self.target, self.db))


# ──────────────────────────────────────────────────────────────────────────────
# Reports Cog
# ──────────────────────────────────────────────────────────────────────────────

class Reports(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /report ───────────────────────────────────────────────────────

    @app_commands.command(name="report", description="Report a member to the moderation team")
    @app_commands.describe(user="The member you want to report")
    async def report(self, interaction: discord.Interaction, user: discord.Member):
        if user == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("You cannot report yourself."), ephemeral=True
            )
        if user.bot:
            return await interaction.response.send_message(
                embed=error_embed("You cannot report bots."), ephemeral=True
            )

        embed = discord.Embed(
            title=f"🚨 Report — {user.display_name}",
            description=(
                f"Click the button below to file a report against {user.mention}.\n"
                "Your report will be reviewed by the moderation team."
            ),
            color=PURPLE,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text="False reports may result in a warning • Modern Security")

        view = ReportView(user, self.db)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /reports ──────────────────────────────────────────────────────

    @app_commands.command(name="reports", description="View recent user reports for this server (Mods only)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reports(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        all_reports = await self.db.get_all_reports()
        guild_reports = [r for r in all_reports if r.get("guild_id") == interaction.guild_id]

        embed = discord.Embed(
            title="📋 User Reports",
            color=PURPLE,
            timestamp=datetime.now(timezone.utc),
        )

        if not guild_reports:
            embed.description = "✅ No reports found for this server."
        else:
            embed.description = f"**Total Reports:** {len(guild_reports)}"
            for r in guild_reports[:10]:
                date = r["timestamp"][:10]
                embed.add_field(
                    name=f"Report #{r['id']}  ·  {date}",
                    value=(
                        f"**Reporter:** <@{r['reporter_id']}>\n"
                        f"**Target:** <@{r['target_id']}>\n"
                        f"**Reason:** {r['reason'][:120]}"
                    ),
                    inline=False,
                )
            if len(guild_reports) > 10:
                embed.set_footer(text=f"Showing 10 of {len(guild_reports)} reports  •  Modern Security")
            else:
                embed.set_footer(text="Modern Security • Report System")

        await interaction.followup.send(embed=embed, ephemeral=True)

    @reports.error
    async def reports_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=error_embed("❌ You need **Manage Server** permission to view reports."),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Reports(bot))
