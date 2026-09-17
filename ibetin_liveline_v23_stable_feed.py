import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse

import ibetin_liveline_trial as liveline
import ibetin_liveline_v21_roanuz_clean_ui as v21
import ibetin_liveline_v20_roanuz_primary_ui as v20

logger = logging.getLogger(__name__)

liveline.LIVELINE_PATH = "/admin/liveline-ibetinv23"
liveline.LIVELINE_API_PATH = "/admin/liveline-ibetinv23/api"
_BASE_NORMALIZE = v20._normalize_roanuz_match


def _admin_url() -> str:
    root = os.getenv("TRACKING_BASE_URL", "").strip().rstrip("/") or "https://ibetin-app-production.up.railway.app"
    return f"{root}{liveline.LIVELINE_PATH}?{urlencode({'t': liveline._token(), 'v': '20260917-v23-stable-feed'})}"


def _overs_text(value) -> str:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return f"{value[0]}.{value[1]} ov"
    if value not in (None, ""):
        text = str(value)
        return text if "ov" in text.lower() else f"{text} ov"
    return ""


def _inning_text(row):
    if not isinstance(row, dict):
        return "", ""
    raw = str(row.get("score_str") or "").strip()
    if raw:
        score = raw.split(" in ", 1)[0].strip()
    else:
        score_obj = row.get("score") if isinstance(row.get("score"), dict) else {}
        runs = score_obj.get("runs")
        if runs is None:
            runs = row.get("runs")
        wickets = row.get("wickets")
        if wickets is None:
            wickets = score_obj.get("wickets")
        score = "" if runs is None else str(runs)
        if score and wickets is not None:
            score += f"/{wickets}"
    overs = row.get("overs")
    if overs in (None, "") and isinstance(row.get("score"), dict):
        overs = row["score"].get("overs")
    return score, _overs_text(overs)


def _apply_play_scores(normalized, node):
    out = dict(normalized or {})
    if not isinstance(node, dict):
        return out
    play = node.get("play") if isinstance(node.get("play"), dict) else {}
    innings = play.get("innings") if isinstance(play.get("innings"), dict) else {}
    order = play.get("innings_order") if isinstance(play.get("innings_order"), list) else []

    def side_score(side: str):
        indexes = [
            str(x)
            for x in order
            if str(x).startswith(side + "_") and isinstance(innings.get(str(x)), dict)
        ]
        if not indexes:
            for idx, row in innings.items():
                if not str(idx).startswith(side + "_") or not isinstance(row, dict):
                    continue
                sc = row.get("score") if isinstance(row.get("score"), dict) else {}
                runs = sc.get("runs")
                balls = sc.get("balls")
                if row.get("is_completed") or (runs not in (None, 0)) or (balls not in (None, 0)):
                    indexes.append(str(idx))
        texts = []
        last_info = ""
        for idx in indexes:
            text, info = _inning_text(innings.get(idx))
            if text:
                texts.append(text)
                last_info = info or last_info
        return " & ".join(texts), last_info

    a_score, a_info = side_score("a")
    b_score, b_info = side_score("b")
    if a_score:
        out["homeScore"] = a_score
        out["homeInfo"] = a_info
    if b_score:
        out["awayScore"] = b_score
        out["awayInfo"] = b_info

    live = play.get("live") if isinstance(play.get("live"), dict) else {}
    live_score = live.get("score") if isinstance(live.get("score"), dict) else {}
    title = str(live_score.get("title") or "").strip()
    batting = str(live.get("batting_team") or "").strip().lower()
    if title:
        side = out.get("home") if batting == "a" else out.get("away") if batting == "b" else {}
        team_name = side.get("name") if isinstance(side, dict) else ""
        out["report"] = f"{team_name} {title}".strip()
    return out


def _normalize_with_play(node):
    return _apply_play_scores(_BASE_NORMALIZE(node), node)


# V23 runtime patch: all Roanuz match-detail normalization understands play.innings.
v20._normalize_roanuz_match = _normalize_with_play


