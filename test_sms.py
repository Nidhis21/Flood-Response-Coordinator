import requests

# 1. First turn: Initial Donation Offer
resp1 = requests.post("http://localhost:8000/api/twilio/inbound", data={
    "From": "+919998881234",
    "Body": "I want to donate some water"
})
print("Turn 1:", resp1.json())

# Wait 2 seconds
import time
time.sleep(2)

# 2. Second turn: Providing details
resp2 = requests.post("http://localhost:8000/api/twilio/inbound", data={
    "From": "+919998881234",
    "Body": "27.23, 94.10, 1, 500 bottles of drinking water"
})
print("Turn 2:", resp2.json())
