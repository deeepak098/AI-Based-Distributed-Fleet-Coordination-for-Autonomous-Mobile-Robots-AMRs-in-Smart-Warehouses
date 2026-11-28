
from __future__ import annotations

import os
import sys
import time
from html import escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import plotly.graph_objects as go
import streamlit as st


from warehouse_sim.events import (
    block_cell, flood_urgent_orders, force_drain, inject_deadlock, kill_robot,
)
from warehouse_sim.model import WarehouseModel



st.set_page_config(
    page_title="NEXUS | Warehouse Digital Twin",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown("""\n<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { --bg:#080d15; --panel:#101a28; --border:#223149; --muted:#9aa9bd; --cyan:#5be7c4; }
.stApp { background:radial-gradient(circle at 85% -10%,#172a49 0,transparent 36%),var(--bg); }
[data-testid="stSidebar"] { background:#0a111b; border-right:1px solid var(--border); }
.block-container { max-width:1550px; padding-top:1.4rem; padding-bottom:2rem; }
h1,h2,h3 { font-family:'Space Grotesk',sans-serif !important; letter-spacing:-.025em; }
body,p,div,label,button { font-family:'DM Sans',sans-serif; }
.eyebrow { color:var(--cyan); text-transform:uppercase; letter-spacing:.16em; font-size:.74rem; font-weight:700; }
.hero { background:linear-gradient(120deg,#14253d,#0d1624 70%); border:1px solid #263b56; border-radius:22px; padding:2.3rem 2.5rem; }
.hero h1 { font-size:clamp(2rem,4.5vw,4.3rem); line-height:1.02; margin:.5rem 0 1rem; }
.hero p { color:#b0bed1; max-width:850px; line-height:1.7; font-size:1.02rem; }
.panel { background:#0e1724; border:1px solid #213149; border-radius:16px; padding:1.15rem 1.3rem; height:100%; }
.panel p { color:#a0aec2; line-height:1.55; }
.pill { display:inline-block; padding:.35rem .65rem; margin:.2rem .2rem .2rem 0; border:1px solid #2c405a; border-radius:999px; color:#b7c5d9; font-size:.78rem; }
.flow { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:.65rem; margin:.8rem 0 1rem; }
.flow-item { border:1px solid #263750; background:#0e1724; border-radius:13px; padding:.95rem; }
.flow-item strong { display:block; color:#e9f0fa; }
.flow-item span { color:#9aa9bd; font-size:.82rem; line-height:1.45; display:block; margin-top:.35rem; }
.logline { border-bottom:1px solid #1c2a3b; padding:.55rem 0; color:#a5b4c8; font-family:ui-monospace,monospace; font-size:.78rem; }
.logline b { color:var(--cyan); }
div[data-testid="stMetric"] { background:#101a28; border:1px solid #24344a; padding:.8rem 1rem; border-radius:14px; }
div[data-testid="stMetricValue"] { color:#eef4fc; }
.stButton button { border-radius:10px; border:1px solid #2a405c; }
@media(max-width:900px){ .flow { grid-template-columns:1fr; } .hero { padding:1.5rem; } }
</style>
""", unsafe_allow_html=True)


def reset_state() -> None:
    st.session_state.model = WarehouseModel(seed=42)
    st.session_state.running = False
    st.session_state.shocks = []
    st.session_state.history = {key: [] for key in ("tick", "completed", "battery", "pending")}


if "model" not in st.session_state:
    reset_state()
model: WarehouseModel = st.session_state.model


def record_metrics() -> None:
    k = model.get_kpis()
    h = st.session_state.history
    h["tick"].append(k["tick"])
    h["completed"].append(k["orders_completed"])
    h["battery"].append(k["avg_battery"])
    h["pending"].append(k["pending_tasks"])
    if len(h["tick"]) > 300:
        for series in h.values():
            del series[:-300]


def advance(ticks: int = 1) -> None:
    for _ in range(ticks):
        model.step()
        record_metrics()


def heading(eyebrow: str, title: str, description: str) -> None:
    st.markdown(f'<div class="eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<p style="color:#9aa9bd;max-width:900px;line-height:1.65">{description}</p>', unsafe_allow_html=True)


def scenario_result(result: dict) -> None:
    st.session_state.shocks.append(result)
    if "error" in result:
        st.error(result["error"])
    else:
        st.success("Scenario injected. Recovery status will be monitored as the simulation continues.")


def render_map() -> go.Figure:
    grid_state = model.get_grid_state()
    grid = np.zeros((model.grid_height, model.grid_width))
    for x, y in grid_state["shelf_locations"]:
        grid[y, x] = 1
    x, y = grid_state["packing_station"]
    grid[y, x] = 2
    for x, y in grid_state["charging_docks"]:
        grid[y, x] = 3
    for x, y in grid_state["blocked_cells"]:
        grid[y, x] = 4

    fig = go.Figure(go.Heatmap(
        z=grid, zmin=0, zmax=4, showscale=False, hoverinfo="skip",
        colorscale=[[0,"#0b1320"],[.249,"#0b1320"],[.25,"#34445b"],[.499,"#34445b"],
                   [.5,"#6c8cff"],[.749,"#6c8cff"],[.75,"#55e6c1"],[.999,"#55e6c1"],[1,"#ff6577"]]
    ))
    status_colors = {"IDLE":"#55e6c1", "FAILED":"#ff6577", "CHARGING":"#ffd166", "NEEDS_CHARGE":"#ff9f43"}
    for robot_id, robot in grid_state["robots"].items():
        x, y = robot["pos"]
        fig.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text", text=[f"R{robot_id}"], textposition="top center",
            marker={"size":17,"color":status_colors.get(robot["status"],"#b79cff"),"line":{"width":2,"color":"white"}},
            name=f'Robot {robot_id} · {robot["status"]}',
            hovertemplate=f'Robot {robot_id}<br>Status: {robot["status"]}<br>Battery: {robot["battery"]:.0f}%<extra></extra>',
        ))
    fig.update_layout(
        height=610, margin=dict(l=10,r=10,t=10,b=10), paper_bgcolor="#080d15", plot_bgcolor="#080d15",
        font_color="#9aa9bd", legend=dict(orientation="h",y=-.12),
        xaxis=dict(dtick=1,gridcolor="#18263a",title="X coordinate"),
        yaxis=dict(dtick=1,gridcolor="#18263a",title="Y coordinate",scaleanchor="x"),
    )
    return fig



