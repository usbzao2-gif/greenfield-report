# -*- coding: utf-8 -*-
"""Проверка входных данных плана и порядок блоков (docs/benchmark.md, проверки 29-33).

Негодные планы готовятся копиями во временной папке pytest; data/plan.csv не меняется.
"""
import csv, io, os, re, sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import build_dashboard, rules

AS_OF = date(2026, 9, 17)
PLAN = os.path.join(os.path.dirname(__file__), "..", "data", "plan.csv")


def plan_copy(tmp_path, edit=None, drop_column=None):
    with open(PLAN, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = list(reader.fieldnames), list(reader)
    if edit:
        edit(rows)
    if drop_column:
        fields.remove(drop_column)
        for r in rows:
            r.pop(drop_column, None)
    path = tmp_path / "plan.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader(); w.writerows(rows)
    return str(path)


def stopped(tmp_path, plan, capsys):
    """Запускает сборку как из командной строки. Возвращает текст ошибки."""
    hist, out = tmp_path / "history", tmp_path / "build" / "dashboard.html"
    with pytest.raises(SystemExit) as e:
        build_dashboard.main(["--as-of", "2026-09-17", "--plan", plan,
                              "--history", str(hist), "--out", str(out)])
    assert e.value.code == 1
    assert not out.exists(), "файл дашборда записан при негодных данных"
    assert not hist.exists() or not list(hist.iterdir()), "снимок записан при негодных данных"
    return capsys.readouterr().err


def by_id(rows, tid):
    return next(r for r in rows if r["id"] == tid)


def test_29_empty_weight_stops(tmp_path, capsys):
    plan = plan_copy(tmp_path, lambda rows: by_id(rows, "B-04").update(weight=""))
    err = stopped(tmp_path, plan, capsys)
    assert "plan.csv, строка 11 (B-04): вес пустой, ожидается целое число 0 или больше" in err, err


def test_30_duplicate_id_stops(tmp_path, capsys):
    plan = plan_copy(tmp_path, lambda rows: rows.append(dict(by_id(rows, "A-04"), id="A-01")))
    err = stopped(tmp_path, plan, capsys)
    assert "plan.csv, строка 29 (A-01): код мероприятия повторяется, впервые в строке 2" in err, err


def test_31_all_errors_at_once(tmp_path, capsys):
    def edit(rows):
        by_id(rows, "A-02").update(weight="2,5")
        by_id(rows, "A-03").update(weight="-1")
        by_id(rows, "A-04").update(regular="да")
        by_id(rows, "A-06").update(name="")
        by_id(rows, "A-05").update(id="")

    err = stopped(tmp_path, plan_copy(tmp_path, edit), capsys)
    expected = [
        "plan.csv, строка 3 (A-02): вес «2,5» не целое число, ожидается целое число 0 или больше",
        "plan.csv, строка 4 (A-03): вес «-1» отрицательный, ожидается целое число 0 или больше",
        "plan.csv, строка 5 (A-04): признак регулярности «да», ожидается 0 или 1",
        "plan.csv, строка 6 (без кода): пустой код мероприятия",
        "plan.csv, строка 7 (A-06): пустое название мероприятия",
    ]
    for line in expected:
        assert line in err, (line, err)

    err = stopped(tmp_path, plan_copy(tmp_path, drop_column="weight"), capsys)
    assert "plan.csv: нет обязательной колонки weight" in err, err


def test_32_working_plan_and_broken_dates_pass(tmp_path):
    with open(PLAN, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert rules.validate_plan(reader.fieldnames, list(reader)) == []
    html, summary = build_dashboard.make_html(AS_OF, history_dir=str(tmp_path / "пусто"))
    tasks = summary["snapshot"]["tasks"]
    assert tasks["X-01"]["status"] == tasks["X-02"]["status"] == "Нет данных"


def test_33_block_order(tmp_path):
    html, _ = build_dashboard.make_html(AS_OF, history_dir=str(tmp_path / "пусто"))
    body = html.split("<body>")[1]
    heads = re.findall(r"<h2>(.*?)</h2>", body)
    assert heads == ["Что изменилось", "Требует внимания", "Журнал событий", "Риски"], heads
    assert body.index("Готовность по весу") < body.index("<h2>Что изменилось</h2>")
