# dashboard.py
# MULTIMODAL_004 Factory AI – Live Operations Center
# pip install streamlit plotly pandas requests websocket-client

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import time
from datetime import datetime
from pathlib import Path

st.set_page_config(
    page_title="MULTIMODAL_004 Factory AI",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Config ---
TELEMETRY_URL = "http://localhost:8001/api/telemetry/poll"
WS_VIDEO_URL = "ws://localhost:8001/api/video/ws"
HTTP_VIDEO_URL = "http://localhost:8001/api/video/stream"
KPI_PATHS = ["factory_kpis.csv", "./factory_kpis.csv", "factory_kpis.xlsx", "./factory_kpis.xlsx"]

# --- WebSocket video reader ---
@st.cache_resource
def get_ws_video_reader():
    import websocket
    import threading
    state = {"frame": None, "connected": False, "last_ts": 0}
    def on_message(ws, message):
        state["frame"] = message
        state["last_ts"] = time.time()
        state["connected"] = True
    def on_error(ws, err): state["connected"] = False
    def on_close(ws, a, b): state["connected"] = False
    def on_open(ws): state["connected"] = True
    def run():
        while True:
            try:
                ws = websocket.WebSocketApp(WS_VIDEO_URL,
                    on_message=on_message, on_error=on_error,
                    on_close=on_close, on_open=on_open)
                ws.run_forever(ping_interval=10, ping_timeout=5)
            except Exception: pass
            state["connected"] = False
            time.sleep(1.0)
    threading.Thread(target=run, daemon=True).start()
    return state

# --- helpers ---
@st.cache_data(ttl=1.5)
def get_live_telemetry():
    try:
        r = requests.get(TELEMETRY_URL, timeout=0.5)
        if r.status_code == 200:
            return r.json(), True
    except Exception: pass
    return {"vibration":0.0,"temperature":0.0,"rpm":0,"pressure":0.0,"machine_id":"Line_2"}, False

@st.cache_data(ttl=10.0)
def load_kpi():
    for p in KPI_PATHS:
        if Path(p).exists():
            try:
                df = pd.read_excel(p) if p.endswith(".xlsx") else pd.read_csv(p)
                df.columns = [c.strip() for c in df.columns]
                if "timestamp" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                return df, p
            except Exception:
                continue
    return pd.DataFrame(), None

# --- CSS ---
st.markdown("""
<style>
.block-container { padding-top: 1.2rem; }
div[data-testid="stMetric"] {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 12px 14px;
    border-radius: 12px;
}
.scene-box {
    background: #f8fafc; border: 1px solid #e2e8f0;
    padding: 14px 16px; border-radius: 12px; font-size: 14px;
}
.safety-alert {
    background: #fef2f2; border: 1px solid #fecaca;
    padding: 12px 14px; border-radius: 10px; color: #b91c1c;
}
</style>
""", unsafe_allow_html=True)

# --- Header ---
h1, h2 = st.columns([3,1])
with h1:
    st.markdown("## 🏭 MULTIMODAL_004 Factory AI")
    st.caption("Live Operations Center • Vision + Telemetry + Safety")
with h2:
    live_ping, api_ok = get_live_telemetry()
    color = "#22c55e" if api_ok else "#ef4444"
    text = "API LIVE" if api_ok else "API OFFLINE"
    st.markdown(f"<div style='text-align:right;font-weight:700;color:{color};font-size:18px'>● {text}</div>", unsafe_allow_html=True)
    st.caption(f"<div style='text-align:right'>{datetime.now().strftime('%H:%M:%S IST')}</div>", unsafe_allow_html=True)

# --- Top row: Video / Telemetry / System ---
col_vid, col_tel, col_sys = st.columns([1.6, 1.1, 1.1])

with col_vid:
    st.markdown("**Live Video Feed**")
    video_mode = st.segmented_control("video", ["WebSocket", "Direct", "Off"], default="WebSocket", label_visibility="collapsed", key="video_mode")

    @st.fragment(run_every=0.12)
    def video_panel():
        mode = st.session_state.get("video_mode", "WebSocket")
        if mode == "WebSocket":
            reader = get_ws_video_reader()
            frame_bytes = reader.get("frame")
            connected = reader.get("connected", False)
            age = time.time() - reader.get("last_ts", 0)
            if frame_bytes:
                st.session_state["last_video_frame"] = frame_bytes
            last_frame = st.session_state.get("last_video_frame")
            if last_frame:
                st.image(last_frame, use_container_width=True)
                status = "LIVE" if connected and age < 1.5 else "reconnecting…"
                st.caption(f"ws://localhost:8001/api/video/ws • {status}")
            else:
                st.info("Waiting for WebSocket video…\nMake sure `python main.py` is running")
                st.caption(WS_VIDEO_URL)
        elif mode == "Direct":
            st.components.v1.html(f'<img src="{HTTP_VIDEO_URL}" style="width:100%;border-radius:12px;" />', height=360)
            st.caption("Direct MJPEG")
        else:
            st.info("Video paused")
    video_panel()

with col_tel:
    @st.fragment(run_every=1.5)
    def telemetry_panel():
        st.markdown("**Live Telemetry**")
        live_ping, _ = get_live_telemetry()
        v = live_ping.get("vibration", 0)
        t = live_ping.get("temperature", 0)
        m1, m2 = st.columns(2)
        m1.metric("Vibration", f"{v:.2f} mm/s")
        m2.metric("Temperature", f"{t:.1f} °C")
        m3, m4 = st.columns(2)
        m3.metric("RPM", f"{live_ping.get('rpm',0)}")
        m4.metric("Pressure", f"{live_ping.get('pressure',0):.2f}")
        st.write(f"Machine: **{live_ping.get('machine_id','Line_2')}**")
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number", value=v, number={'suffix': " mm/s"},
            gauge={'axis': {'range': [0, 15]}, 'bar': {'color': "#ef4444" if v > 8 else "#22c55e"}},
            domain={'x': [0, 1], 'y': [0, 1]}
        ))
        fig_g.update_layout(height=150, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig_g, use_container_width=True, config={"displayModeBar": False})
    telemetry_panel()

