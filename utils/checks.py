"""
utils/checks.py — Shared permission checks for app_commands.
"""

import discord
from discord import app_commands


async def is_moderator(interaction: discord.Interaction) -> bool:
    """
    Returns True if the interaction user has mod-level access:
    - Administrator permission, OR
    - Manage Guild permission, OR
    - Kick/Ban Members, OR
    - Configured mod role in this guild's config
    """
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False

    perms = member.guild_permissions
    if perms.administrator or perms.manage_guild or \
       perms.kick_members or perms.ban_members:
        return True

    config = await interaction.client.db.get_config(interaction.guild_id)
    if config and config.get("mod_role_id"):
        mod_role = interaction.guild.get_role(config["mod_role_id"])
        if mod_role and mod_role in member.roles:
            return True

    return False


async def is_config_admin(interaction: discord.Interaction) -> bool:
    """
    Returns True if the user may access the /config panel:
    - Administrator, OR
    - Manage Guild, OR
    - Configured mod role
    """
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False

    perms = member.guild_permissions
    if perms.administrator or perms.manage_guild:
        return True

    config = await interaction.client.db.get_config(interaction.guild_id)
    if config and config.get("mod_role_id"):
        mod_role = interaction.guild.get_role(config["mod_role_id"])
        if mod_role and mod_role in member.roles:
            return True

    return False


def moderator_check():
    """app_commands check decorator for moderator-level commands."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if await is_moderator(interaction):
            return True
        raise app_commands.CheckFailure(
            "❌ You don't have permission to use this command."
        )
    return app_commands.check(predicate)
