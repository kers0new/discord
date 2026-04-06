import os
import discord
from discord.ext import commands
from discord import app_commands
from pymongo import MongoClient
import uuid
import hashlib

# -----------------------------
# ENVIRONMENT VARIABLES (Render)
# -----------------------------
TOKEN = os.getenv("TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# -----------------------------
# DATABASE
# -----------------------------
db = MongoClient(MONGO_URI)["luarmor_clone"]
users = db["users"]
keys = db["keys"]

# -----------------------------
# BOT SETUP
# -----------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# -----------------------------
# HELPERS
# -----------------------------
def generate_key():
    return str(uuid.uuid4()).replace("-", "").upper()

def hash_hwid(hwid):
    return hashlib.sha256(hwid.encode()).hexdigest()

# -----------------------------
# EVENTS
# -----------------------------
@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print("Sync error:", e)

# -----------------------------
# COMMANDS
# -----------------------------

# Generate a license key
@bot.tree.command(name="genkey", description="Generate a license key")
@app_commands.checks.has_permissions(administrator=True)
async def genkey(interaction: discord.Interaction):
    key = generate_key()
    keys.insert_one({"key": key, "used": False})
    await interaction.response.send_message(f"🔑 Generated key: `{key}`")

# Redeem a key
@bot.tree.command(name="redeem", description="Redeem a license key")
async def redeem(interaction: discord.Interaction, key: str, hwid: str):
    key_data = keys.find_one({"key": key})

    if not key_data:
        return await interaction.response.send_message("❌ Invalid key")

    if key_data["used"]:
        return await interaction.response.send_message("❌ Key already used")

    users.insert_one({
        "user_id": interaction.user.id,
        "hwid": hash_hwid(hwid)
    })

    keys.update_one({"key": key}, {"$set": {"used": True}})

    await interaction.response.send_message("✅ Key redeemed successfully")

# Reset HWID (user)
@bot.tree.command(name="resethwid", description="Reset your HWID")
async def resethwid(interaction: discord.Interaction):
    user = users.find_one({"user_id": interaction.user.id})

    if not user:
        return await interaction.response.send_message("❌ You are not registered")

    users.update_one({"user_id": interaction.user.id}, {"$set": {"hwid": None}})
    await interaction.response.send_message("🔄 HWID reset")

# Admin force reset
@bot.tree.command(name="force_resethwid", description="Force reset a user's HWID")
@app_commands.checks.has_permissions(administrator=True)
async def force_resethwid(interaction: discord.Interaction, member: discord.Member):
    users.update_one({"user_id": member.id}, {"$set": {"hwid": None}})
    await interaction.response.send_message(f"🔧 Reset HWID for {member.mention}")

# -----------------------------
# RUN BOT
# -----------------------------
bot.run(TOKEN)
