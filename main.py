import discord
from discord import app_commands, ui
from discord.ext import commands
import sqlite3, uuid, os, threading, time
from fastapi import FastAPI, Response
import uvicorn

# --- CONFIGURATION ---
# Set these in your Render Environment Variables
TOKEN = os.getenv("DISCORD_TOKEN")
# Example: https://your-app-name.onrender.com
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")

app = FastAPI()

# --- DATABASE INITIALIZATION ---
def init_db():
    # Use "/data/database.db" if you have a Render Disk attached for persistence
    db_path = "database.db" 
    conn = sqlite3.connect(db_path)
    # Projects: Linked to a Channel ID
    conn.execute("""CREATE TABLE IF NOT EXISTS projects 
                 (channel_id TEXT PRIMARY KEY, name TEXT, script TEXT, role_id TEXT)""")
    # Whitelist: Keys linked to a specific Channel/Project
    conn.execute("""CREATE TABLE IF NOT EXISTS whitelist 
                 (key TEXT PRIMARY KEY, channel_id TEXT, hwid TEXT, discord_id TEXT, tier TEXT, expiry INTEGER, last_reset INTEGER DEFAULT 0)""")
    conn.commit()
    conn.close()

# --- THE INTERACTIVE PANEL (BUTTONS) ---
class LuarmorPanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None) # timeout=None makes buttons last forever

    @ui.button(label="Redeem Key", style=discord.ButtonStyle.primary, custom_id="persistent:redeem", emoji="🎟️")
    async def redeem(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RedeemModal(str(interaction.channel_id)))

    @ui.button(label="My Stats", style=discord.ButtonStyle.secondary, custom_id="persistent:stats", emoji="📊")
    async def stats(self, interaction: discord.Interaction, button: ui.Button):
        conn = sqlite3.connect("database.db")
        row = conn.execute("SELECT tier, expiry, hwid, key FROM whitelist WHERE discord_id = ? AND channel_id = ?", 
                           (str(interaction.user.id), str(interaction.channel_id))).fetchone()
        conn.close()

        if not row:
            return await interaction.response.send_message("❌ No license linked to this account for this project.", ephemeral=True)

        tier, expiry, hwid, full_key = row
        time_left = "Lifetime" if expiry == 0 else f"{int((expiry - time.time()) // 86400)}d {int(((expiry - time.time()) % 86400) // 3600)}h"
        
        embed = discord.Embed(title="📊 Your License Stats", color=0xFEE75C)
        embed.add_field(name="Status", value="🟢 Active", inline=False)
        embed.add_field(name="Tier", value=tier, inline=False)
        embed.add_field(name="Expires", value=time_left, inline=False)
        embed.add_field(name="HWID", value=f"`{hwid if hwid else 'Not bound yet'}`", inline=False)
        embed.add_field(name="Key", value=f"`{full_key[:4]}************`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Reset HWID", style=discord.ButtonStyle.danger, custom_id="persistent:reset", emoji="🔄")
    async def reset(self, interaction: discord.Interaction, button: ui.Button):
        conn = sqlite3.connect("database.db")
        # Add a 24h cooldown check here if needed
        conn.execute("UPDATE whitelist SET hwid = NULL WHERE discord_id = ? AND channel_id = ?", 
                     (str(interaction.user.id), str(interaction.channel_id)))
        conn.commit()
        conn.close()
        await interaction.response.send_message("✅ HWID has been cleared! You can now login on a new device.", ephemeral=True)

