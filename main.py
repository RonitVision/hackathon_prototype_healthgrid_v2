from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import firebase_admin
from firebase_admin import credentials, firestore
from ortools.linear_solver import pywraplp
from google import genai
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Federated National Health Grid API", version="2.0")


# Firebase
if not firebase_admin._apps:
    cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase_credentials.json")
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()


MEDICINES = ["Paracetamol", "Amoxicillin", "ORS Packets", "Insulin"]


# Minimum stock levels for the demo.
# In a real deployment these would come from historical demand/forecasting.
MIN_STOCK = {
    "Paracetamol": 100,
    "Amoxicillin": 100,
    "ORS Packets": 100,
    "Insulin": 10,
}

#GEMINI part
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

gemini_client = None

if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)


class AISituationAnalysis(BaseModel):
    overall_status: str
    situation_summary: str
    priority_actions: List[str]
    critical_nodes: List[str]
    resource_concerns: List[str]
    recommended_action: str
    rationale: str

#Root
@app.get("/")
def root():
    return {
        "status": "Online",
        "message": "Federated National Health Grid API is running."
    }


#Firebase/Telemetry
def get_nodes():
    docs = db.collection("phc_telemetry").stream()
    return [doc.to_dict() for doc in docs]


@app.get("/api/v1/phc/telemetry")
def get_all_telemetry():
    try:
        return {"data": get_nodes()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


#early warning
@app.get("/api/v1/ai/early-warnings")
def generate_early_warnings():
    """
    Demo AI-style early warning engine.

    Uses current stock + stock threshold + staff/beds context to create
    explainable risk alerts. The endpoint is deterministic, so the demo
    remains reliable even when Gemini is unavailable.
    """
    try:
        warnings = []

        for data in get_nodes():
            phc_id = data.get("phc_id", "UNKNOWN")
            district = data.get("district", "Unknown")
            stocks = data.get("medicine_stock", {}) or {}
            icu = int(data.get("icu_beds_available", 0))
            staff = float(data.get("staff_attendance_percentage", 0))

            for medicine in MEDICINES:
                count = int(stocks.get(medicine, 0))
                threshold = MIN_STOCK[medicine]

                if count < threshold:
                    shortage_pct = max(
                        0,
                        (threshold - count) / threshold * 100
                    )

                    if count <= threshold * 0.25:
                        severity = "CRITICAL"
                    elif count <= threshold * 0.60:
                        severity = "HIGH"
                    else:
                        severity = "MEDIUM"

                    # Context makes the alert more useful than a bare threshold.
                    context = []

                    if staff < 80:
                        context.append("low staff attendance")

                    if icu <= 2:
                        context.append("low ICU capacity")

                    warnings.append({
                        "phc_id": phc_id,
                        "district": district,
                        "medicine": medicine,
                        "stock_level": count,
                        "threshold": threshold,
                        "shortage_percentage": round(shortage_pct, 1),
                        "severity": severity,
                        "status": f"{severity} - Potential Stock-out",
                        "context": context,
                        "generated_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                    })

        warnings.sort(
            key=lambda x: (
                {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}[x["severity"]],
                -x["shortage_percentage"]
            )
        )

        return {"early_warnings": warnings}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

#AI situation analysis
@app.get("/api/v1/ai/situation-analysis")
def ai_situation_analysis():
    """
    Uses Gemini to interpret current PHC telemetry and detected warnings.

    Gemini provides:
    - situation assessment
    - prioritization
    - explanation
    - recommended operational action

    Gemini does NOT determine exact redistribution quantities.
    OR-Tools remains responsible for numerical optimization.
    """

    if gemini_client is None:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured."
        )

    try:
        # current telemetry
        telemetry = get_nodes()

        if not telemetry:
            raise HTTPException(
                status_code=404,
                detail="No PHC telemetry available."
            )

        # Generate current warnings using our existing
        # deterministic warning engine
        warnings = []

        for data in telemetry:
            phc_id = data.get("phc_id", "UNKNOWN")
            district = data.get("district", "Unknown")
            stocks = data.get("medicine_stock", {}) or {}
            icu = int(data.get("icu_beds_available", 0))
            staff = float(data.get("staff_attendance_percentage", 0))

            for medicine in MEDICINES:
                count = int(stocks.get(medicine, 0))
                threshold = MIN_STOCK[medicine]

                if count < threshold:
                    shortage_pct = max(
                        0,
                        (threshold - count) / threshold * 100
                    )

                    if count <= threshold * 0.25:
                        severity = "CRITICAL"
                    elif count <= threshold * 0.60:
                        severity = "HIGH"
                    else:
                        severity = "MEDIUM"

                    context = []

                    if staff < 80:
                        context.append("low staff attendance")

                    if icu <= 2:
                        context.append("low ICU capacity")

                    warnings.append({
                        "phc_id": phc_id,
                        "district": district,
                        "medicine": medicine,
                        "stock_level": count,
                        "threshold": threshold,
                        "shortage_percentage": round(shortage_pct, 1),
                        "severity": severity,
                        "context": context,
                    })

        # --------------------------------------------------------
        # Gemini prompt
        # --------------------------------------------------------

        prompt = f"""
You are the AI reasoning layer of a federated healthcare
resource management system.

Analyze the CURRENT PHC telemetry and detected early warnings.

Your role is to help a human healthcare coordinator understand
the situation and decide what deserves attention first.

You must:

1. Assess the overall operational situation.
2. Identify the most urgent PHCs.
3. Identify the most urgent medicine/resource shortages.
4. Consider staff attendance and ICU capacity when relevant.
5. Prioritize actions.
6. Explain the reasoning behind the priorities.

IMPORTANT RULES:

- Use ONLY the information provided below.
- Do NOT invent hospitals, PHCs, medicines, numbers, or shortages.
- Do NOT invent telemetry values.
- Do NOT calculate exact redistribution quantities.
- Do NOT replace the optimization algorithm.
- OR-Tools is responsible for calculating exact resource transfers.
- Your role is reasoning, prioritization, explanation, and operational guidance.
- Keep the response concise and suitable for a command-center dashboard.

CURRENT PHC TELEMETRY:

{telemetry}


CURRENT DETECTED EARLY WARNINGS:

{warnings}
"""

        # --------------------------------------------------------
        # Gemini structured response
        # --------------------------------------------------------

        response = gemini_client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": AISituationAnalysis,
                "temperature": 0.2,
            },
        )

        # Pydantic structured response
        if getattr(response, "parsed", None):
            analysis = response.parsed
        else:
            analysis = AISituationAnalysis.model_validate_json(
                response.text
            )

        return {
            "status": "SUCCESS",
            "analysis": analysis.model_dump(),
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini analysis failed: {str(e)}"
        )

