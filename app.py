import json, os
from datetime import date
import pandas as pd
import streamlit as st
import compliance as C
import llm

st.set_page_config(page_title="Software Licence Compliance Assistant", layout="wide")
HERE = os.path.dirname(os.path.abspath(__file__))
COLORS = {"Expired": "#f4b6b6", "Over-deployed": "#ffc7ce", "Expiring soon": "#fce4d6", "Under-used": "#ffeb9c", "Compliant": "#c6efce"}


def secret_key():
    try:
        return st.secrets.get("OPENAI_API_KEY")
    except Exception:
        return None


with st.sidebar:
    st.header("Settings")
    key = st.text_input("OpenAI API key", type="password", value=os.getenv("OPENAI_API_KEY") or secret_key() or "",
                        help="Leave blank to run in offline demo mode.")
    model = st.text_input("Model", value="gpt-4o-mini")
    as_of = st.date_input("As-of date", value=date.today())
    window = st.slider("Expiring-soon window (days)", 15, 120, 60)
    under = st.slider("Under-use threshold (% of seats used)", 30, 90, 60) / 100
    st.caption("Mode: " + ("GPT-assisted" if key else "offline demo (no API key)"))
client = llm.make_client(key)

st.title("Software Licence Compliance Assistant")
st.write("Check licence inventory against purchased entitlements, then use GPT to explain the risks and read licence agreements. "
         "Counts and costs are calculated in code; GPT only writes explanations.")

tab1, tab2, tab3 = st.tabs(["Inventory check", "Agreement terms", "Ask the agreement"])

# ---- Tab 1 ----
with tab1:
    up = st.file_uploader("Licence inventory (CSV)", type="csv")
    st.caption("Columns: " + ", ".join(C.REQUIRED) + ". Leave the sample in place to try the app.")
    try:
        raw = C.read_inventory(up if up else os.path.join(HERE, "sample_licenses.csv"))
    except ValueError as e:
        st.error(str(e)); st.stop()
    d = C.analyse(raw, as_of, window, under)
    s = C.summarise(d)
    c = st.columns(5)
    c[0].metric("Products", s["total_products"])
    c[1].metric("Over-deployed", s["status_counts"]["Over-deployed"])
    c[2].metric("Expired / expiring", s["status_counts"]["Expired"] + s["status_counts"]["Expiring soon"])
    c[3].metric("True-up exposure", f"${s['estimated_trueup_exposure_usd']:,.0f}")
    c[4].metric("Potential saving", f"${s['potential_saving_usd']:,.0f}")
    show = d[["Software", "Vendor", "License Type", "Purchased Seats", "Installed Seats", "Utilisation", "Days to Expiry",
              "Status", "True-up Exposure (USD)", "Potential Saving (USD)"]]
    st.dataframe(show.style.map(lambda v: f"background-color:{COLORS.get(v, '')}; color:#000" if v in COLORS else "", subset=["Status"])
                 .format({"Utilisation": "{:.0%}", "Days to Expiry": "{:.0f}", "True-up Exposure (USD)": "${:,.0f}", "Potential Saving (USD)": "${:,.0f}"}, na_rep="n/a"),
                 width='stretch', hide_index=True)
    st.bar_chart(pd.Series(s["status_counts"], name="Products"))
    if st.button("Generate risk report", type="primary"):
        items = C.findings(d)
        try:
            with st.spinner("Writing report..."):
                st.session_state["report"] = llm.risk_report(client, model, s, items) if client else C.offline_report(s, items)
        except Exception as e:
            st.error(f"GPT request failed: {e}")
    if "report" in st.session_state:
        st.markdown(st.session_state["report"])
        st.download_button("Download report (.md)", st.session_state["report"], "licence_risk_report.md")

# ---- Agreement input shared by tabs 2 and 3 ----
def agreement_text(key_prefix):
    use_sample = st.checkbox("Use sample agreement", value=True, key=key_prefix + "s")
    f = st.file_uploader("Or upload a .txt agreement", type="txt", key=key_prefix + "f")
    if f:
        return f.read().decode("utf-8", errors="ignore")
    if use_sample:
        return open(os.path.join(HERE, "sample_agreement.txt"), encoding="utf-8").read()
    return st.text_area("Paste agreement text", height=200, key=key_prefix + "t")

with tab2:
    text = agreement_text("a")
    with st.expander("Agreement text"):
        st.text(text)
    if st.button("Extract key terms", type="primary", disabled=not text.strip()):
        if not client:
            st.warning("Term extraction needs an OpenAI API key. Add one in the sidebar.")
        else:
            try:
                with st.spinner("Reading agreement..."):
                    st.session_state["terms"] = llm.extract_clauses(client, model, text)
            except json.JSONDecodeError:
                st.error("The model returned invalid JSON. Try again.")
            except Exception as e:
                st.error(f"GPT request failed: {e}")
    t = st.session_state.get("terms")
    if t:
        flags = t.pop("risk_flags", []) if isinstance(t, dict) else []
        rows = [{"Term": k.replace("_", " ").title(), "Summary": v.get("value", ""), "Evidence": v.get("evidence", "")}
                for k, v in t.items() if isinstance(v, dict)]
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
        if flags:
            st.subheader("Risk flags")
            st.dataframe(pd.DataFrame(flags), width='stretch', hide_index=True)
        st.download_button("Download terms (.json)", json.dumps({**t, "risk_flags": flags}, indent=2), "licence_terms.json")
        st.session_state["terms"] = {**t, "risk_flags": flags}

with tab3:
    text3 = agreement_text("b")
    q = st.text_input("Question", placeholder="Can contractors use the software? What happens if we exceed our user count?")
    if st.button("Ask") and q.strip():
        try:
            st.markdown(llm.ask(client, model, q, text3) if client else llm.offline_search(q, text3))
        except Exception as e:
            st.error(f"GPT request failed: {e}")
    st.caption("Informational only, not legal advice. Have Legal confirm contract interpretations.")
