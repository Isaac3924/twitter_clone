from fastapi import FastAPI
from routes import tweets 

app = FastAPI(title="Twitter Clone API")

#Register the routes so the server is aware of them
app.include_router(tweets.router)