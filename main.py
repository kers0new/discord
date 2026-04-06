import discord
from discord.ext import commands
from discord import app_commands, ui
import sqlite3, uuid, os, threading, time
from fastapi import FastAPI, Response
import uvicorn

# --- CONFIG ---
TOKEN = os.getenv("DISCORD_TOKEN")
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")
app = FastAPI()

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("database.db")
    # Project Table: Name, Script, Thumbnail
    conn.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT, script TEXT, thumb TEXT)")
    # Whitelist Table: Key, ProjectID, HWID, DiscordID, Expiry (Unix), Banned
    conn.execute("""CREATE TABLE IF NOT EXISTS whitelist 
                 (key TEXT PRIMARY KEY, pid TEXT, hwid TEXT, discord_id TEXT, expiry INTEGER, banned INTEGER DEFAULT 0)""")
    conn.commit()
    conn.close()

# --- BUTTON UI ---
class LuarmorUI(ui.View):
    def __init__(self, pid=None, name=None):
        super().__init__(timeout=None)
        self.pid = pid
        self.name = name

    @ui.button(label="📜 Get Script", style=discord.ButtonStyle.gray, custom_id="get_script")
    async def get_script(self, interaction: discord.Interaction, button: ui.Button):
        loader = f'loadstring(game:HttpGet("{BASE_URL}/load/{self.pid}"))()'
        await interaction.response.send_message(f"**{self.name} Loader:**\n```lua\n{loader}\n```", ephemeral=True)

    @ui.button(label="🔑 Redeem Key", style=discord.ButtonStyle.green, custom_id="redeem_key")
    async def redeem(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RedeemModal(self.pid))

class RedeemModal(ui.Modal, title="Redeem Whitelist Key"):
    key_input = ui.TextInput(label="Enter your Key", placeholder="LUA-XXXX-XXXX", required=True)
    def __init__(self, pid):
        super().__init__()
        self.pid = pid

    async def on_submit(self, interaction: discord.Interaction):
        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("SELECT discord_id FROM whitelist WHERE key = ? AND pid = ?", (self.key_input.value, self.pid))
        row = cur.fetchone()
        if not row:
            return await interaction.response.send_message("❌ Invalid Key!", ephemeral=True)
        if row[0]:
            return await interaction.response.send_message("❌ Key already linked to another user!", ephemeral=True)
        
        conn.execute("UPDATE whitelist SET discord_id = ? WHERE key = ?", (str(interaction.user.id), self.key_input.value))
        conn.commit()
        conn.close()
        await interaction.response.send_message("✅ Key linked to your Discord successfully!", ephemeral=True)

# --- BOT SETUP ---
class LuarmorBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self):
        await self.tree.sync()
        self.add_view(LuarmorUI()) # Make buttons persistent

bot = LuarmorBot()

# --- ADMIN COMMANDS ---

@bot.tree.command(name="create_project", description="Admin: Create a new project")
async def create_project(interaction: discord.Interaction, name: str, script: str, thumb: str = ""):
    pid = str(uuid.uuid4())[:6]
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", (pid, name, script, thumb))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"✅ Project `{name}` Created! ID: `{pid}`")

@bot.tree.command(name="setup_panel", description="Drop the UI Panel")
async def setup_panel(interaction: discord.Interaction, project_id: str):
    conn = sqlite3.connect("database.db")
    res = conn.execute("SELECT name, thumb FROM projects WHERE id = ?", (project_id,)).fetchone()
    conn.close()
    if not res: return await interaction.response.send_message("❌ Project ID not found.")
    
    embed = discord.Embed(title=f"🛡️ {res[0]} | Panel", description="Click below to manage your access.", color=0x5865f2)
    if res[1]: embed.set_thumbnail(url=res[1])
    await interaction.response.send_message(embed=embed, view=LuarmorUI(project_id, res[0]))

@bot.tree.command(name="gen", description="Generate a Key (Days: 0 for Lifetime)")
async def gen(interaction: discord.Interaction, project_id: str, days: int = 0):
    key = f"LUA-{str(uuid.uuid4())[:12].upper()}"
    expiry = 0 if days == 0 else int(time.time() + (days * 86400))
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT INTO whitelist VALUES (?, ?, NULL, NULL, ?, 0)", (key, project_id, expiry))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"🔑 **Key:** `{key}`\n**Expiry:** {'Lifetime' if days == 0 else f'{days} Days'}", ephemeral=True)

@bot.tree.command(name="blacklist", description="Ban a key/user")
async def blacklist(interaction: discord.Interaction, key: str):
    conn = sqlite3.connect("database.db")
    conn.execute("UPDATE whitelist SET banned = 1 WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"🚫 `{key}` Blacklisted.")

# --- API (ROBLOX INTERFACE) ---

@app.get("/load/{pid}")
async def load(pid: str):
    conn = sqlite3.connect("database.db")
    res = conn.execute("SELECT script FROM projects WHERE id = ?", (pid,)).fetchone()
    conn.close()
    return Response(content=res[0] if res else "-- Script Error", media_type="text/plain")

@app.get("/verify")
def verify(key: str, hwid: str, pid: str):
    conn = sqlite3.connect("database.db")
    row = conn.execute("SELECT hwid, banned, expiry FROM whitelist WHERE key = ? AND pid = ?", (key, pid)).fetchone()
    if not row: return {"status": "error", "message": "invalid_key"}
    if row[1]: return {"status": "error", "message": "blacklisted"}
    if row[2] != 0 and time.time() > row[2]: return {"status": "error", "message": "expired"}
    
    if not row[0]: # Bind HWID
        conn.execute("UPDATE whitelist SET hwid = ? WHERE key = ?", (hwid, key))
        conn.commit()
        return {"status": "success", "message": "hwid_bound"}
    
    return {"status": "success"} if row[0] == hwid else {"status": "error", "message": "hwid_mismatch"}

# --- RUN ---
if __name__ == "__main__":
    init_db()
    threading.Thread(target=lambda: bot.run(TOKEN)).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
