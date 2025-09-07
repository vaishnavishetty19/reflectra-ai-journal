# ---------- Reflectra: AI-Powered Wellness Journal (compact) ----------
# Copyright (c) 2025 Vaishnavi Shetty. All rights reserved.


import json, re, sqlite3
from datetime import datetime, timedelta, date
import pandas as pd, streamlit as st, ollama
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

st.set_page_config(page_title="Reflectra", page_icon="🪞", layout="centered")

#UI
def set_bg(url:str):
    st.markdown(f"""
    <style>
      .stApp{{background-image:url('{url}');background-size:cover;background-position:center;background-attachment:fixed}}
      .block-container{{background:rgba(255,255,255,.88);border-radius:12px;padding:2rem}}
      @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&display=swap');
      html,body,[class*="css"]{{font-family:'Nunito',system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
      .card,.info,.success{{backdrop-filter:blur(6px);border-radius:18px !important;box-shadow:0 10px 26px rgba(0,0,0,.10);border:1px solid rgba(255,255,255,.65) !important}}
      .stTextArea textarea,.stTextInput input{{background:rgba(255,255,255,.9) !important;border:1px solid rgba(0,0,0,.06) !important;border-radius:14px !important;font-size:.98rem !important}}
      .stTextArea textarea{{min-height:140px !important}}
      .stButton>button{{background:linear-gradient(135deg,#31c7b5,#78e0d2) !important;color:#083344 !important;border:0 !important;border-radius:12px !important;padding:10px 16px !important;font-weight:700 !important;box-shadow:0 6px 18px rgba(49,199,181,.28)}}
      .stButton>button:hover{{transform:translateY(-1px);box-shadow:0 10px 22px rgba(49,199,181,.32)}}
      .badge{{border-radius:999px !important;padding:4px 10px !important;font-weight:600}}
      .badge.red{{background:#fff5f5;color:#7f1d1d;border:1px solid #ffd1d1}}
      .badge.orange{{background:#fff8ea;color:#7c2d12;border:1px solid #ffe1b3}}
      .badge.green{{background:#f3faf5;color:#14532d;border:1px solid #cdeccf}}
      [data-testid="stSidebar"]{{background:rgba(255,255,255,.92) !important;backdrop-filter:blur(8px);border-right:1px solid rgba(0,0,0,.05);min-width:200px;max-width:220px}}
      [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2{{color:#0f172a !important;font-weight:700 !important}}
      [data-testid="stSidebar"] div[role="radiogroup"] label{{border:1px solid #d1d5db;border-radius:999px;padding:6px 14px;margin:4px 2px;background:#fff;cursor:pointer;font-size:.95rem}}
      [data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"]{{background:#31c7b5 !important;color:#083344 !important;border:none;box-shadow:0 4px 14px rgba(49,199,181,.25)}}
      .block-container{{max-width:1040px; margin:0 auto; padding: 2rem; padding-top:10px; margin-top: 170px; margin-left:180px;}}
    </style>""", unsafe_allow_html=True)

set_bg("https://images.unsplash.com/photo-1507525428034-b723cf961d3e")

st.title("🎯 Reflectra : AI-Powered Wellness Journal")
st.caption("Private & local (Ollama + SQLite). No cloud calls.")
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Journal","History"], index=0)

# ---- consts
DB_PATH="reflectra.db"; LLM_MODEL="phi3:mini"; MAX_GEN_TOKENS=120
SYSTEM_PROMPT=("You are Reflectra. Return ONLY minified JSON with keys: "
               "summary (<=40 words), affirmation (1 short sentence, second-person), "
               "ritual (a single, specific 3–5 minute action starting with a verb). "
               "No markdown, no extra text. Ground strictly in the user's entry.")

@st.cache_resource
def _warmup():
    try: ollama.chat(model=LLM_MODEL, messages=[{"role":"user","content":"ok"}], options={"num_predict":1})
    except Exception: pass
_warmup()

