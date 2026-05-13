import os
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

#Check if running locally
if os.path.exists("firebase-credentials.json"):
  #Boot up Firebase connection using hidden key
  cred = credentials.Certificate("firebase-credentials.json")
  firebase_admin.initialize_app(cred)
else:
  #Google servers automatically handle credentials
  firebase_admin.initialize_app()

#Tell FastAPI to look for a "Bearer" token in the headers
security = HTTPBearer()

#The Bouncer funcction:
def verify_user(credentials: HTTPAuthorizationCredentials = Security(security)):
  token = credentials.credentials
  try:
    #Ask Google's servers if this token is mathematically valid and not expired
    decoded_token = auth.verify_id_token(token)

    #If valid, return the data within the token
    return decoded_token
  except Exception as e:
    #If the token is fake, expired, or mangled, deny access
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="Invalid or expired authentication token",
      headers={"WWW-Authenticate": "Bearer"},
    )