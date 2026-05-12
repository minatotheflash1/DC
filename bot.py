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

OWNER_ID = 1408861331834273832
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0)) 

bot.chat_enabled = True
afk_users = {}

ai_client = AsyncOpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

def is_admin(ctx):
    return ctx.author.id == OWNER_ID or ctx.author.id == ADMIN_ID or ctx.author.guild_permissions.administrator

# ==========================================
# 🗄️ DATABASE & EVENTS
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
    print(f'Bot {bot.user.name} is ONLINE and Ready to Serve! 🚀')

@bot.event
async def on_message(message):
    if message.author == bot.user: return

    # AFK System Check
    if message.author.id in afk_users:
        del afk_users[message.author.id]
        await message.channel.send(f"👋 Welcome back {message.author.mention}, AFK status removed.", delete_after=5)

    for mention in message.mentions:
        if mention.id in afk_users:
            await message.reply(f"💤 {mention.name} is AFK: {afk_users[mention.id]}")

    # Anti-link Check
    if "http://" in message.content or "https://" in message.content:
        if not (message.author.id == OWNER_ID or message.author.id == ADMIN_ID or message.author.guild_permissions.manage_messages):
            await message.delete()
            await message.channel.send(f"🚫 {message.author.mention}, no links allowed!", delete_after=5)
            return

    # AI Chat via Mention (e.g., @bot hi)
    if bot.user in message.mentions and bot.chat_enabled:
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if prompt:
            async with message.channel.typing():
                try:
                    res = await ai_client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "system", "content": "You are a helpful and intelligent Discord bot."},
                                  {"role": "user", "content": prompt}]
                    )
                    await message.reply(res.choices[0].message.content)
                except:
                    pass

    await bot.process_commands(message)

# ==========================================
# 🤖 AI CHAT COMMANDS
# ==========================================
@bot.command()
async def chat(ctx, *, prompt: str):
    """Must use like: !chat hello"""
    if not bot.chat_enabled:
        return await ctx.send("❌ AI Chat is disabled.")
    async with ctx.typing():
        try:
            res = await ai_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": "You are a helpful and intelligent Discord bot."},
                          {"role": "user", "content": prompt}]
            )
            await ctx.reply(res.choices[0].message.content)
        except:
            await ctx.reply("AI is sleeping! Try later.")

@bot.command()
@commands.check(is_admin)
async def chatoff(ctx):
    bot.chat_enabled = False
    await ctx.send("🔇 AI Chat disabled.")

@bot.command()
@commands.check(is_admin)
async def chaton(ctx):
    bot.chat_enabled = True
    await ctx.send("🔊 AI Chat enabled.")

# ==========================================
# 📌 UTILITY COMMANDS (Ping, Info, etc.)
# ==========================================
@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Bot latency: **{latency}ms**")

@bot.command(aliases=['name'])
async def info(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"User Info - {member.name}", color=member.color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=False)
    embed.add_field(name="Joined", value=member.joined_at.strftime("%d %b %Y"), inline=True)
    await ctx.send(embed=embed)

@bot.command(aliases=['av'])
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(color=discord.Color.green())
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    embed = discord.Embed(title=f"{ctx.guild.name} Info", color=discord.Color.blue())
    embed.add_field(name="Members", value=ctx.guild.member_count)
    embed.add_field(name="Owner", value=ctx.guild.owner.mention)
    await ctx.send(embed=embed)

# ==========================================
# 🛠️ ADVANCED MODERATION & AUTO-INVITE
# ==========================================