# ── Sidebar: global controls ────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="eyebrow">NEXUS · DT-01</div>', unsafe_allow_html=True)
    st.title("Demo controls")
    st.caption("Use this panel to control the simulation from any section.")
    page = st.radio("Go to section", ["Demo Guide", "Live Warehouse", "System Architecture", "Resilience Lab", "Evidence"], label_visibility="collapsed")
    st.divider()
    run_col, pause_col = st.columns(2)
    if run_col.button("▶ Run", use_container_width=True):
        st.session_state.running = True
    if pause_col.button("⏸ Pause", use_container_width=True):
        st.session_state.running = False
    pace = st.slider("Ticks per refresh", min_value=1, max_value=5, value=1, help="Higher values make the simulation progress faster between screen refreshes.")
    if st.button("⏭ Step one tick", use_container_width=True):
        advance(1)
    if st.button("↻ Reset simulation", use_container_width=True):
        reset_state()
        st.rerun()
    st.divider()
    state = "RUNNING" if st.session_state.running else "PAUSED"
    dot = "🟢" if st.session_state.running else "🔴"
    st.markdown(f"**{dot} {state}**  ·  Tick `{model.current_tick}`")
    st.caption("Reset returns the model to seed 42 and clears session history.")


# ── Page: Demo guide ────────────────────────────────────────────────
if page == "Demo Guide":
    st.markdown("""<section class="hero"><div class="eyebrow">Viva-ready · Multi-agent simulation</div>
    <h1>A warehouse that coordinates before it moves.</h1>
    <p>NEXUS is a software simulation of a smart warehouse. Orders become tasks, a Fleet Manager allocates work, robots navigate and execute tasks, and specialized agents respond to changing conditions. Use the guided sequence below to present the project clearly.</p>
    <span class="pill">20 × 20 grid</span><span class="pill">5 robots</span><span class="pill">7 agent roles</span><span class="pill">5 disruption scenarios</span></section>""", unsafe_allow_html=True)
    st.subheader("The warehouse workflow")
    st.markdown("""<div class="flow">
    <div class="flow-item"><strong>01 · Orders</strong><span>Customer Agent generates demand.</span></div>
    <div class="flow-item"><strong>02 · Inventory</strong><span>Stock is checked and a shelf is selected.</span></div>
    <div class="flow-item"><strong>03 · Allocation</strong><span>Fleet Manager chooses a robot for each task.</span></div>
    <div class="flow-item"><strong>04 · Navigation</strong><span>Pathfinding and traffic logic guide movement.</span></div>
    <div class="flow-item"><strong>05 · Fulfillment</strong><span>Robots execute tasks and report status.</span></div>
    </div>""", unsafe_allow_html=True)
    st.subheader("Suggested live demo sequence")
    steps = [
        ("1", "Introduce the project", "Use this page to explain the problem and the order-to-fulfillment flow."),
        ("2", "Show the agents", "Open System Architecture and briefly describe each agent's responsibility."),
        ("3", "Run the warehouse", "Open Live Warehouse, click Run, and point out robot movement, KPIs and communication logs."),
        ("4", "Create a disruption", "Pause, open Resilience Lab, and inject a blocked aisle or robot failure."),
        ("5", "Observe the response", "Resume and watch the model. Then check the recorded scenario status."),
        (("6"), "Show evidence", "Finish with KPIs and automated tests; explain that the metrics are measured, not decorative."),
    ]
    cols = st.columns(3)
    for i, (num, title_text, description) in enumerate(steps):
        with cols[i % 3]:
            st.markdown(f'<div class="panel"><div class="eyebrow">Step {num}</div><h3>{title_text}</h3><p>{description}</p></div>', unsafe_allow_html=True)
    st.info("Viva tip: Keep the simulation pace at 1 tick per refresh. Demonstrate one disruption well rather than clicking every scenario.")


