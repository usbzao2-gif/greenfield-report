# -*- coding: utf-8 -*-
"""Структурные проверки разметки дашборда (docs/benchmark.md, проверки 17-20).

Страница собирается в памяти, файл в build/ не пишется. Раскладку на экране
375 пикселей эти тесты не проверяют: для неё tools/check_mobile.py.
"""
import os, re, sys
from datetime import date, datetime, timezone
from html.parser import HTMLParser

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import build_dashboard

AS_OF = date(2026, 9, 17)
BUILT = datetime(2026, 9, 17, 13, 58, tzinfo=timezone.utc)  # 16:58 по Москве
NO_HISTORY = os.path.join(os.path.dirname(__file__), "_нет_снимков")  # папки нет: базы нет


class Page(HTMLParser):
    """Таблицы: заголовки и строки; ячейка = (класс, видимый текст, текст вложенных блоков)."""

    def __init__(self):
        super().__init__()
        self.tables, self.text = [], []
        self._cell = None
        self._skip = False
        self.cards, self._field = [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = a.get("class", "").split()
        if "card" in classes:
            self.cards.append({})
        field = next((c[2:] for c in classes if c.startswith("c-")), None)
        if field and self.cards:
            self._field = (tag, field); self.cards[-1][field] = ""
        if tag in ("style", "title"):
            self._skip = True
        elif tag == "table":
            self.tables.append({"head": [], "rows": []})
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("th", "td"):
            self._cell = {"tag": tag, "cls": a.get("class", ""), "text": ""}

    def handle_endtag(self, tag):
        if self._field and tag == self._field[0]:
            self.cards[-1][self._field[1]] = self.cards[-1][self._field[1]].strip(); self._field = None
        if tag in ("style", "title"):
            self._skip = False
        elif tag in ("th", "td") and self._cell is not None:
            c = self._cell; c["text"] = c["text"].strip(); self._cell = None
            (self.tables[-1]["head"] if c["tag"] == "th" else self._row).append(c)
        elif tag == "tr" and self.tables and getattr(self, "_row", None):
            self.tables[-1]["rows"].append(self._row); self._row = None

    def handle_data(self, data):
        if self._skip:
            return
        self.text.append(data)
        if self._field:
            self.cards[-1][self._field[1]] += data
        if self._cell is not None:
            self._cell["text"] += data


def page():
    html, summary = build_dashboard.make_html(AS_OF, history_dir=NO_HISTORY)
    p = Page(); p.feed(html)
    return html, p, summary


def test_17_structure():
    _, p, _ = page()
    assert len(p.tables) == 3
    for t in p.tables:
        assert t["head"], "у таблицы нет заголовков"
        for r in t["rows"]:
            assert len(r) == len(t["head"])
            for h, c in zip(t["head"], r):
                if h["text"] in ("Код", "Дата", "Плановый финиш", "Статус"):
                    assert "nw" in c["cls"].split(), (h["text"], c["text"])
    body = " ".join(p.text)
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", body), "осталась дата вида 2026-09-10"


def test_18_decimal_comma():
    _, p, _ = page()
    body = " ".join(p.text)
    assert "29,6%" in body
    no_dates = re.sub(r"\b\d{2}\.\d{2}(\.\d{4})?\b", "", body)
    assert not re.search(r"\d\.\d", no_dates), "число с точкой"


def test_19_header():
    _, p, summary = page()
    body = re.sub(r"\s+", " ", " ".join(p.text))
    assert "Всего мероприятий: 27, из них в расчёте готовности 26, регулярных 1" in body
    expected = {"Выполнено": 8, "В работе": 9, "Просрочено": 2, "Не начато": 6, "Нет данных": 2}
    assert summary["counts"] == expected
    assert sum(expected.values()) == 27
    for name, n in expected.items():
        assert "{}: {}".format(name, n) in body, name


def test_18_console_decimal_comma():
    html, summary = build_dashboard.make_html(AS_OF, history_dir=NO_HISTORY)
    line = build_dashboard.summary_line(summary)
    assert "29,6%" in line and not re.search(r"\d\.\d", line)


def test_20_attention_for_reader():
    # Что должен увидеть читатель по каждому мероприятию блока внимания:
    # на широком экране строка таблицы в заданном порядке колонок,
    # на узком карточка: код и название, затем статус и финиш, затем ответственный.
    _, p, _ = page()
    att = p.tables[0]
    assert [h["text"] for h in att["head"]] == ["Код", "Статус", "Плановый финиш", "Мероприятие", "Ответственный"]
    assert len(p.cards) == len(att["rows"]) == 6
    for row, card in zip(att["rows"], p.cards):
        code, status, finish, name, owner = [c["text"] for c in row]
        seen = {k: card.get(k) for k in ("code", "name", "status", "finish", "owner")}
        assert seen == {"code": code, "name": name, "status": status, "finish": finish, "owner": owner}, card


def test_14_repeatable():
    # Две сборки на тех же данных и той же отчётной дате дают один и тот же HTML.
    first, _ = build_dashboard.make_html(AS_OF, history_dir=NO_HISTORY, built_at=BUILT)
    second, _ = build_dashboard.make_html(AS_OF, history_dir=NO_HISTORY, built_at=BUILT)
    assert first and first == second


def test_21_no_data_explained():
    # Для «Нет данных» читатель видит, что не так со сроком, без похода в plan.csv.
    _, p, _ = page()
    expected = {"X-01": "срок не определён", "X-02": "срок указан неверно: 31.09.2026"}
    rows = {r[0]["text"]: r for r in p.tables[0]["rows"]}
    cards = {c["code"]: c for c in p.cards}
    for code, text in expected.items():
        assert rows[code][1]["text"] == "Нет данных"
        assert rows[code][2]["text"] == text, rows[code][2]["text"]
        assert cards[code]["finish"] == text, cards[code]


def test_34_stage_and_build_time():
    html, summary = build_dashboard.make_html(AS_OF, history_dir=NO_HISTORY, built_at=BUILT)
    p = Page(); p.feed(html)
    body = re.sub(r"\s+", " ", " ".join(p.text))
    assert "Собран 17.09.2026 в 16:58. Стадия: концепция и ТЭО." in body, "время сборки не московское или не в том формате"
    head = html.split("<h2>")[0]
    assert head.index("Дашборд на 17.09.2026") < head.index("Собран 17.09.2026 в 16:58") < head.index("Готовность по весу")
    later = datetime(2026, 9, 18, 6, 5, tzinfo=timezone.utc)
    html2, summary2 = build_dashboard.make_html(AS_OF, history_dir=NO_HISTORY, built_at=later)
    assert "Собран 18.09.2026 в 09:05" in html2
    assert html2.replace("Собран 18.09.2026 в 09:05", "Собран 17.09.2026 в 16:58") == html
    assert summary2["snapshot"] == summary["snapshot"]
