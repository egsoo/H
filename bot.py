import asyncio
import time
import os
import aiohttp
from datetime import datetime, timedelta, timezone
from pyrogram import Client, idle, filters, enums
import pyrogram
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiohttp import web
from motor.motor_asyncio import AsyncIOMotorClient

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MONGO_URL = os.environ.get("MONGO_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003560361279"))
MESSAGE_ID = int(os.environ.get("MESSAGE_ID", "387"))

# Database Setup
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["monitor_bot"]
bots_col = db["bots"]
config_col = db["config"]

app = Client("monitor", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Temporary storage for user input
user_data = {}

async def get_config():
    config = await config_col.find_one({"_id": "settings"})
    if not config:
        # Default settings
        config = {
            "_id": "settings", 
            "update_interval": 60,
            "channel_id": int(os.environ.get("CHANNEL_ID", "0")),
            "message_id": int(os.environ.get("MESSAGE_ID", "0"))
        }
        await config_col.insert_one(config)
    
    # Ensure all fields exist
    updated = False
    if "update_interval" not in config:
        config["update_interval"] = 60
        updated = True
    if "channel_id" not in config:
        config["channel_id"] = int(os.environ.get("CHANNEL_ID", "0"))
        updated = True
    if "message_id" not in config:
        config["message_id"] = int(os.environ.get("MESSAGE_ID", "0"))
        updated = True
    
    if updated:
        await config_col.replace_one({"_id": "settings"}, config)
    
    return config

def get_main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add URL", callback_data="add_bot"),
            InlineKeyboardButton("🤖 Manage URLs", callback_data="manage_bots")
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="settings"),
            InlineKeyboardButton("♻️ Refresh Channel", callback_data="refresh_now")
        ]
    ])

@app.on_message(filters.command("start"))
async def start_handler(client, message):
    if message.from_user.id != ADMIN_ID:
        await message.reply_text("I am alive!\n\nThis is monitoring bot for @username")
        return
    await message.reply_text("Welcome! Manage your monitoring URLs here:", reply_markup=get_main_menu())

@app.on_callback_query()
async def check_admin(client, callback_query):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("You are not authorized!", show_alert=True)
        return
    callback_query.continue_propagation()

@app.on_callback_query(filters.regex("^back_start$"))
async def back_start_callback(client, callback_query):
    await callback_query.edit_message_text("Welcome! Manage your monitoring URLs here:", reply_markup=get_main_menu())

async def check_service_simple(session, url, timeout):
    try:
        async with session.get(url, timeout=timeout) as r:
            return r.status == 200
    except:
        return False

@app.on_callback_query(filters.regex("^settings$"))
async def settings_callback(client, callback_query):
    config = await get_config()
    text = (
        "⚙️ **Settings**\n\n"
        f"**Update Interval:** `{config['update_interval']}s`\n"
        f"**Channel ID:** `{config['channel_id']}`\n"
        f"**Message ID:** `{config['message_id']}`"
    )
    buttons = [
        [InlineKeyboardButton("⏱️ Change Interval", callback_data="set_interval")],
        [
            InlineKeyboardButton("📢 Channel ID", callback_data="set_channel"),
            InlineKeyboardButton("💬 Message ID", callback_data="set_message")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="back_start")]
    ]
    await callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^set_channel$"))
