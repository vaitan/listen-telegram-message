import os
import time
import subprocess
from pathlib import Path

from telethon import TelegramClient, events


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def load_env(path):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")

        os.environ.setdefault(key, value)


def require_env(name):
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


load_env(ENV_FILE)

API_ID = int(require_env("TG_API_ID"))
API_HASH = require_env("TG_API_HASH")
PHONE = require_env("TG_PHONE")

LISTEN_IDS = set(
    x.strip()
    for x in os.getenv("LISTEN_CHAT_IDS", "").split(",")
    if x.strip()
)

client = TelegramClient(
    "tg_session",
    API_ID,
    API_HASH,
    auto_reconnect=True,
    connection_retries=-1,
    retry_delay=5,
)


def run(cmd):
    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        print("cmd error:", e)


def get_topic_id(event):
    try:
        reply = getattr(event.message, "reply_to", None)
        if not reply:
            return None

        topic_id = (
            getattr(reply, "reply_to_top_id", None)
            or getattr(reply, "reply_to_msg_id", None)
        )
        return str(topic_id) if topic_id else None
    except Exception:
        return None


def should_listen(chat_id, topic_key):
    # Không cấu hình gì thì lắng nghe tất cả.
    if not LISTEN_IDS:
        return True

    # Có cấu hình thì chỉ nghe đúng chat_id hoặc chat_id:topic_id.
    return chat_id in LISTEN_IDS or topic_key in LISTEN_IDS


def wake_only(title, body, chat_id, topic_id):
    body = (body or "(Media)")[:220]
    run(
        [
            "am",
            "broadcast",
            "-a",
            "TG_WAKE",
            "--es",
            "title",
            title,
            "--es",
            "body",
            body,
            "--es",
            "chat_id",
            chat_id,
            "--es",
            "topic_id",
            topic_id or "",
        ]
    )


def notify_topic(title, body, chat_id, topic_id):
    body = (body or "(Media)")[:220]
    nid = str(int(time.time() * 1000) % 2147483647)
    title = "{} | topic {}".format(title, topic_id)

    run(
        [
            "termux-notification",
            "--id",
            nid,
            "--title",
            title,
            "--content",
            body,
            "--priority",
            "max",
            "--sound",
            "--vibrate",
            "500,500,500",
        ]
    )

    run(["termux-vibrate", "-d", "800"])

    wake_only(title, body, chat_id, topic_id)


@client.on(events.NewMessage(incoming=True))
async def on_message(event):
    try:
        chat = await event.get_chat()
        sender = await event.get_sender()

        chat_id = str(event.chat_id)
        topic_id = get_topic_id(event)
        topic_key = chat_id + ":" + topic_id if topic_id else chat_id

        sender_name = (
            getattr(sender, "first_name", None)
            or getattr(sender, "username", None)
            or "Sender"
        )
        chat_name = getattr(chat, "title", None) or sender_name or "Telegram"
        text = event.raw_text or "(Media)"

        print("=" * 40)
        print("CHAT_ID   :", chat_id)
        print("TOPIC_ID  :", topic_id)
        print("TOPIC_KEY :", topic_key)
        print("CHAT      :", chat_name)
        print("SENDER    :", sender_name)
        print("TEXT      :", text)

        if not should_listen(chat_id, topic_key):
            print("SKIP      :", topic_key)
            return

        title = "TG | {}".format(chat_name)
        body = "{}: {}".format(sender_name, text) if chat_name != sender_name else text

        if topic_id:
            notify_topic(title, body, chat_id, topic_id)
        else:
            wake_only(title, body, chat_id, topic_id)

    except Exception as e:
        print("handler error:", e)


try:
    while True:
        try:
            print("Connecting...")
            client.start(phone=PHONE)
            print("Listening...")
            print("LISTEN_IDS:", ",".join(sorted(LISTEN_IDS)) if LISTEN_IDS else "ALL")
            client.run_until_disconnected()
            print("Disconnected. Reconnect in 5s...")
            time.sleep(5)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print("Reconnect:", e)
            time.sleep(5)
except KeyboardInterrupt:
    print("Stopped.")
    try:
        client.disconnect()
    except Exception:
        pass
