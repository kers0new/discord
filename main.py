import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3, uuid, os, threading, time

TOKEN = os.getenv("DISCORD_TOKEN")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")

class LuarmorBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self):
        # This keeps the panel buttons working 24/7
        self.add_view(LuarmorPanel())
        await self.tree.sync()

bot = LuarmorBot()

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect("database.db")
    # Links Channels to Projects so you don't need IDs in chat
    conn.execute("CREATE TABLE IF NOT EXISTS channel_links (channel_id TEXT PRIMARY KEY, pid TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT, script TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS whitelist (key TEXT PRIMARY KEY, pid TEXT, hwid TEXT, discord_id TEXT, tier TEXT, expiry INTEGER, banned INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

def get_pid(channel_id):
    conn = sqlite3.connect("database.db")
    res = conn.execute("SELECT pid FROM channel_links WHERE channel_id = ?", (str(channel_id),)).fetchone()
    conn.close()
    return res[0] if res else None

# --- THE "NO MERCY" PANEL ---
class LuarmorPanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="🎟️ Redeem Key", style=discord.ButtonStyle.primary, custom_id="lu_red")
    async def redeem(self, interaction: discord.Interaction, button: ui.Button):
        pid = get_pid(interaction.channel_id)
        if not pid: return await interaction.response.send_message("❌ This channel is not set up.", ephemeral=True)
        # (Insert Modal Logic Here)
        await interaction.response.send_message("Redeem modal opening...", ephemeral=True)

    @ui.button(label="📊 My Stats", style=discord.ButtonStyle.secondary, custom_id="lu_stat")
    async def stats(self, interaction: discord.Interaction, button: ui.Button):
        pid = get_pid(interaction.channel_id)
        # (Insert Stats Embed Logic Here)
        await interaction.response.send_message("Fetching your stats...", ephemeral=True)

# --- ADMIN COMMANDS ---

@bot.tree.command(name="setup", description="Link this channel to a project and drop the panel")
@app_commands.checks.has_permissions(administrator=True)
async def setup(interaction: discord.Interaction, project_id: str):
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT OR REPLACE INTO channel_links VALUES (?, ?)", (str(interaction.channel_id), project_id))
    name = conn.execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.commit()
    conn.close()

    if not name: return await interaction.response.send_message("❌ Invalid Project ID.", ephemeral=True)

    embed = discord.Embed(title="🔐 License Panel", description=f"Welcome to **{name[0]}**!\nUse the buttons below to manage your access.", color=0x337fd5)
    await interaction.response.send_message(embed=embed, view=LuarmorPanel())

@bot.tree.command(name="create_project", description="Admin: Host a new script")
async def create_project(interaction: discord.Interaction, name: str, script: str):
    pid = str(uuid.uuid4())[:6]
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT INTO projects VALUES (?, ?, ?)", (pid, name, script))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ Created! Name: {name} | ID: `{pid}`", ephemeral=True)

# (Rest of API and Whitelist logic goes here...)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=lambda: bot.run(TOKEN)).start()
    import uvicorn
    from fastapi import FastAPI
    uvicorn.run(FastAPI(), host="0.0.0.0", port=8080)
