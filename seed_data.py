import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_credentials.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

phc_data = [
    {
        "phc_id": "PHC_DL_01",
        "district": "New Delhi",
        "node_type": "India-Core-Node",
        "medicine_stock": {
            "Paracetamol": 450,
            "Amoxicillin": 220,
            "ORS Packets": 180,
            "Insulin": 35,
        },
        "icu_beds_available": 4,
        "general_beds_available": 25,
        "staff_attendance_percentage": 92.5,
    },
    {
        "phc_id": "PHC_PB_04",
        "district": "Ludhiana",
        "node_type": "India-Regional-Node",
        "medicine_stock": {
            "Paracetamol": 180,
            "Amoxicillin": 45,
            "ORS Packets": 200,
            "Insulin": 8,
        },
        "icu_beds_available": 2,
        "general_beds_available": 10,
        "staff_attendance_percentage": 78.0,
    },
    {
        "phc_id": "BRICS_BR_99",
        "district": "Sao Paulo (Simulated)",
        "node_type": "BRICS-Federated-Node",
        "medicine_stock": {
            "Paracetamol": 1200,
            "Amoxicillin": 400,
            "ORS Packets": 600,
            "Insulin": 80,
        },
        "icu_beds_available": 15,
        "general_beds_available": 80,
        "staff_attendance_percentage": 95.0,
    },
]

for phc in phc_data:
    db.collection("phc_telemetry").document(phc["phc_id"]).set(phc)

print("✅ Mock PHC data successfully seeded to Firestore.")
