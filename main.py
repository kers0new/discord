import discord
from discord.ext import commands
from fastapi import FastAPI
import uvicorn
import sqlite3
import uuid
import threading
import os

# --- SETUP ---
# On Render, you will set an Environment Variable named DISCORD_TOKEN
TOKEN = os.getenv("DISCORD_TOKEN") 
app = FastAPI()
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# --- DATABASE INIT ---
def init_db():
    conn = sqlite3.connect("database.db")
    conn.execute('''CREATE TABLE IF NOT EXISTS whitelist 
                    (key TEXT PRIMARY KEY, hwid TEXT, status TEXT)''')
    conn.commit()
    conn.close()

# --- DISCORD COMMANDS (PUBLIC - NO PERMS) ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.command()
async def gen(ctx):
    """Generates a unique whitelist key"""
    new_key = f"LUA-{str(uuid.uuid4())[:8].upper()}"
    conn = sqlite3.connect("database.db")
    conn.execute("INSERT INTO whitelist (key, status) VALUES (?, ?)", (new_key, "unused"))
    conn.commit()
    conn.close()
    await ctx.send(f"🔑 **Key Generated:** `{new_key}`")

@bot.command()
async def reset(ctx, key: str):
    """Resets the HWID for a specific key"""
    conn = sqlite3.connect("database.db")
    conn.execute("UPDATE whitelist SET hwid = NULL WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    await ctx.send(f"♻️ **HWID Reset** for key: `{key}`")

@bot.command()
async def check(ctx, key: str):
    """Checks the status of a key"""
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT status, hwid FROM whitelist WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if row:
        await ctx.send(f"📊 **Status:** {row[0]} | **HWID:** {row[1] if row[1] else 'None'}")
    else:
        await ctx.send("❌ Key not found.")

# --- ROBLOX API ENDPOINTS ---

@app.get("/")
def home():
    return {"status": "API is running"}

@app.get("/verify")
def verify(key: str, hwid: str):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT hwid FROM whitelist WHERE key = ?", (key,))
    row = cur.fetchone()
    
    if not row:
        return {"status": "error", "message": "invalid_key"}
    
    saved_hwid = row[0]
    
    if saved_hwid is None: # First time use: Bind the HWID
        conn.execute("UPDATE whitelist SET hwid = ?, status = 'active' WHERE key = ?", (hwid, key))
        conn.commit()
        return {"status": "success", "message": "bound"}
    
    if saved_hwid == hwid:
        return {"status": "success", "message": "verified"}
    
    return {"status": "error", "message": "hwid_mismatch"}

# --- THREADING TO RUN BOTH BOT & API ---
def start_bot():
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("ERROR: DISCORD_TOKEN environment variable not found!")

if __name__ == "__main__":
    init_db()
    # Run the Discord bot in the background
    threading.Thread(target=start_bot, daemon=True).start()
    # Run the FastAPI server (Render uses port 8080 by default or via env)
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
