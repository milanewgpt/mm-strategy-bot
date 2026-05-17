"""Performance metrics for paper trading results."""

from db.database import get_conn


def get_metrics() -> dict:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM paper_trades WHERE status = 'closed'")
    trades = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not trades:
        return {"total_trades": 0}

    total = len(trades)
    winners = [t for t in trades if (t["pnl_usd"] or 0) > 0]
    losers = [t for t in trades if (t["pnl_usd"] or 0) <= 0]
    win_rate = len(winners) / total * 100

    gross_profit = sum(t["pnl_usd"] for t in winners)
    gross_loss = abs(sum(t["pnl_usd"] for t in losers)) or 0.001
    profit_factor = gross_profit / gross_loss

    avg_win = gross_profit / len(winners) if winners else 0
    avg_loss = -gross_loss / len(losers) if losers else 0

    longs = [t for t in trades if t["direction"] == "LONG"]
    shorts = [t for t in trades if t["direction"] == "SHORT"]

    long_wr = sum(1 for t in longs if (t["pnl_usd"] or 0) > 0) / len(longs) * 100 if longs else 0
    short_wr = sum(1 for t in shorts if (t["pnl_usd"] or 0) > 0) / len(shorts) * 100 if shorts else 0

    total_pnl = sum(t["pnl_usd"] or 0 for t in trades)

    # Avg hold time
    def hold_hours(t: dict) -> float:
        if not t.get("opened_at") or not t.get("closed_at"):
            return 0
        from datetime import datetime
        try:
            opened = datetime.fromisoformat(t["opened_at"].replace("Z", "+00:00"))
            closed = datetime.fromisoformat(t["closed_at"].replace("Z", "+00:00"))
            return (closed - opened).total_seconds() / 3600
        except Exception:
            return 0

    avg_hold = sum(hold_hours(t) for t in trades) / total if total else 0

    return {
        "total_trades": total,
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "total_pnl_usd": round(total_pnl, 2),
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "long_trades": len(longs),
        "short_trades": len(shorts),
        "long_win_rate_pct": round(long_wr, 1),
        "short_win_rate_pct": round(short_wr, 1),
        "avg_hold_hours": round(avg_hold, 1),
    }
