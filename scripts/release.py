#!/usr/bin/env python3
"""Выпуск новостей по расписанию.

Новость появляется на сайте и в Telegram только после того, как её адрес
записан в content/published.txt. Этот скрипт запускается по расписанию
(GitHub Actions, раз в 15 минут), находит новости, время которых наступило,
и выпускает ОДНУ — самую раннюю. Поэтому даже опоздавшие новости выходят
по одной, а не пачкой.

Время выхода новости:
  - publish_at в front matter (например «2026-10-25 14:30» или «14:30»), иначе
  - дата выпуска (date) + расписание из site.yml: первая новость дня (по order)
    выходит в publish_start, каждая следующая — через publish_interval минут.
    Если новостей так много, что последняя не успевает до publish_end,
    интервал сокращается, чтобы все вышли в окне.

Использование:
  python scripts/release.py            — выпустить одну новость (печатает её slug)
  python scripts/release.py --plan     — показать расписание, ничего не меняя
"""
import datetime as dt
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "content" / "news"
STATE = ROOT / "content" / "published.txt"


def front_matter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    return (yaml.safe_load(m.group(1)) or {}) if m else {}


def to_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def parse_time(s):
    h, m = str(s).strip().split(":")
    return dt.time(int(h), int(m))


def published_slugs():
    if not STATE.exists():
        return set()
    return {line.split()[0] for line in STATE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")}


def schedule(site):
    tz = ZoneInfo(site.get("timezone", "Europe/Moscow"))
    start = parse_time(site.get("publish_start", "06:00"))
    end = parse_time(site.get("publish_end", "23:00"))
    interval = int(site.get("publish_interval", 60))
    window = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    posts = []
    for path in sorted(NEWS.glob("*.md")):
        meta = front_matter(path)
        if not meta or meta.get("draft") or not meta.get("date"):
            continue
        posts.append({"slug": path.stem, "date": to_date(meta["date"]),
                      "order": meta.get("order", 50), "meta": meta})

    by_day = {}
    for p in posts:
        by_day.setdefault(p["date"], []).append(p)
    for day, items in by_day.items():
        items.sort(key=lambda p: (p["order"], p["slug"]))
        step = interval
        if len(items) > 1:
            step = min(interval, window / (len(items) - 1))
        for i, p in enumerate(items):
            when = p["meta"].get("publish_at")
            if when:
                s = str(when).strip()
                if re.fullmatch(r"\d{1,2}:\d{2}", s):
                    at = dt.datetime.combine(day, parse_time(s))
                elif isinstance(when, dt.datetime):
                    at = when.replace(tzinfo=None)
                else:
                    at = dt.datetime.fromisoformat(s)
            else:
                at = dt.datetime.combine(day, start) + dt.timedelta(minutes=round(i * step))
            p["at"] = at.replace(tzinfo=tz) if at.tzinfo is None else at
    return sorted(posts, key=lambda p: (p["at"], p["order"], p["slug"])), tz


def main(args):
    site = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8"))
    posts, tz = schedule(site)
    done = published_slugs()
    now = dt.datetime.now(tz)

    if "--plan" in args:
        for p in posts:
            mark = "опубликовано" if p["slug"] in done else ("пора" if p["at"] <= now else "ждёт")
            print(f"{p['at']:%Y-%m-%d %H:%M}  {mark:12}  {p['slug']}")
        return

    due = [p for p in posts if p["slug"] not in done and p["at"] <= now]
    if not due:
        print("Сейчас выпускать нечего.", file=sys.stderr)
        return
    p = due[0]
    with STATE.open("a", encoding="utf-8") as f:
        f.write(f"{p['slug']}  {now:%Y-%m-%dT%H:%M%z}\n")
    print(f"Выпуск: {p['slug']} (по плану {p['at']:%d.%m %H:%M}), в очереди ещё {len(due) - 1}",
          file=sys.stderr)
    print(p["slug"])


if __name__ == "__main__":
    main(sys.argv[1:])