async def set_channel_callback(client, callback_query):
    user_data[callback_query.from_user.id] = {"action": "setting_channel"}
    buttons = [[InlineKeyboardButton("🔙 Cancel", callback_data="settings")]]
    await callback_query.edit_message_text("Please send the new Channel ID (e.g., -100123456789):", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^set_message$"))
async def set_message_callback(client, callback_query):
    user_data[callback_query.from_user.id] = {"action": "setting_message"}
    buttons = [[InlineKeyboardButton("🔙 Cancel", callback_data="settings")]]
    await callback_query.edit_message_text("Please send the new Message ID (e.g., 123):", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^set_interval$"))
async def set_interval_callback(client, callback_query):
    user_data[callback_query.from_user.id] = {"action": "setting_interval"}
    buttons = [[InlineKeyboardButton("🔙 Cancel", callback_data="settings")]]
    await callback_query.edit_message_text("Please send the new interval in seconds (e.g., 60):", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^manage_bots$"))
async def manage_bots_callback(client, callback_query):
    bots = await bots_col.find().to_list(length=100)
    if not bots:
        await callback_query.answer("No URLs found!", show_alert=True)
        return
    
    config = await get_config()
    timeout = config.get("update_interval", 10)
    
    text = "**Select a URL to manage:**\n\n"
    buttons = []
    async with aiohttp.ClientSession() as session:
        for i, bot in enumerate(bots, 1):
            is_alive = await check_service_simple(session, bot["url"], timeout)
            status_emoji = "🟢" if is_alive else "🔴"
            text += f"> {i}. {bot['url']} {status_emoji}\n\n"
            buttons.append([InlineKeyboardButton(f"{status_emoji} {bot['name']}", callback_data=f"bot_{bot['_id']}")])
    
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="back_start")])
    await callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^bot_"))
async def bot_info_callback(client, callback_query):
    bot_id = callback_query.data.split("_")[1]
    from bson import ObjectId
    bot = await bots_col.find_one({"_id": ObjectId(bot_id)})
    
    if not bot:
        await callback_query.answer("URL not found!")
        return

    text = f"**URL Name:** `{bot['name']}`\n**URL:** `{bot['url']}`"
    is_maintenance = bot.get("maintenance", False)
    m_status = "ON 🛠️" if is_maintenance else "OFF ✅"
    buttons = [
        [
            InlineKeyboardButton("📝 Name", callback_data=f"edit_name_{bot_id}"),
            InlineKeyboardButton("🔗 URL", callback_data=f"edit_url_{bot_id}")
        ],
        [InlineKeyboardButton(f"🛠️ Maintenance: {m_status}", callback_data=f"toggle_maint_{bot_id}")],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_{bot_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="manage_bots")]
    ]
    await callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^toggle_maint_"))
async def toggle_maint_callback(client, callback_query):
    bot_id = callback_query.data.split("_")[2]
    from bson import ObjectId
    bot = await bots_col.find_one({"_id": ObjectId(bot_id)})
    if bot:
        new_state = not bot.get("maintenance", False)
        await bots_col.update_one({"_id": ObjectId(bot_id)}, {"$set": {"maintenance": new_state}})
        await callback_query.answer(f"Maintenance mode: {'ON' if new_state else 'OFF'}")
        await bot_info_callback(client, callback_query)

@app.on_callback_query(filters.regex("^add_bot$"))
async def add_bot_callback(client, callback_query):
    user_data[callback_query.from_user.id] = {"action": "adding_name"}
    buttons = [[InlineKeyboardButton("🔙 Cancel", callback_data="back_start")]]
    await callback_query.edit_message_text("Please send the URL name (e.g., Google):", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^edit_name_"))
async def edit_name_callback(client, callback_query):
    bot_id = callback_query.data.split("_")[2]
    user_data[callback_query.from_user.id] = {"action": "editing_name", "bot_id": bot_id}
    buttons = [[InlineKeyboardButton("🔙 Cancel", callback_data=f"bot_{bot_id}")]]
    await callback_query.edit_message_text("Please send the NEW URL name:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^edit_url_"))
