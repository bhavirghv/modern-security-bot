"""
cogs/logging.py — Modern Security Bot
Logs: message delete, message edit, member join, member leave.
All output is sent as rich embeds to the configured log channel.
"""

from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.embeds import PURPLE

GREEN = 0x22C55E
RED   = 0xEF4444


class Logging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    async def _get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        config = await self.db.get_config(guild.id)
        if config and config.get("log_channel_id"):
            return guild.get_channel(config["log_channel_id"])
        return None

    async def _send(self, guild: discord.Guild, embed: discord.Embed):
        channel = await self._get_log_channel(guild)
        if channel:
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

    # ── Message Delete ────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        embed = discord.Embed(
            title="🗑️ Message Deleted",
            color=RED,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Author",
            value=f"{message.author.mention} (`{message.author.id}`)",
            inline=True,
        )
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(
            name="Content",
            value=message.content[:1024] if message.content else "*No text content*",
            inline=False,
        )
        if message.attachments:
            embed.add_field(
                name="Attachments",
                value="\n".join(a.filename for a in message.attachments),
                inline=False,
            )
        embed.set_footer(text=f"Message ID: {message.id}")
        await self._send(message.guild, embed)

    # ── Message Edit ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return  # embed-only update, skip

        embed = discord.Embed(
            title="✏️ Message Edited",
            color=PURPLE,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Author",
            value=f"{before.author.mention} (`{before.author.id}`)",
            inline=True,
        )
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(
            name="Before",
            value=before.content[:512] if before.content else "*Empty*",
            inline=False,
        )
        embed.add_field(
            name="After",
            value=after.content[:512] if after.content else "*Empty*",
            inline=False,
        )
        embed.add_field(
            name="Jump to Message",
            value=f"[Click here]({after.jump_url})",
            inline=False,
        )
        embed.set_footer(text=f"Message ID: {before.id}")
        await self._send(before.guild, embed)

    # ── Member Join ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="📥 Member Joined",
            description=f"{member.mention} joined the server.",
            color=GREEN,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Account Created",
            value=discord.utils.format_dt(member.created_at, style="R"),
            inline=True,
        )
        embed.add_field(
            name="Member Count",
            value=str(member.guild.member_count),
            inline=True,
        )
        embed.set_footer(text=f"ID: {member.id}")
        await self._send(member.guild, embed)

    # ── Member Leave ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="📤 Member Left",
            description=f"**{discord.utils.escape_markdown(str(member))}** left the server.",
            color=RED,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if member.joined_at:
            embed.add_field(
                name="Joined",
                value=discord.utils.format_dt(member.joined_at, style="R"),
                inline=True,
            )
        embed.add_field(
            name="Roles",
            value=", ".join(r.mention for r in reversed(member.roles) if r.name != "@everyone")[:512]
            or "None",
            inline=False,
        )
        embed.set_footer(text=f"ID: {member.id}")
        await self._send(member.guild, embed)

    # ── Role Update ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Log role additions/removals."""
        added   = set(after.roles)  - set(before.roles)
        removed = set(before.roles) - set(after.roles)
        if not added and not removed:
            return

        embed = discord.Embed(
            title="🔧 Member Roles Updated",
            color=PURPLE,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Member",
            value=f"{after.mention} (`{after.id}`)",
            inline=False,
        )
        if added:
            embed.add_field(
                name="➕ Roles Added",
                value=" ".join(r.mention for r in added),
                inline=True,
            )
        if removed:
            embed.add_field(
                name="➖ Roles Removed",
                value=" ".join(r.mention for r in removed),
                inline=True,
            )
        embed.set_footer(text="Modern Security • Logging")
        await self._send(after.guild, embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
