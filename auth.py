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

# ---------------------------------------------------------
# SECURITY DEPENDENCIES
# ---------------------------------------------------------

#Tell FastAPI to look for a "Bearer" token in the headers. Throws error if no token, the strict bouncer
security = HTTPBearer()

# Allows empty headers without crashing, a more flexible bouncer
optional_security = HTTPBearer(auto_error=False)

# ---------------------------------------------------------
# AUTHENTICATION FUNCTIONS
# ---------------------------------------------------------

#Strict Bouncer funcction:
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
  
# Flexible Bouncer function:
def get_optional_user(credentials: HTTPAuthorizationCredentials = Security(optional_security)):
  """Allows guests. Returns user data if logged in, otherwise returns None."""
  #If the header is completely missing, wave them through as a Guest
  if not credentials:
    return None
  
  token = credentials.credentials
  try:
    #Ask Google's servers if this token is mathematically valid
    decoded_token = auth.verify_id_token(token)
    return decoded_token
  except Exception:
    #If they provided a token but it expired since they last refreshed the page,
    #silently downgrade them to Guest status instead of crashing the page
    return None