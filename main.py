"""
main.py — Modern Security Bot
Entry point: runs FastAPI (in a background thread) and the Discord
bot (in the main asyncio event loop) side-by-side on Render Web Service.
"""

import asyncio
import os
import threading

import discord
import uvicorn
from discord.ext import commands
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from database import Database

load_dotenv()

# ── Intents ────────────────────────────────────────────────────────────────────
intents = discord.Intents.all()

# ── Bot ────────────────────────────────────────────────────────────────────────
bot = commands.Bot(
    command_prefix="!",   # prefix not used (slash only), but required by library
    intents=intents,
    help_command=None,
    description="Modern Security — Production Moderation Bot"
)

# ── Database (shared singleton) ────────────────────────────────────────────────
db = Database()

# ── Cogs to load ──────────────────────────────────────────────────────────────
COGS = [
    "cogs.moderation",
    "cogs.automod",
    "cogs.logging",
    "cogs.setup",
    "cogs.trust",
    "cogs.reports",
]

# ──────────────────────────────────────────────────────────────────────────────
# FastAPI Application
# ──────────────────────────────────────────────────────────────────────────────
api = FastAPI(
    title="Modern Security Bot API",
    description="REST API for the Modern Security Discord bot.",
    version="1.0.0"
)


@api.get("/", tags=["Status"])
async def root():
    """Health check + bot info."""
    return {
        "status": "Modern Security Bot Running",
        "bot_name":   str(bot.user) if bot.is_ready() else "Starting…",
        "guilds":     len(bot.guilds) if bot.is_ready() else 0,
        "latency_ms": round(bot.latency * 1000, 2) if bot.is_ready() else None,
    }


@api.get("/health", tags=["Status"])
async def health():
    return {"status": "ok"}


@api.get("/trust/{user_id}", tags=["Trust"])
async def get_trust(user_id: int, guild_id: int):
    """Look up a user's trust score in a specific guild."""
    score = await db.get_trust_score(user_id, guild_id)
    return {"user_id": user_id, "guild_id": guild_id, "trust_score": score}


@api.get("/cases/{case_id}", tags=["Cases"])
async def get_case(case_id: int):
    """Retrieve a single moderation case by ID."""
    case = await db.get_case(case_id)
    if not case:
        return JSONResponse(status_code=404, content={"error": "Case not found"})
    return case


@api.get("/cases", tags=["Cases"])
async def list_cases():
    """Return all moderation cases (newest first)."""
    cases = await db.get_all_cases()
    return {"cases": cases, "total": len(cases)}


@api.get("/reports", tags=["Reports"])
async def get_reports():
    """Return all user reports."""
    reports = await db.get_all_reports()
    return {"reports": reports, "total": len(reports)}


# ──────────────────────────────────────────────────────────────────────────────
# Bot Events
# ──────────────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅  Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"📡  Connected to {len(bot.guilds)} guild(s)")
    try:
        synced = await bot.tree.sync()
        print(f"✅  Synced {len(synced)} slash command(s)")
    except Exception as exc:
        print(f"❌  Failed to sync commands: {exc}")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="over your server 🛡️"
        )
    )


@bot.event
async def on_guild_join(guild: discord.Guild):
    await db.ensure_config(guild.id)
    print(f"📥  Joined guild: {guild.name} ({guild.id})")


@bot.event
async def on_command_error(ctx, error):
    # Suppress "command not found" noise since we use slash commands only
    pass


# ──────────────────────────────────────────────────────────────────────────────
# Startup Routines
# ──────────────────────────────────────────────────────────────────────────────

async def run_bot():
    """Initialise DB, load cogs, then start the Discord bot."""
    await db.initialize()
    bot.db = db  # expose to all cogs via self.bot.db

    for cog in COGS:
        try:
            await bot.load_extension(cog)
            print(f"✅  Loaded cog: {cog}")
        except Exception as exc:
            print(f"❌  Failed to load {cog}: {exc}")

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set!")

    await bot.start(token)


def run_fastapi():
    """Launch uvicorn in the background thread."""
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")


# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # FastAPI runs in a daemon thread; the Discord bot owns the main event loop.
    # If the bot exits, the whole process exits (Render will restart it).
    api_thread = threading.Thread(target=run_fastapi, daemon=True)
    api_thread.start()
    print("🚀  FastAPI thread started")

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("🛑  Shutdown requested.")