# OR-TOOLS REDISTRIBUTION


@app.get("/api/v1/optimization/redistribute")
def optimize_redistribution():
    """
    Optimize medicine transfers from surplus nodes to shortage nodes.
    Objective: maximize fulfilled shortage while minimizing transfers.
    Each medicine is solved independently.
    """
    try:
        nodes = get_nodes()

        if not nodes:
            return {
                "optimization_status": "NO_DATA",
                "recommended_transfer_units": 0,
                "transfers": [],
                "message": "No PHC telemetry available."
            }

        transfers = []

        for medicine in MEDICINES:
            suppliers = []
            receivers = []

            for node in nodes:
                stock = int(
                    (node.get("medicine_stock") or {}).get(
                        medicine,
                        0
                    )
                )

                threshold = MIN_STOCK[medicine]

                if stock > threshold:
                    suppliers.append({
                        "id": node.get("phc_id"),
                        "district": node.get("district"),
                        "surplus": stock - threshold,
                    })

                elif stock < threshold:
                    receivers.append({
                        "id": node.get("phc_id"),
                        "district": node.get("district"),
                        "need": threshold - stock,
                    })

            if not suppliers or not receivers:
                continue

            solver = pywraplp.Solver.CreateSolver("CBC")

            if not solver:
                raise HTTPException(
                    status_code=500,
                    detail="OR-Tools CBC solver unavailable."
                )

            x = {}

            for s in suppliers:
                for r in receivers:
                    x[(s["id"], r["id"])] = solver.IntVar(
                        0,
                        min(s["surplus"], r["need"]),
                        f"x_{medicine}_{s['id']}_{r['id']}"
                    )

            for s in suppliers:
                solver.Add(
                    sum(
                        x[(s["id"], r["id"])]
                        for r in receivers
                    ) <= s["surplus"]
                )

            for r in receivers:
                solver.Add(
                    sum(
                        x[(s["id"], r["id"])]
                        for s in suppliers
                    ) <= r["need"]
                )

            total_transfer = sum(x.values())

            solver.Maximize(total_transfer)

            status = solver.Solve()

            if status != pywraplp.Solver.OPTIMAL:
                continue

            for s in suppliers:
                for r in receivers:
                    amount = int(
                        x[(s["id"], r["id"])].solution_value()
                    )

                    if amount > 0:
                        transfers.append({
                            "medicine": medicine,
                            "from_phc": s["id"],
                            "from_district": s["district"],
                            "to_phc": r["id"],
                            "to_district": r["district"],
                            "units": amount,
                        })

        total_units = sum(
            t["units"]
            for t in transfers
        )

        return {
            "optimization_status": "SUCCESS",
            "recommended_transfer_units": total_units,
            "transfers": transfers,
            "message": (
                f"OR-Tools generated {len(transfers)} "
                f"recommended transfer(s), covering "
                f"{total_units} total medicine units."
            ),
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )