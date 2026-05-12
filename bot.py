import os
import discord
from discord.ext import commands, tasks
import asyncpg
from openai import AsyncOpenAI
from dotenv import load_dotenv
import datetime
import asyncio
import secrets

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

PAID_ROLE_ID = 1503661161089073243  # 👈 Paid Role ID
PAID_CHANNEL_LINK = "https://discord.com/channels/1498333809907601480/1503655238446612540"  # 👈 Paid Channel Link
MAIN_SERVER_LINK = "https://discord.gg/D9QV3MS64" # 👈 তোমার মেইন সার্ভারের ইনভাইট লিংক

# 🆕 নতুন চ্যানেল আইডি গুলো এখানে বসাও
LOGS_CHANNEL_ID = 1503679373184860301  # 👈 তোমার Log Channel ID এখানে দাও
ADMIN_CHANNEL_ID = 1503653140988166174 # 👈 তোমার Admin Control Channel ID এখানে দাও

bot.chat_enabled = True
afk_users = {}
sniped_messages = {}

# UI/UX Colors (Aura / Cyberpunk Vibe)
NEON_CYAN = 0x00FFCC
NEON_PURPLE = 0x8A2BE2
ERROR_RED = 0xFF003C

ai_client = AsyncOpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")

def is_admin(ctx):
    return ctx.author.id == OWNER_ID or ctx.author.id == ADMIN_ID or ctx.author.guild_permissions.administrator

def is_admin_user(user):
    # ইন্টার‍্যাকশন বাটন চেকের জন্য
    return user.id == OWNER_ID or user.id == ADMIN_ID or getattr(user.guild_permissions, 'administrator', False)

# ==========================================
# 🗄️ DATABASE & EVENTS
# ==========================================
async def init_db():
    bot.db = await asyncpg.create_pool(os.environ.get("DATABASE_URL"))
    async with bot.db.acquire() as conn:
        # Create tables for invites and pending users
        await conn.execute('CREATE TABLE IF NOT EXISTS server_invites (code TEXT PRIMARY KEY, uses INTEGER)')
        await conn.execute('CREATE TABLE IF NOT EXISTS pending_users (user_id BIGINT PRIMARY KEY)')
        
        # 🆕 ওয়েবসাইটের স্টুডেন্টদের জন্য ডাটাবেস টেবিল
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS website_users (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100),
                phone VARCHAR(30),
                whatsapp VARCHAR(30),
                discord_username VARCHAR(100),
                payment_method VARCHAR(20),
                sender_number VARCHAR(20),
                trx_id VARCHAR(100),
                amount INTEGER DEFAULT 1000,
                user_token VARCHAR(50) UNIQUE,
                status VARCHAR(20) DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

@tasks.loop(minutes=5)
async def update_status():
    for guild in bot.guilds:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{guild.member_count} Members 🌐"))

@bot.event
async def on_ready():
    await init_db()
    update_status.start()
    print(f'⚡ Bot {bot.user.name} is ONLINE and Ready to Serve! 🚀')

@bot.event
async def on_message_delete(message):
    if not message.author.bot:
        sniped_messages[message.channel.id] = {
            "content": message.content,
            "author": message.author,
            "time": datetime.datetime.utcnow()
        }

@bot.event
async def on_member_join(member):
    # 🌟 Auto-detect Pending Users when they join
    async with bot.db.acquire() as conn:
        record = await conn.fetchrow('SELECT user_id FROM pending_users WHERE user_id = $1', member.id)
        
        if record:
            paid_role = member.guild.get_role(PAID_ROLE_ID)
            if paid_role:
                try:
                    await member.add_roles(paid_role, reason="Auto-assigned pending premium access")
                    
                    # DM the customer professionally
                    embed = discord.Embed(
                        title="💎 Premium Enrollment Successful!",
                        description=f"Welcome {member.name}! আমাদের মেইন সার্ভারে জয়েন করার জন্য ধন্যবাদ।\n\n"
                                    f"✅ তোমার অ্যাকাউন্টে **Paid Access** অ্যাক্টিভ করা হয়েছে।\n"
                                    f"এখন নিচে দেওয়া লিংকে ক্লিক করে আমাদের পেইড চ্যানেলে এনরোল করো:\n\n"
                                    f"🔗 **[Enter Paid Channel Here]({PAID_CHANNEL_LINK})**",
                        color=NEON_CYAN
                    )
                    embed.add_field(name="👑 Bot Owner & Admin", value=f"Ononto Hasan (<@{OWNER_ID}>)", inline=False)
                    embed.set_footer(text=f"Secured Access Provided by {member.guild.name}")
                    
                    await member.send(embed=embed)
                    
                    # Remove user from pending list after success
                    await conn.execute('DELETE FROM pending_users WHERE user_id = $1', member.id)
                except Exception as e:
                    print(f"Error assigning role/DMing pending user: {e}")

@bot.event
async def on_message(message):
    if message.author == bot.user: return

    if message.author.id in afk_users:
        del afk_users[message.author.id]
        await message.channel.send(f"👋 Welcome back {message.author.mention}, AFK status removed.", delete_after=5)

    for mention in message.mentions:
        if mention.id in afk_users:
            await message.reply(f"💤 {mention.name} is currently AFK: {afk_users[mention.id]}")

    if "http://" in message.content or "https://" in message.content:
        if not (message.author.id == OWNER_ID or message.author.id == ADMIN_ID or message.author.guild_permissions.manage_messages):
            await message.delete()
            await message.channel.send(f"🚫 {message.author.mention}, links are not allowed here!", delete_after=5)
            return

    if bot.user in message.mentions and bot.chat_enabled:
        prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if prompt:
            async with message.channel.typing():
                try:
                    res = await ai_client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "system", "content": "You are a helpful and elite Discord AI bot."},
                                  {"role": "user", "content": prompt}]
                    )
                    await message.reply(res.choices[0].message.content)
                except:
                    pass

    await bot.process_commands(message)

# ==========================================
# 💎 SMART PREMIUM ACCESS COMMAND (!add)
# ==========================================
@bot.command()
@commands.check(is_admin)
async def add(ctx, user_input: str):
    """!add <ID> দিলে সার্ভারে থাকলে রোল দেবে, না থাকলে Pending লিস্টে রাখবে"""
    
    # ID Extract from mention or raw ID
    try:
        user_id = int(user_input.strip("<@!>"))
    except ValueError:
        return await ctx.send("❌ Error: অনুগ্রহ করে সঠিক ইউজার আইডি বা মেনশন দাও!")

    paid_role = ctx.guild.get_role(PAID_ROLE_ID)
    if paid_role is None:
        return await ctx.send("❌ Error: PAID_ROLE_ID ঠিকমতো সেট করা নেই!")

    # Check if user is already in the server
    member = ctx.guild.get_member(user_id)

    if member:
        # User is in server, assign role immediately
        try:
            await member.add_roles(paid_role, reason=f"Premium access granted by {ctx.author.name}")

            embed = discord.Embed(
                title="🚀 Premium Access Granted!",
                description=f"Hey {member.name}, তোমাকে আমাদের পেইড সেকশনে অ্যাক্সেস দেওয়া হয়েছে।\n\n"
                            f"✅ তুমি এখন পেইড চ্যানেলগুলোতে মেসেজ করতে ও দেখতে পারবে।\n\n"
                            f"🔗 **[Click Here to Enter the Paid Channel]({PAID_CHANNEL_LINK})**",
                color=NEON_CYAN
            )
            embed.add_field(name="👑 Bot Owner & Admin", value=f"Ononto Hasan (<@{OWNER_ID}>)", inline=False)
            embed.set_footer(text=f"Sent from {ctx.guild.name}")

            dm_sent = True
            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                dm_sent = False 

            if dm_sent:
                await ctx.send(f"✅ **Success!** {member.mention} অলরেডি সার্ভারে ছিল। তাকে `{paid_role.name}` দেওয়া হয়েছে এবং পেইড লিংক DM করা হয়েছে।")
            else:
                await ctx.send(f"✅ **Success!** {member.mention}-কে রোল দেওয়া হয়েছে (কিন্তু ইউজারের DM অফ থাকায় লিংক যায়নি)।")
        except discord.Forbidden:
            await ctx.send("❌ আমার কাছে মেম্বারকে রোল দেওয়ার পারমিশন নেই!")
    
    else:
        # User is NOT in the server (Save to Pending Database)
        try:
            async with bot.db.acquire() as conn:
                await conn.execute('INSERT INTO pending_users (user_id) VALUES ($1) ON CONFLICT DO NOTHING', user_id)
            
            embed = discord.Embed(
                title="⏳ User Added to Pending List",
                description=f"ইউজার (<@{user_id}>) এখনো সার্ভারে জয়েন করেনি।\n"
                            f"আমি তাকে **Pending** লিস্টে সেভ করে রেখেছি।\n\n"
                            f"**কাস্টমারকে নিচের লিংকটি কপি করে দাও:**\n"
                            f"> **১ম ধাপ:** আগে সার্ভারে জয়েন করুন:\n> {MAIN_SERVER_LINK}\n\n"
                            f"**নোট:** কাস্টমার সার্ভারে জয়েন করলেই বট অটোমেটিক তাকে রোল দিয়ে পেইড চ্যানেলের লিংক DM করে দেবে!",
                color=NEON_PURPLE
            )
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ ডাটাবেস এরর: {e}")

@bot.command()
@commands.check(is_admin)
async def create_access(ctx):
    """১ বার ব্যবহারযোগ্য ইনভাইট লিংক তৈরি করবে"""
    invite = await ctx.channel.create_invite(max_uses=1, unique=True, reason=f"Access created by {ctx.author.name}")
    try:
        async with bot.db.acquire() as conn:
            await conn.execute('INSERT INTO server_invites (code, uses) VALUES ($1, $2) ON CONFLICT (code) DO UPDATE SET uses = $2', invite.code, invite.uses)
    except Exception as e:
        print(f"Database Error: {e}")
        
    embed = discord.Embed(
        title="🔗 Client Access Link Created",
        description=f"**1-Use Limit Link:**\n{invite.url}",
        color=NEON_PURPLE
    )
    embed.set_footer(text=f"Generated for {ctx.channel.name}")
    await ctx.send(embed=embed)

# ==========================================
# 🆕 WEBSITE ADMIN CONTROL (APPROVE/REJECT UI)
# ==========================================
class ApprovalView(discord.ui.View):
    def __init__(self, user_db_id, bot):
        super().__init__(timeout=None)
        self.user_db_id = user_db_id
        self.bot = bot

    @discord.ui.button(label="Approve Student", style=discord.ButtonStyle.success, custom_id="btn_approve", emoji="✅")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_user(interaction.user): 
            return await interaction.response.send_message("❌ Access Denied! শুধু এডমিনরাই এক্সেস দিতে পারবে।", ephemeral=True)
        
        async with self.bot.db.acquire() as conn:
            await conn.execute("UPDATE website_users SET status = 'Approved' WHERE id = $1", self.user_db_id)
        
        await interaction.message.edit(content=f"✅ **Approved by {interaction.user.mention}!**", view=None)
        await interaction.response.send_message("স্টুডেন্টকে Approve করা হয়েছে!", ephemeral=True)
        
        # Log to log channel
        log_channel = self.bot.get_channel(LOGS_CHANNEL_ID)
        if log_channel:
            await log_channel.send(f"🎉 **New Student Enrolled!**\n> Database ID: `{self.user_db_id}`\n> Approved by: {interaction.user.mention}")

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, custom_id="btn_reject", emoji="❌")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_admin_user(interaction.user): 
            return await interaction.response.send_message("❌ Access Denied!", ephemeral=True)
        
        async with self.bot.db.acquire() as conn:
            await conn.execute("UPDATE website_users SET status = 'Rejected' WHERE id = $1", self.user_db_id)
        
        await interaction.message.edit(content=f"❌ **Rejected by {interaction.user.mention}!**", view=None)
        await interaction.response.send_message("স্টুডেন্টকে Reject করা হয়েছে!", ephemeral=True)

@bot.command()
@commands.check(is_admin)
async def fetch_pending(ctx):
    """ওয়েবসাইটের সব Pending রিকোয়েস্ট ডিসকর্ডে দেখাবে"""
    async with bot.db.acquire() as conn:
        records = await conn.fetch("SELECT id, name, discord_username, payment_method, trx_id, sender_number FROM website_users WHERE status = 'Pending'")
        
        if not records:
            return await ctx.send("✅ কোন Pending রিকোয়েস্ট নেই!")
            
        for row in records:
            embed = discord.Embed(title="📝 New Web Registration", color=0xf39c12)
            embed.add_field(name="Name", value=row['name'], inline=True)
            embed.add_field(name="Discord", value=row['discord_username'], inline=True)
            embed.add_field(name="Payment", value=f"{row['payment_method']}\nNumber: {row['sender_number']}\nTrx: {row['trx_id']}", inline=False)
            
            view = ApprovalView(user_db_id=row['id'], bot=bot)
            await ctx.send(embed=embed, view=view)

