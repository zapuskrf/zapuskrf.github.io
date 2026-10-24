#!/usr/bin/env python3
"""Сборка сайта «Запуск»: content/news/*.md -> _site/.

Зависимости: pip install markdown pyyaml jinja2
Запуск: python build.py [--content DIR] [--out DIR]
"""
import argparse
import datetime as dt
import html
import re
import shutil
from collections import OrderedDict
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

REQUIRED = ["title", "date", "rubric", "lead"]


def to_date(value):
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def ru_date(value, year=True):
    d = to_date(value)
    s = f"{d.day} {MONTHS[d.month - 1]}"
    return f"{s} {d.year}" if year else s


def read_post(path, rubrics_by_name):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        raise SystemExit(f"{path.name}: нет блока front matter (--- ... ---)")
    meta = yaml.safe_load(m.group(1)) or {}
    for key in REQUIRED:
        if not meta.get(key):
            raise SystemExit(f"{path.name}: не заполнено поле «{key}»")
    if meta["rubric"] not in rubrics_by_name:
        raise SystemExit(f"{path.name}: неизвестная рубрика «{meta['rubric']}»")
    body_html = markdown.markdown(m.group(2), extensions=["extra", "sane_lists"])
    body_html = re.sub(r'<a href="(https?://)', r'<a rel="noopener" target="_blank" href="\1', body_html)
    slug = path.stem
    meta.update(
        slug=slug,
        url=f"/news/{slug}/",
        date=to_date(meta["date"]),
        event_date=to_date(meta["event_date"]) if meta.get("event_date") else None,
        body=body_html,
        rubric_obj=rubrics_by_name[meta["rubric"]],
        sources=meta.get("sources") or [],
        order=meta.get("order", 50),
        draft=bool(meta.get("draft", False)),
    )
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", default=str(ROOT / "content" / "news"))
    ap.add_argument("--out", default=str(ROOT / "_site"))
    ap.add_argument("--all", action="store_true",
                    help="показать и ещё не выпущенные новости (для локального просмотра)")
    args = ap.parse_args()

    site = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8"))
    site["url"] = site["url"].rstrip("/")
    rubrics = site["rubrics"]
    rubrics_by_name = {r["name"]: r for r in rubrics}

    content_dir = Path(args.content)
    posts = [read_post(p, rubrics_by_name) for p in sorted(content_dir.glob("*.md"))]
    posts = [p for p in posts if not p["draft"]]
    # На сайт попадают только новости, выпущенные по расписанию (scripts/release.py)
    state = content_dir.parent / "published.txt"
    if state.exists() and not args.all:
        released = {line.split()[0] for line in state.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#")}
        waiting = [p["slug"] for p in posts if p["slug"] not in released]
        if waiting:
            print(f"Ждут выхода по расписанию: {len(waiting)}")
        posts = [p for p in posts if p["slug"] in released]
    posts.sort(key=lambda p: (-p["date"].toordinal(), p["order"], p["slug"]))

    by_day = OrderedDict()
    for p in posts:
        by_day.setdefault(p["date"], []).append(p)

    for r in rubrics:
        r["posts"] = [p for p in posts if p["rubric"] == r["name"]]

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")),
                      autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["ru_date"] = ru_date
    env.filters["weekday"] = lambda d: WEEKDAYS[to_date(d).weekday()]
    env.filters["rfc822"] = lambda d: dt.datetime.combine(to_date(d), dt.time(6, 0)).strftime(
        "%a, %d %b %Y %H:%M:%S +0300")
    env.globals.update(site=site, rubrics=rubrics, now=dt.datetime.now(),
                       year=dt.date.today().year)

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    def render(template, dest, **ctx):
        path = out / dest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(env.get_template(template).render(**ctx), encoding="utf-8")

    days = list(by_day.items())
    render("index.html", "index.html", days=days[:7], page_url="/")
    render("archive.html", "archive/index.html", days=days, page_url="/archive/")
    render("about.html", "about/index.html", page_url="/about/")
    render("404.html", "404.html", page_url="/404.html")
    for r in rubrics:
        render("rubric.html", f"rubric/{r['slug']}/index.html", rubric=r,
               page_url=f"/rubric/{r['slug']}/")
    for p in posts:
        same = [q for q in p["rubric_obj"]["posts"] if q["slug"] != p["slug"]][:3]
        render("post.html", f"news/{p['slug']}/index.html", post=p, related=same,
               page_url=p["url"])
    render("feed.xml", "feed.xml", posts=posts[:40])
    render("sitemap.xml", "sitemap.xml", posts=posts)
    render("robots.txt", "robots.txt")

    shutil.copytree(ROOT / "static", out, dirs_exist_ok=True)
    (out / ".nojekyll").write_text("")
    if site.get("domain"):
        (out / "CNAME").write_text(site["domain"].strip() + "\n")
    print(f"Собрано: {len(posts)} статей, {len(days)} выпусков -> {out}")


if __name__ == "__main__":
    main()
