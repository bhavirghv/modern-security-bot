"""
cogs/setup.py — Modern Security Bot
Interactive /config panel: buttons, channel/role selects, automod toggles.
Also exposes quick-setup slash commands: /setlog, /setmodrole, /setmuterole.
"""

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from utils.checks import is_config_admin
from utils.embeds import PURPLE, error_embed, success_embed


# ──────────────────────────────────────────────────────────────────────────────
# Embed builders (pure functions, no bot dependency)
# ──────────────────────────────────────────────────────────────────────────────

def _bool_str(val) -> str:
    return "✅ ON" if val else "❌ OFF"


def build_panel_embed(config: dict | None) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Modern Security — Configuration Panel",
        description=(
            "Manage your server settings using the buttons below.\n"
            "All responses are private — only you can see them."
        ),
        color=PURPLE,
        timestamp=datetime.now(timezone.utc),
    )
    if config:
        embed.add_field(
            name="📢 Log Channel",
            value=f"<#{config['log_channel_id']}>" if config.get("log_channel_id") else "❌ Not set",
            inline=True,
        )
        embed.add_field(
            name="🛡️ Mod Role",
            value=f"<@&{config['mod_role_id']}>" if config.get("mod_role_id") else "❌ Not set",
            inline=True,
        )
        embed.add_field(
            name="🔇 Mute Role",
            value=f"<@&{config['mute_role_id']}>" if config.get("mute_role_id") else "❌ Not set",
            inline=True,
        )
        embed.add_field(
            name="⚙️ AutoMod",
            value=_bool_str(config.get("automod_enabled", 1)),
            inline=True,
        )
    else:
        embed.description += "\n\n⚠️ No configuration exists yet — start with the buttons below."

    embed.set_footer(text="Modern Security • Config Panel")
    return embed


def build_full_config_embed(config: dict | None, guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title=f"📊 {guild.name} — Current Settings",
        color=PURPLE,
        timestamp=datetime.now(timezone.utc),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    if not config:
        embed.description = "⚠️ No configuration found. Use `/config` to set things up."
        return embed

    embed.add_field(
        name="📢 Log Channel",
        value=f"<#{config['log_channel_id']}>" if config.get("log_channel_id") else "❌ Not configured",
        inline=False,
    )
    embed.add_field(
        name="🛡️ Mod Role",
        value=f"<@&{config['mod_role_id']}>" if config.get("mod_role_id") else "❌ Not configured",
        inline=False,
    )
    embed.add_field(
        name="🔇 Mute Role",
        value=f"<@&{config['mute_role_id']}>" if config.get("mute_role_id") else "❌ Not configured",
        inline=False,
    )
    embed.add_field(name="\u200b", value="**─── AutoMod Settings ───**", inline=False)
    embed.add_field(name="🤖 AutoMod Master",  value=_bool_str(config.get("automod_enabled",     1)), inline=True)
    embed.add_field(name="🧠 Anti-Spam",       value=_bool_str(config.get("anti_spam_enabled",   1)), inline=True)
    embed.add_field(name="🔗 Anti-Link",       value=_bool_str(config.get("anti_link_enabled",   0)), inline=True)
    embed.add_field(name="🤬 Bad Words Filter",value=_bool_str(config.get("bad_words_enabled",   1)), inline=True)
    embed.add_field(name="⚡ Auto Punish",     value=_bool_str(config.get("auto_punish_enabled", 1)), inline=True)
    embed.set_footer(text=f"Server ID: {guild.id}")
    return embed


def build_automod_embed(config: dict | None) -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ AutoMod Settings",
        description=(
            "Toggle each feature on or off.\n"
            "Changes apply instantly — no save button needed."
        ),
        color=PURPLE,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="🤖 AutoMod Master",  value=_bool_str(config.get("automod_enabled",     1) if config else 1), inline=True)
    embed.add_field(name="🧠 Anti-Spam",       value=_bool_str(config.get("anti_spam_enabled",   1) if config else 1), inline=True)
    embed.add_field(name="🔗 Anti-Link",       value=_bool_str(config.get("anti_link_enabled",   0) if config else 0), inline=True)
    embed.add_field(name="🤬 Bad Words Filter",value=_bool_str(config.get("bad_words_enabled",   1) if config else 1), inline=True)
    embed.add_field(name="⚡ Auto Punish",     value=_bool_str(config.get("auto_punish_enabled", 1) if config else 1), inline=True)
    embed.set_footer(text="Modern Security • AutoMod Panel")
    return embed