async def edit_url_callback(client, callback_query):
    bot_id = callback_query.data.split("_")[2]
    user_data[callback_query.from_user.id] = {"action": "editing_url", "bot_id": bot_id}
    buttons = [[InlineKeyboardButton("🔙 Cancel", callback_data=f"bot_{bot_id}")]]
    await callback_query.edit_message_text("Please send the NEW health check URL:", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^delete_"))
async def delete_bot_callback(client, callback_query):
    bot_id = callback_query.data.split("_")[1]
    from bson import ObjectId
    await bots_col.delete_one({"_id": ObjectId(bot_id)})
    await callback_query.answer("URL deleted!")
    await manage_bots_callback(client, callback_query)

@app.on_callback_query(filters.regex("^back_start$"))
async def back_start_callback(client, callback_query):
    await callback_query.edit_message_text("Welcome! Manage your monitoring URLs here:", reply_markup=get_main_menu())

@app.on_callback_query(filters.regex("^refresh_now$"))
async def refresh_now_callback(client, callback_query):
    await callback_query.answer("this is Health check massage !!", show_alert=True)
    if callback_query.message.chat.type == enums.ChatType.PRIVATE:
        asyncio.create_task(run_manual_update())

async def run_manual_update():
    async with aiohttp.ClientSession() as session:
        config = await get_config()
        timeout = config.get("update_interval", 60)
        channel_id = config.get("channel_id")
        message_id = config.get("message_id")
        bots = await bots_col.find().to_list(length=100)
        
        if not bots:
            text = "<blockquote>❤️ᴏғғɪᴄɪᴧʟ ʙσᴛs:\n\nNo URLs configured.</blockquote>"
        else:
            tasks = [check_service(session, b["name"], b["url"], timeout, b.get("maintenance", False)) for b in bots]
            results = await asyncio.gather(*tasks)
            content = "\n\n".join(results)
            text = f"<blockquote>❤️ᴏғғɪᴄɪᴧʟ ʙσᴛs:\n\n{content}</blockquote>"
        
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist).strftime('%H:%M:%S')
        text += f"\n\nLast update: {now_ist}"
        try:
            await app.edit_message_text(channel_id, message_id, text, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            print("Manual update failed:", e)

@app.on_message(filters.private & ~filters.command("start"))
async def handle_text(client, message):
    if message.from_user.id != ADMIN_ID:
        return
    user_id = message.from_user.id
    if user_id not in user_data:
        return

    action = user_data[user_id].get("action")
    
    if action == "adding_name":
        user_data[user_id]["name"] = message.text
        user_data[user_id]["action"] = "adding_url"
        await message.reply("Now send the health check URL:")
    
    elif action == "adding_url":
        name = user_data[user_id]["name"]
        url = message.text
        await bots_col.insert_one({"name": name, "url": url})
        del user_data[user_id]
        await message.reply(f"URL `{name}` added successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_start")]]))
    
    elif action == "editing_name":
        bot_id = user_data[user_id]["bot_id"]
        from bson import ObjectId
        await bots_col.update_one({"_id": ObjectId(bot_id)}, {"$set": {"name": message.text}})
        del user_data[user_id]
        await message.reply("Name updated successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="manage_bots")]]))

    elif action == "editing_url":
        bot_id = user_data[user_id].get("bot_id")
        from bson import ObjectId
        await bots_col.update_one({"_id": ObjectId(bot_id)}, {"$set": {"url": message.text}})
        del user_data[user_id]
        await message.reply("URL updated successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="manage_bots")]]))

    elif action == "setting_interval":
        try:
            val = int(message.text)
            if val < 30 or val > 1800:
                await message.reply("Interval must be between 30 seconds and 1800 seconds (30 min).")
                return
            await config_col.update_one({"_id": "settings"}, {"$set": {"update_interval": val}}, upsert=True)
            del user_data[user_id]
            await message.reply(f"Interval set to {val}s!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings")]]))
        except ValueError:
            await message.reply("Please send a valid number.")

    elif action == "setting_channel":
        try:
            val = int(message.text)
            await config_col.update_one({"_id": "settings"}, {"$set": {"channel_id": val}}, upsert=True)
            del user_data[user_id]
            await message.reply(f"Channel ID updated to `{val}`!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings")]]))
        except ValueError:
            await message.reply("Please send a valid number.")

    elif action == "setting_message":
        try:
            val = int(message.text)
            await config_col.update_one({"_id": "settings"}, {"$set": {"message_id": val}}, upsert=True)
            del user_data[user_id]
            await message.reply(f"Message ID updated to `{val}`!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings")]]))
        except ValueError:
            await message.reply("Please send a valid number.")

async def check_service(session, name, url, timeout, maintenance=False):
    if maintenance:
        return f"╭⎋ {name}  \n╰⊚ ᴍᴧɪɴᴛᴇɴᴧɴᴄᴇ 🛠️"
    start_time = time.time()
    try:
        async with session.get(url, timeout=timeout) as r:
            elapsed = round((time.time() - start_time) * 1000)
            if r.status == 200:
                return f"╭⎋ {name}  \n╰⊚ ᴀʟɪᴠᴇ  🟢 ({elapsed}ms)"
            return f"╭⎋ {name}  \n╰⊚ Not working 🔴 ({r.status})"
    except Exception as e:
        return f"╭⎋ {name}  \n╰⊚ Not working 🔴 (Error)"

