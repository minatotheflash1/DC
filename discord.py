import os
import discord
from discord.ext import commands, tasks
import asyncpg
from openai import AsyncOpenAI
from dotenv import load_dotenv
import datetime

load_dotenv()

# ==========================================
# ⚙️ CONFIGURATION & IDS
# ==========================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# 🆔 ID Setup
OWNER_ID = 123456789012345678  # 👈 Tomar ID ekhane paste koro (Hardcoded)
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0)) # 👈 Railway variable theke ashbe

# Chat Feature Flag
bot.chat_enabled = True
afk_users = {} # AFK system er jonno

ai_client = AsyncOpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

def is_admin(ctx):
    return ctx.author.id == OWNER_ID or ctx.author.id == ADMIN_ID or ctx.author.guild_permissions.administrator

# ==========================================
# 🗄️ DATABASE
# ==========================================
async def init_db():
    bot.db = await asyncpg.create_pool(os.environ.get("DATABASE_URL"))
    async with bot.db.acquire() as conn:
        await conn.execute('CREATE TABLE IF NOT EXISTS server_invites (code TEXT PRIMARY KEY, uses INTEGER)')

@tasks.loop(minutes=5)
async def update_status():
    for guild in bot.guilds:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{guild.member_count} Members"))

@bot.event
async def on_ready():
    await init_db()
    update_status.start()
    async with bot.db.acquire() as conn:
        for guild in bot.guilds:
            for inv in await guild.invites():
                await conn.execute('INSERT INTO server_invites (code, uses) VALUES ($1, $2) ON CONFLICT (code) DO UPDATE SET uses = $2', inv.code, inv.uses)
    print(f'Bot {bot.user.name} is ONLINE and Ready to Serve!')

# ==========================================
# 🛑 AUTO MODERATION & EVENTS
# ==========================================
@bot.event
async def on_message(message):
    if message.author == bot.user: return

    # Feature: AFK Check
    if message.author.id in afk_users:
        del afk_users[message.author.id]
        await message.channel.send(f"👋 Welcome back {message.author.mention}, I removed your AFK status.", delete_after=5)

    for mention in message.mentions:
        if mention.id in afk_users:
            await message.reply(f"💤 {mention.name} is currently AFK: {afk_users[mention.id]}")

    # Feature: Anti-Link System
    if "http://" in message.content or "https://" in message.content:
        if not (message.author.id == OWNER_ID or message.author.id == ADMIN_ID or message.author.guild_permissions.manage_messages):
            await message.delete()
            await message.channel.send(f"🚫 {message.author.mention}, you are not allowed to send links here!", delete_after=5)
            return

    await bot.process_commands(message)

# ==========================================
# 🤖 AI CHAT SYSTEM
# ==========================================
@bot.command()
async def chat(ctx, *, prompt: str):
    """!chat <message> dile bot reply dibe"""
    if not bot.chat_enabled:
        await ctx.send("❌ Admin currently disabled the AI chat.")
        return

    async with ctx.typing():
        try:
            res = await ai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": "You are a helpful and intelligent community bot."},
                          {"role": "user", "content": prompt}]
            )
            await ctx.reply(res.choices[0].message.content)
        except:
            await ctx.reply("AI is sleeping right now. Try again later! 😅")

@bot.command()
@commands.check(is_admin)
async def chatoff(ctx):
    bot.chat_enabled = False
    await ctx.send("🔇 AI Chat has been disabled.")

@bot.command()
@commands.check(is_admin)
async def chaton(ctx):
    bot.chat_enabled = True
    await ctx.send("🔊 AI Chat has been enabled.")

# ==========================================
# 💎 PREMIUM FEATURES
# ==========================================
@bot.command()
async def afk(ctx, *, reason="I am away"):
    """Feature: Set AFK status"""
    afk_users[ctx.author.id] = reason
    await ctx.send(f"✅ {ctx.author.mention} is now AFK: {reason}")

@bot.command()
async def ticket(ctx):
    """Feature: Support Ticket System"""
    thread = await ctx.channel.create_thread(name=f"support-{ctx.author.name}", type=discord.ChannelType.private_thread)
    await thread.add_user(ctx.author)
    await thread.send(f"Hello {ctx.author.mention}, an admin will be with you shortly to help. Please describe your issue.")
    await ctx.send(f"✅ Ticket created! Check your threads.", delete_after=5)

@bot.command()
@commands.check(is_admin)
async def poll(ctx, *, question):
    """Feature: Create a poll"""
    embed = discord.Embed(title="📊 Community Poll", description=question, color=discord.Color.gold())
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

@bot.command()
@commands.check(is_admin)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    """Feature: Warn a user via DM"""
    try:
        await member.send(f"⚠️ **WARNING** from {ctx.guild.name}\n**Reason:** {reason}")
        await ctx.send(f"✅ Warned {member.mention} successfully.")
    except:
        await ctx.send(f"❌ Could not DM {member.mention}. They might have DMs off.")

@bot.command()
@commands.check(is_admin)
async def slowmode(ctx, seconds: int):
    """Feature: Set slowmode for chat"""
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"🐢 Slowmode set to {seconds} seconds.")

@bot.command()
@commands.check(is_admin)
async def announce(ctx, *, message):
    """Feature: Official Announcement"""
    embed = discord.Embed(title="📢 Announcement", description=message, color=discord.Color.red())
    await ctx.send("@everyone", embed=embed)

# ==========================================
# 🔑 ADMIN SYSTEM (Previous commands)
# ==========================================
@bot.command()
@commands.check(is_admin)
async def create_access(ctx):
    invite = await ctx.channel.create_invite(max_uses=1, unique=True)
    async with bot.db.acquire() as conn:
        await conn.execute('INSERT INTO server_invites (code, uses) VALUES ($1, $2)', invite.code, invite.uses)
    await ctx.send(f"Link for client: {invite.url}")

bot.run(os.environ.get('DISCORD_TOKEN'))