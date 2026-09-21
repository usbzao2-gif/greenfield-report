# -*- coding: utf-8 -*-
"""Блок «Что изменилось» и снимки (docs/benchmark.md, проверки 22-28).

Все сборки идут во временные папки pytest: снимки и дашборд проекта не затрагиваются.
"""
import copy, json, os, re, sys
from datetime import date, datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))
import build_dashboard, history
from test_render import Page

AS_OF = date(2026, 9, 17)
BUILT = datetime(2026, 9, 17, 13, 58, tzinfo=timezone.utc)


def current_snapshot(tmp_path):
    _, summary = build_dashboard.make_html(AS_OF, history_dir=str(tmp_path / "пусто"))
    return summary["snapshot"]


def base_from(snap, day, mutate=None):
    base = copy.deepcopy(snap)
    base["as_of"] = day.isoformat()
    if mutate:
        mutate(base)
    return base


def changes_text(html):
    block = re.search(r"<section class='changes'>(.*?)</section>", html, re.S).group(1)
    block = re.sub(r"</?span[^>]*>", "", block)  # строчные теги не дают пробела на экране
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", block)).strip()


def html_with(tmp_path, *bases):
    hist = tmp_path / "history"
    for b in bases:
        history.save(str(hist), b)
    html, _ = build_dashboard.make_html(AS_OF, history_dir=str(hist))
    return html


def test_22_no_data_start_explained(monkeypatch, tmp_path):
    orig = build_dashboard.load_plan

    def plan_with_broken_start(*args):
        rows = orig(*args)
        extra = dict(rows[0], direction="Экономика", name="Проверочная строка", owner="Технолог",
                     fact="", weight=1, regular=False, note="")
        rows += [dict(extra, id="X-04", start="", finish="2026-09-25"),
                 dict(extra, id="X-05", start="2026-13-01", finish="2026-09-25"),
                 dict(extra, id="X-06", start="2026-13-01", finish="")]
        return rows

    monkeypatch.setattr(build_dashboard, "load_plan", plan_with_broken_start)
    html, _ = build_dashboard.make_html(AS_OF, history_dir=str(tmp_path / "пусто"))
    p = Page(); p.feed(html)
    rows = {r[0]["text"]: r for r in p.tables[0]["rows"]}
    cards = {c["code"]: c for c in p.cards}
    expected = {"X-04": "старт не определён",
                "X-05": "старт указан неверно: 2026-13-01",
                "X-06": "срок не определён; старт указан неверно: 2026-13-01"}
    for code, text in expected.items():
        assert rows[code][1]["text"] == "Нет данных"
        assert rows[code][2]["text"] == text, rows[code][2]["text"]
        assert cards[code]["finish"] == text, cards[code]
    assert "25.09.2026" not in rows["X-04"][2]["text"]


def test_23_no_base(tmp_path):
    text = changes_text(html_with(tmp_path))
    assert "Нет базы для сравнения" in text
    assert not re.search(r"\d", text), text
    for word in ("Закрылись", "просрочку", "Готовность", "Переносы", "Состав"):
        assert word not in text


def test_24_base_date_named(tmp_path):
    snap = current_snapshot(tmp_path)
    text = changes_text(html_with(tmp_path, base_from(snap, date(2026, 9, 16))))
    assert "Изменения с 16.09.2026" in text
    assert "вчера" not in text.lower()


