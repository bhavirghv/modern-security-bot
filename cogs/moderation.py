"""
cogs/moderation.py — Modern Security Bot
Slash-command moderation: warn, warnings, mute, unmute, kick, ban, clear, case.
Every action: creates a case, logs to log channel, updates trust score.
Auto-punishment: 3 warnings → auto-mute | 5 warnings → auto-ban.
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from typing import Optional

from utils.checks import moderator_check
from utils.embeds import mod_action_embed, error_embed, PURPLE


# ── Helpers ────────────────────────────────────────────────────────────────────

ACTION_EMOJI = {
    "WARN":      "⚠️",
    "MUTE":      "🔇",
    "UNMUTE":    "🔊",
    "KICK":      "👢",
    "BAN":       "🔨",
    "AUTO-MUTE": "🤖🔇",
    "AUTO-BAN":  "🤖🔨",
}


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── Internal helpers ──────────────────────────────────────────────

    async def _log(self, guild: discord.Guild, embed: discord.Embed):
        """Send embed to the configured log channel (silently fails)."""
        config = await self.db.get_config(guild.id)
        if not config or not config.get("log_channel_id"):
            return
        channel = guild.get_channel(config["log_channel_id"])
        if channel:
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    async def _dm(self, user: discord.Member, embed: discord.Embed):
        """DM the user (silently fails if DMs are closed)."""
        try:
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _run_auto_punish(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ):
        """Check warning count and apply automatic punishments if enabled."""
        config = await self.db.get_config(interaction.guild_id)
        if not config or not config.get("auto_punish_enabled", 1):
            return

        warn_count = await self.db.count_warnings(user.id, interaction.guild_id)

        if warn_count >= 5:
            try:
                await user.ban(reason=f"Auto-ban: {warn_count} warnings")
                case_id = await self.db.create_case(
                    interaction.guild_id, user.id,
                    self.bot.user.id, "AUTO-BAN",
                    f"Automatic ban — {warn_count} warnings reached"
                )
                await self.db.update_trust_score(user.id, interaction.guild_id, -50)
                embed = discord.Embed(
                    title="🤖🔨 Auto-Ban Triggered",
                    description=(
                        f"{user.mention} was **automatically banned** "
                        f"after reaching **{warn_count} warnings**."
                    ),
                    color=PURPLE,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Case ID", value=f"#{case_id}", inline=True)
                embed.set_footer(text="Modern Security • Auto-Punishment")
                await self._log(interaction.guild, embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        elif warn_count >= 3:
            mute_role_id = config.get("mute_role_id")
            if not mute_role_id:
                return
            mute_role = interaction.guild.get_role(mute_role_id)
            if mute_role and mute_role not in user.roles:
                try:
                    await user.add_roles(
                        mute_role,
                        reason=f"Auto-mute: {warn_count} warnings"
                    )
                    case_id = await self.db.create_case(
                        interaction.guild_id, user.id,
                        self.bot.user.id, "AUTO-MUTE",
                        f"Automatic mute — {warn_count} warnings reached"
                    )
                    await self.db.update_trust_score(user.id, interaction.guild_id, -20)
                    embed = discord.Embed(
                        title="🤖🔇 Auto-Mute Triggered",
                        description=(
                            f"{user.mention} was **automatically muted** "
                            f"after reaching **{warn_count} warnings**."
                        ),
                        color=PURPLE,
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="Case ID", value=f"#{case_id}", inline=True)
                    embed.set_footer(text="Modern Security • Auto-Punishment")
                    await self._log(interaction.guild, embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

    # ── /warn ──────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Issue a warning to a member")
    @app_commands.describe(
        user="Member to warn",
        reason="Reason for the warning"
    )
    @moderator_check()
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided"
    ):
        if user.bot:
            return await interaction.response.send_message(
                embed=error_embed("You cannot warn bots."), ephemeral=True
            )
        if user == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("You cannot warn yourself."), ephemeral=True
            )

        warn_id = await self.db.add_warning(
            user.id, interaction.guild_id, interaction.user.id, reason
        )
        case_id = await self.db.create_case(
            interaction.guild_id, user.id,
            interaction.user.id, "WARN", reason
        )
        await self.db.update_trust_score(user.id, interaction.guild_id, -10)
        warn_count = await self.db.count_warnings(user.id, interaction.guild_id)

        embed = mod_action_embed(
            "Warning Issued", "⚠️",
            user, interaction.user, reason, case_id,
            extra_fields=[
                ("Total Warnings", str(warn_count), True),
                ("Warning ID",     f"#{warn_id}",   True),
            ]
        )
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

        dm_embed = discord.Embed(
            title=f"⚠️ You received a warning in **{interaction.guild.name}**",
            description=f"**Reason:** {reason}\n**Total Warnings:** {warn_count}",
            color=PURPLE
        )
        await self._dm(user, dm_embed)
        await self._run_auto_punish(interaction, user)

    # ── /warnings ─────────────────────────────────────────────────────

    @app_commands.command(name="warnings", description="View a member's warning history")
    @app_commands.describe(user="Member to check")
    async def warnings(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ):
        records = await self.db.get_warnings(user.id, interaction.guild_id)

        embed = discord.Embed(
            title=f"⚠️ Warnings — {user.display_name}",
            color=PURPLE,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=user.display_avatar.url)

        if not records:
            embed.description = "✅ This member has no warnings."
        else:
            embed.description = f"**Total Warnings:** {len(records)}"
            for w in records[:10]:
                date = w["timestamp"][:10]
                embed.add_field(
                    name=f"Warning #{w['id']}  ·  {date}",
                    value=(
                        f"**Reason:** {w['reason']}\n"
                        f"**Moderator:** <@{w['moderator_id']}>"
                    ),
                    inline=False
                )
            if len(records) > 10:
                embed.set_footer(text=f"Showing 10 of {len(records)} warnings")

        await interaction.response.send_message(embed=embed)

    # ── /mute ──────────────────────────────────────────────────────────

    @app_commands.command(name="mute", description="Mute a member using the configured mute role")
    @app_commands.describe(user="Member to mute", reason="Reason for mute")
    @moderator_check()
    async def mute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided"
    ):
        config = await self.db.get_config(interaction.guild_id)
        if not config or not config.get("mute_role_id"):
            return await interaction.response.send_message(
                embed=error_embed(
                    "Mute role not configured. Use `/setmuterole` or `/config` first."
                ), ephemeral=True
            )

        mute_role = interaction.guild.get_role(config["mute_role_id"])
        if not mute_role:
            return await interaction.response.send_message(
                embed=error_embed("Mute role not found. Please reconfigure."),
                ephemeral=True
            )
        if mute_role in user.roles:
            return await interaction.response.send_message(
                embed=error_embed("This member is already muted."), ephemeral=True
            )

        try:
            await user.add_roles(mute_role, reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("I don't have permission to mute this member."),
                ephemeral=True
            )

        case_id = await self.db.create_case(
            interaction.guild_id, user.id, interaction.user.id, "MUTE", reason
        )
        await self.db.update_trust_score(user.id, interaction.guild_id, -15)

        embed = mod_action_embed("Member Muted", "🔇", user, interaction.user, reason, case_id)
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)
        await self._dm(user, discord.Embed(
            title=f"🔇 You were muted in **{interaction.guild.name}**",
            description=f"**Reason:** {reason}", color=PURPLE
        ))

    # ── /unmute ────────────────────────────────────────────────────────

    @app_commands.command(name="unmute", description="Unmute a member")
    @app_commands.describe(user="Member to unmute", reason="Reason for unmute")
    @moderator_check()
    async def unmute(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided"
    ):
        config = await self.db.get_config(interaction.guild_id)
        if not config or not config.get("mute_role_id"):
            return await interaction.response.send_message(
                embed=error_embed("Mute role not configured."), ephemeral=True
            )

        mute_role = interaction.guild.get_role(config["mute_role_id"])
        if not mute_role or mute_role not in user.roles:
            return await interaction.response.send_message(
                embed=error_embed("This member is not currently muted."),
                ephemeral=True
            )

        try:
            await user.remove_roles(mute_role, reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("I don't have permission to unmute this member."),
                ephemeral=True
            )

        case_id = await self.db.create_case(
            interaction.guild_id, user.id, interaction.user.id, "UNMUTE", reason
        )
        await self.db.update_trust_score(user.id, interaction.guild_id, +5)

        embed = mod_action_embed("Member Unmuted", "🔊", user, interaction.user, reason, case_id)
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    # ── /kick ──────────────────────────────────────────────────────────

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(user="Member to kick", reason="Reason for kick")
    @moderator_check()
    async def kick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided"
    ):
        if user == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("You cannot kick yourself."), ephemeral=True
            )
        if user.top_role >= interaction.user.top_role and \
           not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=error_embed("You cannot kick someone with an equal or higher role."),
                ephemeral=True
            )

        await self._dm(user, discord.Embed(
            title=f"👢 You were kicked from **{interaction.guild.name}**",
            description=f"**Reason:** {reason}", color=PURPLE
        ))

        try:
            await user.kick(reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("I don't have permission to kick this member."),
                ephemeral=True
            )

        case_id = await self.db.create_case(
            interaction.guild_id, user.id, interaction.user.id, "KICK", reason
        )
        await self.db.update_trust_score(user.id, interaction.guild_id, -20)

        embed = mod_action_embed("Member Kicked", "👢", user, interaction.user, reason, case_id)
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    # ── /ban ───────────────────────────────────────────────────────────

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        user="Member to ban",
        reason="Reason for ban",
        delete_days="Days of message history to delete (0–7)"
    )
    @moderator_check()
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
        delete_days: app_commands.Range[int, 0, 7] = 0
    ):
        if user == interaction.user:
            return await interaction.response.send_message(
                embed=error_embed("You cannot ban yourself."), ephemeral=True
            )
        if user.top_role >= interaction.user.top_role and \
           not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                embed=error_embed("You cannot ban someone with an equal or higher role."),
                ephemeral=True
            )

        await self._dm(user, discord.Embed(
            title=f"🔨 You were banned from **{interaction.guild.name}**",
            description=f"**Reason:** {reason}", color=PURPLE
        ))

        try:
            await user.ban(reason=reason, delete_message_days=delete_days)
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=error_embed("I don't have permission to ban this member."),
                ephemeral=True
            )

        case_id = await self.db.create_case(
            interaction.guild_id, user.id, interaction.user.id, "BAN", reason
        )
        await self.db.update_trust_score(user.id, interaction.guild_id, -50)

        embed = mod_action_embed("Member Banned", "🔨", user, interaction.user, reason, case_id)
        await interaction.response.send_message(embed=embed)
        await self._log(interaction.guild, embed)

    # ── /clear ─────────────────────────────────────────────────────────

    @app_commands.command(name="clear", description="Bulk-delete messages in this channel")
    @app_commands.describe(amount="Number of messages to delete (1–100)")
    @moderator_check()
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100]
    ):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)

        embed = discord.Embed(
            title="🗑️ Messages Cleared",
            description=f"Deleted **{len(deleted)}** message(s).",
            color=PURPLE,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="Channel",   value=interaction.channel.mention, inline=True)
        embed.add_field(name="Moderator", value=interaction.user.mention,    inline=True)
        embed.set_footer(text="Modern Security • Moderation")

        await interaction.followup.send(embed=embed, ephemeral=True)
        await self._log(interaction.guild, embed)

    # ── /case ──────────────────────────────────────────────────────────

    @app_commands.command(name="case", description="Look up a moderation case by ID")
    @app_commands.describe(case_id="The case number to retrieve")
    async def case_lookup(
        self,
        interaction: discord.Interaction,
        case_id: int
    ):
        record = await self.db.get_case(case_id)
        if not record:
            return await interaction.response.send_message(
                embed=error_embed(f"Case **#{case_id}** was not found."), ephemeral=True
            )
        if record["guild_id"] != interaction.guild_id:
            return await interaction.response.send_message(
                embed=error_embed("That case does not belong to this server."),
                ephemeral=True
            )

        emoji = ACTION_EMOJI.get(record["action"], "📋")
        timestamp_fmt = record["timestamp"][:19].replace("T", " ") + " UTC"

        embed = discord.Embed(
            title=f"{emoji} Case #{case_id} — {record['action']}",
            color=PURPLE,
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="User",      value=f"<@{record['user_id']}> (`{record['user_id']}`)", inline=True)
        embed.add_field(name="Moderator", value=f"<@{record['moderator_id']}>",                    inline=True)
        embed.add_field(name="Reason",    value=record["reason"],                                  inline=False)
        embed.add_field(name="Issued At", value=timestamp_fmt,                                     inline=False)
        embed.set_footer(text="Modern Security • Case System")

        await interaction.response.send_message(embed=embed)

    # ── Error handler ─────────────────────────────────────────────────

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CheckFailure):
            msg = str(error) or "❌ You don't have permission to use this command."
        else:
            msg = "❌ An unexpected error occurred. Please try again."
        try:
            await interaction.response.send_message(
                embed=error_embed(msg), ephemeral=True
            )
        except discord.InteractionResponded:
            await interaction.followup.send(
                embed=error_embed(msg), ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
