#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Синхронизатор отзывов: info-hit.ru -> reviews.json
Забирает отзывы со страницы Ольги, фильтрует по правилам бренда,
сортирует (закреплённые -> по полезности -> по свежести) и пишет reviews.json.

Запуск по крону раз в день. Готовый reviews.json публикуется на нашем CDN
с заголовком Access-Control-Allow-Origin, лендинг sabitovainvest.ru его грузит.
"""
import re, json, html as ihtml, sys, urllib.request, datetime, os
from anonymize import anonymize_name   # имя -> без фамилии / ник -> 3 буквы

RU_MONTHS = {"января":1,"февраля":2,"марта":3,"апреля":4,"мая":5,"июня":6,
             "июля":7,"августа":8,"сентября":9,"октября":10,"ноября":11,"декабря":12}

def parse_dt(s):
    """Текст с info-hit ('Сегодня в 09:34', 'Вчера в 19:15', '21 июля 2026 в 14:42') -> datetime."""
    now = datetime.datetime.now()
    s = (s or "").strip().lower()
    m = re.search(r"(\d{1,2}):(\d{2})", s)
    hh, mm = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    if s.startswith("сегодня"):
        d = now.date()
    elif s.startswith("вчера"):
        d = (now - datetime.timedelta(days=1)).date()
    else:
        m2 = re.search(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", s)
        if m2 and m2.group(2) in RU_MONTHS:
            d = datetime.date(int(m2.group(3)), RU_MONTHS[m2.group(2)], int(m2.group(1)))
        else:
            return None
    return datetime.datetime(d.year, d.month, d.day, hh, mm)

SRC_URL = "https://info-hit.ru/author-sabitova-olga/reviews/"
OUT     = os.path.join(os.path.dirname(__file__), "reviews.json")
UA      = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

# ---------- НАСТРОЙКИ ОТБОРА (правь здесь) ----------
MIN_RATING = 5           # показываем только 5 звёзд
MIN_LEN    = 120         # минимум символов — отсекает «спасибо, всё супер»
MAX_OUT    = 24          # сколько максимум выводить на лендинг

# ЗАПРЕТЫ БРЕНДА: отзыв выкидывается, если попал под любой шаблон.
# (обещания доходности/иксов, темы мошенники/1998/дефолт)
BLACKLIST = [
    r"\bмошенник",          # тема мошенников — граница Юрия
    r"\b1998\b", r"дефолт",
    r"\bиксы?\b", r"[xх]\s?\d{1,2}\b",      # x2, x10, «иксы»
    r"\d{1,3}\s?%",                          # любые проценты доходности
    r"заработал[аи]?\b", r"прибыль", r"удво", r"приумнож",
    r"годовых",
]
BLACKLIST_RE = re.compile("|".join(BLACKLIST), re.I)

# Ручное управление (id — это номер из info-hit, поле "id" в reviews.json):
PIN_IDS    = []          # закрепить вверху, в этом порядке (лучшие отзывы)
EXCLUDE_IDS = set()      # никогда не показывать (напр. про другой продукт)
# ----------------------------------------------------


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(raw):
    blocks = re.split(r'<div class="br_comment ', raw)[1:]
    items = []
    for b in blocks:
        mname = re.search(r'<header[^>]*>.*?<span[^>]*>([^<]+)</span>\s*<time', b, re.S)
        mdate = re.search(r'<time[^>]*>([^<]+)</time>', b)
        mrate = re.search(r'data-shape="star" data-value="(\d)"', b)
        mid   = re.search(r'id="answercontainer_(\d+)"', b)
        mvote = re.search(r'title="\+(\d+)"', b)          # «полезно» голосов
        vals  = re.findall(r'<div class="brca_value">(.*?)</div>', b, re.S)
        bodies = [re.sub(r'\s+', ' ', ihtml.unescape(re.sub(r'<[^>]+>', ' ', v))).strip() for v in vals]
        text = max(bodies, key=len) if bodies else ""
        if not mname or not text:
            continue
        items.append({
            "id":     mid.group(1) if mid else None,
            "author": mname.group(1).strip(),
            "date":   mdate.group(1).strip() if mdate else "",
            "rating": int(mrate.group(1)) if mrate else 5,
            "votes":  int(mvote.group(1)) if mvote else 0,
            "text":   text,
        })
    return items


def curate(items):
    kept = []
    for r in items:
        if r["id"] in EXCLUDE_IDS:            continue
        if (r["rating"] or 0) < MIN_RATING:   continue
        if len(r["text"]) < MIN_LEN:          continue
        if BLACKLIST_RE.search(r["text"]):    continue
        kept.append(r)
    # порядок: закреплённые вперёд, затем ПО ДАТЕ (свежие сверху, дальше на убывание).
    # id — вторичный ключ и запасной, если дату не удалось разобрать (id растёт со временем).
    pin_pos = {pid: i for i, pid in enumerate(PIN_IDS)}
    def sort_key(r):
        dt = parse_dt(r["date"])
        ts = dt.timestamp() if dt else 0
        rid = int(r["id"]) if r.get("id") and str(r["id"]).isdigit() else 0
        return (pin_pos.get(r["id"], 10_000), -ts, -rid)
    kept.sort(key=sort_key)
    kept = kept[:MAX_OUT]
    # анонимизация для легальной публикации: имя без фамилии / ник -> 3 буквы
    for r in kept:
        r["author"] = anonymize_name(r["author"])
    return kept


def main():
    raw = fetch(SRC_URL)
    parsed = parse(raw)
    kept = curate(parsed)
    out = {
        "source": SRC_URL,
        "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_on_site": len(parsed),
        "shown": len(kept),
        "reviews": kept,
    }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"OK: спарсено {len(parsed)}, после фильтра {len(kept)} -> {OUT}")
    dropped = len(parsed) - len(kept)
    if dropped:
        print(f"   отсеяно {dropped} (не 5*, коротко, запретные слова или в EXCLUDE)")


if __name__ == "__main__":
    main()