# ── Page: Live warehouse ────────────────────────────────────────────
elif page == "Live Warehouse":
    heading("Live operation", "Watch the warehouse run", "The map and KPIs below are read from the running model. Start, pause, or advance one tick using the sidebar controls.")
    k = model.get_kpis()
    metric_cols = st.columns(6)
    for col, (label, value) in zip(metric_cols, [
        ("Tick", k["tick"]), ("Completed", k["orders_completed"]), ("Pending", k["pending_tasks"]),
        ("Active robots", k["active_robots"]), ("Average battery", f'{k["avg_battery"]:.0f}%'), ("Collisions", k["collision_count"]),
    ]):
        col.metric(label, value)
    map_col, right_col = st.columns([1.35, 1])
    with map_col:
        st.subheader("Warehouse map")
        st.plotly_chart(render_map(), use_container_width=True)
        st.caption("Shelf · Packing station · Charging dock · Blocked cell · Robot. Hover over robot markers for state and battery.")
    with right_col:
        st.subheader("Workload over time")
        hist = st.session_state.history
        trend = go.Figure()
        trend.add_trace(go.Scatter(x=hist["tick"], y=hist["completed"], name="Completed tasks", line={"width":3}))
        trend.add_trace(go.Scatter(x=hist["tick"], y=hist["pending"], name="Pending tasks", line={"width":2}))
        trend.update_layout(height=300, margin=dict(l=10,r=10,t=10,b=25), paper_bgcolor="#080d15", plot_bgcolor="#0e1724", font_color="#9aa9bd", legend=dict(orientation="h"), xaxis_title="Simulation tick")
        st.plotly_chart(trend, use_container_width=True)
        st.subheader("Recent agent messages")
        messages = model.get_recent_messages(9)
        if not messages:
            st.info("No messages yet. Run the simulation to populate this panel.")
        for message in reversed(messages):
            payload = message.get("payload", {})
            action = escape(str(payload.get("action", payload.get("shock_type", "message"))))
            sender = escape(str(message.get("from_agent", "?")))
            receiver = escape(str(message.get("to_agent", "?")))
            st.markdown(f'<div class="logline"><b>Tick {message.get("tick", "—")}</b> · {sender} → {receiver}<br>{action}</div>', unsafe_allow_html=True)