# ---- helpers
@st.cache_resource
def _an(): return SentimentIntensityAnalyzer()
an=_an()
label_sentiment=lambda x: "Positive 😊" if x>=.05 else ("Negative 😔" if x<=-.05 else "Neutral 😐")
mood_percent=lambda x: max(0.0, min(1.0, (x+1)/2))
def extract_json(s:str)->dict:
    try: return json.loads(s)
    except Exception: pass
    m=re.search(r"\{.*\}", s, flags=re.DOTALL)
    if not m: raise ValueError("Model did not return JSON.")
    return json.loads(m.group(0))

BURNOUT_KEYWORDS={"overwork":["deadline","overtime","late night","back-to-back","no break","pressure","crunch"],
                  "sleep":["insomnia","slept late","3am","tired","fatigue","restless"],
                  "self-talk":["not good enough","can't keep up","overwhelmed","exhausted","stressed"]}

def burnout_signal(text:str, sentiment:float, rituals_df:pd.DataFrame)->dict:
    t=text.lower(); hits=sum(any(k in t for k in words) for words in BURNOUT_KEYWORDS.values())
    if rituals_df.empty: miss=0.0
    else:
        df=rituals_df.copy(); df["due_date"]=pd.to_datetime(df["due_date"]).dt.date
        df=df[df["due_date"]>= (datetime.now().date()-timedelta(days=7))]
        miss=0.0 if df.empty else 1.0-(df["done"].sum()/len(df))
    sent_risk=1.0-((sentiment+1)/2)
    risk=(0.45*sent_risk+0.4*miss+0.15*min(hits,3)/3)*100
    level="Low 🟢" if risk<35 else ("Moderate 🟠" if risk<70 else "High 🔴")
    drivers=[]; 
    if sent_risk>.6: drivers.append("low mood")
    if miss>.5: drivers.append("low ritual adherence")
    if hits>=2: drivers.append("stress keywords")
    return {"risk":round(risk,1),"level":level,"drivers":drivers}

monday=lambda d: d - timedelta(days=d.weekday())
def compute_streak(df:pd.DataFrame)->int:
    today=datetime.now().date(); streak=0; day=today; done={}
    for _,r in df.iterrows():
        d=datetime.strptime(r["due_date"],"%Y-%m-%d").date()
        done[d]=done.get(d,False) or bool(r["done"])
    while done.get(day,False): streak+=1; day=day-timedelta(days=1)
    return streak

def compute_weekly_wellbeing(entries_30d:pd.DataFrame, rituals_df:pd.DataFrame)->dict:
    today=datetime.now().date(); wk=monday(today); lwk=wk-timedelta(days=7); lwkend=wk-timedelta(days=1)
    def avg_sent(df,a,b):
        if df.empty: return 0.0
        d=df.copy(); d["date"]=pd.to_datetime(d["ts"]).dt.date
        d=d[(d["date"]>=a)&(d["date"]<=b)]
        return 0.0 if d.empty else (float(d["sentiment"].mean())+1)/2*100.0
    def adh(df,a,b):
        if df.empty: return 0.0
        d=df.copy(); d["date"]=pd.to_datetime(d["due_date"]).dt.date
        d=d[(d["date"]>=a)&(d["date"]<=b)]
        return 0.0 if d.empty else float(d["done"].sum())/len(d)*100.0
    sent_this, sent_last = avg_sent(entries_30d,wk,today), avg_sent(entries_30d,lwk,lwkend)
    adh_this, adh_last   = adh(rituals_df,wk,today),      adh(rituals_df,lwk,lwkend)
    streak_days=compute_streak(rituals_df); streak_comp=min(streak_days/7.0,1.0)*100.0
    score_this=.4*sent_this+.4*adh_this+.2*streak_comp; score_last=.4*sent_last+.4*adh_last
    return {"score":round(score_this,1),"delta":round(score_this-score_last,1),
            "sent7":round(sent_this,1),"adh7":round(adh_this,1),
            "streak_days":int(streak_days),"week_start":wk.strftime("%Y-%m-%d")}

