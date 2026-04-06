import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import uuid
import os
import threading
from fastapi import FastAPI, Response
import uvicorn

# --- CONFIGURATION ---
TOKEN = os.getenv("DISCORD_TOKEN")
# Make sure to set RENDER_EXTERNAL_URL in Render Env Vars (e.g., https://bot-name.onrender.com)
BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-app.onrender.com")

app = FastAPI()

class LuarmorEngine(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    
    async def setup_hook(self):
        await self.tree.sync()
        print(f"🚀 Luarmor Engine Online | Base URL: {BASE_URL}")

bot = LuarmorEngine()

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("database.db")
    # Table for Scripts/Projects
    conn.execute('''CREATE TABLE IF NOT EXISTS projects 
                    (project_id TEXT PRIMARY KEY, name TEXT, script_content TEXT)''')
    # Table for Keys
    conn.execute('''CREATE TABLE IF NOT EXISTS whitelist 
                    (key TEXT PRIMARY KEY, project_id TEXT, hwid TEXT, status TEXT, blacklisted INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

# --- PROJECT MANAGEMENT (THE PANEL SHIT) ---

@bot.hybrid_command(name="hostscript", description="Create a new project and host a script")
async def hostscript(ctx, name: str, script_content: str):
    project_id = str(uuid.uuid4())[:6].lower()
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT INTO projects (project_id, name, script_content) VALUES (?, ?, ?)", 
                 (project_id, name, script_content))
    conn.commit()
    conn.close()
    
    loader = f'loadstring(game:HttpGet("{BASE_URL}/load/{project_id}"))()'
    embed = discord.Embed(title="✅ Script Hosted Successfully", color=discord.Color.green())
    embed.add_field(name="Project Name", value=name, inline=True)
    embed.add_field(name="Project ID", value=f"`{project_id}`", inline=True)
    embed.add_field(name="Your Loader", value=f"```lua\n{loader}\n```", inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="editproject", description="Change a project's name or code")
async def editproject(ctx, project_id: str, new_name: str = None, new_script: str = None):
    conn = sqlite3.connect("database.db")
    if new_name:
        conn.execute("UPDATE projects SET name = ? WHERE project_id = ?", (new_name, project_id))
    if new_script:
        conn.execute("UPDATE projects SET script_content = ? WHERE project_id = ?", (new_script, project_id))
    conn.commit()
    conn.close()
    await ctx.send(f"🛠️ Project `{project_id}` updated.")

@bot.hybrid_command(name="panel", description="Display the project management menu")
async def panel(ctx, project_id: str):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT name FROM projects WHERE project_id = ?", (project_id,))
    res = cur.fetchone()
    conn.close()
    
    if not res: return await ctx.send("❌ Project not found.")
    
    embed = discord.Embed(title=f"🛡️ {res[0]} Panel", color=discord.Color.blue())
    embed.description = f"**ID:** `{project_id}`\n\nUse `/gen {project_id}` to whitelist a user.\nUse `/getscript {project_id}` for the code."
    await ctx.send(embed=embed)

# --- WHITELIST COMMANDS ---

@bot.hybrid_command(name="gen", description="Generate a whitelist key for a project")
async def gen(ctx, project_id: str):
    new_key = f"KEY-{str(uuid.uuid4())[:8].upper()}"
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT INTO whitelist (key, project_id, status) VALUES (?, ?, ?)", (new_key, project_id, "unused"))
    conn.commit()
    conn.close()
    await ctx.send(f"🔑 **Key Generated for `{project_id}`:** `{new_key}`")

@bot.hybrid_command(name="reset", description="Reset HWID for a user")
async def reset(ctx, key: str):
    conn = sqlite3.connect("database.db")
    conn.execute("UPDATE whitelist SET hwid = NULL WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    await ctx.send(f"♻️ HWID Reset for `{key}`")

# --- WEB API (ROBLOX INTERACTION) ---

@app.get("/load/{project_id}")
async def fetch_script(project_id: str):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT script_content FROM projects WHERE project_id = ?", (project_id,))
    res = cur.fetchone()
    conn.close()
    if res:
        return Response(content=res[0], media_type="text/plain")
    return Response(content="print('Error: Project not found')", media_type="text/plain")

@app.get("/verify")
def verify(key: str, hwid: str, project_id: str):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT hwid, blacklisted FROM whitelist WHERE key = ? AND project_id = ?", (key, project_id))
    row = cur.fetchone()
    
    if not row: return {"status": "error", "message": "invalid_key"}
    if row[1] == 1: return {"status": "error", "message": "banned"}
    
    if row[0] is None:
        conn.execute("UPDATE whitelist SET hwid = ?, status = 'active' WHERE key = ?", (hwid, key))
        conn.commit()
        return {"status": "success", "message": "bound"}
    
    if row[0] == hwid: return {"status": "success", "message": "verified"}
    return {"status": "error", "message": "hwid_mismatch"}

# --- SERVER RUNNER ---
if __name__ == "__main__":
    init_db()
    threading.Thread(target=lambda: bot.run(TOKEN)).start()
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
