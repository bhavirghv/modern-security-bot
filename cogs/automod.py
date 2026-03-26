"""
cogs/automod.py — Modern Security Bot
Automatic moderation: anti-spam, anti-link, bad-word filtering.
All features are per-guild and individually toggleable via /config.
"""

import asyncio
import re
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.embeds import PURPLE

# ── Configurable constants ─────────────────────────────────────────────────────

SPAM_LIMIT        = 5     # messages …
SPAM_WINDOW_SECS  = 5     # … within this many seconds = spam
WARN_DELETE_SECS  = 6     # how long the bot's warning message stays visible

# Link / invite pattern
URL_PATTERN = re.compile(
    r"(https?://[^\s]+|discord\.gg/[^\s]+|discordapp\.com/invite/[^\s]+)",
    re.IGNORECASE,
)

# Default bad-word list — extend as needed
BAD_WORDS: list[str] = [
    "badword1",
    "badword2",
    "slur1",
]


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # spam tracker: { user_id: [timestamp, ...] }
        self._spam_tracker: defaultdict[int, list[datetime]] = defaultdict(list)

    @property
    def db(self):
        return self.bot.db

    # ── Helpers ───────────────────────────────────────────────────────

    async def _get_config(self, guild_id: int) -> dict | None:
        return await self.db.get_config(guild_id)

    async def _send_automod_log(
        self,
        guild: discord.Guild,
        title: str,
        description: str,
        user: discord.Member,
        channel: discord.TextChannel,
    ):
        config = await self._get_config(guild.id)
        if not config or not config.get("log_channel_id"):
            return
        log_ch = guild.get_channel(config["log_channel_id"])
        if not log_ch:
            return

        embed = discord.Embed(
            title=f"🤖 AutoMod — {title}",
            description=description,
            color=PURPLE,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User",    value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="Channel", value=channel.mention,                 inline=True)
        embed.set_footer(text="Modern Security • AutoMod")
        try:
            await log_ch.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _temp_warn(self, channel: discord.TextChannel, content: str):
        """Send a visible warning message that auto-deletes after WARN_DELETE_SECS."""
        try:
            embed = discord.Embed(description=content, color=PURPLE)
            msg = await channel.send(embed=embed)
            await asyncio.sleep(WARN_DELETE_SECS)
            await msg.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

    def _is_exempt(self, member: discord.Member, config: dict | None) -> bool:
        """Return True if this member should be skipped by AutoMod."""
        if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
            return True
        if config and config.get("mod_role_id"):
            mod_role = member.guild.get_role(config["mod_role_id"])
            if mod_role and mod_role in member.roles:
                return True
        return False

    # ── Main on_message listener ──────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = await self._get_config(message.guild.id)
        if not config or not config.get("automod_enabled", 1):
            return

        if self._is_exempt(message.author, config):
            return

        tasks = []
        if config.get("anti_spam_enabled", 1):
            tasks.append(self._check_spam(message))
        if config.get("anti_link_enabled", 0):
            tasks.append(self._check_links(message))
        if config.get("bad_words_enabled", 1):
            tasks.append(self._check_bad_words(message))

        await asyncio.gather(*tasks)

    # ── Anti-Spam ─────────────────────────────────────────────────────

    async def _check_spam(self, message: discord.Message):
        uid = message.author.id
        now = datetime.now(timezone.utc)

        # Prune old timestamps
        self._spam_tracker[uid] = [
            t for t in self._spam_tracker[uid]
            if (now - t).total_seconds() < SPAM_WINDOW_SECS
        ]
        self._spam_tracker[uid].append(now)

        if len(self._spam_tracker[uid]) < SPAM_LIMIT:
            return

        # Spam detected — reset counter, act
        self._spam_tracker[uid] = []

        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        await self.db.add_warning(
            message.author.id, message.guild.id,
            self.bot.user.id, "AutoMod: Spam detected"
        )
        await self.db.update_trust_score(message.author.id, message.guild.id, -5)

        asyncio.create_task(self._temp_warn(
            message.channel,
            f"🛑 {message.author.mention}, please stop spamming!"
        ))
        await self._send_automod_log(
            message.guild, "Spam Detected",
            f"Sent {SPAM_LIMIT}+ messages in {SPAM_WINDOW_SECS}s. Message deleted.",
            message.author, message.channel,
        )

    # ── Anti-Link ─────────────────────────────────────────────────────

    async def _check_links(self, message: discord.Message):
        if not URL_PATTERN.search(message.content):
            return

        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        await self.db.update_trust_score(message.author.id, message.guild.id, -3)

        asyncio.create_task(self._temp_warn(
            message.channel,
            f"🔗 {message.author.mention}, links are not allowed in this server!"
        ))
        await self._send_automod_log(
            message.guild, "Link Blocked",
            f"Link detected and removed:\n`{message.content[:120]}`",
            message.author, message.channel,
        )

    # ── Bad-Word Filter ───────────────────────────────────────────────

    async def _check_bad_words(self, message: discord.Message):
        content_lower = message.content.lower()
        for word in BAD_WORDS:
            if word.lower() in content_lower:
                try:
                    await message.delete()
                except (discord.Forbidden, discord.HTTPException):
                    pass

                await self.db.update_trust_score(message.author.id, message.guild.id, -5)

                asyncio.create_task(self._temp_warn(
                    message.channel,
                    f"🤬 {message.author.mention}, that language is not permitted here!"
                ))
                await self._send_automod_log(
                    message.guild, "Bad Word Filtered",
                    "Prohibited language detected and message removed.",
                    message.author, message.channel,
                )
                break  # one strike per message is enough


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
