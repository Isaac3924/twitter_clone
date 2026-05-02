from fastapi import APIRouter , HTTPException
from pydantic import BaseModel
from database import get_db_connection
import psycopg2 

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

@router.get("/api/v1/tweets/{tweet_id}", status_code=200)
def get_tweet(tweet_id: int):
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Fetch the specific tweet using the ID from the URL
    cursor.execute(
      """
      SELECT tweet_id, user_id, body, created_at
      FROM Tweets
      WHERE tweet_id = %s;
      """,
      (tweet_id,) #Pass the ID securely
    )

    tweet = cursor.fetchone()

    #If the query returns nothing, return a 404 error
    if not tweet:
      raise HTTPException(status_code=404, detail="Tweet not found")
    
    #Map the returned db tuple back into a readable JSON dict
    return {
      "tweet_id": tweet[0],
      "user_id": tweet[1],
      "body": tweet[2],
      "created_at": tweet[3]
    }

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

#Small Pydantic model to accept the user_id of the person liking the tweet
class LikeCreate(BaseModel):
  user_id: str

@router.post("/api/v1/tweets/{tweet_id}/like", status_code=201)
def like_tweet(tweet_id: int, like_data: LikeCreate):
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Attempt to insert the like.
    cursor.execute(
      """
      INSERT INTO Likes (user_id, tweet_id)
      VALUES (%s, %s);
      """,
      (like_data.user_id, tweet_id)
    )
    conn.commit()
    return {"message": "Tweet liked successfully"}
  
  except psycopg2.errors.UniqueViolation:
    #Catches the error PostgreSQL throws if tweet was already liked
    conn.rollback()
    raise HTTPException(status_code=400, detail="You already liked this tweet")
  
  except psycopg2.errors.ForeignKeyViolation:
    #Catches if the tweet_id or user_id don't exist in the DB
    conn.rollback()
    raise HTTPException(status_code=404, detail="Tweet or user not found")
  
  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()