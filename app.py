import os
import streamlit as st
from scheduler.scenario_loader import load_scenario, list_scenario_files, scenario_name_from_file
from scheduler.engine import run
from scheduler.rules import registry

SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "data", "scenarios")


def fmt(t: int) -> str:
    total = 19 * 60 + t
    h = total // 60
    m = total % 60
    return f"{h:02d}:{m:02d}"


st.set_page_config(page_title="Bus Charging Scheduler", layout="wide")
st.title("Bus Charging Scheduler")

scenario_files = list_scenario_files(SCENARIOS_DIR)
if not scenario_files:
    st.error("No scenario files found in data/scenarios/")
    st.stop()

scenario_names = {f: scenario_name_from_file(f) for f in scenario_files}
selected_file = st.sidebar.selectbox(
    "Select Scenario",
    scenario_files,
    format_func=lambda f: scenario_names[f],
)

scenario = load_scenario(selected_file)

st.sidebar.markdown("---")
st.sidebar.subheader("Weights")
for k, v in scenario.weights.items():
    st.sidebar.text(f"  {k}: {v}")

st.sidebar.subheader("Constants")
for k, v in scenario.constants.items():
    st.sidebar.text(f"  {k}: {v}")

st.sidebar.markdown("---")
if st.sidebar.button("Run Schedule", type="primary", use_container_width=True):
    with st.spinner("Computing schedule..."):
        result = run(scenario)
    st.session_state.result = result
    st.session_state.scenario_name = scenario.name

if "result" in st.session_state and st.session_state.scenario_name == scenario.name:
    result = st.session_state.result
else:
    result = None

tab1, tab2, tab3 = st.tabs(["Scenario Input", "Per-Bus Timetable", "Per-Station View"])

with tab1:
    st.header("Route")
    seg_data = []
    for s in scenario.route.segments:
        seg_data.append({
            "From": s.from_station,
            "To": s.to_station,
            "Distance (km)": s.distance_km,
        })
    st.table(seg_data)
    st.text(f"Total distance: {scenario.route.total_distance_km()} km")

    st.header("Operators")
    op_data = [{"ID": o.id, "Name": o.name} for o in scenario.operators]
    st.table(op_data)

    st.header("Stations")
    stn_data = []
    for sid in scenario.station_ids:
        stn_data.append({
            "Station": sid,
            "Chargers": scenario.chargers_per_station.get(sid, 1),
        })
    st.table(stn_data)

    st.header("Buses")
    bus_data = []
    for b in scenario.buses:
        bus_data.append({
            "Bus ID": b.id,
            "Operator": b.operator,
            "Direction": "Bengaluru→Kochi" if b.direction == "BK" else "Kochi→Bengaluru",
            "Departure": fmt(b.departure_time_minutes),
        })
    st.table(bus_data)

    st.header("Weights & Constants")
    col_w, col_c = st.columns(2)
    with col_w:
        st.subheader("Weights")
        for k, v in scenario.weights.items():
            st.text(f"{k}: {v}")
    with col_c:
        st.subheader("Constants")
        for k, v in scenario.constants.items():
            st.text(f"{k}: {v}")

with tab2:
    if result is None:
        st.info("Click 'Run Schedule' in the sidebar to compute the schedule.")
    else:
        st.header("Per-Bus Timetable")

        direction_filter = st.radio(
            "Filter by direction",
            ["All", "Bengaluru→Kochi", "Kochi→Bengaluru"],
            horizontal=True,
        )

        for tl in result.bus_timelines:
            if direction_filter == "Bengaluru→Kochi" and tl.bus.direction != "BK":
                continue
            if direction_filter == "Kochi→Bengaluru" and tl.bus.direction != "KB":
                continue

            with st.expander(
                f"**{tl.bus.id}** — {tl.bus.operator} — "
                f"{'BK' if tl.bus.direction == 'BK' else 'KB'} — "
                f"Dep: {fmt(tl.bus.departure_time_minutes)} — "
                f"Total wait: {tl.total_wait} min — "
                f"Arrival: {fmt(tl.final_arrival_time)}"
            ):
                if not tl.charging_events:
                    st.text("No charging events (direct route — not feasible for this distance)")
                else:
                    event_data = []
                    for ev in tl.charging_events:
                        event_data.append({
                            "Station": ev.station_id,
                            "Arrival": fmt(ev.arrival_time),
                            "Charge Start": fmt(ev.charge_start_time),
                            "Charge End": fmt(ev.charge_end_time),
                            "Departure": fmt(ev.departure_time),
                            "Wait (min)": ev.wait_time,
                        })
                    st.table(event_data)

with tab3:
    if result is None:
        st.info("Click 'Run Schedule' in the sidebar to compute the schedule.")
    else:
        st.header("Per-Station Charging Order")

        station_cols = st.columns(len(scenario.station_ids))
        for col, sid in zip(station_cols, scenario.station_ids):
            with col:
                st.subheader(f"Station {sid}")
                log = result.station_logs.get(sid)
                if log and log.entries:
                    order_data = []
                    for i, entry in enumerate(log.entries, 1):
                        order_data.append({
                            "#": i,
                            "Bus": entry.bus_id,
                            "Arrival": fmt(entry.arrival_time),
                            "Charge Start": fmt(entry.charge_start_time),
                            "Charge End": fmt(entry.charge_end_time),
                            "Wait": f"{entry.wait_time} min",
                        })
                    st.table(order_data)
                else:
                    st.text("No buses charged here.")

if result is not None:
    st.markdown("---")
    st.header("Schedule Scores")
    score_cols = st.columns(len(result.scores))
    for col, (name, val) in zip(score_cols, result.scores.items()):
        with col:
            st.metric(label=name.capitalize(), value=f"{val:.1f}")
