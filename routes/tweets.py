from fastapi import APIRouter , HTTPException
from pydantic import BaseModel
from database import get_db_connection

#Create a router for all tweet-related endpoints
router = APIRouter()

#Define the data expected from the user
class TweetCreate(BaseModel):
  user_id: str
  body: str

@router.post("/api/v1/tweets", status_code=201)
def create_tweet(tweet: TweetCreate):
  #1. Open the DB connection
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #2. Execute the raw SQL.
    #We use %s to safely inject the variables to prevent SQL injection hacks.
    cursor.execute(
      """
      INSERT INTO Tweets (user_id, body)
      VALUES (%s, %s)
      RETURNING tweet_id;
      """,
      (tweet.user_id, tweet.body)
    )

    #3. Fetch the ID of the newly created tweet
    new_tweet_id = cursor.fetchone()[0]

    #4. Commit the save to the db
    conn.commit()

    return {"message": "Tweet created successfully", "tweet_id": new_tweet_id}
  
  except Exception as e:
    #If anything goes wrong, undo the db transaction
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    #5. Always close the connection when finished

    cursor.close()
    conn.close()