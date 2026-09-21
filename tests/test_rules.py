# -*- coding: utf-8 -*-
"""Проверки из docs/benchmark.md. Каждый тест назван по номеру проверки."""
import csv, os, sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from rules import (task_status, overdue_days, readiness, needs_attention,
                   STATUS_DONE, STATUS_WORK, STATUS_OVERDUE, STATUS_NOT_STARTED, STATUS_NO_DATA)

AS_OF = date(2026, 9, 17)
DATA = os.path.join(os.path.dirname(__file__), "..", "data", "plan.csv")


def load():
    with open(DATA, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["weight"] = int(r["weight"])
        r["regular"] = r["regular"] == "1"
    return rows


def by_id(rows, tid):
    return next(r for r in rows if r["id"] == tid)


def test_01_overdue():
    t = by_id(load(), "A-05")
    assert task_status(t, AS_OF) == STATUS_OVERDUE
    assert overdue_days(t, AS_OF) == 2


def test_02_fact_before_plan():
    t = by_id(load(), "A-02")
    assert task_status(t, AS_OF) == STATUS_DONE


def test_03_not_started_out_of_attention():
    # X-03: старт 20.09 (в будущем), финиш 22.09 (в пределах 7 дней).
    # По spec.md «Не начато» в блок внимания не попадает.
    t = by_id(load(), "X-03")
    assert task_status(t, AS_OF) == STATUS_NOT_STARTED
    assert needs_attention(t, AS_OF) is False


def test_04_finish_within_week():
    t = by_id(load(), "B-03")
    assert task_status(t, AS_OF) == STATUS_WORK
    assert needs_attention(t, AS_OF) is True


def test_05_statuses_sum_to_total():
    rows = load()
    counts = {}
    for t in rows:
        counts[task_status(t, AS_OF)] = counts.get(task_status(t, AS_OF), 0) + 1
    assert sum(counts.values()) == len(rows)


def test_06_readiness_normalised_on_plan_weights():
    rows = load()
    scope = [t for t in rows if not t["regular"]]
    total_w = sum(t["weight"] for t in scope)
    done_w = sum(t["weight"] for t in scope if task_status(t, AS_OF) == STATUS_DONE)
    assert readiness(scope, AS_OF) == round(done_w / total_w * 100, 1)


def test_07_weight_differs_from_count():
    rows = [t for t in load() if not t["regular"]]
    by_count = round(sum(1 for t in rows if task_status(t, AS_OF) == STATUS_DONE) / len(rows) * 100, 1)
    assert readiness(rows, AS_OF) != by_count


def test_09_empty_finish_no_crash():
    t = by_id(load(), "X-01")
    assert task_status(t, AS_OF) == STATUS_NO_DATA


def test_10_broken_date_no_crash():
    t = by_id(load(), "X-02")
    assert task_status(t, AS_OF) == STATUS_NO_DATA


def test_11_regular_excluded_from_readiness():
    rows = load()
    with_regular = readiness(rows, AS_OF)
    without_regular = readiness([t for t in rows if not t["regular"]], AS_OF)
    assert with_regular == without_regular, "регулярные мероприятия влияют на готовность"


def test_15_no_data_in_denominator():
    # «Нет данных» входит в знаменатель и не входит в числитель.
    # На вход подаётся полный план, регулярные функция исключает сама.
    rows = load()
    scope = [t for t in rows if not t["regular"]]
    no_data = [t for t in scope if task_status(t, AS_OF) == STATUS_NO_DATA]
    assert sorted(t["id"] for t in no_data) == ["X-01", "X-02"]
    assert sum(t["weight"] for t in no_data) == 6
    assert readiness(rows, AS_OF) == 29.6  # 32 / 108


def test_16_done_out_of_attention():
    # A-01: факт 22.07, плановый финиш 24.07 в прошлом.
    # По spec.md «Выполнено» в блок внимания не попадает независимо от плановой даты.
    rows = load()
    t = by_id(rows, "A-01")
    assert task_status(t, AS_OF) == STATUS_DONE
    assert needs_attention(t, AS_OF) is False
    done_in_attention = [r["id"] for r in rows
                         if task_status(r, AS_OF) == STATUS_DONE and needs_attention(r, AS_OF)]
    assert done_in_attention == []