# ── Page: Architecture ───────────────────────────────────────────────
elif page == "System Architecture":
    heading("System design", "Who does what?", "Each agent has a specialized responsibility. The WarehouseModel coordinates the simulation lifecycle and holds the shared warehouse state.")
    agents = [
        ("Customer Agent", "Creates incoming customer demand/orders."),
        ("Order Agent", "Prioritizes orders and manages the task lifecycle."),
        ("Inventory Agent", "Checks inventory, reserves stock and selects shelves."),
        ("Fleet Manager", "Allocates tasks to robots using the selected allocation strategy."),
        ("Robot Agents × 5", "Execute assigned work, navigate, track battery and report status."),
        ("Traffic Controller", "Coordinates routes, reservations, rerouting and deadlock handling."),
        ("Charging Agent", "Handles charging requests, queues and dock coordination."),
    ]
    cols = st.columns(3)
    for index, (agent_name, responsibility) in enumerate(agents):
        with cols[index % 3]:
            st.markdown(f'<div class="panel" style="margin-bottom:.8rem"><div class="eyebrow">Component {index+1:02}</div><h3>{agent_name}</h3><p>{responsibility}</p></div>', unsafe_allow_html=True)
    st.subheader("Simulation cycle")
    st.markdown("""<div class="flow"><div class="flow-item"><strong>Sense</strong><span>Agents read state and due messages.</span></div><div class="flow-item"><strong>Decide</strong><span>Agents choose their next action.</span></div><div class="flow-item"><strong>Act</strong><span>Movement, assignments and events execute.</span></div><div class="flow-item"><strong>Monitor</strong><span>Recovery checks and KPIs are updated.</span></div><div class="flow-item"><strong>Repeat</strong><span>The model advances to the next tick.</span></div></div>""", unsafe_allow_html=True)
    with st.expander("Algorithm concepts (quick explanation)", expanded=False):
        st.markdown("- **A*:** searches for a route through the grid.\n- **CBS:** coordinates multiple routes to resolve conflicts.\n- **Task scoring:** compares robot suitability factors for allocation.\n- **Wait-for graph:** identifies circular waiting relationships associated with deadlocks.")
    st.warning("Auction allocation in this project is not fully decentralized: robots submit bids, while the Fleet Manager collects and selects the winner.")


