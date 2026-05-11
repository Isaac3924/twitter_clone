from fastapi import FastAPI
from routes import tweets, users
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Twitter Clone API")

#Register the routes so the server is aware of them
app.include_router(tweets.router)
app.include_router(users.router)

#Add CORS middleware to allow frontend to connect with the backend
app.add_middleware(
  CORSMiddleware,
  #Allow any origin to connect for now
  #When in production with a real domain, will set it to the website URL
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"], #Allows GET, POST, PUT, DELETE, etc
  allow_headers=["*"], #Allows any headers 
)