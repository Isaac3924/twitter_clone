import os
import psycopg2
from dotenv import load_dotenv

#Load connection string securely from .env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
  #Opens and returns a connection to the Neon database.
  return psycopg2.connect(DATABASE_URL)