# ── Page: Resilience Lab ────────────────────────────────────────────
elif page == "Resilience Lab":
    heading("Controlled disruption testing", "Introduce a problem. Observe the response.", "Inject one scenario at a time. For a clean demo, run the model for a few ticks, pause, inject the event, then resume and inspect the recovery record.")
    st.caption("These controls modify the live model. Reset simulation from the sidebar if you want to start over.")
    alive = [robot_id for robot_id, robot in model.robots.items() if robot.status != "FAILED"]
    tabs = st.tabs(["Robot failure", "Blocked aisle", "Battery drain", "Urgent orders", "Deadlock"])
    with tabs[0]:
        st.markdown("### Robot failure")
        st.write("Disable one robot. Its current task, if any, is handled by the failure/reassignment logic.")
        robot_id = st.selectbox("Robot to disable", alive, key="failure_robot") if alive else None
        if st.button("Inject robot failure", key="inject_failure", disabled=robot_id is None, type="primary"):
            scenario_result(kill_robot(model, robot_id))
    with tabs[1]:
        st.markdown("### Blocked aisle")
        st.write("Mark a valid grid cell as unavailable. The Traffic Controller can respond to affected routes.")
        bx_col, by_col = st.columns(2)
        bx = bx_col.number_input("Grid X", min_value=0, max_value=19, value=5, key="block_x")
        by = by_col.number_input("Grid Y", min_value=0, max_value=19, value=6, key="block_y")
        if st.button("Block selected cell", key="inject_block", type="primary"):
            scenario_result(block_cell(model, (int(bx), int(by))))
    with tabs[2]:
        st.markdown("### Battery drain")
        st.write("Force a robot's battery down to a critical level and trigger charging behavior.")
        robot_id = st.selectbox("Robot to drain", alive, key="battery_robot") if alive else None
        if st.button("Drain selected robot", key="inject_drain", disabled=robot_id is None, type="primary"):
            scenario_result(force_drain(model, robot_id))
    with tabs[3]:
        st.markdown("### Urgent order surge")
        st.write("Inject a batch of urgent orders to create a workload spike and observe the pending-task backlog.")
        amount = st.slider("Urgent orders to add", min_value=5, max_value=30, value=10, step=5)
        if st.button("Inject urgent order surge", key="inject_orders", type="primary"):
            scenario_result(flood_urgent_orders(model, amount))
    with tabs[4]:
        st.markdown("### Controlled deadlock")
        st.write("Create a controlled two-robot route conflict and invoke the Traffic Controller's deadlock logic.")
        if st.button("Inject controlled deadlock", key="inject_deadlock", type="primary"):
            scenario_result(inject_deadlock(model))
    if st.session_state.shocks:
        st.subheader("Scenario log / recovery history")
        st.dataframe(list(reversed(st.session_state.shocks)), use_container_width=True, hide_index=True)


# ── Page: Evidence ─────────────────────────────────────────────────
elif page == "Evidence":
    heading("Evaluation", "Evidence from the simulation", "Use the current run's metrics to discuss system behavior. These are live session values, not pre-filled demonstration results.")
    k = model.get_kpis()
    cols = st.columns(4)
    for col, (label, value) in zip(cols, [
        ("Ticks", k["tick"]), ("Collisions", k["collision_count"]),
        ("Deadlocks resolved", k["deadlocks_resolved"]), ("Shock recoveries", k["shocks_recovered"]),
    ]):
        col.metric(label, value)
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="panel"><div class="eyebrow">Automated tests</div><h3>What we validate</h3><p>Pathfinding correctness · CBS conflict handling · task allocation scoring · deadlock detection/recovery · longer stability runs · disruption scenarios.</p></div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel"><div class="eyebrow">Run locally</div><h3>Project commands</h3><p><code>python -m pytest warehouse_sim/tests -q</code><br/><br/><code>streamlit run warehouse_sim/dashboard.py</code></p></div>', unsafe_allow_html=True)
    st.subheader("Before the viva")
    st.markdown("- Reset to a fresh seed-42 simulation.\n- Keep simulation pace at 1.\n- Start on Demo Guide.\n- Demonstrate one disruption cleanly.\n- Avoid claiming guaranteed recovery; show the recorded status.")


st.markdown("<div style='text-align:center;color:#75849b;padding:1.5rem 0'>NEXUS · Warehouse Digital Twin · Viva Demonstration Interface</div>", unsafe_allow_html=True)


if st.session_state.running:
    advance(pace)
    time.sleep(0.6)
    st.rerun()