# ──────────────────────────────────────────────────────────────────────────────
# Channel select view
# ──────────────────────────────────────────────────────────────────────────────

class ChannelSelectView(discord.ui.View):
    def __init__(self, db, setting_key: str, label: str):
        super().__init__(timeout=60)
        self.db = db
        self.setting_key = setting_key   # "log"
        self.label_str   = label          # human-readable description

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Select a text channel…",
        min_values=1,
        max_values=1,
    )
    async def channel_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.ChannelSelect,
    ):
        channel = select.values[0]
        if self.setting_key == "log":
            await self.db.set_log_channel(interaction.guild_id, channel.id)

        embed = success_embed(
            f"{self.label_str} has been set to {channel.mention}",
            title=f"✅ {self.label_str} Updated",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()

    async def on_timeout(self):
        self.disable_all_items()


# ──────────────────────────────────────────────────────────────────────────────
# Role select view
# ──────────────────────────────────────────────────────────────────────────────

class RoleSelectView(discord.ui.View):
    def __init__(self, db, setting_key: str, label: str):
        super().__init__(timeout=60)
        self.db = db
        self.setting_key = setting_key   # "mod" | "mute"
        self.label_str   = label

    @discord.ui.select(
        cls=discord.ui.RoleSelect,
        placeholder="Select a role…",
        min_values=1,
        max_values=1,
    )
    async def role_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.RoleSelect,
    ):
        role = select.values[0]
        if self.setting_key == "mod":
            await self.db.set_mod_role(interaction.guild_id, role.id)
        elif self.setting_key == "mute":
            await self.db.set_mute_role(interaction.guild_id, role.id)

        embed = success_embed(
            f"{self.label_str} has been set to {role.mention}",
            title=f"✅ {self.label_str} Updated",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        self.stop()

    async def on_timeout(self):
        self.disable_all_items()


# ──────────────────────────────────────────────────────────────────────────────
# AutoMod toggle view
# ──────────────────────────────────────────────────────────────────────────────

class AutoModView(discord.ui.View):
    def __init__(self, db, guild_id: int, config: dict | None):
        super().__init__(timeout=120)
        self.db       = db
        self.guild_id = guild_id
        self.config   = config

    async def _toggle(self, interaction: discord.Interaction, key: str):
        await self.db.toggle_automod_setting(interaction.guild_id, key)
        self.config = await self.db.get_config(interaction.guild_id)
        embed = build_automod_embed(self.config)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🤖 Toggle AutoMod",       style=discord.ButtonStyle.primary,   row=0)
    async def toggle_automod(self, interaction, button): await self._toggle(interaction, "automod_enabled")

    @discord.ui.button(label="🧠 Toggle Anti-Spam",     style=discord.ButtonStyle.secondary, row=0)
    async def toggle_spam(self, interaction, button):    await self._toggle(interaction, "anti_spam_enabled")

    @discord.ui.button(label="🔗 Toggle Anti-Link",     style=discord.ButtonStyle.secondary, row=1)
    async def toggle_link(self, interaction, button):    await self._toggle(interaction, "anti_link_enabled")

    @discord.ui.button(label="🤬 Toggle Bad Words",     style=discord.ButtonStyle.secondary, row=1)
    async def toggle_bad_words(self, interaction, button): await self._toggle(interaction, "bad_words_enabled")

    @discord.ui.button(label="⚡ Toggle Auto Punish",   style=discord.ButtonStyle.danger,    row=2)
    async def toggle_auto_punish(self, interaction, button): await self._toggle(interaction, "auto_punish_enabled")

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ──────────────────────────────────────────────────────────────────────────────
# Main Config Panel view
# ──────────────────────────────────────────────────────────────────────────────

class ConfigView(discord.ui.View):
    def __init__(self, db, guild_id: int):
        super().__init__(timeout=120)
        self.db       = db
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await is_config_admin(interaction):
            await interaction.response.send_message(
                embed=error_embed("❌ You don't have permission to use this."),
                ephemeral=True,
            )
            return False
        return True

    # Row 0 ───────────────────────────────────────────────────────────

    @discord.ui.button(label="📢 Set Log Channel", style=discord.ButtonStyle.primary, row=0)
    async def set_log_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view  = ChannelSelectView(self.db, "log", "Log Channel")
        embed = discord.Embed(
            title="📢 Set Log Channel",
            description="Select the channel where all moderation logs will be sent.",
            color=PURPLE,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🛡️ Set Mod Role", style=discord.ButtonStyle.primary, row=0)
    async def set_mod_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view  = RoleSelectView(self.db, "mod", "Mod Role")
        embed = discord.Embed(
            title="🛡️ Set Mod Role",
            description="Select the role that grants moderator access to this bot.",
            color=PURPLE,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="🔇 Set Mute Role", style=discord.ButtonStyle.primary, row=0)
    async def set_mute_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        view  = RoleSelectView(self.db, "mute", "Mute Role")
        embed = discord.Embed(
            title="🔇 Set Mute Role",
            description=(
                "Select the role used to mute members.\n"
                "Ensure this role **cannot send messages** in your channels."
            ),
            color=PURPLE,
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # Row 1 ───────────────────────────────────────────────────────────

    @discord.ui.button(label="⚙️ AutoMod Settings", style=discord.ButtonStyle.secondary, row=1)
    async def automod_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_config(interaction.guild_id)
        view   = AutoModView(self.db, interaction.guild_id, config)
        embed  = build_automod_embed(config)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📊 View Current Config", style=discord.ButtonStyle.secondary, row=1)
    async def view_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await self.db.get_config(interaction.guild_id)
        embed  = build_full_config_embed(config, interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ──────────────────────────────────────────────────────────────────────────────
# Setup Cog
# ──────────────────────────────────────────────────────────────────────────────

class Setup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    # ── /config ───────────────────────────────────────────────────────

    @app_commands.command(
        name="config",
        description="Open the Modern Security interactive configuration panel"
    )
    async def config(self, interaction: discord.Interaction):
        if not await is_config_admin(interaction):
            return await interaction.response.send_message(
                embed=error_embed("❌ You don't have permission to use this."),
                ephemeral=True,
            )

        await self.db.ensure_config(interaction.guild_id)
        config = await self.db.get_config(interaction.guild_id)
        embed  = build_panel_embed(config)
        view   = ConfigView(self.db, interaction.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /setlog ───────────────────────────────────────────────────────

    @app_commands.command(name="setlog", description="Set the log channel directly")
    @app_commands.describe(channel="Channel to send moderation logs to")
    async def setlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await is_config_admin(interaction):
            return await interaction.response.send_message(
                embed=error_embed("❌ You don't have permission."), ephemeral=True
            )
        await self.db.set_log_channel(interaction.guild_id, channel.id)
        await interaction.response.send_message(
            embed=success_embed(f"Log channel set to {channel.mention}"),
            ephemeral=True,
        )

    # ── /setmodrole ───────────────────────────────────────────────────

    @app_commands.command(name="setmodrole", description="Set the moderator role directly")
    @app_commands.describe(role="The moderator role")
    async def setmodrole(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_config_admin(interaction):
            return await interaction.response.send_message(
                embed=error_embed("❌ You don't have permission."), ephemeral=True
            )
        await self.db.set_mod_role(interaction.guild_id, role.id)
        await interaction.response.send_message(
            embed=success_embed(f"Moderator role set to {role.mention}"),
            ephemeral=True,
        )

    # ── /setmuterole ──────────────────────────────────────────────────

    @app_commands.command(name="setmuterole", description="Set the mute role directly")
    @app_commands.describe(role="The mute role")
    async def setmuterole(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_config_admin(interaction):
            return await interaction.response.send_message(
                embed=error_embed("❌ You don't have permission."), ephemeral=True
            )
        await self.db.set_mute_role(interaction.guild_id, role.id)
        await interaction.response.send_message(
            embed=success_embed(f"Mute role set to {role.mention}"),
            ephemeral=True,
        )

    # ── Error handler ─────────────────────────────────────────────────

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        msg = str(error) or "❌ An error occurred."
        try:
            await interaction.response.send_message(
                embed=error_embed(msg), ephemeral=True
            )
        except discord.InteractionResponded:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Setup(bot))
