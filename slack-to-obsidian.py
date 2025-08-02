import os
import base64
from datetime import datetime, timedelta
from pathlib import Path
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# SlackチャンネルID一覧（カンマ区切り）
CHANNEL_IDS = [
    "C07D72VLD54", "C07F691AE9Z", "C06NDUSU68Y",
    "C06MEPPRXJN", "C05218NK8TB", "C01SQH2UT9C"
]

# 保存ディレクトリ
OUTPUT_DIR = Path("logs")
OUTPUT_DIR.mkdir(exist_ok=True)

# Botトークンを環境変数から読み取り
token_encoded = os.getenv("SLACK_BOT_TOKEN")
if not token_encoded:
    raise ValueError("SLACK_BOT_TOKEN not found in environment variables")

SLACK_TOKEN = base64.b64decode(token_encoded).decode("utf-8")
client = WebClient(token=SLACK_TOKEN)

# 今日の日付を取得
# 一時的にデバッグしたい時は、以下をコメントアウトする
today = datetime.utcnow() + timedelta(hours=9)  # JST
log_date_str = today.strftime("%Y-%m-%d")
start_of_day = datetime(today.year, today.month, today.day, 0, 0, 0) - timedelta(hours=9)
end_of_day = start_of_day + timedelta(days=1)

start_ts = start_of_day.timestamp()
end_ts = end_of_day.timestamp()

# メッセージをMarkdownに変換
def format_message(ts, user, text):
    time_str = datetime.fromtimestamp(float(ts) + 9 * 3600).strftime("%H:%M")
    return f"- **{time_str}** [@{user}]: {text.strip()}"

# ユーザーID → ユーザー名の変換キャッシュ
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

# チャンネルごとにメッセージ取得
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
                continue  # ボットメッセージなどは除外
            user = get_user_name(message.get("user", "unknown"))
            text = message.get("text", "").replace("\n", " ")
            md_lines.append(format_message(message["ts"], user, text))

    except SlackApiError as e:
        md_lines.append(f"\n> Error fetching messages for channel {channel_id}: {e}\n")

# 保存
output_file = OUTPUT_DIR / f"{log_date_str}.md"
with open(output_file, "w", encoding="utf-8") as f:
    f.write("\n".join(md_lines))

print(f"Saved: {output_file}")