with col_sys:
    st.markdown("**System Health**")
    st.write("● Vision Agent \n● Telemetry Agent \n● Safety Agent \n● Scene Description Agent \n● Orchestrator")
    st.caption(f"Telemetry: `{TELEMETRY_URL.split('//')[1]}`")
    st.caption(f"Video WS: `{WS_VIDEO_URL.split('//')[1]}`")
    if st.button("Refresh data", use_container_width=True):
        load_kpi.clear()
        st.rerun()

st.divider()

# --- Load KPI ---
df, kpi_path = load_kpi()
if df.empty:
    st.info("No KPI file found yet. Run `python main.py` to generate factory_kpis.csv")
    st.stop()

# --- Filters ---
f1, f2, f3, f4 = st.columns([1,1,1,2])
with f1:
    machines = ["All"] + sorted(df["machine_id"].dropna().unique().tolist()) if "machine_id" in df.columns else ["All"]
    machine_f = st.selectbox("Machine", machines, key="mf")
with f2:
    decisions = ["All"] + sorted(df["agent_decision"].dropna().unique().tolist()) if "agent_decision" in df.columns else ["All"]
    decision_f = st.selectbox("Decision", decisions, key="dfilt")
with f3:
    window = st.selectbox("Window", ["Last 100", "Last 500", "All"], index=0, key="win")
with f4:
    col_search, col_live = st.columns([3,1])
    with col_search:
        search_scene = st.text_input("Search CCTV / Safety text", placeholder="helmet, falling, Line_2…", label_visibility="collapsed")
    with col_live:
        live_data = st.toggle("Live data", value=False, help="Auto-refresh KPI tables every 5s")

if live_data:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=5000, key="kpi_tick")
    except ImportError:
        pass

df_f = df.copy()
if machine_f!= "All" and "machine_id" in df_f.columns:
    df_f = df_f[df_f["machine_id"] == machine_f]
