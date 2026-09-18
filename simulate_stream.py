import time
import random
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Two Indian PHCs + one federated BRICS node.
PHC_NODES = [
    {
        "phc_id": "PHC_DL_01",
        "district": "New Delhi",
        "node_type": "India-Core-Node",
        "base": {
            "Paracetamol": 450,
            "Amoxicillin": 220,
            "ORS Packets": 180,
            "Insulin": 35,
        },
        "icu": 4,
        "general": 25,
        "staff": 92.5,
    },
    {
        "phc_id": "PHC_PB_04",
        "district": "Ludhiana",
        "node_type": "India-Regional-Node",
        "base": {
            "Paracetamol": 180,
            "Amoxicillin": 75,
            "ORS Packets": 200,
            "Insulin": 15,
        },
        "icu": 2,
        "general": 10,
        "staff": 78.0,
    },
    {
        "phc_id": "BRICS_BR_99",
        "district": "Sao Paulo (Simulated)",
        "node_type": "BRICS-Federated-Node",
        "base": {
            "Paracetamol": 1200,
            "Amoxicillin": 400,
            "ORS Packets": 600,
            "Insulin": 80,
        },
        "icu": 15,
        "general": 80,
        "staff": 95.0,
    },
]

print("🔴 Starting Real-Time Telemetry Simulator")
print("Press Ctrl+C to stop.")

try:
    while True:
        for node in PHC_NODES:
            # Deliberately create realistic fluctuations.
            stocks = {}

            for medicine, base in node["base"].items():
                # Ludhiana is more likely to experience shortages for demo purposes.
                if node["phc_id"] == "PHC_PB_04":
                    if medicine == "Amoxicillin":
                        value = random.randint(10, 130)
                    elif medicine == "Insulin":
                        value = random.randint(2, 25)
                    else:
                        value = random.randint(max(20, base - 80), base + 100)
                else:
                    value = random.randint(max(5, base - 80), base + 100)

                stocks[medicine] = value

            payload = {
                "phc_id": node["phc_id"],
                "district": node["district"],
                "node_type": node["node_type"],
                "medicine_stock": stocks,
                "icu_beds_available": max(
                    0, node["icu"] + random.randint(-2, 2)
                ),
                "general_beds_available": max(
                    0, node["general"] + random.randint(-5, 5)
                ),
                "staff_attendance_percentage": round(
                    max(50, min(100, node["staff"] + random.uniform(-5, 5))), 1
                ),
                "timestamp": firestore.SERVER_TIMESTAMP,
            }

            db.collection("phc_telemetry").document(
                node["phc_id"]
            ).set(payload, merge=True)

            print(
                f"[{time.strftime('%H:%M:%S')}] "
                f"{node['district']} | "
                f"Amox: {stocks['Amoxicillin']} | "
                f"Insulin: {stocks['Insulin']} | "
                f"ICU: {payload['icu_beds_available']}"
            )

        time.sleep(60)

except KeyboardInterrupt:
    print("\n🛑 Simulator stopped.")
