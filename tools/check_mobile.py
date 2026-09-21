# -*- coding: utf-8 -*-
"""Ручная проверка дашборда глазами читателя (docs/benchmark.md, проверки 12, 13, 17, 20).

Открывает build/dashboard.html в headless Chromium: окно 375x812 (телефон) и 1280x800.
Проверяет то, что должен увидеть читатель, а не только размеры контейнеров.
Зависимость не входит в репозиторий, ставится один раз:
    pip install playwright
    python -m playwright install chromium

Запуск из корня репозитория:
    python tools/check_mobile.py
    python tools/check_mobile.py build/dashboard.html --shot build_375.png

Код выхода 0, если все проверки прошли, иначе 1. Снимок экрана смотреть глазами.
"""
import argparse, os, pathlib, sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Нет playwright. Установите: pip install playwright && python -m playwright install chromium")

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LONG_WORD = "Сверхдлинноеназваниебезпробеловдляпроверкиширины" * 2

MEASURE = """() => {
  const vw = document.documentElement.clientWidth;
  const inside = e => { const r = e.getBoundingClientRect(); return r.left >= -0.5 && r.right <= vw + 0.5; };
  const shown = e => e && e.getClientRects().length > 0;
  const cards = [...document.querySelectorAll('.cards .card')];
  const bad = [];
  cards.forEach((c, i) => {
    const code = c.querySelector('.c-code')?.textContent || ('#' + i);
    for (const f of ['c-name', 'c-status', 'c-finish', 'c-code']) {
      const e = c.querySelector('.' + f);
      if (!shown(e) || !inside(e) || e.scrollWidth > e.clientWidth + 1) bad.push(code + ' ' + f);
    }
    if (!inside(c)) bad.push(code + ' карточка шире экрана');
  });
  const multi = [...document.querySelectorAll('.nw')].filter(e => shown(e)).filter(e => {
    const r = document.createRange(); r.selectNodeContents(e); return r.getClientRects().length > 1;
  }).map(e => e.textContent);
  const table = document.querySelector('.att-table');
  return {
    vw, page: document.documentElement.scrollWidth,
    cardsShown: cards.length > 0 && shown(cards[0]), tableShown: shown(table),
    cards: cards.length, rows: table ? table.querySelectorAll('tbody tr').length : 0,
    heads: table ? [...table.querySelectorAll('th')].map(t => t.textContent) : [],
    bad, multi,
  };
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=os.path.join(ROOT, "build", "dashboard.html"))
    ap.add_argument("--shot", help="куда сохранить снимок всей страницы на 375 пикселях, PNG")
    a = ap.parse_args()
    uri = pathlib.Path(os.path.abspath(a.path)).as_uri()

    ext = []
    with sync_playwright() as p:
        b = p.chromium.launch()

        pg = b.new_page(viewport={"width": 375, "height": 812}, device_scale_factor=2)
        pg.on("request", lambda r: ext.append(r.url) if not r.url.startswith("file:") else None)
        pg.goto(uri)
        m = pg.evaluate(MEASURE)
        if a.shot:
            pg.screenshot(path=a.shot, full_page=True)
        # Проба: одно очень длинное слово в названии первой карточки.
        pg.evaluate("w => { const n = document.querySelector('.cards .c-name'); if (n) n.textContent += ' ' + w; }", LONG_WORD)
        s = pg.evaluate(MEASURE)
        pg.close()

        pg = b.new_page(viewport={"width": 1280, "height": 800})
        pg.goto(uri)
        w = pg.evaluate(MEASURE)
        b.close()

    heads = ["Код", "Статус", "Плановый финиш", "Мероприятие", "Ответственный"]
    checks = [
        ("12 внешних запросов нет", not ext, ext),
        ("13 телефон: страница не шире экрана", m["page"] <= m["vw"], "{} из {}".format(m["page"], m["vw"])),
        ("20 телефон: блок внимания карточками, таблица скрыта", m["cardsShown"] and not m["tableShown"],
         "карточки {}, таблица {}".format(m["cardsShown"], m["tableShown"])),
        ("20 телефон: карточка на каждое мероприятие блока", m["cards"] == m["rows"] and m["cards"] > 0,
         "карточек {}, строк {}".format(m["cards"], m["rows"])),
        ("17, 20 телефон: код, название, статус и финиш целиком на экране", m["cards"] > 0 and not m["bad"],
         m["bad"] or "карточек {}".format(m["cards"])),
        ("20 телефон, длинное слово: название целиком, страница не шире экрана",
         s["cards"] > 0 and not s["bad"] and s["page"] <= s["vw"], "{}; ширина {} из {}".format(s["bad"], s["page"], s["vw"])),
        ("17 коды и даты в одну строку", not m["multi"], m["multi"]),
        ("20 экран 1280: блок внимания таблицей, карточки скрыты", w["tableShown"] and not w["cardsShown"],
         "таблица {}, карточки {}".format(w["tableShown"], w["cardsShown"])),
        ("20 экран 1280: колонки в заданном порядке", w["heads"] == heads, w["heads"]),
    ]
    for name, ok, detail in checks:
        print("{}  {}  ({})".format("OK  " if ok else "FAIL", name, detail))
    sys.exit(0 if all(ok for _, ok, _ in checks) else 1)


if __name__ == "__main__":
    main()
