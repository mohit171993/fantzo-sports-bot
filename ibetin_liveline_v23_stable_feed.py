import logging
import os
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
        indexes = [str(x) for x in order if str(x).startswith(side + "_") and isinstance(innings.get(str(x)), dict)]
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


# V23 runtime patch: all Roanuz match-detail normalization now understands play.innings.
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


def _score_summary(key: str):
    if not v21._valid_key(key):
        raise ValueError("Invalid match key")
    payload = v20.admin._roanuz_get(f"match/{key}/", ttl=15)
    node = v20._find_match_dict(payload, key)
    normalized = v20._normalize_roanuz_match(node)
    if not normalized.get("id"):
        normalized["id"] = key
        normalized["roanuzMatchKey"] = key
    return normalized


v21._matches = _fast_matches


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
            liveline._send_json(handler, 200, {"ok": True, "source": "score pending", "match": {"id": key}})
        return

    return v21._api(handler)


def _page() -> str:
    html = v21._page()
    html = html.replace("/admin/liveline-ibetinv21/api", liveline.LIVELINE_API_PATH)
    html = html.replace("V21 · ROANUZ", "V23 · STABLE")
    html = html.replace("20260917-v21-clean-roanuz", "20260917-v23-stable-feed")

    # Home list: hydrate live scores only. BHAV stays on-demand inside match detail.
    html = html.replace(
        "if(mode==='live')rows.slice(0,8).forEach(loadCardBhav)",
        "if(mode==='live')rows.slice(0,8).forEach(hydrateScore)",
    )

    # Remove misleading empty BHAV placeholders from list cards.
    html = html.replace("</style></head>", ".bhav{display:none!important}</style></head>")

    hydrate_js = r'''
async function hydrateScore(m){
  const key=matchKey(m); if(!key)return;
  if(m.homeScore&&m.awayScore)return;
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
    if(foot&&(s.report||s.state)) foot.textContent=s.report||s.state;
    const idx=allMatches.findIndex(x=>matchKey(x)===key);
    if(idx>=0) allMatches[idx]=Object.assign({},allMatches[idx],s);
  }catch(e){console.warn('score hydrate pending',key,e&&e.message)}
}
'''
    marker = "document.querySelectorAll('.tab').forEach(b=>b.onclick"
    html = html.replace(marker, hydrate_js + marker, 1)
    html = html.replace("Refreshing '+mode+' cricket…", "Loading '+mode+' cricket…")
    html = html.replace("setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},20000)", "setInterval(()=>{if(!document.hidden&&document.getElementById('home').style.display!=='none')load('live')},30000)")
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
            and "forEach(loadCardBhav)" not in page
        )
        rows, source = _fast_matches("live")
        if not rows:
            logger.warning("IBETIN V23 self-test: page_ok=%s live feed empty source=%s", page_ok, source)
            return
        first = rows[0]
        key = str(first.get("roanuzMatchKey") or first.get("id") or "")
        score = _score_summary(key)
        score_ok = bool(score.get("homeScore") or score.get("awayScore"))
        level = logger.info if page_ok and score_ok else logger.error
        level(
            "IBETIN V23 self-test %s page_ok=%s score_ok=%s source=%s matches=%s key=%s score=%s/%s info=%s/%s state=%s report=%s",
            "PASS" if page_ok and score_ok else "FAILED",
            page_ok,
            score_ok,
            source,
            len(rows),
            key,
            score.get("homeScore") or "-",
            score.get("awayScore") or "-",
            score.get("homeInfo") or "-",
            score.get("awayInfo") or "-",
            score.get("state") or "-",
            score.get("report") or "-",
        )
    except Exception as exc:
        logger.exception("IBETIN V23 self-test FAILED: %s", exc)


_startup_self_test()
logger.info("IBETIN V23 installed: fast fixtures + Roanuz play.innings score mapping + background hydration + on-demand BHAV")

if __name__ == "__main__":
    app.base.ibetin_start.main()
