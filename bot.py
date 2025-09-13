import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions, ChatMember
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# ====== GHI THẲNG TOKEN Ở ĐÂY ======
BOT_TOKEN = "GHI THẲNG TOKEN Ở ĐÂY "

CONFIG_FILE = "config.json"

def load_config():
    """Tải cấu hình: thời gian mute & danh sách từ cấm."""
    cfg = {
        "mute_minutes": 10,
        "banned_words": ["spam", "quảng cáo", "link lừa đảo"]
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                file_cfg = json.load(f)
                if isinstance(file_cfg, dict):
                    cfg["mute_minutes"] = file_cfg.get("mute_minutes", cfg["mute_minutes"])
                    bw = file_cfg.get("banned_words", [])
                    if isinstance(bw, list) and bw:
                        cfg["banned_words"] = bw
        except Exception:
            pass
    return cfg

def save_config(cfg):
    """Lưu cấu hình xuống file (để lệnh admin có tác dụng lâu dài)."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Save config failed: {e}")

CONFIG = load_config()

# ---------- Helpers ----------
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return chat_member.status in [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except Exception:
        return False

def extract_text_from_message(update: Update) -> str | None:
    """
    Lấy nội dung chữ từ mọi loại tin:
    - Tin nhắn text: message.text
    - Media có chú thích: message.caption (ảnh/video/document/animation/audio...)
    """
    msg = update.effective_message
    if not msg:
        return None
    if msg.text:
        return msg.text
    if msg.caption:
        return msg.caption
    return None

def text_has_banned_word(text: str) -> str | None:
    if not text:
        return None
    low = text.lower()
    for w in CONFIG["banned_words"]:
        w_norm = str(w).strip().lower()
        if w_norm and w_norm in low:
            return w
    return None

async def send_and_autodelete(chat, text: str, seconds: int = 10, **kwargs):
    """Gửi tin nhắn và tự xoá sau 'seconds' giây."""
    try:
        m = await chat.send_message(text, **kwargs)
        await asyncio.sleep(seconds)
        try:
            await m.delete()
        except Exception:
            pass
    except Exception as e:
        print(f"send_and_autodelete error: {e}")

# ---------- Core xử lý tin ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or msg.from_user is None:
        return

    # Bỏ qua lệnh; lệnh để CommandHandler xử lý
    text = extract_text_from_message(update)
    if not text:
        return

    # Bỏ qua admin (tùy nhu cầu: nếu muốn phạt cả admin thì xoá block này)
    if await is_admin(update, context, msg.from_user.id):
        return

    matched = text_has_banned_word(text)
    if matched:
        # 1) Xoá tin nhắn vi phạm
        try:
            await msg.delete()
        except Exception as e:
            print(f"Delete failed: {e}")

        # 2) Mute người vi phạm (v21: chỉ cần can_send_messages=False)
        mute_minutes = int(CONFIG.get("mute_minutes", 10))
        until = datetime.now(tz=timezone.utc) + timedelta(minutes=mute_minutes)
        perms_block = ChatPermissions(can_send_messages=False)

        try:
            await context.bot.restrict_chat_member(
                chat_id=update.effective_chat.id,
                user_id=msg.from_user.id,
                permissions=perms_block,
                until_date=until
            )
            # 3) Thông báo (tự xoá sau 10s)
            await send_and_autodelete(
                msg.chat,
                f"⚠️ @{msg.from_user.username or msg.from_user.id} "
                f"đã bị cấm chat {mute_minutes} phút vì dùng từ cấm: “{matched}”.",
                seconds=10
            )
        except Exception as e:
            print(f"Restrict failed: {e}")

# ---------- Admin commands ----------
async def addword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context, update.effective_user.id):
        return
    if not context.args:
        await send_and_autodelete(update.effective_chat, "Cách dùng: /addword từ_cấm")
        return
    word = " ".join(context.args).strip()
    if word.lower() in [w.lower() for w in CONFIG["banned_words"]]:
        await send_and_autodelete(update.effective_chat, f"“{word}” đã có trong danh sách.")
        return
    CONFIG["banned_words"].append(word)
    save_config(CONFIG)
    await send_and_autodelete(update.effective_chat, f"✅ Đã thêm từ cấm: “{word}”")

async def delword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context, update.effective_user.id):
        return
    if not context.args:
        await send_and_autodelete(update.effective_chat, "Cách dùng: /delword từ_cấm")
        return
    word = " ".join(context.args).strip().lower()
    before = len(CONFIG["banned_words"])
    CONFIG["banned_words"] = [w for w in CONFIG["banned_words"] if str(w).lower() != word]
    save_config(CONFIG)
    if len(CONFIG["banned_words"]) < before:
        await send_and_autodelete(update.effective_chat, f"🗑️ Đã xoá: “{word}”")
    else:
        await send_and_autodelete(update.effective_chat, f"Không tìm thấy: “{word}”")

async def listwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context, update.effective_user.id):
        return
    words = CONFIG.get("banned_words", [])
    if not words:
        await send_and_autodelete(update.effective_chat, "Danh sách từ cấm đang trống.")
    else:
        items = "\n".join(f"• {w}" for w in words)
        await send_and_autodelete(update.effective_chat, f"📄 Danh sách từ cấm:\n{items}")

async def setmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context, update.effective_user.id):
        return
    if not context.args:
        await send_and_autodelete(update.effective_chat, "Cách dùng: /setmute số_phút (vd: /setmute 30)")
        return
    try:
        minutes = int(context.args[0])
        if minutes < 1 or minutes > 7 * 24 * 60:
            raise ValueError
        CONFIG["mute_minutes"] = minutes
        save_config(CONFIG)
        await send_and_autodelete(update.effective_chat, f"⏱️ Thời gian cấm chat: {minutes} phút.")
    except ValueError:
        await send_and_autodelete(update.effective_chat, "Số phút không hợp lệ.")

def extract_target_user_id(update: Update) -> int | None:
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        return msg.reply_to_message.from_user.id
    return None

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context, update.effective_user.id):
        return
    target_id = extract_target_user_id(update)
    if not target_id:
        await send_and_autodelete(update.effective_chat, "Hãy reply vào tin nhắn của người cần gỡ cấm rồi gửi /unmute.")
        return
    perms_allow = ChatPermissions(can_send_messages=True)
    try:
        await context.bot.restrict_chat_member(
            chat_id=update.effective_chat.id,
            user_id=target_id,
            permissions=perms_allow,
            until_date=0
        )
        await send_and_autodelete(update.effective_chat, "✅ Đã gỡ cấm chat.")
    except Exception as e:
        await send_and_autodelete(update.effective_chat, f"Không gỡ được hạn chế: {e}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context, update.effective_user.id):
        return
    words = CONFIG.get("banned_words", [])
    mute_minutes = CONFIG.get("mute_minutes", 10)
    await send_and_autodelete(
        update.effective_chat,
        f"⚙️ Cấu hình:\n- Thời gian cấm: {mute_minutes} phút\n- Số từ cấm: {len(words)}"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_and_autodelete(
        update.effective_chat,
        "👋 Bot cấm chat theo từ cấm đã sẵn sàng.\n"
        "Admin dùng /addword, /delword, /listwords, /setmute, /unmute, /status."
    )

def main():
    token = BOT_TOKEN or os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("Thiếu BOT_TOKEN (chèn thẳng vào code hoặc đặt ENV).")

    app = Application.builder().token(token).build()

    # Lệnh admin
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addword", addword))
    app.add_handler(CommandHandler("delword", delword))
    app.add_handler(CommandHandler("listwords", listwords))
    app.add_handler(CommandHandler("setmute", setmute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("status", status_cmd))

    # Bắt mọi tin không phải command; bên trong tự lọc text/caption
    app.add_handler(MessageHandler(~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()

