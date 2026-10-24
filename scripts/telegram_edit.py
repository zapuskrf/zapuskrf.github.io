#!/usr/bin/env python3
"""Переписывает уже опубликованные посты канала в текущий формат
(ссылка под словом «Источник», без предпросмотра).

Использование: python scripts/telegram_edit.py 2=content/news/xxx.md 3=content/news/yyy.md ...
где число — номер сообщения в канале (из ссылки t.me/канал/номер).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import telegram_post as tp  # noqa: E402


def edit(token, chat, message_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": json.dumps({"is_disabled": True}),
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/editMessageText", data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        if "message is not modified" in body:
            return {"ok": True, "note": "без изменений"}
        raise SystemExit(f"Сообщение {message_id}: Telegram ответил ошибкой {e.code}: {body}")


def main(pairs):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан.")
    site = yaml.safe_load((tp.ROOT / "site.yml").read_text(encoding="utf-8"))
    chat = os.environ.get("TELEGRAM_CHANNEL", "").strip() or "@" + site["telegram_channel"]
    rubrics = {r["name"]: r for r in site["rubrics"]}
    base = site["url"].rstrip("/")
    for pair in pairs:
        mid, path = pair.split("=", 1)
        meta = tp.load(tp.ROOT / path)
        url = f"{base}/news/{Path(path).stem}/"
        edit(token, chat, int(mid), tp.message(meta, url, rubrics))
        print(f"Обновлено сообщение {mid}: {meta['title']}")
        time.sleep(2)


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]).split())