# ==========================================
# 📣 ANNOUNCEMENT COMMANDS
# ==========================================
@bot.command()
@commands.check(is_admin)
async def announce(ctx, channel: discord.TextChannel, *, message: str):
    """!announce #channel তোমার মেসেজ"""
    embed = discord.Embed(title="📢 Announcement", description=message, color=NEON_CYAN)
    embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else None)
    embed.set_footer(text=f"Announced by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
    
    msg = await channel.send(embed=embed)
    await ctx.send(f"✅ Announcement sent to {channel.mention}! Message ID: `{msg.id}`")

@bot.command()
@commands.check(is_admin)
async def delete_announce(ctx, channel: discord.TextChannel, message_id: int):
    """!delete_announce #channel <message_id>"""
    try:
        msg = await channel.fetch_message(message_id)
        await msg.delete()
        await ctx.send("🗑️ Announcement deleted successfully!")
    except discord.NotFound:
        await ctx.send("❌ Message ID খুঁজে পাওয়া যায়নি!")
    except discord.Forbidden:
        await ctx.send("❌ আমার মেসেজ ডিলেট করার পারমিশন নেই!")

# ==========================================
# 🛡️ ADMIN & MODERATION COMMANDS
# ==========================================
@bot.command()
@commands.check(is_admin)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(embed=discord.Embed(title="🔒 Channel Locked", description="এই চ্যানেলে এখন শুধু এডমিনরা মেসেজ দিতে পারবে।", color=ERROR_RED))

@bot.command()
@commands.check(is_admin)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send(embed=discord.Embed(title="🔓 Channel Unlocked", description="চ্যানেলটি সবার জন্য উন্মুক্ত করা হয়েছে।", color=NEON_CYAN))

@bot.command()
@commands.check(is_admin)
async def slowmode(ctx, seconds: int):
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"⏳ Slowmode set to **{seconds} seconds**.")

@bot.command()
@commands.check(is_admin)
async def poll(ctx, *, question):
    embed = discord.Embed(title="📊 Server Poll", description=question, color=NEON_PURPLE)
    embed.set_footer(text=f"Poll created by {ctx.author.name}")
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

@bot.command(aliases=['purge'])
@commands.check(is_admin)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"✅ Cleared {amount} messages!", delete_after=3)

@bot.command()
@commands.check(is_admin)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason="No reason"):
    duration = datetime.timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"🔇 {member.mention} timed out for **{minutes}m**. Reason: {reason}")

@bot.command()
@commands.check(is_admin)
async def ban(ctx, member: discord.Member, *, reason="No reason"):
    await member.ban(reason=reason)
    await ctx.send(embed=discord.Embed(title="🔨 Banned", description=f"{member.mention} has been banned.", color=ERROR_RED))

# ==========================================
# 📌 UTILITIES & USER COMMANDS
# ==========================================
@bot.command()
async def ticket(ctx):
    thread = await ctx.channel.create_thread(name=f"ticket-{ctx.author.name}", type=discord.ChannelType.private_thread)
    await thread.add_user(ctx.author)
    embed = discord.Embed(title="🎟️ Support Ticket", description=f"Hello {ctx.author.mention}, এডমিনরা খুব শিগগিরই এখানে রিপ্লাই দেবে। তোমার সমস্যাটি বিস্তারিত লিখে রাখো।", color=NEON_CYAN)
    await thread.send(embed=embed)
    await ctx.send(f"✅ Ticket created! Please check your threads.", delete_after=5)

@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Bot latency: **{latency}ms**")

