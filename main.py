from fastapi import FastAPI
from routes import tweets, users

app = FastAPI(title="Twitter Clone API")

#Register the routes so the server is aware of them
app.include_router(tweets.router)
app.include_router(users.router)