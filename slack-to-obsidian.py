import os
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# タイムゾーン定義
JST = timezone(timedelta(hours=9))
UTC = timezone.utc

load_dotenv()

# SlackチャンネルID一覧
channel_ids_str = os.getenv("SLACK_CHANNEL_IDS")
if not channel_ids_str:
    raise ValueError("SLACK_CHANNEL_IDS not found in environment variables")

CHANNEL_IDS = [cid.strip() for cid in channel_ids_str.split(",")]

# 保存ディレクトリ
OUTPUT_DIR = Path("logs")
OUTPUT_DIR.mkdir(exist_ok=True)

# Botトークン読み込み
token_encoded = os.getenv("SLACK_BOT_TOKEN")
if not token_encoded:
    raise ValueError("SLACK_BOT_TOKEN not found")
SLACK_TOKEN = base64.b64decode(token_encoded).decode("utf-8")
client = WebClient(token=SLACK_TOKEN)

# 実行日（JST）の前日を対象にする
yesterday_jst_date = datetime.now(JST).date() - timedelta(days=1)
today_jst = datetime(
    year=yesterday_jst_date.year,
    month=yesterday_jst_date.month,
    day=yesterday_jst_date.day,
    tzinfo=JST,
)

# today_jst = datetime(2025, 7, 31, tzinfo=JST)  # ← 任意に変更

log_date_str = today_jst.strftime("%Y-%m-%d")

# JSTの0:00〜24:00 → UTCタイムスタンプに変換
start_jst = datetime(today_jst.year, today_jst.month, today_jst.day, 0, 0, 0, tzinfo=JST)
end_jst = start_jst + timedelta(days=1)
start_ts = start_jst.astimezone(UTC).timestamp()
end_ts = end_jst.astimezone(UTC).timestamp()

# メッセージをMarkdown形式に変換
def format_message(ts, user, text, indent_level=0):
    time_str = datetime.fromtimestamp(float(ts), JST).strftime("%H:%M")
    indent = "    " * indent_level
    return f"{indent}- **{time_str}** [@{user}]: {text.strip()}"

# ユーザーIDからユーザー名を取得
user_cache = {}
def get_user_name(user_id):
    if user_id in user_cache:
        return user_cache[user_id]
    try:
        user_info = client.users_info(user=user_id)
        name = user_info["user"]["real_name"] or user_info["user"]["name"]
        user_cache[user_id] = name
        return name
    except:
        return user_id

# スレッドの返信を取得
def fetch_thread_replies(channel_id, thread_ts):
    replies = []
    try:
        thread_response = client.conversations_replies(
            channel=channel_id,
            ts=thread_ts,
            limit=50
        )
        for reply in thread_response["messages"][1:]:  # 最初は親なので除外
            if "subtype" in reply:
                continue
            user = get_user_name(reply.get("user", "unknown"))
            text = reply.get("text", "").replace("\n", " ")
            replies.append(format_message(reply["ts"], user, text, indent_level=1))
    except:
        pass
    return replies

# チャンネルごとに取得
md_lines = [f"# Slackログ（{log_date_str}）\n"]
for channel_id in CHANNEL_IDS:
    try:
        channel_info = client.conversations_info(channel=channel_id)
        channel_name = channel_info["channel"]["name"]
        md_lines.append(f"\n## #{channel_name}\n")

        result = client.conversations_history(
            channel=channel_id,
            oldest=start_ts,
            latest=end_ts,
            inclusive=True,
            limit=1000
        )

        for message in reversed(result["messages"]):
            if "subtype" in message:
                continue

            user = get_user_name(message.get("user", "unknown"))
            text = message.get("text", "").replace("\n", " ")
            formatted = format_message(message["ts"], user, text)
            md_lines.append(formatted)

            # スレッドがある場合、返信を取得
            if "thread_ts" in message and message["thread_ts"] == message["ts"]:
                replies = fetch_thread_replies(channel_id, message["ts"])
                md_lines.extend(replies)

    except SlackApiError as e:
        md_lines.append(f"\n> Error fetching messages for channel {channel_id}: {e}\n")

# 保存
output_file = OUTPUT_DIR / f"{log_date_str}.md"
with open(output_file, "w", encoding="utf-8") as f:
    f.write("\n".join(md_lines))

print(f"Saved: {output_file}")