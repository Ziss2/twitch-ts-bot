import socket
import time
import re
import random
import json
import os
from collections import defaultdict
from googletrans import Translator

# =========================
# CONFIG
# =========================
BOT_USERNAME = "aut0fal7m"
OAUTH_TOKEN = ""  # ❗ ใส่ token จริง (ไม่มี oauth:)
CHANNEL_NAME = "chakeawhehe"

RR_COOLDOWN = 20
RR_TIMEOUT_SEC = 10
RR_CHAMBERS = 6
RR_STATS_FILE = "rr_stats.json"

CUSTOM_TRANSLATION_FILE = "custom_translations.json"
USER_EMOTES_FILE = "user_emotes.json"
SAVE_INTERVAL = 30
TRANSLATE_COOLDOWN = 3

# =========================
# IRC SETUP
# =========================
SERVER = "irc.chat.twitch.tv"
PORT = 6667
CHANNEL = f"#{CHANNEL_NAME.lower()}"

sock = socket.socket()
sock.connect((SERVER, PORT))
sock.send(f"PASS oauth:{OAUTH_TOKEN}\r\n".encode())
sock.send(f"NICK {BOT_USERNAME}\r\n".encode())
sock.send("CAP REQ :twitch.tv/tags twitch.tv/commands\r\n".encode())
sock.send(f"JOIN {CHANNEL}\r\n".encode())
sock.settimeout(0.5)

print("✅ Bot connected")

# =========================
# TRANSLATOR
# =========================
translator = Translator()

def translate_to_th(text):
    try:
        result = translator.translate(text, dest="th")
        if result and result.text and result.text != text:
            return result.text
    except Exception as e:
        print("Translate error:", e)
    return None

# =========================
# LOAD DATA
# =========================
rr_stats = {}
custom_translations = {}
user_emotes = []

if os.path.exists(RR_STATS_FILE):
    rr_stats = json.load(open(RR_STATS_FILE, encoding="utf-8"))

if os.path.exists(CUSTOM_TRANSLATION_FILE):
    custom_translations = json.load(open(CUSTOM_TRANSLATION_FILE, encoding="utf-8"))

if os.path.exists(USER_EMOTES_FILE):
    user_emotes = json.load(open(USER_EMOTES_FILE, encoding="utf-8"))

translate_cd = defaultdict(lambda: 0)
last_save_time = time.time()

# =========================
# REGEX / UTILS
# =========================
THAI_RE = re.compile(r"[ก-๙]")
NUMBER_ONLY_RE = re.compile(r"^[0-9\s.,:+\-*/=()%]+$")
URL_RE = re.compile(r"(https?://|www\.)", re.IGNORECASE)

def is_mostly_thai(text):
    thai = sum(1 for c in text if THAI_RE.match(c))
    letters = sum(1 for c in text if c.isalpha())
    return letters > 0 and thai / letters > 0.6

# =========================
# IRC PARSER
# =========================
def parse_privmsg(raw):
    tags = {}
    username = ""
    message = ""

    if raw.startswith("@"):
        tags_part, raw = raw.split(" ", 1)
        for tag in tags_part[1:].split(";"):
            if "=" in tag:
                k, v = tag.split("=", 1)
                tags[k] = v

    if " PRIVMSG " not in raw:
        return None, None, None

    prefix, trailing = raw.split(" PRIVMSG ", 1)

    if "!" in prefix:
        username = prefix.split("!")[0].lstrip(":")
    else:
        username = ""

    message = trailing.split(":", 1)[1].strip()
    display_name = tags.get("display-name", username)

    return display_name, message, tags

# =========================
# HELPERS
# =========================
def send_message(msg):
    sock.send(f"PRIVMSG {CHANNEL} :{msg}\r\n".encode())

