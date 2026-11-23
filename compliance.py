"""Deterministic licence-compliance checks. All numbers shown to the user come from here, never from the LLM."""
from __future__ import annotations
from datetime import date
import pandas as pd

REQUIRED = ["Software", "Vendor", "License Type", "Purchased Seats", "Installed Seats", "Expiry Date", "Annual Cost (USD)"]
STATUS_ORDER = ["Expired", "Over-deployed", "Expiring soon", "Under-used", "Compliant"]


def read_inventory(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("Missing column(s): " + ", ".join(missing) + ". Expected: " + ", ".join(REQUIRED))
    for c in ("Purchased Seats", "Installed Seats", "Annual Cost (USD)"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Expiry Date"] = pd.to_datetime(df["Expiry Date"], errors="coerce")
    bad = df[df[["Purchased Seats", "Installed Seats", "Annual Cost (USD)"]].isna().any(axis=1)]
    if not bad.empty:
        raise ValueError(f"{len(bad)} row(s) have non-numeric seats or cost (first: {bad.iloc[0]['Software']}).")
    return df[REQUIRED].copy()


def analyse(df: pd.DataFrame, as_of: date, window_days: int = 60, under_use_pct: float = 0.6) -> pd.DataFrame:
    d = df.copy()
    ts = pd.Timestamp(as_of)
    d["Utilisation"] = (d["Installed Seats"] / d["Purchased Seats"].where(d["Purchased Seats"] > 0)).fillna(0)
    d["Seat Gap"] = d["Installed Seats"] - d["Purchased Seats"]
    d["Days to Expiry"] = (d["Expiry Date"] - ts).dt.days
    unit = (d["Annual Cost (USD)"] / d["Purchased Seats"].where(d["Purchased Seats"] > 0)).fillna(0)
    d["Unit Cost"] = unit

    def status(r):
        if pd.notna(r["Days to Expiry"]) and r["Days to Expiry"] < 0:
            return "Expired"
        if r["Seat Gap"] > 0:
            return "Over-deployed"
        if pd.notna(r["Days to Expiry"]) and r["Days to Expiry"] <= window_days:
            return "Expiring soon"
        if r["Utilisation"] < under_use_pct:
            return "Under-used"
        return "Compliant"

    d["Status"] = d.apply(status, axis=1)
    d["True-up Exposure (USD)"] = (d["Seat Gap"].clip(lower=0) * d["Unit Cost"]).round(0)
    d["Potential Saving (USD)"] = ((-d["Seat Gap"]).clip(lower=0) * d["Unit Cost"]).where(d["Status"] == "Under-used", 0).round(0)
    return d


def summarise(d: pd.DataFrame) -> dict:
    counts = d["Status"].value_counts().to_dict()
    return {
        "total_products": int(len(d)),
        "status_counts": {s: int(counts.get(s, 0)) for s in STATUS_ORDER},
        "total_annual_spend_usd": float(d["Annual Cost (USD)"].sum()),
        "estimated_trueup_exposure_usd": float(d["True-up Exposure (USD)"].sum()),
        "potential_saving_usd": float(d["Potential Saving (USD)"].sum()),
    }


def findings(d: pd.DataFrame, limit: int = 12) -> list[dict]:
    f = d[d["Status"] != "Compliant"].copy()
    f["rank"] = f["Status"].map({s: i for i, s in enumerate(STATUS_ORDER)})
    f = f.sort_values(["rank", "True-up Exposure (USD)"], ascending=[True, False]).head(limit)
    out = []
    for _, r in f.iterrows():
        out.append({
            "software": r["Software"], "vendor": r["Vendor"], "license_type": r["License Type"], "status": r["Status"],
            "purchased": int(r["Purchased Seats"]), "installed": int(r["Installed Seats"]),
            "utilisation_pct": round(r["Utilisation"] * 100, 1),
            "days_to_expiry": None if pd.isna(r["Days to Expiry"]) else int(r["Days to Expiry"]),
            "trueup_exposure_usd": float(r["True-up Exposure (USD)"]), "potential_saving_usd": float(r["Potential Saving (USD)"]),
        })
    return out


def offline_report(summary: dict, items: list[dict]) -> str:
    """Template fallback used when no API key is set, so the demo still works."""
    lines = ["### Executive summary",
             f"{summary['total_products']} products reviewed, annual spend ${summary['total_annual_spend_usd']:,.0f}. "
             f"Estimated true-up exposure is ${summary['estimated_trueup_exposure_usd']:,.0f} and potential savings from unused seats are ${summary['potential_saving_usd']:,.0f}.",
             "", "### Priority findings"]
    for i in items[:8]:
        if i["status"] == "Expired":
            lines.append(f"- **{i['software']}** ({i['vendor']}): licence expired {abs(i['days_to_expiry'])} days ago while {i['installed']} seats are installed. Renew or remove.")
        elif i["status"] == "Over-deployed":
            lines.append(f"- **{i['software']}** ({i['vendor']}): {i['installed']} installed vs {i['purchased']} purchased. Exposure about ${i['trueup_exposure_usd']:,.0f}.")
        elif i["status"] == "Expiring soon":
            lines.append(f"- **{i['software']}** ({i['vendor']}): expires in {i['days_to_expiry']} days. Start renewal now.")
        else:
            lines.append(f"- **{i['software']}** ({i['vendor']}): only {i['utilisation_pct']}% of seats used. Consider reducing at renewal (about ${i['potential_saving_usd']:,.0f}).")
    lines += ["", "### Recommended actions",
              "1. Remove or purchase seats for over-deployed products before any vendor audit.",
              "2. Renew or uninstall expired products.",
              "3. Right-size under-used products at the next renewal.",
              "", "_Template summary (offline mode). Add an OpenAI API key for a GPT-written report._"]
    return "\n".join(lines)
