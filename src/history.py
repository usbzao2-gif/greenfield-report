# -*- coding: utf-8 -*-
"""Снимки состояния и сравнение с базой. Правила: docs/spec.md, раздел «Что изменилось»."""
import json, os, re
from datetime import date

from rules import STATUS_DONE, STATUS_OVERDUE

NAME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.json$")


def snapshot(plan, ready, as_of):
    """Снимок на отчётную дату: то, что нужно для сравнения завтра."""
    return {
        "as_of": as_of.isoformat(),
        "ready": ready,
        "tasks": {t["id"]: {"name": t["name"], "status": t["calc"], "start": t.get("start", ""),
                            "finish": t.get("finish", ""), "fact": t.get("fact", ""),
                            "weight": t["weight"]} for t in plan},
    }


def save(history_dir, snap):
    """Пишет снимок атомарно: сначала во временный файл, затем переименование."""
    os.makedirs(history_dir, exist_ok=True)
    path = os.path.join(history_dir, snap["as_of"] + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, sort_keys=True, indent=1)
    os.replace(tmp, path)
    return path


def load_base(history_dir, as_of):
    """Последний читаемый снимок с датой строго раньше as_of или None."""
    if not os.path.isdir(history_dir):
        return None
    days = []
    for name in os.listdir(history_dir):
        m = NAME.match(name)
        if not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if d < as_of:
            days.append((d, name))
    for d, name in sorted(days, reverse=True):
        try:
            with open(os.path.join(history_dir, name), encoding="utf-8") as f:
                snap = json.load(f)
            if snap.get("as_of") == d.isoformat() and "tasks" in snap:
                return snap
        except (ValueError, OSError):
            continue  # повреждённый снимок пропускается
    return None


def diff(base, cur):
    """Разница между базой и текущим снимком. Списки отсортированы по коду."""
    b, c = base["tasks"], cur["tasks"]
    both = sorted(set(b) & set(c))
    return {
        "base_date": base["as_of"],
        "closed": [k for k in both if b[k]["status"] != STATUS_DONE and c[k]["status"] == STATUS_DONE],
        "overdue": [k for k in both if b[k]["status"] != STATUS_OVERDUE and c[k]["status"] == STATUS_OVERDUE],
        "moved": [(k, b[k]["finish"], c[k]["finish"]) for k in both if b[k]["finish"] != c[k]["finish"]],
        "ready_delta": round(cur["ready"] - base["ready"], 1),
        "added": len(set(c) - set(b)),
        "removed": len(set(b) - set(c)),
    }
