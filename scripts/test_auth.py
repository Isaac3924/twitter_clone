import os
import requests
from dotenv import load_dotenv

load_dotenv()

#Web API Key for Firebase
API_KEY = os.getenv("FIREBASE_WEB_API_KEY")
EMAIL = os.getenv("TEST_USER_EMAIL")
PASSWORD = os.getenv("TEST_USER_PASSWORD")

def login():
  print(f"Attempting to login as {EMAIL}...")

  #Google's official REST API endpoint for password logins
  url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={API_KEY}"
  payload = {
    "email": EMAIL,
    "password": PASSWORD,
    "returnSecureToken": True
  }

  response = requests.post(url, json=payload)
  data = response.json()

  if "idToken" in data:
    print("\n✅ Login Successful! Here is your Firebase JWT (VIP Pass):\n")
    print(data["idToken"])
    print("\n(Copy this entire string to use in Swagger UI)")
  else:
    print("\n❌ Login Failed:")
    print(data)

if __name__ == "__main__":
  login()