# ---- DB
def init_db():
    with sqlite3.connect(DB_PATH) as con:
        c=con.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS entries(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, text TEXT NOT NULL,
            summary TEXT, affirmation TEXT, ritual TEXT, sentiment REAL);""")
        c.execute("""CREATE TABLE IF NOT EXISTS rituals(
            id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER NOT NULL, ritual TEXT NOT NULL,
            due_date TEXT NOT NULL, done INTEGER DEFAULT 0,
            FOREIGN KEY(entry_id) REFERENCES entries(id));""")
        con.commit()
def add_entry(text, summary, affirmation, ritual, sentiment)->int:
    ts=datetime.now().strftime("%Y-%m-%d %H:%M")
    with sqlite3.connect(DB_PATH) as con:
        c=con.cursor()
        c.execute("INSERT INTO entries(ts,text,summary,affirmation,ritual,sentiment) VALUES(?,?,?,?,?,?)",
                  (ts,text,summary,affirmation,ritual,float(sentiment)))
        eid=c.lastrowid; due=(datetime.now()+timedelta(days=1)).strftime("%Y-%m-%d")
        c.execute("SELECT COUNT(*) FROM rituals WHERE due_date=?", (due,)); 
        if c.fetchone()[0]==0: c.execute("INSERT INTO rituals(entry_id,ritual,due_date,done) VALUES(?,?,?,0)",(eid,ritual,due))
        con.commit(); return eid
def get_recent_entries(days=30):
    cutoff=(datetime.now()-timedelta(days=days)).strftime("%Y-%m-%d 00:00")
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query("SELECT * FROM entries WHERE ts>=? ORDER BY id DESC", con, params=(cutoff,))
def get_all_entries():
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query("SELECT * FROM entries ORDER BY id DESC", con)
def get_open_rituals():
    with sqlite3.connect(DB_PATH) as con:
        return pd.read_sql_query(
            "SELECT r.id,r.entry_id,r.ritual,r.due_date,r.done,e.ts AS entry_time "
            "FROM rituals r JOIN entries e ON e.id=r.entry_id ORDER BY r.due_date ASC, r.id DESC", con)
def set_ritual_done(ritual_id:int, done:bool):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE rituals SET done=? WHERE id=?", (1 if done else 0, ritual_id))
def clear_all():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("DELETE FROM entries;"); con.execute("DELETE FROM rituals;")

init_db()
if "show_results" not in st.session_state: st.session_state.show_results=False

# ---- JOURNAL
if page=="Journal":
    entry=st.text_area("📝 Write about your day:", height=160, placeholder="What went well? What felt heavy? Any small wins?")
    c1,c2,c3=st.columns([1,1,2])
    with c1: run_btn=st.button("Reflect ✨", type="primary")
    with c2: clear_btn=st.button("Clear")
    with c3: st.caption("Tip: short & specific entries respond fastest.")
    if clear_btn: st.session_state.show_results=False; st.rerun()

    st.markdown("""<script>
      document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){
        const b=[...parent.document.querySelectorAll('button')].find(x=>x.innerText.includes('Reflect')); if(b) b.click();}});
    </script>""", unsafe_allow_html=True)

    if run_btn:
        if not entry.strip(): st.warning("Please write something first.")
        else:
            s=an.polarity_scores(entry)
            with st.spinner("🌱 Reflecting locally..."):
                r=ollama.chat(model=LLM_MODEL, messages=[{"role":"system","content":SYSTEM_PROMPT},
                                                         {"role":"user","content":entry}],
                              options={"temperature":.4,"top_p":.9,"num_predict":MAX_GEN_TOKENS})
            try: data=extract_json(r["message"]["content"])
            except Exception as e: st.error(f"Model format error: {e}"); st.stop()
            add_entry(entry,(data.get("summary") or "").strip(),
                     (data.get("affirmation") or "").strip(),
                     (data.get("ritual") or "").strip(), s["compound"])
            st.session_state.show_results=True; st.toast("Saved to history ✅")

    if st.session_state.show_results:
        df=get_recent_entries(30)
        if not df.empty:
            latest=df.iloc[0]
            st.markdown("### 🧾 Insight Cards")
            L,R=st.columns(2)
            with L: st.markdown('<div class="card"><b>Summary</b><br>', unsafe_allow_html=True); st.write(latest["summary"] or "_no summary_"); st.markdown("</div>", unsafe_allow_html=True)
            with R: st.markdown('<div class="card info"><b>Micro-ritual (3–5 min)</b><br>', unsafe_allow_html=True); st.write(latest["ritual"] or "_no ritual_"); st.markdown("</div>", unsafe_allow_html=True)
            st.markdown('<div class="card success"><b>Affirmation</b><br>', unsafe_allow_html=True); st.write(latest["affirmation"] or "_no affirmation_"); st.markdown("</div>", unsafe_allow_html=True)
            st.markdown("### 📈 Mood Meter"); lab=label_sentiment(latest["sentiment"]); st.metric("Sentiment", lab, f"{latest['sentiment']:.2f}"); st.progress(mood_percent(latest["sentiment"])); st.caption(f"Logged at {latest['ts']}")
            rituals=get_open_rituals(); br=burnout_signal(latest["text"], float(latest["sentiment"]), rituals)
            color="red" if "High" in br["level"] else ("orange" if "Moderate" in br["level"] else "green")
            st.markdown(f'<span class="badge {color}">🧯 Burnout: <b>{br["level"]}</b> · {br["risk"]}</span>', unsafe_allow_html=True)
            if br["drivers"]: st.caption("Drivers: " + ", ".join(br["drivers"]))
            st.markdown("## ✅ Ritual Tracker")
            if rituals.empty: st.write("No rituals yet. Reflect to create one for tomorrow.")
            else:
                for _,r in rituals.iterrows():
                    c=st.columns([.76,.12,.12])
                    with c[0]: st.write(f"**{r['ritual']}**  · due **{r['due_date']}**")
                    with c[1]: checked=st.checkbox("Done", value=bool(r["done"]), key=f"rit_{r['id']}")
                    with c[2]:
                        if checked!=bool(r["done"]): set_ritual_done(int(r["id"]), checked); st.rerun()
            st.markdown("## 💚 Well-being Score")
            wb=compute_weekly_wellbeing(get_recent_entries(30), rituals)
            c1,c2,c3=st.columns(3)
            c1.metric("This week", f"{wb['score']}", delta=f"{wb['delta']}"); c2.metric("Avg Sentiment (7d)", f"{wb['sent7']}"); c3.metric("Ritual Adherence (7d)", f"{wb['adh7']}%")
            st.progress(wb['score']/100.0); st.caption(f"Streak: {wb['streak_days']} day(s) · Week start {wb['week_start']}")

# ---- HISTORY
if page=="History":
    st.header("📚 Your History")
    df=get_all_entries()
    if df.empty: st.info("No entries yet. Write your first reflection in the Journal tab."); st.stop()
    df["ts_dt"]=pd.to_datetime(df["ts"])
    c1,c2=st.columns([1,1])
    with c1:
        min_d,max_d=df["ts_dt"].min().date(), df["ts_dt"].max().date()
        dr=st.date_input("Date range", value=(min_d,max_d), min_value=min_d, max_value=max_d)
        start_d,end_d=(dr if isinstance(dr,tuple) else (dr,dr))
    with c2: q=st.text_input("Search (text / summary / ritual / affirmation)","")
    mask=(df["ts_dt"].dt.date>=start_d)&(df["ts_dt"].dt.date<=end_d)
    if q.strip():
        ql=q.lower()
        mask&=(df["text"].str.lower().str.contains(ql,na=False)|df["summary"].str.lower().str.contains(ql,na=False)|
               df["affirmation"].str.lower().str.contains(ql,na=False)|df["ritual"].str.lower().str.contains(ql,na=False))
    view=df.loc[mask].copy().sort_values("id",ascending=False)
    c1,c2=st.columns([1,1])
    with c1:
        csv=view[["id","ts","text","summary","affirmation","ritual","sentiment"]].to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Download CSV", data=csv, file_name="reflectra_history.csv", mime="text/csv", type="secondary")
    with c2:
        if st.button("🗑️ Clear All History"): clear_all(); st.success("All history cleared."); st.rerun()
    st.markdown(f"Showing {len(view)} of {len(df)} entries")
    for _,row in view.iterrows():
        with st.expander(f"#{row['id']} · {row['ts']} · sentiment {row['sentiment']:.2f}"):
            st.markdown("**Entry**");       st.write(row["text"])
            st.markdown("**Summary**");     st.write(row["summary"] or "_no summary_")
            st.markdown("**Affirmation**"); st.success(row["affirmation"] or "_no affirmation_")
            st.markdown("**Ritual**");      st.info(row["ritual"] or "_no ritual_")

