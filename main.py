import os
import psycopg2
from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

#Load connection string securely from .env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="Twitter Clone API")

@app.get("/")
def read_root():
  return {"message": "Welcome to the Twitter Clone API"}

@app.get("/test-db")
def test_db_connection():
  try:
    #Attempt to open a connection to Neon
    conn = psycopg2.connect(DATABASE_URL)
    conn.close()
    return {"status": "success", "message": "Successfully connected to the Neon DB"}
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")