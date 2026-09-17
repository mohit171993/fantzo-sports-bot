import logging

import ibetin_liveline_v23_stable_feed as v23

logger = logging.getLogger(__name__)

_ORIGINAL_DETAIL = v23._match_detail_v23


def _match_detail_contract(key: str):
    """Return the (detail, source) pair expected by the V21 API dispatcher."""
    result = _ORIGINAL_DETAIL(key)
    if isinstance(result, tuple) and len(result) == 2:
        return result
    return result, "Roanuz V5 primary"


# V21's action=match dispatcher does: detail, source = _match_detail(key).
# Keep the richer V23 payload, but restore that two-value interface.
v23.v21._match_detail = _match_detail_contract


def _contract_self_test() -> None:
    try:
        rows, source = v23._fast_matches("live")
        if not rows:
            logger.warning("IBETIN V24 detail-contract self-test: no live rows source=%s", source)
            return
        first = rows[0]
        key = str(first.get("roanuzMatchKey") or first.get("id") or "")
        detail, detail_source = _match_detail_contract(key)
        ok = (
            isinstance(detail, dict)
            and isinstance(detail.get("match"), dict)
            and isinstance(detail.get("statistics"), list)
            and isinstance(detail.get("timeline"), list)
            and bool(detail_source)
        )
        level = logger.info if ok else logger.error
        level(
            "IBETIN V24 detail-contract self-test %s key=%s source=%s innings=%s balls=%s",
            "PASS" if ok else "FAILED",
            key,
            detail_source,
            len(detail.get("statistics") or []) if isinstance(detail, dict) else -1,
            len(detail.get("timeline") or []) if isinstance(detail, dict) else -1,
        )
        if not ok:
            raise RuntimeError("V24 match detail contract self-test failed")
    except Exception:
        logger.exception("IBETIN V24 detail-contract self-test FAILED")
        raise


_contract_self_test()
logger.info("IBETIN V24 installed: V23 UI/data + fixed match-detail API contract")

app = v23.app

if __name__ == "__main__":
    app.base.ibetin_start.main()