@bot.command(aliases=['av'])
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(color=NEON_PURPLE)
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(aliases=['userinfo'])
async def info(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"User Info - {member.name}", color=NEON_CYAN)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=False)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%d %b %Y"), inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%d %b %Y"), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    embed = discord.Embed(title=f"🏢 {ctx.guild.name} Server Info", color=NEON_CYAN)
    if ctx.guild.icon: embed.set_thumbnail(url=ctx.guild.icon.url)
    embed.add_field(name="👑 Owner", value=ctx.guild.owner.mention, inline=True)
    embed.add_field(name="👥 Members", value=ctx.guild.member_count, inline=True)
    embed.add_field(name="📅 Created On", value=ctx.guild.created_at.strftime("%d %b %Y"), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def snipe(ctx):
    if ctx.channel.id in sniped_messages:
        msg = sniped_messages[ctx.channel.id]
        embed = discord.Embed(description=msg["content"], color=ERROR_RED, timestamp=msg["time"])
        embed.set_author(name=msg["author"], icon_url=msg["author"].display_avatar.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ No recently deleted messages to snipe!")

@bot.command()
async def afk(ctx, *, reason="Away"):
    afk_users[ctx.author.id] = reason
    await ctx.send(f"✅ {ctx.author.mention} is AFK: {reason}")

# ==========================================
# 🤖 AI COMMANDS & CUSTOM HELP
# ==========================================
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="🤖 Bot Command Menu", description="Here are all the available commands:", color=NEON_CYAN)
    
    embed.add_field(name="👑 Admin Commands", value="`!add <User_ID>` - Give paid access (Smart)\n`!fetch_pending` - Approve Web Users 🆕\n`!announce #channel <msg>` - Send Announcement 🆕\n`!delete_announce #channel <id>` - Delete Announcement 🆕\n`!create_access` - Generate 1-use invite\n`!lock` / `!unlock` - Manage channels\n`!slowmode <sec>` - Set slowmode\n`!clear <num>` - Delete messages\n`!timeout @user <min>` - Mute user\n`!ban @user` - Ban user\n`!poll <question>` - Start poll", inline=False)
    
    embed.add_field(name="📌 Utility Commands", value="`!ticket` - Open support ticket\n`!serverinfo` - Server stats\n`!info [@user]` - User info\n`!avatar [@user]` - Profile picture\n`!ping` - Bot latency\n`!snipe` - See deleted message\n`!afk <reason>` - Set AFK status", inline=False)
    
    embed.add_field(name="🤖 AI Commands", value="`@bot <message>` - Talk directly\n`!chatoff` / `!chaton` - Toggle AI (Admin)", inline=False)
    
    embed.set_footer(text=f"Developed by Ononto Hasan")
    await ctx.send(embed=embed)

@bot.command()
@commands.check(is_admin)
async def chatoff(ctx):
    bot.chat_enabled = False
    await ctx.send("🔇 AI Chat disabled.")

@bot.command()
@commands.check(is_admin)
async def gencoupon(ctx, percentage: str):
    """!gencoupon 10% - ডিসকাউন্ট কুপন তৈরি করবে"""
    # % সাইন রিমুভ করে শুধু ইন্টিজার নেওয়া হচ্ছে
    try:
        discount_val = int(percentage.replace('%', ''))
    except ValueError:
        return await ctx.send("❌ Error: সঠিক পার্সেন্টেজ দাও! (Example: !gencoupon 10%)")
    
    # Generate random code: DISC-XYZ123
    code = f"DISC-{secrets.token_hex(3).upper()}"
    
    try:
        async with bot.db.acquire() as conn:
            await conn.execute('INSERT INTO coupons (code, discount) VALUES ($1, $2)', code, discount_val)
        
        embed = discord.Embed(title="🎟️ Discount Coupon Generated!", color=NEON_CYAN)
        embed.add_field(name="Coupon Code", value=f"`{code}`", inline=False)
        embed.add_field(name="Discount", value=f"**{discount_val}% OFF**", inline=False)
        embed.set_footer(text=f"Generated by {ctx.author.name}")
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Database Error: {e}")

@bot.command()
@commands.check(is_admin)
async def chaton(ctx):
    bot.chat_enabled = True
    await ctx.send("🔊 AI Chat enabled.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=discord.Embed(description="❌ কমান্ডটি অসম্পূর্ণ! তুমি কিছু বাদ দিয়েছো।", color=ERROR_RED))
    elif isinstance(error, commands.CommandNotFound):
        pass

# ==========================================
# 🌐 RUN FLASK WEBSITE & BOT TOGETHER
# ==========================================
from threading import Thread
from app import app as flask_app

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    # ওয়েবসাইট রান হবে থ্রেডের মাধ্যমে
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)

if __name__ == "__main__":
    # Flask কে ব্যাকগ্রাউন্ডে চালু করা হচ্ছে
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Discord Bot কে মেইন থ্রেডে চালু করা হচ্ছে
    bot.run(os.environ.get('DISCORD_TOKEN'))
