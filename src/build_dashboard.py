# -*- coding: utf-8 -*-
"""Сборка дашборда проекта «Гринфилд-1».

Запуск:
    python src/build_dashboard.py --as-of 2026-09-17
"""
import argparse, csv, os, sys
from datetime import date, datetime, timedelta, timezone

import history
from rules import (PlanError, validate_plan, parse_date, task_status, overdue_days, readiness, needs_attention,
                   STATUS_DONE, STATUS_WORK, STATUS_OVERDUE, STATUS_NOT_STARTED, STATUS_NO_DATA)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def read(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_plan(path=None):
    """План с проверкой входных данных. Негодные данные: PlanError, без подстановок."""
    path = path or os.path.join(ROOT, "data", "plan.csv")
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    errors = validate_plan(reader.fieldnames, rows, os.path.basename(path))
    if errors:
        raise PlanError(errors)
    for r in rows:
        r["weight"] = int(r["weight"])
        r["regular"] = r["regular"].strip() == "1"
    return rows


HISTORY_DIR = os.path.join(ROOT, "data", "history")
PROJECT_STAGE = "концепция и ТЭО"
MSK = timezone(timedelta(hours=3), "MSK")  # Москва без перехода на летнее время


def make_html(as_of, history_dir=None, plan_path=None, built_at=None):
    """Собирает страницу в памяти и возвращает (html, сводка). Ничего не пишет.

    Снимки только читаются: база сравнения берётся из history_dir.
    built_at: время сборки; по умолчанию текущее. Выводится по московскому времени.
    """
    built_at = (built_at or datetime.now(timezone.utc)).astimezone(MSK)
    plan = load_plan(plan_path)
    journal = read("journal.csv")
    risks = read("risks.csv")

    for t in plan:
        t["calc"] = task_status(t, as_of)
        t["days"] = overdue_days(t, as_of)

    counts = {s: sum(1 for t in plan if t["calc"] == s)
              for s in (STATUS_DONE, STATUS_WORK, STATUS_OVERDUE, STATUS_NOT_STARTED, STATUS_NO_DATA)}
    ready = readiness(plan, as_of)

    attention = [t for t in plan if needs_attention(t, as_of)]
    snap = history.snapshot(plan, ready, as_of)
    base = history.load_base(history_dir or HISTORY_DIR, as_of)
    changes = history.diff(base, snap) if base else None
    html = render(as_of, plan, counts, ready, attention, journal, risks, changes, built_at)
    return html, {"ready": ready, "counts": counts, "snapshot": snap}


def build(as_of, history_dir=None, out=None, plan_path=None, built_at=None):
    """Сборка: страница, затем файл дашборда, и только после него снимок."""
    history_dir = history_dir or HISTORY_DIR
    html, summary = make_html(as_of, history_dir, plan_path, built_at)
    out = out or os.path.join(ROOT, "build", "dashboard.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)
    os.replace(tmp, out)
    history.save(history_dir, summary["snapshot"])
    print("Собрано:", out)
    print(summary_line(summary))
    return out


def summary_line(summary):
    counts = summary["counts"]
    return "Готовность: {}%. Просрочено: {}. Нет данных: {}.".format(
        fmt_num(summary["ready"]), counts[STATUS_OVERDUE], counts[STATUS_NO_DATA])


def fmt_date(value):
    """ДД.ММ.ГГГГ для вывода. Некорректная дата выводится как есть, пустая остаётся пустой."""
    d = parse_date(value)
    return d.strftime("%d.%m.%Y") if d else (value or "")


def date_problem(value, what):
    """Объяснение для пустой или некорректной даты, иначе None."""
    raw = (value or "").strip()
    if parse_date(raw) is not None:
        return None
    return "{} указан неверно: {}".format(what, raw) if raw else "{} не определён".format(what)


def finish_text(t):
    """Плановый финиш для блока внимания и признак, что это объяснение, а не дата.

    У «Нет данных» объясняет, что не так: сначала со сроком, затем со стартом.
    """
    if t["calc"] == STATUS_NO_DATA:
        problems = [p for p in (date_problem(t.get("finish"), "срок"), date_problem(t.get("start"), "старт")) if p]
        if problems:
            return "; ".join(problems), True
    return fmt_date(t.get("finish")), False


def fmt_num(x):
    """Число с одним знаком после запятой, десятичный разделитель запятая."""
    return "{:.1f}".format(x).replace(".", ",")


def table(headers, rows, cls=""):
    """Таблица с заголовками в прокручиваемом контейнере.

    headers: список (название, классы ячейки). "nw" запрещает перенос строки,
    rows: список списков значений в порядке headers.
    cls: дополнительный класс контейнера.
    """
    head = "".join("<th class='{}'>{}</th>".format(c, h) for h, c in headers)
    body = "".join(
        "<tr>" + "".join("<td class='{}'>{}</td>".format(c, v) for (_, c), v in zip(headers, r)) + "</tr>"
        for r in rows) or "<tr><td colspan='{}'>Нет позиций</td></tr>".format(len(headers))
    return "<div class='tw {}'><table><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>".format(cls, head, body).replace("tw '", "tw'")


def fmt_delta(x):
    """Разница в п.п. со знаком: +1,2, -0,5, 0,0."""
    return ("+" if x > 0 else "") + fmt_num(x)


def changes_block(changes, plan, limit=5):
    """Блок «Что изменилось». Без базы только «Нет базы для сравнения»."""
    if changes is None:
        return "<section class='changes'><h2>Что изменилось</h2><p>Нет базы для сравнения</p></section>"
    names = {t["id"]: t["name"] for t in plan}

    def category(title, items):
        if not items:
            return "<li><b>{}: нет</b></li>".format(title)
        shown = "".join("<li>{}</li>".format(i) for i in items[:limit])
        more = "<li>и ещё {}</li>".format(len(items) - limit) if len(items) > limit else ""
        return "<li><b>{}: {}</b><ul>{}{}</ul></li>".format(title, len(items), shown, more)

    item = lambda k: "<span class='nw'>{}</span> {}".format(k, names[k])
    moved = ["{}: было <span class='nw'>{}</span>, стало <span class='nw'>{}</span>".format(
        item(k), fmt_date(old) or "не указан", fmt_date(new) or "не указан") for k, old, new in changes["moved"]]
    return ("<section class='changes'><h2>Что изменилось</h2><p>Изменения с {base}</p><ul class='chg'>"
            "{closed}{overdue}<li><b>Готовность: {delta} п.п.</b></li>{moved}"
            "<li><b>Состав плана: добавлено {added}, удалено {removed}</b></li></ul></section>").format(
        base=fmt_date(changes["base_date"]),
        closed=category("Закрылись", [item(k) for k in changes["closed"]]),
        overdue=category("Ушли в просрочку", [item(k) for k in changes["overdue"]]),
        delta=fmt_delta(changes["ready_delta"]), moved=category("Переносы сроков", moved),
        added=changes["added"], removed=changes["removed"])


def render(as_of, plan, counts, ready, attention, journal, risks, changes=None, built_at=None):
    # Разметка вынесена в отдельную функцию намеренно: логика в rules.py, вид здесь.
    # Состав и требования к виду: docs/spec.md, разделы «Состав дашборда» и «Оформление».
    regular = sum(1 for t in plan if t["regular"])
    statuses = "".join("<li>{}: <b>{}</b></li>".format(s, counts[s])
                       for s in (STATUS_DONE, STATUS_WORK, STATUS_OVERDUE, STATUS_NOT_STARTED, STATUS_NO_DATA))
    # Блок внимания: таблица на широком экране, карточки на экране уже 600 пикселей.
    t_att = table([("Код", "nw"), ("Статус", "nw"), ("Плановый финиш", "nw"), ("Мероприятие", ""),
                   ("Ответственный", "")],
                  [[t["id"], t["calc"], finish_text(t)[0], t["name"], t["owner"]] for t in attention],
                  cls="att-table")
    c_att = "<div class='cards'>{}</div>".format("".join(
        "<div class='card'><div class='c-title'><span class='c-code nw'>{id}</span> "
        "<span class='c-name'>{name}</span></div>"
        "<div class='c-meta'><span class='c-status nw'>{calc}</span>, {label}"
        "<span class='c-finish{nw}'>{finish}</span></div>"
        "<div class='c-owner'>{owner}</div></div>".format(
            id=t["id"], name=t["name"], calc=t["calc"], owner=t["owner"], finish=finish_text(t)[0],
            **({"label": "", "nw": ""} if finish_text(t)[1] else {"label": "финиш ", "nw": " nw"}))
        for t in attention) or "<div class='card'>Нет позиций</div>")
    t_j = table([("Дата", "nw"), ("Код", "nw"), ("Событие", ""), ("Тип", ""), ("Следующий шаг", "")],
                [[fmt_date(e["date"]), e["id"], e["event"], e["type"], e["next"]] for e in reversed(journal)])
    t_r = table([("Код", "nw"), ("Риск", ""), ("Уровень", ""), ("Митигация", "")],
                [[r["id"], r["risk"], r["level"], r["mitigation"]] for r in risks])
    return """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Дашборд проекта «Гринфилд-1»</title>
<style>body{{font:14px sans-serif;margin:24px}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ddd;padding:6px;text-align:left;vertical-align:top}}
th{{background:#f3f4f6}}
.nw{{white-space:nowrap}}
.meta{{color:#555;margin-top:-8px}}
.tw{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
.st{{list-style:none;padding:0;margin:8px 0 0;display:flex;flex-wrap:wrap;gap:4px 16px}}
.cards{{display:none}}
.card{{border:1px solid #ddd;border-radius:6px;padding:8px 10px;margin:0 0 8px}}
.c-title{{overflow-wrap:anywhere}}.c-code{{font-weight:700;margin-right:4px}}.c-name{{font-weight:600}}
.c-meta{{margin-top:4px}}
.chg{{padding-left:18px}}.chg ul{{padding-left:18px;margin:2px 0 6px}}.chg li{{margin:2px 0}}.c-owner{{margin-top:2px;color:#555;font-size:13px}}
@media (max-width:599px){{.att-table{{display:none}}.cards{{display:block}}}}
@media (max-width:480px){{body{{margin:16px}}}}</style></head><body>
<h1>Проект «Гринфилд-1». Дашборд на {as_of}</h1>
<p class="meta"><span class="nw">Собран {built}.</span> Стадия: {stage}.</p>
<p>Готовность по весу: <b>{ready}%</b>.</p>
<p>Всего мероприятий: {total}, из них в расчёте готовности {in_scope}, регулярных {regular}.</p>
<ul class="st">{statuses}</ul>
{chg}
<h2>Требует внимания</h2>{t_att}{c_att}
<h2>Журнал событий</h2>{t_j}
<h2>Риски</h2>{t_r}
</body></html>""".format(as_of=as_of.strftime("%d.%m.%Y"), stage=PROJECT_STAGE,
                         built=built_at.strftime("%d.%m.%Y в %H:%M") if built_at else "", ready=fmt_num(ready), total=len(plan),
                         in_scope=len(plan) - regular, regular=regular, statuses=statuses,
                         t_att=t_att, c_att=c_att, chg=changes_block(changes, plan), t_j=t_j, t_r=t_r)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--plan", help="план, по умолчанию data/plan.csv")
    ap.add_argument("--history", help="папка снимков, по умолчанию data/history")
    ap.add_argument("--out", help="файл дашборда, по умолчанию build/dashboard.html")
    a = ap.parse_args(argv)
    y, m, d = map(int, a.as_of.split("-"))
    try:
        build(date(y, m, d), history_dir=a.history, out=a.out, plan_path=a.plan)
    except PlanError as e:
        print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
