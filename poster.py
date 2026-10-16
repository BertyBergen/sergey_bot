import requests
from config import BOT_TOKEN, CHAT_IDS


def send_to_all(text: str, targets=None) -> dict:
    """
    Отправляет сообщение в указанные группы.
    targets: список chat_id. Если None — во все из CHAT_IDS.
    Возвращает {"ok": N, "fail": M}.
    """
    if targets is None:
        targets = list(CHAT_IDS.keys())

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    ok, fail = 0, 0

    for chat_id in targets:
        try:
            r = requests.post(
                url,
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
            data = r.json()
            if data.get("ok"):
                print(f"[OK] {chat_id}")
                ok += 1
            else:
                print(f"[FAIL] {chat_id}: {data.get('description')}")
                fail += 1
        except Exception as e:
            print(f"[ERROR] {chat_id}: {e}")
            fail += 1

    return {"ok": ok, "fail": fail}