def _fast_matches(mode: str):
    source = "Roanuz V5 primary"
    try:
        rows = v20._roanuz_matches_mode(mode)
    except Exception as exc:
        logger.warning("IBETIN V23 Roanuz %s list failed: %s", mode, str(exc)[:160])
        rows = []

    valid = [m for m in rows if v21._display_ok(m)]
    if valid:
        logger.info(
            "IBETIN V23 feed mode=%s source=Roanuz matches=%s first=%s vs %s",
            mode,
            len(valid),
            valid[0].get("home", {}).get("name"),
            valid[0].get("away", {}).get("name"),
        )
        return valid[:40], source

    try:
        fallback = v20._OLD_MATCHES_MODE(mode)
        if fallback:
            logger.warning("IBETIN V23 display fallback mode=%s matches=%s", mode, len(fallback))
            return fallback[:40], "Highlightly display fallback"
    except Exception as exc:
        logger.warning("IBETIN V23 fallback failed mode=%s: %s", mode, str(exc)[:160])
    return [], source


def _match_payload(key: str):
    if not v21._valid_key(key):
        raise ValueError("Invalid match key")
    payload = v20.admin._roanuz_get(f"match/{key}/", ttl=15)
    node = v20._find_match_dict(payload, key)
    if not isinstance(node, dict):
        node = {}
    return payload, node


def _score_summary(key: str):
    _payload, node = _match_payload(key)
    normalized = v20._normalize_roanuz_match(node)
    if not normalized.get("id"):
        normalized["id"] = key
        normalized["roanuzMatchKey"] = key
    return normalized


def _ordered_innings(node):
    play = node.get("play") if isinstance(node, dict) and isinstance(node.get("play"), dict) else {}
    innings = play.get("innings") if isinstance(play.get("innings"), dict) else {}
    order = play.get("innings_order") if isinstance(play.get("innings_order"), list) else []
    rows = []
    seen = set()
    for idx in order:
        idx = str(idx)
        row = innings.get(idx)
        if isinstance(row, dict):
            item = dict(row)
            item.setdefault("index", idx)
            rows.append(item)
            seen.add(idx)
    for idx, row in innings.items():
        idx = str(idx)
        if idx in seen or not isinstance(row, dict):
            continue
        item = dict(row)
        item.setdefault("index", idx)
        rows.append(item)
    return rows


_TAG_RE = re.compile(r"<[^>]+>")


def _embedded_timeline(node):
    play = node.get("play") if isinstance(node, dict) and isinstance(node.get("play"), dict) else {}
    related = play.get("related_balls")
    if not isinstance(related, (dict, list)):
        related = node.get("related_balls") if isinstance(node, dict) else None
    if isinstance(related, dict):
        values = list(related.values())
    elif isinstance(related, list):
        values = related
    else:
        values = []

    rows = []
    for ball in values:
        if not isinstance(ball, dict):
            continue
        overs = ball.get("overs")
        if isinstance(overs, (list, tuple)) and len(overs) >= 2:
            ball_label = f"{overs[0]}.{overs[1]}"
        else:
            ball_label = str(
                ball.get("over_str")
                or ball.get("overStr")
                or ball.get("ball")
                or ball.get("over")
                or ""
            )
        comment = str(
            ball.get("comment")
            or ball.get("commentary")
            or ball.get("description")
            or ball.get("text")
            or ""
        )
        comment = _TAG_RE.sub("", comment).strip()
        display_score = str(ball.get("display_score") or "").strip()
        if display_score and display_score not in comment:
            comment = f"{comment} · {display_score}".strip(" ·")
        try:
            sort_value = float(ball.get("updated_time") or ball.get("entry_time") or 0)
        except (TypeError, ValueError):
            sort_value = 0.0
        rows.append({"ball": ball_label, "commentary": comment, "_sort": sort_value})
    rows.sort(key=lambda x: x.get("_sort", 0))
    for row in rows:
        row.pop("_sort", None)
    return rows[-240:]