def periodic_save():
    global last_save_time
    if time.time() - last_save_time > SAVE_INTERVAL:
        json.dump(rr_stats, open(RR_STATS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(custom_translations, open(CUSTOM_TRANSLATION_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(user_emotes, open(USER_EMOTES_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        last_save_time = time.time()

# =========================
# TRANSLATION HANDLER
# =========================
def handle_translation(message, username, tags):
    if message.startswith("!"):
        return
    if URL_RE.search(message):
        return
    if NUMBER_ONLY_RE.match(message):
        return
    if tags.get("emote-only") == "1":
        return
    if is_mostly_thai(message):
        return
    if time.time() - translate_cd[username] < TRANSLATE_COOLDOWN:
        return

    if message in custom_translations:
        send_message(f"🌐 TL | {username}: {custom_translations[message]}")
        translate_cd[username] = time.time()
        return

    translated = translate_to_th(message)
    if translated:
        translate_cd[username] = time.time()
        send_message(f"🌐 TL | {username}: {translated}")

# =========================
# COMMANDS
# =========================
def handle_fix_command(message, username):
    parts = message[5:].split("|", 1)
    if len(parts) != 2:
        send_message(f"⚠️ {username} รูปแบบไม่ถูกต้อง")
        return
    custom_translations[parts[0].strip()] = parts[1].strip()
    periodic_save()
    send_message(f"✅ {username} บันทึกคำแปลแล้ว")

def handle_addemote_command(message):
    added = []
    for em in message.split()[1:]:
        if em not in user_emotes:
            user_emotes.append(em)
            added.append(em)
    if added:
        periodic_save()
        send_message(f"✅ เพิ่มอีโมต: {' '.join(added)}")

# =========================
# RUSSIAN ROULETTE
# =========================
rr_last_used = {}
rr_current_chamber = 0
rr_bullet_position = random.randint(1, RR_CHAMBERS)

def add_rr_stat(user, key):
    rr_stats.setdefault(user, {"survive": 0, "dead": 0})
    rr_stats[user][key] += 1

def handle_rr(message, username):
    global rr_current_chamber, rr_bullet_position
    if time.time() - rr_last_used.get(username, 0) < RR_COOLDOWN:
        return
    rr_last_used[username] = time.time()

    target = username
    m = re.match(r"!rr\s+@(\w+)", message)
    if m:
        target = m.group(1)

    rr_current_chamber = (rr_current_chamber % RR_CHAMBERS) + 1

    if rr_current_chamber == rr_bullet_position:
        add_rr_stat(target, "dead")
        send_message(f"💥 {username} ยิงใส่ {target} — *BANG!*")
        sock.send(f"PRIVMSG {CHANNEL} :/timeout {target} {RR_TIMEOUT_SEC}\r\n".encode())
        rr_current_chamber = 0
        rr_bullet_position = random.randint(1, RR_CHAMBERS)
    else:
        add_rr_stat(target, "survive")
        send_message(f"😌 {username} ยิงใส่ {target} — คลิก! รอด")

# =========================
# MAIN LOOP
# =========================
buffer = ""

while True:
    try:
        try:
            buffer += sock.recv(2048).decode("utf-8", errors="ignore")
        except socket.timeout:
            pass

        while "\r\n" in buffer:
            raw, buffer = buffer.split("\r\n", 1)

            if raw.startswith("PING"):
                sock.send("PONG :tmi.twitch.tv\r\n".encode())
                continue

            if "PRIVMSG" not in raw:
                continue

            username, message, tags = parse_privmsg(raw)
            if not username or not message:
                continue

            if username.lower() == BOT_USERNAME.lower():
                continue

            if message.startswith("!rr"):
                handle_rr(message, username)
            elif message.startswith("!fix"):
                handle_fix_command(message, username)
            elif message.startswith("!addemote"):
                handle_addemote_command(message)
            else:
                handle_translation(message, username, tags)

        periodic_save()

    except Exception as e:
        import traceback
        traceback.print_exc()
        time.sleep(5)

