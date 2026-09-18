import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title="Federated National Health Grid",
    page_icon="🏥",
    layout="wide",
)

FASTAPI_URL = "http://127.0.0.1:8000"

page = st.sidebar.radio(
    "Navigation",
    [
        "National Command Center",
        "Early Warnings & AI Alerts",
        "Resource Redistribution",
    ],
)

if page == "National Command Center":
    st_autorefresh(interval=60000, key="health_grid_refresh")

st.title("Federated National Health Grid")
st.caption(
    "Real-time visibility • AI early warnings • OR-Tools resource redistribution"
)

if "gemini_analysis" not in st.session_state:
    st.session_state.gemini_analysis = None

def get_json(endpoint):
    try:
        response = requests.get(f"{FASTAPI_URL}{endpoint}", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(
            f"Cannot reach FastAPI at {FASTAPI_URL}. "
            f"Start Uvicorn first. Details: {e}"
        )
        return None

def get_gemini_analysis():
    try:
        response = requests.get(
            f"{FASTAPI_URL}/api/v1/ai/situation-analysis",
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Gemini analysis failed: {e}")
        return None

if page == "National Command Center":
    st.header("National & Federated PHC Telemetry")

    payload = get_json("/api/v1/phc/telemetry")

    if payload is not None:
        data = payload.get("data", [])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Active PHC Nodes", len(data))
        col2.metric(
            "Federated Nodes",
            sum("Federated" in str(x.get("node_type", "")) for x in data),
        )
        col3.metric(
            "Critical Stock Items",
            sum(
                1
                for x in data
                for v in (x.get("medicine_stock") or {}).values()
                if isinstance(v, (int, float)) and v < 100
            ),
        )
        col4.metric("Telemetry Refresh", "1 min")

        coords = {
            "PHC_DL_01": [28.6139, 77.2090],
            "PHC_PB_04": [30.9010, 75.8573],
            "BRICS_BR_99": [-23.5505, -46.6333],
        }

        m = folium.Map(
            location=[22.5937, 78.9629],
            zoom_start=3
        )

        for phc in data:
            p_id = phc.get("phc_id")
            loc = coords.get(p_id, [20.0, 78.0])
            node_type = str(phc.get("node_type", ""))

            popup = (
                f"<b>{phc.get('district')} ({p_id})</b><br>"
                f"Node: {node_type}<br>"
                f"ICU Beds: {phc.get('icu_beds_available', 0)}<br>"
                f"General Beds: {phc.get('general_beds_available', 0)}<br>"
                f"Staff: {phc.get('staff_attendance_percentage', 0)}%<br>"
                f"Medicines: {phc.get('medicine_stock', {})}"
            )

            folium.Marker(
                location=loc,
                popup=popup,
                tooltip=p_id,
                icon=folium.Icon(
                    color="green" if "Federated" in node_type else "blue"
                ),
            ).add_to(m)

        st_folium(m, width=None, height=450)

        st.subheader("Live Telemetry")

        for phc in data:
            with st.expander(
                f"{phc.get('district')} — {phc.get('phc_id')}"
            ):
                st.json(phc)

elif page == "Early Warnings & AI Alerts":
    st.header("AI Early Warning System")
    st.write(
        "The engine checks current stock against medicine-specific safety "
        "levels and adds operational context."
    )

    payload = get_json("/api/v1/ai/early-warnings")

    if payload is not None:
        warnings = payload.get("early_warnings", [])

        if not warnings:
            st.success("No current stock-out risks detected.")
        else:
            for w in warnings:
                severity = w["severity"]
                text = (
                    f"**{severity}** — {w['district']} ({w['phc_id']}) | "
                    f"**{w['medicine']}** | "
                    f"{w['stock_level']} units left / "
                    f"{w['threshold']} safety level | "
                    f"Shortage: {w['shortage_percentage']}%"
                )

                if severity == "CRITICAL":
                    st.error(text)
                elif severity == "HIGH":
                    st.warning(text)
                else:
                    st.info(text)

                if w.get("context"):
                    st.caption(
                        "Context: " + ", ".join(w["context"])
                    )

    st.markdown("---")

    st.subheader("🧠 Gemini AI Situation Analysis")

    st.write(
        "Gemini analyzes the current federated telemetry and early-warning "
        "signals to identify priority risks and recommend actions."
    )

    if st.button(
        "🧠 Analyze Current Situation with Gemini",
        type="primary"
    ):
        with st.spinner(
            "Gemini is analyzing the current health network..."
        ):
            result = get_gemini_analysis()

        if result is not None:
            st.session_state.gemini_analysis = result

    if st.session_state.gemini_analysis is not None:
        analysis = st.session_state.gemini_analysis.get(
            "analysis",
            {}
        )

        st.markdown("### 🚦 Overall Situation")

        st.warning(
            analysis.get(
                "overall_status",
                "No overall status available."
            )
        )

        st.markdown("### 📋 Situation Summary")

        st.write(
            analysis.get(
                "situation_summary",
                "No situation summary available."
            )
        )

        st.markdown("### 🎯 Priority Actions")

        priority_actions = analysis.get(
            "priority_actions",
            []
        )

        if priority_actions:
            for action in priority_actions:
                st.markdown(f"• {action}")
        else:
            st.write("No priority actions returned.")

        critical_nodes = analysis.get(
            "critical_nodes",
            []
        )

        if critical_nodes:
            st.markdown("### 🔴 Critical Nodes")

            for node in critical_nodes:
                st.error(node)

        resource_concerns = analysis.get(
            "resource_concerns",
            []
        )

        if resource_concerns:
            st.markdown("### 📦 Resource Concerns")

            for concern in resource_concerns:
                st.warning(concern)

        st.markdown("### 🚀 Recommended Action")

        st.info(
            analysis.get(
                "recommended_action",
                "No recommended action available."
            )
        )

        st.markdown("### 💡 AI Rationale")

        st.write(
            analysis.get(
                "rationale",
                "No rationale available."
            )
        )

        st.success("Gemini analysis completed successfully.")

elif page == "Resource Redistribution":
    st.header("Cross-District Resource Redistribution")
    st.write(
        "OR-Tools matches surplus inventory with shortage nodes while "
        "respecting each node's available surplus and required stock."
    )

    if st.button("Run Optimization Solver", type="primary"):
        payload = get_json("/api/v1/optimization/redistribute")

        if payload is not None:
            st.success(
                f"Optimization status: "
                f"{payload.get('optimization_status')}"
            )

            st.metric(
                "Recommended Transfer Units",
                payload.get("recommended_transfer_units", 0),
            )

            transfers = payload.get("transfers", [])

            if not transfers:
                st.info("No transfers are currently required.")
            else:
                st.subheader("Recommended Actions")

                for t in transfers:
                    st.success(
                        f"**{t['medicine']} — {t['units']} units**  \n"
                        f"{t['from_district']} → {t['to_district']}"
                    )

                st.subheader("Machine-readable optimization result")
                st.json(payload)