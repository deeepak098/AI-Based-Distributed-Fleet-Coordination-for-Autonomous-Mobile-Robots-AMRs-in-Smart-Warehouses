"""Professor-ready Streamlit showcase for the autonomous warehouse simulation."""

from __future__ import annotations

import os
import sys
import time
from html import escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from warehouse_sim.events import block_cell, flood_urgent_orders, force_drain, inject_deadlock, kill_robot
from warehouse_sim.model import WarehouseModel


st.set_page_config(page_title="NEXUS | Warehouse Digital Twin", page_icon="N", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { --ink:#e8edf6; --muted:#8d99ae; --cyan:#55e6c1; --blue:#6c8cff; --panel:#101827; }
.stApp { background: radial-gradient(circle at 85% -10%,#18294b 0,transparent 35%),#070b12; color:var(--ink); }
[data-testid="stHeader"] { background:transparent; }
[data-testid="stSidebar"] { background:#090f19; border-right:1px solid #1c2a3c; }
h1,h2,h3 { font-family:'Space Grotesk',sans-serif !important; letter-spacing:-.03em; }
p,div,label,button { font-family:'DM Sans',sans-serif; }
.block-container { max-width:1500px; padding-top:2rem; }
.eyebrow { color:var(--cyan); font-size:.76rem; font-weight:700; letter-spacing:.18em; text-transform:uppercase; }
.hero { padding:3.2rem 3.4rem; border:1px solid #203149; border-radius:24px;
 background:linear-gradient(125deg,rgba(20,33,54,.96),rgba(9,15,25,.9)); position:relative; overflow:hidden; }
.hero:after { content:''; position:absolute; width:320px;height:320px;right:-90px;top:-150px;
 border:55px solid rgba(85,230,193,.06);border-radius:50%; }
.hero h1 { font-size:clamp(2.5rem,5vw,5rem); line-height:.98; margin:.7rem 0 1.1rem; max-width:900px; }
.hero p { color:#aab5c8; max-width:720px; font-size:1.08rem; line-height:1.7; }
.pill { display:inline-block;padding:.38rem .75rem;border:1px solid #2d405d;border-radius:999px;color:#b7c4d8;font-size:.78rem;margin:.25rem .25rem .25rem 0; }
.card { background:linear-gradient(145deg,rgba(18,28,44,.98),rgba(11,17,28,.98));border:1px solid #1d2b40;
 border-radius:18px;padding:1.4rem;height:100%;box-shadow:0 15px 45px rgba(0,0,0,.18); }
.card h3 { margin:.25rem 0 .65rem;font-size:1.08rem; }.card p {color:#91a0b7;line-height:1.55;font-size:.9rem;}
.number { color:var(--cyan);font-family:'Space Grotesk';font-size:2rem;font-weight:700; }
.status {display:inline-flex;align-items:center;gap:.5rem;color:#9eabc0;font-size:.86rem}
.dot {width:8px;height:8px;border-radius:50%;background:#ff6577;box-shadow:0 0 12px currentColor}.dot.live{background:#55e6c1}
.flow { display:grid;grid-template-columns:repeat(5,1fr);gap:.8rem;align-items:stretch;margin:1.2rem 0; }
.flow-step {border:1px solid #23334b;border-radius:14px;padding:1.1rem;background:#0d1522;position:relative;}
.flow-step b{color:#e8edf6}.flow-step small{display:block;color:#7f8ca1;margin-top:.45rem;line-height:1.4}
.log {font-family:ui-monospace,monospace;font-size:.75rem;border-bottom:1px solid #1b2738;padding:.55rem 0;color:#9cabc0}
.log b{color:#55e6c1}.footer-note{color:#6f7c90;font-size:.8rem;text-align:center;padding:2rem 0}
div[data-testid="stMetric"] {background:#0e1725;border:1px solid #1d2c41;padding:1rem 1.1rem;border-radius:16px;}
div[data-testid="stMetricValue"] {color:#eef3fb;font-family:'Space Grotesk';}
.stButton>button {border-radius:11px;border:1px solid #29405d;background:#111c2c;color:#dce5f4;transition:.2s;}
.stButton>button:hover {border-color:#55e6c1;color:#55e6c1;transform:translateY(-1px)}
div[role="radiogroup"] {gap:.25rem} div[role="radiogroup"] label {background:#0e1724;border:1px solid #1c2a3e;padding:.5rem .75rem;border-radius:10px;}
@keyframes reveal {from{opacity:0;transform:translateY(20px);filter:blur(4px)}to{opacity:1;transform:none;filter:none}}
.main .block-container > div > div > div {animation:reveal .9s cubic-bezier(.2,.8,.2,1) both}
.main .block-container > div > div > div:nth-child(2){animation-delay:.12s}.main .block-container > div > div > div:nth-child(3){animation-delay:.24s}
@media(max-width:900px){.hero{padding:2rem}.flow{grid-template-columns:1fr}.hero h1{font-size:2.6rem}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
""",
    unsafe_allow_html=True,
)


def fresh_state() -> None:
    st.session_state.model = WarehouseModel(seed=42)
    st.session_state.running = False
    st.session_state.shocks = []
    st.session_state.history = {k: [] for k in ("tick", "completed", "battery", "pending")}


if "model" not in st.session_state:
    fresh_state()

model: WarehouseModel = st.session_state.model


def record() -> None:
    k = model.get_kpis()
    h = st.session_state.history
    h["tick"].append(k["tick"]); h["completed"].append(k["orders_completed"])
    h["battery"].append(k["avg_battery"]); h["pending"].append(k["pending_tasks"])
    if len(h["tick"]) > 300:
        for values in h.values(): del values[:-300]


def step(count: int = 1) -> None:
    for _ in range(count):
        model.step(); record()


def title(label: str, heading: str, copy: str) -> None:
    st.markdown(f'<div class="eyebrow">{label}</div>', unsafe_allow_html=True)
    st.header(heading)
    st.markdown(f'<p style="color:#91a0b7;max-width:850px;line-height:1.65">{copy}</p>', unsafe_allow_html=True)


def run_shock(result: dict) -> None:
    st.session_state.shocks.append(result)
    if "error" in result: st.error(result["error"])
    else: st.toast("Scenario injected and recovery response logged", icon="✅")


with st.sidebar:
    st.markdown('<div class="eyebrow">NEXUS / DT-01</div>', unsafe_allow_html=True)
    st.title("Control room")
    st.caption("Autonomous warehouse digital twin")
    st.markdown("---")
    page = st.radio("Presentation", ["Overview", "Live Twin", "Architecture", "Resilience Lab", "Evidence"], label_visibility="collapsed")
    st.markdown("---")
    c1, c2 = st.columns(2)
    if c1.button("▶ Run", width="stretch"): st.session_state.running = True
    if c2.button("⏸ Pause", width="stretch"): st.session_state.running = False
    speed = st.slider("Simulation pace", 1, 5, 1, help="Ticks processed per visual refresh")
    if st.button("Step one tick", width="stretch"): step()
    if st.button("Reset demo", width="stretch"): fresh_state(); st.rerun()
    st.markdown("---")
    state = "RUNNING" if st.session_state.running else "PAUSED"
    st.markdown(f'<span class="status"><i class="dot {"live" if st.session_state.running else ""}"></i>{state} · TICK {model.current_tick}</span>', unsafe_allow_html=True)


if page == "Overview":
    st.markdown("""<section class="hero"><div class="eyebrow">Multi-agent systems · Digital twin · Operations AI</div>
    <h1>A warehouse that thinks before it moves.</h1>
    <p>NEXUS is a live digital twin where specialized agents collaborate to accept orders, reserve stock, assign robots, avoid collisions, manage batteries, and recover from disruption—without a central script controlling every move.</p>
    <span class="pill">20 × 20 live grid</span><span class="pill">5 autonomous robots</span><span class="pill">7 agent roles</span><span class="pill">5 resilience scenarios</span></section>""", unsafe_allow_html=True)
    st.write("")
    title("The thesis", "One operational loop, multiple intelligent decisions", "Every tick follows a transparent sense–decide–act cycle. This makes the system observable enough for a digital twin and adaptive enough for real warehouse uncertainty.")
    st.markdown("""<div class="flow">
      <div class="flow-step"><b>01 · Demand</b><small>Customer Agent creates normal and urgent orders.</small></div>
      <div class="flow-step"><b>02 · Inventory</b><small>Inventory Agent validates and reserves a shelf.</small></div>
      <div class="flow-step"><b>03 · Allocate</b><small>Fleet Manager scores distance, battery and workload.</small></div>
      <div class="flow-step"><b>04 · Navigate</b><small>A* and CBS produce safe, conflict-free routes.</small></div>
      <div class="flow-step"><b>05 · Fulfil</b><small>Robot picks, packs and reports completion.</small></div>
    </div>""", unsafe_allow_html=True)
    cols = st.columns(3)
    cards = [("01", "Adaptive allocation", "Tasks go to the best available robot—not simply the first one."), ("02", "Conflict-free motion", "Reservations and Conflict-Based Search prevent vertex and edge collisions."), ("03", "Designed to recover", "Robot failure, blocked aisles, battery drain, order floods and deadlocks are handled live.")]
    for col, (n, h, p) in zip(cols, cards): col.markdown(f'<div class="card"><div class="number">{n}</div><h3>{h}</h3><p>{p}</p></div>', unsafe_allow_html=True)

elif page == "Live Twin":
    title("Live operations", "The warehouse, one tick at a time", "Run, pause or step the system from the control room. Every marker, metric and message below comes directly from the simulation model.")
    k = model.get_kpis(); metrics = st.columns(6)
    values = [("Tick", k["tick"]),("Completed",k["orders_completed"]),("Pending",k["pending_tasks"]),("Active robots",k["active_robots"]),("Avg battery",f'{k["avg_battery"]:.0f}%'),("Collisions",k["collision_count"])]
    for col,(label,value) in zip(metrics,values): col.metric(label,value)
    left,right = st.columns([1.35,1])
    with left:
        st.subheader("Spatial digital twin")
        gs=model.get_grid_state(); matrix=np.zeros((model.grid_height,model.grid_width))
        for x,y in gs["shelf_locations"]: matrix[y,x]=1
        x,y=gs["packing_station"]; matrix[y,x]=2
        for x,y in gs["charging_docks"]: matrix[y,x]=3
        for cell in gs["blocked_cells"]: x,y=cell; matrix[y,x]=4
        fig=go.Figure(go.Heatmap(z=matrix,zmin=0,zmax=4,showscale=False,colorscale=[[0,"#0b1320"],[.249,"#0b1320"],[.25,"#34445b"],[.499,"#34445b"],[.5,"#6c8cff"],[.749,"#6c8cff"],[.75,"#55e6c1"],[.999,"#55e6c1"],[1,"#ff6577"]],hoverinfo="skip"))
        colors={"IDLE":"#55e6c1","FAILED":"#ff6577","CHARGING":"#ffd166","NEEDS_CHARGE":"#ff9f43"}
        for rid,r in gs["robots"].items():
            x,y=r["pos"]; fig.add_trace(go.Scatter(x=[x],y=[y],mode="markers+text",text=[f"R{rid}"],textposition="top center",marker={"size":17,"color":colors.get(r["status"],"#b79cff"),"line":{"width":2,"color":"white"}},name=f'R{rid} · {r["status"]}',hovertemplate=f'Robot {rid}<br>{r["status"]}<br>Battery {r["battery"]:.0f}%<extra></extra>'))
        fig.update_layout(height=570,margin=dict(l=10,r=10,t=10,b=10),paper_bgcolor="#070b12",plot_bgcolor="#070b12",font_color="#93a1b7",legend=dict(orientation="h",y=-.12),xaxis=dict(dtick=1,gridcolor="#162235"),yaxis=dict(dtick=1,gridcolor="#162235",scaleanchor="x"))
        st.plotly_chart(fig,width="stretch")
        st.caption("■ Shelf   ■ Packing station   ■ Charging dock   ■ Blocked aisle   ● Robot")
    with right:
        st.subheader("Operational trend")
        h=st.session_state.history
        trend=go.Figure()
        trend.add_trace(go.Scatter(x=h["tick"],y=h["completed"],name="Completed",line=dict(color="#55e6c1",width=3)))
        trend.add_trace(go.Scatter(x=h["tick"],y=h["pending"],name="Pending",line=dict(color="#6c8cff",width=2)))
        trend.update_layout(height=270,margin=dict(l=10,r=10,t=10,b=25),paper_bgcolor="#070b12",plot_bgcolor="#0d1522",font_color="#93a1b7",legend=dict(orientation="h"),xaxis_title="Tick")
        st.plotly_chart(trend,width="stretch")
        st.subheader("Agent communication")
        messages=model.get_recent_messages(9)
        if not messages: st.info("Start the simulation to observe agent messages.")
        for msg in reversed(messages):
            action=escape(str(msg.get("payload",{}).get("action",msg.get("payload",{}).get("shock_type","event"))))
            st.markdown(f'<div class="log"><b>T{msg.get("tick","—")}</b> · {escape(str(msg.get("from_agent","?")))} → {escape(str(msg.get("to_agent","?")))}<br>{action}</div>',unsafe_allow_html=True)

elif page == "Architecture":
    title("System design", "Seven agents, clear responsibilities", "The model separates business decisions from physical motion. Agents communicate through explicit messages, while the WarehouseModel remains the single source of truth.")
    agents=[("Customer", "Generates demand and receives fulfilment updates."),("Order", "Prioritizes orders and manages the task lifecycle."),("Inventory", "Checks stock, reserves SKUs and selects shelves."),("Fleet Manager", "Allocates work using distance, battery and workload."),("Robot × 5", "Executes routes, picks goods and reports telemetry."),("Traffic Controller", "Reserves cells, reroutes paths and resolves deadlocks."),("Charging", "Queues low-battery robots and assigns charging docks.")]
    cols=st.columns(3)
    for i,(name,desc) in enumerate(agents): cols[i%3].markdown(f'<div class="card" style="margin-bottom:1rem"><div class="eyebrow">Agent {i+1:02}</div><h3>{name}</h3><p>{desc}</p></div>',unsafe_allow_html=True)
    st.subheader("Decision stack")
    st.markdown("""<div class="flow"><div class="flow-step"><b>Sense</b><small>Read orders, positions, battery and reservations.</small></div><div class="flow-step"><b>Decide</b><small>Prioritize, score, reserve and plan.</small></div><div class="flow-step"><b>Act</b><small>Move, pick, drop, charge and report.</small></div><div class="flow-step"><b>Observe</b><small>Collect KPIs and structured messages.</small></div><div class="flow-step"><b>Adapt</b><small>Replan when state or environment changes.</small></div></div>""",unsafe_allow_html=True)
    with st.expander("Algorithms used",expanded=True):
        st.markdown("**A-star** finds efficient single-robot paths. **Conflict-Based Search (CBS)** resolves multi-robot vertex and edge conflicts. **Weighted task scoring** balances travel distance, battery level, workload, and urgency. A **wait-for graph** detects cyclic deadlocks and selects a lower-priority robot to yield.")

elif page == "Resilience Lab":
    title("Interactive demonstration", "Break the warehouse. Watch it recover.", "Each scenario mutates the live model and routes the response to the responsible agent. For a clean presentation: run 10–20 ticks, pause, inject one scenario, then continue.")
    alive=[rid for rid,r in model.robots.items() if r.status!="FAILED"]
    c1,c2,c3=st.columns(3)
    with c1:
        st.markdown('<div class="card"><div class="eyebrow">Scenario 01</div><h3>Robot failure</h3><p>Disables a robot and asks the Fleet Manager to reassign unfinished work.</p></div>',unsafe_allow_html=True)
        rid=st.selectbox("Robot to disable",alive,key="kill") if alive else None
        if st.button("Inject robot failure",width="stretch",disabled=rid is None): run_shock(kill_robot(model,rid))
    with c2:
        st.markdown('<div class="card"><div class="eyebrow">Scenario 02</div><h3>Blocked aisle</h3><p>Adds an obstacle and forces every affected route to be recalculated.</p></div>',unsafe_allow_html=True)
        xy=st.columns(2); bx=xy[0].number_input("Grid X",0,19,5); by=xy[1].number_input("Grid Y",0,19,6)
        if st.button("Block selected cell",width="stretch"): run_shock(block_cell(model,(int(bx),int(by))))
    with c3:
        st.markdown('<div class="card"><div class="eyebrow">Scenario 03</div><h3>Battery drain</h3><p>Reduces battery to 5% so the Charging Agent redirects the robot.</p></div>',unsafe_allow_html=True)
        drain=st.selectbox("Robot to drain",alive,key="drain") if alive else None
        if st.button("Drain robot battery",width="stretch",disabled=drain is None): run_shock(force_drain(model,drain))
    st.write(""); c4,c5=st.columns(2)
    with c4:
        st.markdown('<div class="card"><div class="eyebrow">Scenario 04</div><h3>Urgent order surge</h3><p>Stress-tests allocation and traffic under a sudden workload spike.</p></div>',unsafe_allow_html=True)
        amount=st.slider("Urgent orders",5,30,10)
        if st.button("Flood urgent orders",width="stretch"): run_shock(flood_urgent_orders(model,amount))
    with c5:
        st.markdown('<div class="card"><div class="eyebrow">Scenario 05</div><h3>Deadlock injection</h3><p>Creates a head-on conflict and invokes wait-for detection plus rollback.</p></div>',unsafe_allow_html=True)
        if st.button("Inject controlled deadlock",width="stretch"): run_shock(inject_deadlock(model))
    if st.session_state.shocks:
        st.subheader("Recovery history")
        st.dataframe(list(reversed(st.session_state.shocks)),width="stretch",hide_index=True)

else:
    title("Verification", "Evidence, not just animation", "The showcase is backed by focused algorithm tests and full simulation stress tests. Use the commands below to reproduce the results on any machine.")
    k=model.get_kpis(); cols=st.columns(4)
    for col,(label,value) in zip(cols,[("Simulation ticks",k["tick"]),("Collision count",k["collision_count"]),("Deadlocks resolved",k["deadlocks_resolved"]),("Shocks recovered",k["shocks_recovered"])]): col.metric(label,value)
    left,right=st.columns(2)
    left.markdown('<div class="card"><div class="eyebrow">Automated validation</div><h3>What is tested</h3><p>A* path quality and constraints<br>CBS conflict detection and resolution<br>Task allocation scoring<br>Deadlock detection and recovery<br>100/200-tick stability runs<br>Rapid and compound shock scenarios</p></div>',unsafe_allow_html=True)
    right.markdown('<div class="card"><div class="eyebrow">Reproduce locally</div><h3>Two commands</h3><p><code>python -m pytest warehouse_sim/tests -q</code><br><br><code>streamlit run warehouse_sim/dashboard.py</code></p></div>',unsafe_allow_html=True)
    st.subheader("Professor demo script")
    st.markdown("1. Start on **Overview** and explain the order-to-fulfilment loop.\n2. Open **Architecture** and identify agent responsibilities.\n3. In **Live Twin**, run 15 ticks and point out messages and KPIs.\n4. Pause, open **Resilience Lab**, inject a blocked aisle or robot failure.\n5. Resume and return to **Live Twin** to show replanning.\n6. Finish on **Evidence** with the collision count and automated tests.")

st.markdown('<div class="footer-note">NEXUS · Autonomous Warehouse Digital Twin · Built for explainability, resilience and live demonstration</div>',unsafe_allow_html=True)

if st.session_state.running:
    step(speed); time.sleep(0.65); st.rerun()