if decision_f!= "All" and "agent_decision" in df_f.columns:
    df_f = df_f[df_f["agent_decision"] == decision_f]
if search_scene:
    text_cols = [c for c in ["video_description","safety_description","input_detected_objects","alert_type"] if c in df_f.columns]
    if text_cols:
        mask = False
        for c in text_cols:
            mask = mask | df_f[c].astype(str).str.contains(search_scene, case=False, na=False)
        df_f = df_f[mask]

if window == "Last 100": df_f = df_f.tail(100)
elif window == "Last 500": df_f = df_f.tail(500)

# --- KPI cards ---
total_cycles = len(df_f)
downtime = df_f["downtime_saved_hrs"].sum() if "downtime_saved_hrs" in df_f.columns else 0
defects = df_f["defects_caught"].sum() if "defects_caught" in df_f.columns else 0
safety = df_f["safety_violations"].sum() if "safety_violations" in df_f.columns else 0
falling_avg = df_f["falling_risk_score"].mean() if "falling_risk_score" in df_f.columns else 0
accident_avg = df_f["accident_prediction_score"].mean() if "accident_prediction_score" in df_f.columns else 0
last_decision = df_f["agent_decision"].iloc[-1] if "agent_decision" in df_f.columns and len(df_f) else "normal"

k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
k1.metric("Total Cycles", f"{total_cycles:,}")
k2.metric("Downtime Saved", f"{downtime:.1f} hrs")
k3.metric("Defects Caught", f"{int(defects):,}")
k4.metric("Safety Violations", f"{int(safety):,}")
k5.metric("Falling Risk Avg", f"{falling_avg:.0f}")
k6.metric("Accident Pred. Avg", f"{accident_avg:.0f}")
k7.metric("Last Decision", last_decision)

# --- Tabs ---
tab_overview, tab_safety, tab_cctv, tab_raw = st.tabs(["Overview", "Safety Center", "CCTV Log", "Raw Data"])

with tab_overview:
    c_left, c_right = st.columns([1.5, 1])
    with c_left:
        if "timestamp" in df_f.columns and "input_vibration" in df_f.columns:
            plot_df = df_f.dropna(subset=["timestamp"]).tail(200)
            y_cols = [c for c in ["input_vibration", "input_temp"] if c in plot_df.columns]
            if y_cols:
                fig = px.line(plot_df, x="timestamp", y=y_cols, title="Vibration / Temperature Trend")
                fig.update_layout(height=320, margin=dict(l=10,r=10,t=40,b=10), legend=dict(orientation="h"))
                st.plotly_chart(fig, use_container_width=True)
    with c_right:
        if "agent_decision" in df_f.columns:
            counts = df_f["agent_decision"].value_counts().reset_index()
            counts.columns = ["decision", "count"]
            color_map = {"normal": "#22c55e", "quality_defect": "#f59e0b", "safety_violation": "#ef4444", "critical_maintenance": "#7c3aed"}
            fig2 = px.pie(counts, names="decision", values="count", hole=0.55, title="Decision Distribution", color="decision", color_discrete_map=color_map)
            fig2.update_layout(height=320, margin=dict(l=10,r=10,t=40,b=10), showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)