# --- POP-UP MODALS ---
class RedeemModal(ui.Modal, title="License Redemption"):
    key_input = ui.TextInput(label="Enter License Key", placeholder="LUA-XXXX-XXXX", min_length=10, required=True)
    def __init__(self, channel_id): 
        super().__init__()
        self.channel_id = channel_id

    async def on_submit(self, interaction: discord.Interaction):
        conn = sqlite3.connect("database.db")
        row = conn.execute("SELECT discord_id FROM whitelist WHERE key = ? AND channel_id = ?", 
                           (self.key_input.value, self.channel_id)).fetchone()
        if row and not row[0]:
            conn.execute("UPDATE whitelist SET discord_id = ? WHERE key = ?", (str(interaction.user.id), self.key_input.value))
            conn.commit()
            await interaction.response.send_message("✅ License linked to your Discord!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Invalid key or already redeemed.", ephemeral=True)
        conn.close()

# --- BOT SETUP ---
class LuarmorCore(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self):
        self.add_view(LuarmorPanel()) # Register the button view globally
        await self.tree.sync()

bot = LuarmorCore()

# --- COMMANDS (THE PANEL SHIT) ---

@bot.tree.command(name="createscript", description="Initialize this channel as a script project")
@app_commands.checks.has_permissions(administrator=True)
async def createscript(interaction: discord.Interaction, name: str, script_content: str):
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT OR REPLACE INTO projects (channel_id, name, script) VALUES (?, ?, ?)", 
                 (str(interaction.channel_id), name, script_content))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(title="🔐 License Panel", color=0x2b2d31)
    embed.description = f"Welcome! Use the buttons below to manage your license for **{name}**.\n\n🎟️ **Redeem Key** — Link a license key\n📊 **My Stats** — View subscription & HWID\n🔄 **Reset HWID** — Clear bound machine"
    
    await interaction.response.send_message(embed=embed, view=LuarmorPanel())

@bot.tree.command(name="whitelist", description="Generate a key for the script in THIS channel")
@app_commands.checks.has_permissions(administrator=True)
async def whitelist(interaction: discord.Interaction, days: int = 30, tier: str = "Premium"):
    channel_id = str(interaction.channel_id)
    conn = sqlite3.connect("database.db")
    project = conn.execute("SELECT name FROM projects WHERE channel_id = ?", (channel_id,)).fetchone()
    
    if not project:
        conn.close()
        return await interaction.response.send_message("❌ Run `/createscript` in this channel first!", ephemeral=True)
    
    new_key = f"LUA-{str(uuid.uuid4())[:12].upper()}"
    expiry = 0 if days == 0 else int(time.time() + (days * 86400))
    
    conn.execute("INSERT INTO whitelist (key, channel_id, expiry, tier) VALUES (?, ?, ?, ?)", 
                 (new_key, channel_id, expiry, tier))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ **Key Created for {project[0]}**\nKey: `{new_key}`\nTier: `{tier}`\nExpires: `{days} days`", ephemeral=True)

# --- ROBLOX API ENDPOINTS ---

@app.get("/load/{channel_id}")
async def loader(channel_id: str):
    conn = sqlite3.connect("database.db")
    res = conn.execute("SELECT script FROM projects WHERE channel_id = ?", (channel_id,)).fetchone()
    conn.close()
    return Response(content=res[0] if res else "-- Project Error", media_type="text/plain")

@app.get("/verify")
def verify(key: str, hwid: str, channel_id: str):
    conn = sqlite3.connect("database.db")
    row = conn.execute("SELECT hwid, expiry FROM whitelist WHERE key = ? AND channel_id = ?", (key, channel_id)).fetchone()
    if not row: return {"status": "error", "message": "invalid_key"}
    if row[1] != 0 and time.time() > row[1]: return {"status": "error", "message": "expired"}
    
    if not row[0]: # First use
        conn.execute("UPDATE whitelist SET hwid = ? WHERE key = ?", (hwid, key))
        conn.commit()
        return {"status": "success", "message": "bound"}
    
    return {"status": "success"} if row[0] == hwid else {"status": "error", "message": "hwid_mismatch"}

# --- RUNNER ---
if __name__ == "__main__":
    init_db()
    # Start Discord Bot in a background thread
    threading.Thread(target=lambda: bot.run(TOKEN)).start()
    # Start FastAPI server for Roblox
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