async def updater():
    async with aiohttp.ClientSession() as session:
        while True:
            config = await get_config()
            interval = config.get("update_interval", 60)
            channel_id = config.get("channel_id")
            message_id = config.get("message_id")
            timeout = interval
            
            bots = await bots_col.find().to_list(length=100)
            if not bots:
                text = "<blockquote>❤️ᴏғғɪᴄɪᴧʟ ʙσᴛs:\n\nNo URLs configured.</blockquote>"
            else:
                tasks = [check_service(session, b["name"], b["url"], timeout, b.get("maintenance", False)) for b in bots]
                results = await asyncio.gather(*tasks)
                content = "\n\n".join(results)
                text = f"<blockquote>❤️ᴏғғɪᴄɪᴧʟ ʙσᴛs:\n\n{content}</blockquote>"
            
            ist = timezone(timedelta(hours=5, minutes=30))
            now_ist = datetime.now(ist).strftime('%H:%M:%S')
            text += f"\n\nLast update: {now_ist}"
            try:
                if channel_id and message_id:
                    await app.edit_message_text(channel_id, message_id, text, parse_mode=enums.ParseMode.HTML)
            except Exception as e:
                print("Update failed:", e)
            
            await asyncio.sleep(interval)

async def health_check(request):
    bots = await bots_col.find().to_list(length=100)
    config = await get_config()
    timeout = config.get("update_interval", 60)
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Service Status Page</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #0f172a; color: white; display: flex; flex-direction: column; align-items: center; padding: 20px; }
            .container { width: 100%; max-width: 600px; }
            h1 { color: #38bdf8; text-align: center; }
            .service-card { background: #1e293b; padding: 15px; border-radius: 12px; margin-bottom: 15px; border-left: 5px solid #64748b; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
            .alive { border-left-color: #22c55e; }
            .dead { border-left-color: #ef4444; }
            .maint { border-left-color: #f59e0b; }
            .header { display: flex; justify-content: space-between; align-items: center; }
            .name { font-weight: bold; font-size: 1.1em; }
            .status { font-size: 0.9em; padding: 4px 8px; border-radius: 6px; text-transform: uppercase; }
            .status-alive { background: #14532d; color: #4ade80; }
            .status-dead { background: #450a0a; color: #f87171; }
            .status-maint { background: #451a03; color: #fbbf24; }
            .url { color: #94a3b8; font-size: 0.85em; margin-top: 5px; word-break: break-all; }
            .footer { margin-top: 20px; font-size: 0.8em; color: #64748b; text-align: center; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>❤️ᴏғғɪᴄɪᴧʟ ʙσᴛs Status</h1>
    """
    
    async with aiohttp.ClientSession() as session:
        for bot in bots:
            if bot.get("maintenance", False):
                status_class = "maint"
                status_text = "Maintenance 🛠️"
                status_label = "status-maint"
            else:
                is_alive = await check_service_simple(session, bot["url"], timeout)
                status_class = "alive" if is_alive else "dead"
                status_text = "Alive 🟢" if is_alive else "Down 🔴"
                status_label = "status-alive" if is_alive else "status-dead"
            
            html += f"""
            <div class="service-card {status_class}">
                <div class="header">
                    <span class="name">{bot['name']}</span>
                    <span class="status {status_label}">{status_text}</span>
                </div>
                <div class="url">{bot['url']}</div>
            </div>
            """
    
    ist = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist).strftime('%Y-%m-%d %H:%M:%S')
    html += f"""
            <div class="footer">
                Last update: {now_ist} IST<br>
                Monitoring bot for @username
            </div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type='text/html')

async def main():
    server = web.Application()
    server.router.add_get("/", health_check)
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    asyncio.create_task(site.start())
    
    async with app:
        asyncio.create_task(updater())
        await idle()

if __name__ == "__main__":
    app.run(main())
