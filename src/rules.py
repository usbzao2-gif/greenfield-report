# -*- coding: utf-8 -*-
"""Правила расчёта статусов. Единственное место, где живёт бизнес-логика.

Спецификация: docs/spec.md
Критерии приёмки: docs/benchmark.md
"""
from datetime import date

STATUS_DONE = "Выполнено"
STATUS_WORK = "В работе"
STATUS_OVERDUE = "Просрочено"
STATUS_NOT_STARTED = "Не начато"
STATUS_NO_DATA = "Нет данных"


def parse_date(value):
    """Возвращает date или None. Битый формат не роняет сборку."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


def task_status(task, as_of):
    """Статус мероприятия на отчётную дату.

    Колонка status из исходного файла намеренно не используется:
    она ведётся вручную и устаревает.
    """
    start = parse_date(task.get("start"))
    finish = parse_date(task.get("finish"))
    fact = parse_date(task.get("fact"))

    if fact:
        return STATUS_DONE
    if finish is None or start is None:
        return STATUS_NO_DATA
    if finish < as_of:
        return STATUS_OVERDUE
    if start <= as_of:
        return STATUS_WORK
    return STATUS_NOT_STARTED


def overdue_days(task, as_of):
    finish = parse_date(task.get("finish"))
    fact = parse_date(task.get("fact"))
    if fact or finish is None or finish >= as_of:
        return 0
    return (as_of - finish).days


def readiness(tasks, as_of):
    """Готовность по весам, в процентах, с одним знаком после запятой.

    Числитель: веса мероприятий со статусом «Выполнено».
    Знаменатель: веса всех мероприятий, кроме регулярных.
    «Нет данных» входит в знаменатель и не входит в числитель.
    Регулярные мероприятия исключаются здесь, а не в вызывающем коде.
    См. docs/spec.md, раздел «Готовность».
    """
    scope = [t for t in tasks if not t.get("regular")]
    total = sum(t["weight"] for t in scope)
    if total == 0:
        return 0.0
    done = sum(t["weight"] for t in scope if task_status(t, as_of) == STATUS_DONE)
    return round(done / total * 100, 1)


def needs_attention(task, as_of, horizon_days=7):
    """Попадает ли мероприятие в блок «Требует внимания».

    Попадают: «Просрочено», «Нет данных» и «В работе» с плановым финишем
    в ближайшие horizon_days дней. «Выполнено» и «Не начато» не попадают.
    См. docs/spec.md, раздел «Блок „Требует внимания“».
    """
    st = task_status(task, as_of)
    if st in (STATUS_OVERDUE, STATUS_NO_DATA):
        return True
    if st != STATUS_WORK:
        return False
    finish = parse_date(task.get("finish"))
    return (finish - as_of).days <= horizon_days


REQUIRED_COLUMNS = ("id", "direction", "name", "owner", "start", "finish", "fact", "weight", "regular")
WEIGHT_HINT = "ожидается целое число 0 или больше"


class PlanError(ValueError):
    """Негодные входные данные плана. Сборка останавливается, подстановок нет."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("Сборка остановлена, данные плана негодны:\n" + "\n".join(errors))


def validate_plan(fieldnames, rows, source="plan.csv"):
    """Все ошибки входных данных плана. Пустой список: план годен.

    Строки нумеруются как в файле: заголовок строка 1. Даты не проверяются,
    битая дата даёт статус «Нет данных». См. docs/spec.md, «Проверка входных данных».
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in (fieldnames or [])]
    if missing:
        return ["{}: нет обязательной колонки {}".format(source, c) for c in missing]
    errors, first_line = [], {}
    for n, r in enumerate(rows, start=2):
        tid = (r.get("id") or "").strip()
        where = "{}, строка {} ({})".format(source, n, tid or "без кода")
        if not tid:
            errors.append(where + ": пустой код мероприятия")
        elif tid in first_line:
            errors.append(where + ": код мероприятия повторяется, впервые в строке {}".format(first_line[tid]))
        else:
            first_line[tid] = n
        if not (r.get("name") or "").strip():
            errors.append(where + ": пустое название мероприятия")
        w = (r.get("weight") or "").strip()
        if not w:
            errors.append(where + ": вес пустой, " + WEIGHT_HINT)
        else:
            try:
                if int(w) < 0:
                    errors.append(where + ": вес «{}» отрицательный, ".format(w) + WEIGHT_HINT)
            except ValueError:
                errors.append(where + ": вес «{}» не целое число, ".format(w) + WEIGHT_HINT)
        reg = (r.get("regular") or "").strip()
        if reg not in ("0", "1"):
            errors.append(where + ": признак регулярности «{}», ожидается 0 или 1".format(reg))
    return errors