with tab_safety:
    s1, s2, s3 = st.columns(3)
    last_falling = df_f["falling_risk_score"].iloc[-1] if "falling_risk_score" in df_f.columns and len(df_f) else 0
    with s1:
        st.markdown("**Falling Risk**")
        fg = go.Figure(go.Indicator(mode="gauge+number", value=last_falling,
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#ef4444" if last_falling > 85 else "#f59e0b" if last_falling > 50 else "#22c55e"}},
            domain={'x': [0, 1], 'y': [0, 1]}))
        fg.update_layout(height=180, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fg, use_container_width=True, config={"displayModeBar": False})
    last_accident = df_f["accident_prediction_score"].iloc[-1] if "accident_prediction_score" in df_f.columns and len(df_f) else 0
    with s2:
        st.markdown("**Accident Prediction**")
        ag = go.Figure(go.Indicator(mode="gauge+number", value=last_accident,
            gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "#ef4444" if last_accident > 70 else "#f59e0b" if last_accident > 40 else "#22c55e"}},
            domain={'x': [0, 1], 'y': [0, 1]}))
        ag.update_layout(height=180, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(ag, use_container_width=True, config={"displayModeBar": False})
    with s3:
        st.markdown("**PPE Violations**")
        if "ppe_violations" in df_f.columns:
            ppe_all = ",".join(df_f["ppe_violations"].dropna().astype(str))
            ppe_list = [x.strip() for x in ppe_all.split(",") if x.strip()]
            if ppe_list:
                ppe_counts = pd.Series(ppe_list).value_counts()
                st.bar_chart(ppe_counts)
            else:
                st.success("No PPE violations in current filter")
    if all(c in df_f.columns for c in ["timestamp", "falling_risk_score", "accident_prediction_score"]):
        risk_df = df_f.dropna(subset=["timestamp"]).tail(200)
        fig_risk = px.line(risk_df, x="timestamp", y=["falling_risk_score", "accident_prediction_score"], title="Safety Risk Trend")
        fig_risk.add_hline(y=85, line_dash="dash", line_color="red", annotation_text="Falling Risk Alert 85")
        fig_risk.update_layout(height=280, margin=dict(l=10,r=10,t=40,b=10))
        st.plotly_chart(fig_risk, use_container_width=True)
    if "safety_description" in df_f.columns and len(df_f):
        last_safety = df_f["safety_description"].dropna().iloc[-1] if not df_f["safety_description"].dropna().empty else ""
        if last_safety and "ALERT" in str(last_safety).upper():
            st.markdown(f'<div class="safety-alert"><b>Latest Safety Alert:</b> {last_safety}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="scene-box"><b>Latest Safety:</b> {last_safety or "CLEAR"}</div>', unsafe_allow_html=True)

with tab_cctv:
    if "video_description" in df_f.columns and len(df_f):
        last_scene = df_f["video_description"].dropna().iloc[-1] if not df_f["video_description"].dropna().empty else ""
        last_ts = df_f["timestamp"].iloc[-1] if "timestamp" in df_f.columns else ""
        st.markdown(f'<div class="scene-box"><b>CCTV Scene – {last_ts}</b><br>{last_scene or "No description yet"}</div>', unsafe_allow_html=True)
    scene_cols = [c for c in ["timestamp","machine_id","input_detected_objects","video_description","safety_description","falling_risk_score","accident_prediction_score","ppe_violations","agent_decision"] if c in df_f.columns]
    st.markdown("**CCTV Scene History**")
    if scene_cols:
        scene_df = df_f[scene_cols].tail(100)
        if "timestamp" in scene_df.columns:
            scene_df = scene_df.sort_values("timestamp", ascending=False)
        st.dataframe(scene_df, use_container_width=True, height=420)

with tab_raw:
    st.markdown("**All KPI Columns**")
    all_cols = df_f.columns.tolist()
    default_cols = [c for c in [
        "timestamp","machine_id","input_vibration","input_temp","input_detected_objects",
        "video_description","agent_decision","alert_type","action_taken",
        "defects_caught","safety_violations","safety_description",
        "falling_risk_score","accident_prediction_score","ppe_violations","downtime_saved_hrs"
    ] if c in all_cols]
    for c in all_cols:
        if c not in default_cols:
            default_cols.append(c)
    show_cols = st.multiselect("Columns to display", all_cols, default=default_cols, key="raw_cols")
    if show_cols:
        raw_df = df_f[show_cols].sort_values("timestamp", ascending=False) if "timestamp" in show_cols else df_f[show_cols]
        st.dataframe(raw_df, use_container_width=True, height=500)

# --- Footer ---
lf, rf = st.columns([3,1])
with rf:
    if kpi_path:
        with open(kpi_path, "rb") as f:
            st.download_button("⬇ Download KPI", f, file_name=Path(kpi_path).name, use_container_width=True)
with lf:
    st.caption(f"KPI: {kpi_path or 'not found'} • Rows: {len(df_f)} • {datetime.now().strftime('%H:%M:%S')}")