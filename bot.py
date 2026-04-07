import os
import asyncio
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")

queue = asyncio.Queue()


# -------- CLEAN TITLE --------
def clean_title(title):
    title = re.sub(r'[\\/*?:"<>|]', "", title)
    return title[:60]


# -------- DOWNLOAD WORKER --------
async def download_worker(app):
    while True:
        url, chat_id, quality = await queue.get()

        try:
            await app.bot.send_message(chat_id, "⏳ Processing...")

            # -------- COMMON OPTIONS --------
            base_opts = {
                "cookiefile": "cookies.txt",
                "noplaylist": True,
                "continuedl": True,
                "retries": 10,
                "fragment_retries": 10,
                "socket_timeout": 60,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                },
            }

            # -------- AUDIO --------
            if quality == "audio":
                ydl_opts = {
                    **base_opts,
                    "format": "bestaudio",
                    "outtmpl": "%(title)s.%(ext)s",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                    }],
                }

            # -------- VIDEO --------
            else:
                ydl_opts = {
                    **base_opts,
                    "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
                    "outtmpl": "%(title)s.%(ext)s",
                }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                title = clean_title(info.get("title", "video"))

                filename = title + (".mp3" if quality == "audio" else ".mp4")

                original = ydl.prepare_filename(info)
                if os.path.exists(original):
                    os.rename(original, filename)

            # -------- FILE SIZE CHECK --------
            size = os.path.getsize(filename) / (1024 * 1024)

            if size > 1900:
                await app.bot.send_message(chat_id, "❌ File too large (>2GB)")
                os.remove(filename)
                continue

            await app.bot.send_message(chat_id, f"📤 Uploading... ({round(size,1)} MB)")

            # -------- SEND FILE --------
            with open(filename, "rb") as f:
                if quality == "audio":
                    await app.bot.send_audio(
                        chat_id,
                        f,
                        read_timeout=300,
                        write_timeout=300
                    )
                else:
                    await app.bot.send_video(
                        chat_id,
                        f,
                        supports_streaming=True,
                        read_timeout=300,
                        write_timeout=300
                    )

            # -------- THUMBNAIL --------
            thumb = info.get("thumbnail")
            if thumb:
                await app.bot.send_photo(chat_id, thumb)

            os.remove(filename)

        except Exception as e:
            await app.bot.send_message(chat_id, f"❌ Error: {e}")

        queue.task_done()


# -------- START --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎬 Send YouTube URL")


# -------- MESSAGE --------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text

    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ Invalid URL")
        return

    keyboard = [
        [
            InlineKeyboardButton("360p", callback_data=f"360|{url}"),
            InlineKeyboardButton("720p", callback_data=f"720|{url}")
        ],
        [
            InlineKeyboardButton("🎵 Audio", callback_data=f"audio|{url}")
        ]
    ]

    await update.message.reply_text(
        "Choose quality:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# -------- BUTTON --------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    quality, url = query.data.split("|", 1)

    if quality == "360":
        fmt = "360"
    elif quality == "720":
        fmt = "720"
    else:
        fmt = "audio"

    await queue.put((url, query.message.chat_id, fmt))
    await query.edit_message_text("✅ Added to queue")


# -------- MAIN --------
async def post_init(app):
    asyncio.create_task(download_worker(app))


def main():
    app = ApplicationBuilder()\
        .token(BOT_TOKEN)\
        .connect_timeout(60)\
        .read_timeout(300)\
        .write_timeout(300)\
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button))

    app.post_init = post_init

    print("🚀 Bot Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