@bot.command()
@commands.check(is_admin)
async def add(ctx, member: discord.Member):
    """!add @user দিলে তাকে ১ বার ব্যবহারযোগ্য ইনভাইট লিংক ডিএম করবে"""
    
    # ১. তোমার প্রাইভেট চ্যানেলের আইডি এখানে হার্ডকোড করো (ID কপি করে বসাও)
    PRIVATE_CHANNEL_ID = 1503655238446612540  # 👈 তোমার চ্যানেল আইডি এখানে দাও
    
    # ২. ওই স্পেসিফিক চ্যানেলের জন্য ১ বার ব্যবহারযোগ্য লিংক জেনারেট করা
    channel = bot.get_channel(PRIVATE_CHANNEL_ID)
    
    if channel is None:
        return await ctx.send("❌ হার্ডকোড করা চ্যানেল আইডিটি পাওয়া যায়নি! আইডি ঠিক করো।")

    try:
        # ১ বার ব্যবহারযোগ্য এবং ২৪ ঘণ্টা মেয়াদের ইনভাইট লিংক
        invite = await channel.create_invite(max_uses=1, unique=True, reason=f"Added by {ctx.author.name}")
        
        # ৩. ইউজারের ডিএম-এ ইনভাইট লিংক পাঠানো
        embed = discord.Embed(
            title="🚀 Exclusive Access Granted!",
            description=f"Hey {member.name}, তোমাকে আমাদের প্রাইভেট সেকশনে অ্যাক্সেস দেওয়া হয়েছে।",
            color=discord.Color.gold()
        )
        embed.add_field(name="Invite Link", value=f"{invite.url}", inline=False)
        embed.add_field(name="Note", value="এই লিংকটি মাত্র ১ বার ব্যবহার করা যাবে। দ্রুত জয়েন করো!", inline=False)
        embed.set_footer(text=f"Sent from {ctx.guild.name}")

        await member.send(embed=embed)
        await ctx.send(f"✅ {member.mention}-এর জন্য ১-টাইম ইনভাইট জেনারেট করে ডিএম করা হয়েছে!")
        
    except discord.Forbidden:
        await ctx.send(f"❌ {member.mention}-কে ডিএম করা যাচ্ছে না (Privacy Settings অন থাকতে হবে)।")
    except Exception as e:
        await ctx.send(f"❌ একটি এরর হয়েছে: {e}")

@bot.command()
@commands.check(is_admin)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    """!ban @user দিলে মেম্বারকে পার্মানেন্ট ব্যান করবে"""
    try:
        # ব্যানের আগে ইউজারকে ডিএম করে জানানো (অপশনাল)
        try:
            await member.send(f"🔨 You have been banned from **{ctx.guild.name}**.\n**Reason:** {reason}")
        except:
            pass # ডিএম না গেলে সমস্যা নেই
            
        await member.ban(reason=reason)
        
        embed = discord.Embed(
            title="🔨 Member Banned",
            description=f"**Target:** {member.mention}\n**Reason:** {reason}\n**Admin:** {ctx.author.mention}",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.utcnow()
        )
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ ব্যান করা সম্ভব হয়নি। চেক করো আমার রোল মেম্বারের রোলের উপরে কি না।")

@bot.command()
@commands.check(is_admin)
async def unban(ctx, *, member_id: int):
    """!unban <ID> দিলে ব্যান রিমুভ হবে"""
    try:
        user = await bot.fetch_user(member_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ User ID: `{member_id}` ({user.name}) এর ব্যান রিমুভ করা হয়েছে।")
    except:
        await ctx.send("❌ এই আইডিটি ব্যান লিস্টে পাওয়া যায়নি।")

# ==========================================
# 💎 PREMIUM / MOD COMMANDS
# ==========================================
@bot.command()
async def afk(ctx, *, reason="Away"):
    afk_users[ctx.author.id] = reason
    await ctx.send(f"✅ {ctx.author.mention} is AFK: {reason}")

@bot.command()
async def ticket(ctx):
    thread = await ctx.channel.create_thread(name=f"support-{ctx.author.name}", type=discord.ChannelType.private_thread)
    await thread.add_user(ctx.author)
    await thread.send(f"Hello {ctx.author.mention}, an admin will help you here.")
    await ctx.send("✅ Ticket created!", delete_after=5)

@bot.command()
@commands.check(is_admin)
async def poll(ctx, *, question):
    msg = await ctx.send(embed=discord.Embed(title="📊 Poll", description=question, color=discord.Color.gold()))
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

@bot.command()
@commands.check(is_admin)
async def create_access(ctx):
    invite = await ctx.channel.create_invite(max_uses=1, unique=True)
    async with bot.db.acquire() as conn:
        await conn.execute('INSERT INTO server_invites (code, uses) VALUES ($1, $2) ON CONFLICT (code) DO UPDATE SET uses = $2', invite.code, invite.uses)
    await ctx.send(f"Client Link (1 use): {invite.url}")

@bot.command()
@commands.check(is_admin)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"✅ Cleared {amount} messages!", delete_after=3)

@bot.command()
@commands.check(is_admin)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Channel Locked.")

@bot.command()
@commands.check(is_admin)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Channel Unlocked.")

# Error Handler
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Command incompleted! You missed something. Example: `!chat hello`")
    elif isinstance(error, commands.CommandNotFound):
        pass # Ignore unknown commands to keep console clean

bot.run(os.environ.get('DISCORD_TOKEN'))
