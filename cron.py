import json
import base64
import os
import modal
from modal import Image
import math


latest_img = (
    Image.debian_slim()
    .pip_install("firebase-admin", force_build=True)
    .run_commands("echo hi")
)

with latest_img.imports():
    import firebase_admin
    from firebase_admin import credentials
    from firebase_admin import firestore
    from google.oauth2 import service_account

app = modal.App(image=latest_img)

# A helper function to calculate the distance between two points
def haversine(lat1, lon1, lat2, lon2):
    # Radius of the Earth in km
    R = 6371.0
    # Convert coordinates from degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Compute differences in coordinates
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Apply haversine formula
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # Distance in kilometers
    distance = R * c
    return distance * 1000  # Distance in meters

# Define a threshold (100 meters)
DISTANCE_THRESHOLD = 100.0

def get_people_near_eachother(users_ref):
    users_docs = [doc.to_dict() for doc in users_ref.stream()]

    near_pairs = []
    # Compare each user with every other user in the list
    for i, user_doc in enumerate(users_docs):
        for j, other_user_doc in enumerate(users_docs):
            # Avoid comparing the user with themselves
            if i != j:
                user_location = user_doc.get("latitude"), user_doc.get("longitude")
                other_user_location = other_user_doc.get("latitude"), other_user_doc.get("longitude")

                # Ensure that both users have location data
                if all(user_location) and all(other_user_location):
                    distance = haversine(*user_location, *other_user_location)
                    # If the users are closer than the threshold, add their docs to the list
                    if distance <= 100:  # 100 meters threshold
                        near_pairs.append((user_doc, other_user_doc))

    return near_pairs

twilio_image = modal.Image.debian_slim().pip_install("twilio")

@stub.function(image=twilio_image, secrets=[modal.Secret.from_name("twilio")])
def send_sms(to_number: str, body_text: str):
    from twilio.rest import Client

    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = "+12165038253"
    client = Client(account_sid, auth_token)

    client.messages.create(
        from_=from_number,
        body=body_text,
        to=to_number,
    )

@app.function(schedule=modal.Period(minutes=5), image=latest_img, secrets=[modal.Secret.from_name("google_cloud")])
async def cron_job():
    service_account_info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    credentials = firebase_admin.credentials.Certificate(service_account_info)
    app = firebase_admin.initialize_app(credentials)
    db = firestore.client(app=app)

    users_ref = db.collection("users")
    people_near_eachother = get_people_near_eachother(users_ref)
    print(people_near_eachother)
    

@app.function(image=latest_img)
def run_cron_job():
    cron_job.remote()

@app.local_entrypoint()
def main():
    print("Hello, world!")
    run_cron_job.remote()