def _match_detail_v23(key: str):
    _payload, node = _match_payload(key)
    normalized = v20._normalize_roanuz_match(node)
    if not normalized.get("id"):
        normalized["id"] = key
        normalized["roanuzMatchKey"] = key

    play = node.get("play") if isinstance(node.get("play"), dict) else {}
    live = play.get("live") if isinstance(play.get("live"), dict) else {}
    live_score = live.get("score") if isinstance(live.get("score"), dict) else {}
    venue = node.get("venue") if isinstance(node.get("venue"), dict) else {}

    return {
        "match": normalized,
        "venue": venue,
        "forecast": {},
        "statistics": _ordered_innings(node),
        "squad": [],
        "bestBatsmen": [],
        "bestBowlers": [],
        "inplayData": live,
        # Roanuz already includes recent delivery objects in match/{key}/.
        # Use them instead of the separate ball-by-ball endpoint, which returns
        # HTTP 400 for some currently live matches.
        "timeline": _embedded_timeline(node),
        "roanuz": {
            "matchKey": key,
            "source": "Roanuz V5 primary",
            "target": play.get("target"),
            "runRate": live_score.get("run_rate"),
            "toss": node.get("toss"),
            "winner": node.get("winner"),
        },
    }


v21._matches = _fast_matches
v21._match_detail = _match_detail_v23