def test_25_changes(tmp_path):
    snap = current_snapshot(tmp_path)

    def mutate(b):
        t = b["tasks"]
        t["A-01"]["status"] = "В работе"; t["D-02"]["status"] = "В работе"      # закрылись
        t["A-05"]["status"] = "В работе"                                          # ушла в просрочку
        t["A-03"]["finish"] = "2026-09-05"                                        # перенос
        b["ready"] = 28.0                                                         # готовность +1,6
        del t["E-04"]                                                             # добавлено 1
        t["Z-99"] = dict(t["A-01"], name="Снятое мероприятие")                    # удалено 1

    base = base_from(snap, date(2026, 9, 16), mutate)
    d = history.diff(base, snap)
    assert d["closed"] == ["A-01", "D-02"]
    assert d["overdue"] == ["A-05"]
    assert d["moved"] == [("A-03", "2026-09-05", "2026-09-10")]
    assert d["ready_delta"] == 1.6
    assert (d["added"], d["removed"]) == (1, 1)
    text = changes_text(html_with(tmp_path, base))
    for piece in ("Закрылись: 2", "A-01 Подбор земельного участка", "D-02 Модель операционных затрат",
                  "Ушли в просрочку: 1", "A-05 ТУ на электроснабжение",
                  "Готовность: +1,6 п.п.",
                  "Переносы сроков: 1", "A-03 Предварительное согласование с ведомством: было 05.09.2026, стало 10.09.2026",
                  "Состав плана: добавлено 1, удалено 1"):
        assert piece in text, piece
    assert "A-03 Предварительное согласование с ведомством" not in text.split("Ушли в просрочку")[1].split("Готовность")[0]


def test_25_negative_delta_and_empty(tmp_path):
    snap = current_snapshot(tmp_path)
    text = changes_text(html_with(tmp_path, base_from(snap, date(2026, 9, 16), lambda b: b.update(ready=30.1))))
    assert "Готовность: -0,5 п.п." in text
    assert "Закрылись: нет" in text and "Ушли в просрочку: нет" in text and "Переносы сроков: нет" in text
    assert "Состав плана: добавлено 0, удалено 0" in text


def test_26_limit_five(tmp_path):
    snap = current_snapshot(tmp_path)
    done = sorted(k for k, v in snap["tasks"].items() if v["status"] == "Выполнено")
    assert len(done) == 8

    def mutate(b):
        for k in done:
            b["tasks"][k]["status"] = "В работе"

    text = changes_text(html_with(tmp_path, base_from(snap, date(2026, 9, 16), mutate)))
    closed = text.split("Закрылись: 8")[1].split("Ушли в просрочку")[0]
    for k in done[:5]:
        assert k in closed
    for k in done[5:]:
        assert k not in closed
    assert "и ещё 3" in closed


def test_27_snapshot_only_after_success(monkeypatch, tmp_path):
    hist, out = tmp_path / "history", tmp_path / "build" / "dashboard.html"

    def boom(*a):
        raise RuntimeError("сбой разметки")

    monkeypatch.setattr(build_dashboard, "render", boom)
    with pytest.raises(RuntimeError):
        build_dashboard.build(AS_OF, history_dir=str(hist), out=str(out))
    assert not out.exists()
    assert not hist.exists() or not list(hist.iterdir())
    monkeypatch.undo()

    # Сбой на записи файла дашборда: на месте файла каталог, переименование не пройдёт.
    blocked = tmp_path / "blocked"
    (blocked / "dashboard.html").mkdir(parents=True)
    with pytest.raises(OSError):
        build_dashboard.build(AS_OF, history_dir=str(hist), out=str(blocked / "dashboard.html"))
    assert not hist.exists() or not list(hist.iterdir())

    build_dashboard.build(AS_OF, history_dir=str(hist), out=str(out), built_at=BUILT)
    first = out.read_text(encoding="utf-8")
    assert [f.name for f in hist.iterdir()] == ["2026-09-17.json"]
    build_dashboard.build(AS_OF, history_dir=str(hist), out=str(out), built_at=BUILT)
    assert [f.name for f in hist.iterdir()] == ["2026-09-17.json"]
    assert out.read_text(encoding="utf-8") == first


def test_28_base_selection(tmp_path):
    snap = current_snapshot(tmp_path)
    hist = tmp_path / "history"
    for day in (date(2026, 9, 14), date(2026, 9, 17), date(2026, 9, 20)):
        history.save(str(hist), base_from(snap, day))
    (hist / "2026-09-15.json").write_text("{повреждён", encoding="utf-8")
    base = history.load_base(str(hist), AS_OF)
    assert base["as_of"] == "2026-09-14"
    html, _ = build_dashboard.make_html(AS_OF, history_dir=str(hist))
    assert "Изменения с 14.09.2026" in changes_text(html)
