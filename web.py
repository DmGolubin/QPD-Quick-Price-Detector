import logging
from datetime import datetime, timedelta

import psycopg2.extras
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

from database import get_conn
from scraper import scrape_price

logger = logging.getLogger("price-tracker.web")
jinja_env = Environment(loader=FileSystemLoader("templates"), autoescape=True)

web_app = FastAPI(title="Price Tracker", docs_url=None, redoc_url=None)
web_app.mount("/static", StaticFiles(directory="static"), name="static")


@web_app.get("/", response_class=HTMLResponse)
async def dashboard():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT w.*,
            (SELECT price FROM price_history WHERE watch_id = w.id ORDER BY recorded_at DESC LIMIT 1 OFFSET 1) as prev_price,
            (SELECT COUNT(*) FROM price_history WHERE watch_id = w.id) as data_points
        FROM watches w ORDER BY w.created_at DESC
    """)
    watches = cur.fetchall()
    cur.close()
    conn.close()
    tpl = jinja_env.get_template("dashboard.html")
    return HTMLResponse(tpl.render(watches=watches))


@web_app.get("/watch/{watch_id}", response_class=HTMLResponse)
async def watch_detail(watch_id: int):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM watches WHERE id = %s", (watch_id,))
    watch = cur.fetchone()
    if not watch:
        raise HTTPException(404)
    cur.execute(
        "SELECT * FROM price_history WHERE watch_id = %s ORDER BY recorded_at DESC LIMIT 500",
        (watch_id,)
    )
    history = cur.fetchall()
    cur.execute(
        "SELECT MIN(price) as min_p, MAX(price) as max_p, AVG(price) as avg_p FROM price_history WHERE watch_id = %s",
        (watch_id,)
    )
    stats = cur.fetchone()
    cur.close()
    conn.close()
    tpl = jinja_env.get_template("detail.html")
    return HTMLResponse(tpl.render(watch=watch, history=history, stats=stats))


@web_app.get("/api/watch/{watch_id}/chart")
async def chart_data(watch_id: int, days: int = 30):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    since = datetime.now() - timedelta(days=days)
    cur.execute(
        "SELECT price, recorded_at FROM price_history WHERE watch_id = %s AND recorded_at >= %s ORDER BY recorded_at",
        (watch_id, since)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return JSONResponse({
        "labels": [r["recorded_at"].isoformat() for r in rows],
        "prices": [float(r["price"]) for r in rows],
    })


@web_app.post("/watch/add")
async def add_watch(
    name: str = Form(...),
    url: str = Form(...),
    css_selector: str = Form(""),
    threshold_below: str = Form(""),
    threshold_above: str = Form(""),
    currency: str = Form("RUB"),
):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """INSERT INTO watches (name, url, css_selector, threshold_below, threshold_above, currency)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (name, url, css_selector or None,
         float(threshold_below) if threshold_below else None,
         float(threshold_above) if threshold_above else None,
         currency)
    )
    watch = cur.fetchone()
    cur.close()
    conn.close()

    # First scrape
    result = await scrape_price(url, css_selector or None)
    if result["price"] is not None:
        conn2 = get_conn()
        cur2 = conn2.cursor()
        cur2.execute(
            "INSERT INTO price_history (watch_id, price, raw_text) VALUES (%s, %s, %s)",
            (watch["id"], result["price"], result["raw_text"])
        )
        cur2.execute(
            "UPDATE watches SET last_price = %s, last_checked = NOW() WHERE id = %s",
            (result["price"], watch["id"])
        )
        cur2.close()
        conn2.close()

    return RedirectResponse("/", status_code=303)


@web_app.post("/watch/{watch_id}/delete")
async def delete_watch(watch_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM watches WHERE id = %s", (watch_id,))
    cur.close()
    conn.close()
    return RedirectResponse("/", status_code=303)


@web_app.post("/watch/{watch_id}/toggle")
async def toggle_watch(watch_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE watches SET is_active = NOT is_active, updated_at = NOW() WHERE id = %s", (watch_id,))
    cur.close()
    conn.close()
    return RedirectResponse("/", status_code=303)


@web_app.get("/api/watches")
async def api_watches():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM watches ORDER BY created_at DESC")
    watches = cur.fetchall()
    cur.close()
    conn.close()
    result = []
    for w in watches:
        item = dict(w)
        for k, v in item.items():
            if isinstance(v, datetime):
                item[k] = v.isoformat()
            elif hasattr(v, '__float__'):
                item[k] = float(v)
        result.append(item)
    return JSONResponse(result)


@web_app.get("/health")
async def health():
    return {"status": "ok"}