def _api(handler):
    q = parse_qs(urlparse(handler.path).query)
    action = (q.get("action") or ["matches"])[0].strip().lower()
    key = (q.get("matchId") or q.get("id") or q.get("key") or [""])[0].strip()

    if action == "score":
        try:
            match = _score_summary(key)
            liveline._send_json(
                handler,
                200,
                {
                    "ok": True,
                    "source": "Roanuz V5 live score",
                    "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "match": match,
                },
            )
        except ValueError as exc:
            liveline._send_json(handler, 400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            logger.warning("IBETIN V23 score hydrate failed key=%s: %s", key, str(exc)[:160])
            liveline._send_json(
                handler,
                200,
                {"ok": True, "source": "score pending", "match": {"id": key}},
            )
        return

    return v21._api(handler)


def _page() -> str:
    html = v21._page()
    html = html.replace("/admin/liveline-ibetinv21/api", liveline.LIVELINE_API_PATH)
    html = html.replace("V21 · ROANUZ", "V23 · STABLE")
    html = html.replace("20260917-v21-clean-roanuz", "20260917-v23-stable-feed")

    # Home list: hydrate live scores only. BHAV stays on-demand in match detail.
    html = html.replace(
        "if(mode==='live')rows.slice(0,8).forEach(loadCardBhav)",
        "if(mode==='live')rows.slice(0,8).forEach(hydrateScore)",
    )

    # Readability and Telegram mobile safe-area polish.
    ui_css = r"""
.bhav{display:none!important}
body{padding-bottom:calc(84px + env(safe-area-inset-bottom))}
.brand span{font-size:9px}.v{font-size:9px}.tab{font-size:11px}
.hero small{font-size:8px}.hero p{font-size:10px;line-height:1.4}
.pill{font-size:8px}.status{font-size:9px}.league{font-size:10px}
.fmt{font-size:8px}.badge{font-size:8px}.ta,.si{font-size:8px}
.foot{font-size:9px;line-height:1.35}.bottom{bottom:max(8px,env(safe-area-inset-bottom))}
.bottom button{font-size:8px}.ptitle b{font-size:11px}.notice{font-size:10px}
.table{font-size:9px}.ball{font-size:9px}.graph{font-size:9px}
.scorecardRow strong{font-size:17px;color:#083f7f}
"""
    html = html.replace(
        "</style></head>",
        ui_css + '</style><link rel="icon" href="data:"></head>',
        1,
    )

    # Roanuz start_at is an epoch in seconds. Native JS Date expects ms.
    old_fmt = "function fmtTime(v){if(!v)return'';try{return new Date(v).toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch(e){return String(v)}}"
    new_fmt = r"function fmtTime(v){if(!v)return'';try{let x=v;if(typeof v==='string'&&/^\d+(\.\d+)?$/.test(v))x=Number(v)*1000;else if(typeof v==='number'&&v<1000000000000)x=v*1000;const d=new Date(x);if(Number.isNaN(d.getTime()))return'';return d.toLocaleString([],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}catch(e){return''}}function prettyState(v){const s=String(v||'').toLowerCase().replace(/[_-]+/g,' ').trim();if(!s)return'';if(['in play','inplay','started','live','playing'].includes(s))return'LIVE';if(['not started','scheduled','upcoming','fixture','created','confirmed'].includes(s))return'UPCOMING';if(['completed','complete','finished','result','ended','closed'].includes(s))return'FINAL';return s.replace(/\b\w/g,c=>c.toUpperCase())}"
    html = html.replace(old_fmt, new_fmt, 1)
    html = html.replace(
        "esc(m.state||fmtTime(m.startTime)||mode.toUpperCase())",
        "esc(mode==='upcoming'?(fmtTime(m.startTime)||'UPCOMING'):mode==='results'?(prettyState(m.state)||'FINAL'):(prettyState(m.state)||mode.toUpperCase()))",
    )
    html = html.replace(
        "esc(m.report||m.state||fmtTime(m.startTime)||'Tap for details')",
        "esc(m.report||(mode==='upcoming'?fmtTime(m.startTime):prettyState(m.state))||'Tap for details')",
    )

    # Make the fixed bottom bar match what it actually does.
    html = html.replace(
        '<button data-nav="cricket"><b>🏏</b>CRICKET</button>',
        '<button data-nav="cricket"><b>◷</b>UPCOMING</button>',
    )
    html = html.replace(
        '<button data-nav="alerts"><b>🔔</b>ALERTS</button>',
        '<button data-nav="alerts"><b>✓</b>RESULTS</button>',
    )
    html = html.replace(
        '<button data-nav="more"><b>•••</b>MORE</button>',
        '<button data-nav="more"><b>⌕</b>SEARCH</button>',
    )
    html = html.replace(
        "if(x==='live'||x==='cricket'||x==='home'){backHome();load('live')}else if(x==='alerts'){alert('Smart match alerts are active in IBETIN.')}else document.getElementById('search').focus()",
        "if(x==='home'||x==='live'){backHome();load('live')}else if(x==='cricket'){backHome();load('upcoming')}else if(x==='alerts'){backHome();load('results')}else{backHome();document.getElementById('search').focus()}",
    )

    hydrate_js = r"""
const __scoreHydrateAt=new Map(),__scoreHydrateBusy=new Set();
async function hydrateScore(m){
  const key=matchKey(m); if(!key)return;
  if(m.homeScore&&m.awayScore)return;
  const now=Date.now(),last=__scoreHydrateAt.get(key)||0;
  if(__scoreHydrateBusy.has(key)||now-last<12000)return;
  __scoreHydrateBusy.add(key);__scoreHydrateAt.set(key,now);
  try{
    const j=await api({action:'score',matchId:key});
    const s=j.match||{};
    const box=Array.from(document.querySelectorAll('.match')).find(x=>x.dataset.key===key);
    if(!box)return;
    const scores=box.querySelectorAll('.sc');
    if(scores[0]&&s.homeScore) scores[0].textContent=s.homeScore;
    if(scores[1]&&s.awayScore) scores[1].textContent=s.awayScore;
    const infos=box.querySelectorAll('.si');
    if(infos[0]&&s.homeInfo) infos[0].textContent=s.homeInfo;
    if(infos[1]&&s.awayInfo) infos[1].textContent=s.awayInfo;
    const foot=box.querySelector('.foot span');
    if(foot&&(s.report||s.state)) foot.textContent=s.report||prettyState(s.state);
    const idx=allMatches.findIndex(x=>matchKey(x)===key);
    if(idx>=0) allMatches[idx]=Object.assign({},allMatches[idx],s);
  }catch(e){console.warn('score hydrate pending',key,e&&e.message)}
  finally{__scoreHydrateBusy.delete(key);__scoreHydrateAt.set(key,Date.now())}
}
function scorecardHtml(rows,m){
  return rows.map(r=>{
    const idx=String((r&&r.index)||'');
    const side=idx.startsWith('a_')?(m.home||{}):idx.startsWith('b_')?(m.away||{}):{};
    const name=side.name||idx.replace('_',' ').toUpperCase()||'Innings';
    const sc=(r&&r.score&&typeof r.score==='object')?r.score:{};
    let score=String((r&&r.score_str)||'').split(' in ')[0];
    if(!score){
      const runs=sc.runs;
      const wk=(r&&r.wickets!==undefined)?r.wickets:sc.wickets;
      score=(runs===undefined||runs===null)?'':String(runs)+(wk===undefined||wk===null?'':'/'+wk);
    }
    const ov=Array.isArray(r&&r.overs)?r.overs.join('.'):(r&&r.overs)||'';
    const rr=sc.run_rate;
    return `<div class="notice scorecardRow"><div style="display:flex;justify-content:space-between;gap:10px;align-items:center"><b>${esc(name)}</b><strong>${esc(score||'—')}</strong></div><div style="margin-top:5px">${ov?esc(ov)+' overs':''}${rr!==undefined&&rr!==null?(ov?' · ':'')+'RR '+esc(rr):''}</div></div>`;
  }).join('');
}
"""
    marker = "document.querySelectorAll('.tab').forEach(b=>b.onclick"
    html = html.replace(marker, hydrate_js + marker, 1)

    html = html.replace(
        "else if(tab==='scorecard'){const s=x.statistics||[];p.innerHTML=ptitle('SCORECARD')+(s.length?`<div class=\"graph\">${esc(JSON.stringify(s,null,2).slice(0,9000))}</div>`:'<div class=\"notice\">Scorecard data is not available yet.</div>')}",
        "else if(tab==='scorecard'){const s=x.statistics||[];p.innerHTML=ptitle('SCORECARD')+(s.length?scorecardHtml(s,m):'<div class=\"notice\">Scorecard data is not available yet.</div>')}",
        1,
    )

    # Use Telegram's native back control while match detail is open.
    html = html.replace(
        "async function openMatch(key){document.getElementById('home').style.display='none';",
        "async function openMatch(key){if(tg&&tg.BackButton)try{tg.BackButton.show()}catch(e){}document.getElementById('home').style.display='none';",
        1,
    )
    html = html.replace(
        "function backHome(){document.getElementById('detail').style.display='none';",
        "function backHome(){if(tg&&tg.BackButton)try{tg.BackButton.hide()}catch(e){}document.getElementById('detail').style.display='none';",
        1,
    )
    back_marker = "document.querySelectorAll('.tab').forEach(b=>b.onclick"
    back_js = "if(tg&&tg.BackButton){try{tg.BackButton.onClick(()=>{if(document.getElementById('detail').style.display==='block')backHome()})}catch(e){}}"
    html = html.replace(back_marker, back_js + back_marker, 1)

    html = html.replace("Refreshing '+mode+' cricket…", "Loading '+mode+' cricket…")
    html = html.replace(
        "setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},20000)",
        "setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},30000)",
    )
    return html


liveline.admin_url = _admin_url
liveline._page = _page
liveline._api = _api
app = v21.app


def _startup_self_test() -> None:
    try:
        page = _page()
        page_ok = (
            "/admin/liveline-ibetinv23/api" in page
            and "hydrateScore" in page
            and "__scoreHydrateBusy" in page
            and "forEach(loadCardBhav)" not in page
        )
        rows, source = _fast_matches("live")
        if not rows:
            logger.warning("IBETIN V23 self-test: page_ok=%s live feed empty source=%s", page_ok, source)
            return
        first = rows[0]
        key = str(first.get("roanuzMatchKey") or first.get("id") or "")
        score = _score_summary(key)
        detail = _match_detail_v23(key)
        score_ok = bool(score.get("homeScore") or score.get("awayScore"))
        detail_ok = isinstance(detail.get("statistics"), list) and isinstance(detail.get("timeline"), list)
        level = logger.info if page_ok and score_ok and detail_ok else logger.error
        level(
            "IBETIN V23 self-test %s page_ok=%s score_ok=%s detail_ok=%s source=%s matches=%s key=%s score=%s/%s info=%s/%s innings=%s balls=%s state=%s report=%s",
            "PASS" if page_ok and score_ok and detail_ok else "FAILED",
            page_ok,
            score_ok,
            detail_ok,
            source,
            len(rows),
            key,
            score.get("homeScore") or "-",
            score.get("awayScore") or "-",
            score.get("homeInfo") or "-",
            score.get("awayInfo") or "-",
            len(detail.get("statistics") or []),
            len(detail.get("timeline") or []),
            score.get("state") or "-",
            score.get("report") or "-",
        )
    except Exception as exc:
        logger.exception("IBETIN V23 self-test FAILED: %s", exc)


_startup_self_test()
logger.info(
    "IBETIN V23 installed: stable Roanuz feed + embedded scorecard/balls + deduped hydration + mobile UI polish"
)

if __name__ == "__main__":
    app.base.ibetin_start.main()
