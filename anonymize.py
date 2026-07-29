#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анонимизация имени автора для легальной публикации отзыва.
Правило (по требованию Юрия):
  • аватарку не показываем вообще (это делает вёрстка — в карточке нет фото);
  • настоящее имя -> только имя без фамилии ("Максим Бадашин" -> "Максим");
  • ник/логин -> первые 3 буквы + "…" ("@ivan_petrov" -> "iva…"), чтобы автора нельзя было найти.
"""
import re

def anonymize_name(raw):
    if not raw or not raw.strip():
        return "Аноним"
    s = raw.strip().lstrip("@").strip()
    parts = s.split()

    def is_nick(token, single):
        # явные признаки логина: цифры, _, точка
        if re.search(r"[\d_.]", token):
            return True
        # одиночный токен в нижнем регистре латиницей — похоже на логин (nickname)
        if single and re.match(r"^[a-z]+$", token):
            return True
        return False

    single = len(parts) == 1
    first = parts[0]

    if is_nick(first, single):
        core = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]", "", first)
        return (core[:3] + "…") if core else "Аноним"

    # настоящее имя -> берём первое слово, аккуратно с заглавной
    name = first
    return name[:1].upper() + name[1:]


if __name__ == "__main__":
    tests = [
        "Максим Бадашин", "Elena Drozdova", "Наталья", "Mayya Martynova Martynova",
        "артур юлдашев", "@ivan_petrov", "kate2015", "Ольга", "jasmine",
        "Таиьяна", "Юлия С.", "Evgeny Emelyanenko", "Аня Дедкова", "olga_k",
    ]
    for t in tests:
        print(f"  {t!r:36} -> {anonymize_name(t)!r}")
