from urllib.parse import urlparse
import datetime
import telebot
import config
import yt_dlp
import re
import os
from telebot.util import quick_markup
import time

bot = telebot.TeleBot(config.token)
last_edited = {}

# ✅ Supports YouTube + YouTube Music
def youtube_url_validation(url):
    youtube_regex = (
        r'(https?://)?(www\.|music\.)?'  # includes music.youtube.com
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    youtube_regex_match = re.match(youtube_regex, url)
    return youtube_regex_match

@bot.message_handler(commands=['start', 'help'])
def start_cmd(message):
    bot.reply_to(
        message,
        "Send me a YouTube or YouTube Music link.",
        parse_mode="MARKDOWN",
        disable_web_page_preview=True
    )

def download_video(message, url, audio=False, format_id="mp4"):
    url_info = urlparse(url)
    if not url_info.scheme:
        bot.reply_to(message, 'Invalid URL')
        return

    msg = bot.reply_to(message, 'Downloading...')

    def progress(d):
        if d['status'] == 'downloading':
            try:
                key = f"{message.chat.id}-{msg.message_id}"
                update = False
                if last_edited.get(key):
                    if (datetime.datetime.now() - last_edited[key]).total_seconds() >= 5:
                        update = True
                else:
                    update = True
                if update:
                    perc = round(d.get('downloaded_bytes', 0) * 100 / max(1, d.get('total_bytes', 1)))
                    title = d.get("info_dict", {}).get("title", "video")
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=msg.message_id,
                        text=f"Downloading {title}\n\n{perc}%"
                    )
                    last_edited[key] = datetime.datetime.now()
            except Exception as e:
                print(e)

    video_title = round(time.time() * 1000)
    opts = {
        'format': format_id,
        'outtmpl': f'{config.output_folder}/{video_title}.%(ext)s',
        'progress_hooks': [progress],
        'max_filesize': config.max_filesize
    }

    if audio:
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3'
        }]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text='Sending file to Telegram...'
        )

        file_path = info['requested_downloads'][0]['filepath']
        if audio:
            bot.send_audio(message.chat.id, open(file_path, 'rb'), reply_to_message_id=message.message_id)
        else:
            width = info['requested_downloads'][0].get('width', 0)
            height = info['requested_downloads'][0].get('height', 0)
            bot.send_video(message.chat.id, open(file_path, 'rb'), reply_to_message_id=message.message_id, width=width, height=height)

        bot.delete_message(message.chat.id, msg.message_id)

    except Exception as e:
        print(e)
        bot.edit_message_text(
            f"⚠️ Error downloading or sending file. It may exceed *{round(config.max_filesize / 1000000)}MB* or be unsupported.",
            message.chat.id, msg.message_id, parse_mode="MARKDOWN"
        )

    # Cleanup files
    for file in os.listdir(config.output_folder):
        if file.startswith(str(video_title)):
            try:
                os.remove(f'{config.output_folder}/{file}')
            except:
                pass

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_youtube_link(message):
    text = message.text.strip()
    if not text or not youtube_url_validation(text):
        bot.reply_to(message, "Please send a valid YouTube or YouTube Music URL.")
        return

    if "music.youtube.com" in text:
        bot.reply_to(message, "🎶 YouTube Music link detected — showing available audio & video formats...")

    msg = bot.reply_to(message, "Fetching available formats...")

    try:
        with yt_dlp.YoutubeDL() as ydl:
            info = ydl.extract_info(text, download=False)

        buttons = {}

        # 🎧 Audio formats
        for f in info['formats']:
            if f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                abr = f.get('abr', 'N/A')
                ext = f.get('ext', 'm4a')
                fmt_id = f.get('format_id')
                label = f"🎧 {abr}kbps ({ext})"
                buttons[label] = {'callback_data': f"audio|{fmt_id}|{text}"}

        # 🎥 Video formats
        for f in info['formats']:
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                res = f.get('format_note') or f.get('resolution') or 'N/A'
                ext = f.get('ext', 'mp4')
                fmt_id = f.get('format_id')
                label = f"🎥 {res.upper()} ({ext})"
                buttons[label] = {'callback_data': f"video|{fmt_id}|{text}"}

        markup = quick_markup(buttons, row_width=2)
        bot.edit_message_text("Select format:", chat_id=message.chat.id, message_id=msg.message_id, reply_markup=markup)

    except Exception as e:
        print(e)
        bot.edit_message_text("❌ Failed to fetch formats.", chat_id=message.chat.id, message_id=msg.message_id)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    try:
        data = call.data.split("|")
        if len(data) < 2:
            return
        mode = data[0]
        fmt_id = data[1]
        url = data[2]
        if mode == "audio":
            bot.answer_callback_query(call.id, "Downloading audio...")
            download_video(call.message, url, audio=True, format_id=fmt_id)
        elif mode == "video":
            bot.answer_callback_query(call.id, "Downloading video...")
            download_video(call.message, url, audio=False, format_id=f"{fmt_id}+bestaudio")
    except Exception as e:
        print(e)
        bot.answer_callback_query(call.id, "Error while processing.")

bot.infinity_polling()
