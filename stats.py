"""
Dashboard ke numbers. Sab kuch SQLite (items + events) se nikalta hai — koi bahar ka service nahi.
Timing (avg sec/thumbnail) sirf v3 ke baad bane thumbnails ka hota hai (pehle record nahi hota tha).
"""
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import db


def _day(ts):
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _avg(xs):
    xs = [x for x in xs if x is not None and x > 0]
    return round(sum(xs) / len(xs), 1) if xs else None


def _median(xs):
    xs = sorted(x for x in xs if x is not None and x > 0)
    if not xs:
        return None
    m = len(xs) // 2
    return round(xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2, 1)


def _norm_error(e):
    e = (e or "").strip()
    if not e:
        return "Unknown"
    low = e.lower()
    if "mana" in low or "refus" in low or "policy" in low or "safety" in low:
        return "ChatGPT ne mana kiya / policy"
    if "timeout" in low or "time pe" in low:
        return "Timeout"
    if "save nahi" in low:
        return "Image save nahi hui"
    if "chrome" in low or "9222" in low or "9223" in low or "cdp" in low:
        return "Chrome / login connection"
    if "429" in low or "limit" in low or "quota" in low:
        return "Rate limit / quota"
    return re.sub(r"\s+", " ", e)[:60]


def _jlen(t):
    try:
        v = json.loads(t or "[]")
        return len(v) if isinstance(v, list) else 0
    except Exception:
        return 0


def _variant_use(ok_ev):
    c = Counter()
    for e in ok_ev:
        try:
            v = json.loads(e.get("meta") or "{}").get("variant")
        except Exception:
            v = None
        if isinstance(v, int) and v >= 0:
            c["ABCDEF"[v] if v < 6 else str(v)] += 1
    return [{"variant": k, "count": c[k]} for k in sorted(c)]


def build(series_dir_fn, agent_online_secs=45, days=14, workspace_id=None):
    now = time.time()
    today = _day(now)
    week_ago = now - 7 * 86400

    series = db.list_series(workspace_id)
    sids = {x["id"] for x in series}
    items = db.q("SELECT id, series_id, kind, status, poster_path, updated_at, prompt, label, "
                 "COALESCE(regen_count,0) AS regen_count FROM items")
    if workspace_id is not None:
        items = [i for i in items if i["series_id"] in sids]
    ev_thumb = [e for e in db.events("thumb") if workspace_id is None or e.get("series_id") in sids]
    ev_prompt = []
    ev_poster = [e for e in db.events("poster") if workspace_id is None or e.get("series_id") in sids]
    ev_train = []

    eps = [i for i in items if i["kind"] == "episode"]
    done = [i for i in items if i["status"] == "done"]
    failed = [i for i in items if i["status"] == "failed"]
    pending = [i for i in items if i["status"] in ("pending", "queued", "running")]
    posters = [i for i in items if (i.get("poster_path") or "").strip()]

    ok_ev = [e for e in ev_thumb if e.get("ok")]
    secs_ok = [e["seconds"] for e in ok_ev if e.get("seconds") is not None]
    first_try = [e for e in ok_ev if (e.get("attempts") or 1) == 1]
    week_ok = [e for e in ok_ev if (e.get("ended_at") or 0) >= week_ago]

    # ---- KPIs ----
    kpi = {
        "series": len(series),
        "series_complete": sum(1 for s in series if s["total"] and s["done"] == s["total"]),
        "episodes": len(eps),
        "thumbs_done": len(done),
        "thumbs_failed": len(failed),
        "thumbs_pending": len(pending),
        "posters": len(posters),
        "today": sum(1 for e in ok_ev if e.get("ended_at") and _day(e["ended_at"]) == today),
        "week": len(week_ok),
        "avg_sec": _avg(secs_ok),
        "median_sec": _median(secs_ok),
        "avg_sec_week": _avg([e["seconds"] for e in week_ok if e.get("seconds") is not None]),
        "success_rate": round(100 * len(ok_ev) / len(ev_thumb)) if ev_thumb else None,
        "first_try_rate": round(100 * len(first_try) / len(ok_ev)) if ok_ev else None,
        "timed_thumbs": len(ok_ev),
        "hours_generating": round(sum(secs_ok) / 3600, 1) if secs_ok else 0,
        "regens": sum(i["regen_count"] or 0 for i in items),
    }

    # ---- daily trend (last N days) ----
    start = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    daily = []
    by_day_ok, by_day_fail, by_day_sec = Counter(), Counter(), defaultdict(list)
    for e in ev_thumb:
        d = _day(e.get("ended_at"))
        if not d:
            continue
        if e.get("ok"):
            by_day_ok[d] += 1
            if e.get("seconds") is not None:
                by_day_sec[d].append(e["seconds"])
        else:
            by_day_fail[d] += 1
    for k in range(days):
        d = (start + timedelta(days=k)).strftime("%Y-%m-%d")
        daily.append({"date": d, "ok": by_day_ok[d], "failed": by_day_fail[d], "avg_sec": _avg(by_day_sec[d])})

    # ---- per series ----
    sec_by_series = defaultdict(list)
    for e in ok_ev:
        if e.get("series_id") and e.get("seconds") is not None:
            sec_by_series[e["series_id"]].append(e["seconds"])
    last_act = {}
    for e in ev_thumb + ev_prompt:
        sid = e.get("series_id")
        end_ts = e.get("ended_at") or 0
        if sid and end_ts:
            last_act[sid] = max(last_act.get(sid, 0), end_ts)
    poster_by_series = Counter(i["series_id"] for i in posters)
    ep_by_series = Counter(i["series_id"] for i in eps)
    rows = []
    for s in series:
        rows.append({
            "id": s["id"], "name": s["name"], "engine": s["engine"], "created_at": s.get("created_at") or "",
            "created_by": s.get("created_by") or "",
            "episodes": ep_by_series[s["id"]], "total": s["total"], "done": s["done"], "failed": s["failed"],
            "posters": poster_by_series[s["id"]],
            "avg_sec": _avg(sec_by_series[s["id"]]),
            "last_activity": last_act.get(s["id"]),
        })

    # ---- people / agents ----
    per = defaultdict(lambda: {"ok": 0, "failed": 0, "secs": []})
    for e in ev_thumb:
        p = per[e.get("who") or "Hub PC"]
        if e.get("ok"):
            p["ok"] += 1
            if e.get("seconds") is not None:
                p["secs"].append(e["seconds"])
        else:
            p["failed"] += 1
    users = {u["name"]: u for u in db.list_users()}
    people = []
    for who, p in sorted(per.items(), key=lambda kv: -kv[1]["ok"]):
        u = users.get(who)
        people.append({"who": who, "ok": p["ok"], "failed": p["failed"], "avg_sec": _avg(p["secs"]),
                       "online": bool(u and now - (u.get("last_seen") or 0) < agent_online_secs) if u else None})
    online = [u["name"] for u in users.values() if now - (u.get("last_seen") or 0) < agent_online_secs]

    # ---- failures ----
    fails = Counter(_norm_error(e.get("error")) for e in ev_thumb if not e.get("ok"))
    if not fails:  # purana data: items ke error se
        fails = Counter(_norm_error(i.get("error")) for i in db.q("SELECT error FROM items WHERE status='failed'"))
    top_fail = [{"reason": r, "count": c} for r, c in fails.most_common(5)]

    # ---- master variants / regenerate ----
    regen_items = [i for i in items if (i.get("regen_count") or 0) > 0]
    variants = {
        "regens": sum(i["regen_count"] or 0 for i in items),
        "items_regenerated": len(regen_items),
        "regen_rate": round(100 * len(regen_items) / len(done)) if done else None,
        "use": _variant_use(ok_ev),
        "series_with_variants": sum(1 for s_ in series if _jlen(s_.get("master_variants")) > 1),
        "series_with_characters": sum(1 for s_ in series if _jlen(s_.get("characters")) > 0),
    }

    # ---- engines + posters ----
    eng = Counter(e.get("engine") or "browser" for e in ok_ev)
    poster_secs = []
    for e in ev_poster:
        try:
            n = json.loads(e.get("meta") or "{}").get("count") or 0
            secs = e.get("seconds")
            if n and secs is not None:
                poster_secs.append(secs / n)
        except Exception:
            pass

    # ---- recent activity feed ----
    feed = []
    sname = {s["id"]: s["name"] for s in series}
    for e in sorted(ev_thumb + ev_prompt + ev_poster + ev_train, key=lambda e: -(e.get("ended_at") or 0))[:12]:
        feed.append({"kind": e.get("kind", ""), "ok": bool(e.get("ok")), "who": e.get("who", ""),
                     "series": sname.get(e.get("series_id"), ""),
                     "item_id": e.get("item_id"), "seconds": e.get("seconds"),
                     "at": e.get("ended_at"), "error": (e.get("error") or "")[:80],
                     "model": e.get("model", "")})
    labels = {i["id"]: i["label"] for i in items}
    for f in feed:
        f["label"] = labels.get(f.pop("item_id"), "")

    # ---- busiest hours ----
    hours = Counter(datetime.fromtimestamp(e["ended_at"]).hour for e in ok_ev if e.get("ended_at"))

    return {
        "generated_at": now, "kpi": kpi, "daily": daily, "series": rows, "people": people,
        "agents_online": online, "failures": top_fail, "variants": variants,
        "engines": [{"engine": k, "count": v} for k, v in eng.most_common()],
        "poster_avg_sec": _avg(poster_secs), "feed": feed,
        "hours": [{"hour": h, "count": hours[h]} for h in range(24)],
    }
