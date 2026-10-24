#!/usr/bin/env python3
"""Публикует в Telegram-канал посты для новых статей.

Использование: python scripts/telegram_post.py content/news/2026-10-25-xxx.md [...]
Переменные окружения:
  TELEGRAM_BOT_TOKEN  — токен бота (секрет репозитория)
  TELEGRAM_CHANNEL    — @адрес канала; если пусто, берётся из site.yml
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load(path):
    text = Path(path).read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def message(meta, url, rubrics):
    text = (meta.get("telegram") or "").strip()
    if not text:
        emoji = rubrics.get(meta.get("rubric"), {}).get("emoji", "")
        text = f"{emoji} {meta['title']}\n\n{meta['lead']}".strip()
    # строка-заглушка из шаблона убирается, ссылка ставится ниже
    text = re.sub(r"\n*(Подробнее|Источник):.*$", "", text, flags=re.M).rstrip()
    # сообщение отправляется в HTML-разметке: экранируем текст,
    # ссылку на статью прячем под слово «Источник»
    text = html.escape(text, quote=False)
    text += f'\n\n<a href="{html.escape(url)}">Источник</a>'
    if meta.get("hashtags"):
        text += f"\n\n{html.escape(meta['hashtags'].strip(), quote=False)}"
    return text


def send(token, chat, text):
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
        "parse_mode": "HTML",
        # без карточки-предпросмотра ссылки, чтобы не нагружать ленту
        "link_preview_options": json.dumps({"is_disabled": True}),
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429 and attempt < 2:
                wait = json.loads(body).get("parameters", {}).get("retry_after", 10)
                time.sleep(int(wait) + 1)
                continue
            raise SystemExit(f"Telegram ответил ошибкой {e.code}: {body}")


def main(files):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print("TELEGRAM_BOT_TOKEN не задан — публикация в Telegram пропущена.")
        return
    site = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8"))
    chat = os.environ.get("TELEGRAM_CHANNEL", "").strip() or "@" + site["telegram_channel"]
    rubrics = {r["name"]: r for r in site["rubrics"]}
    base = site["url"].rstrip("/")

    posts = []
    for f in files:
        meta = load(f)
        if not meta or meta.get("draft") or meta.get("tg_skip"):
            continue
        posts.append((meta.get("order", 50), Path(f).stem, meta))
    posts.sort(key=lambda x: (x[0], x[1]))

    for i, (_, slug, meta) in enumerate(posts):
        url = f"{base}/news/{slug}/"
        send(token, chat, message(meta, url, rubrics))
        print(f"Опубликовано: {meta['title']}")
        if i < len(posts) - 1:
            time.sleep(4)
    print(f"Готово: {len(posts)} постов в {chat}")


if __name__ == "__main__":
    main(sys.argv[1:])
