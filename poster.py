import requests
from config import BOT_TOKEN, CHAT_IDS


def send_to_all(text: str) -> None:
    """Отправляет сообщение во все группы из CHAT_IDS."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        try:
            r = requests.post(
                url,
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
            data = r.json()
            if data.get("ok"):
                print(f"[OK] {chat_id}")
            else:
                print(f"[FAIL] {chat_id}: {data.get('description')}")
        except Exception as e:
            print(f"[ERROR] {chat_id}: {e}")