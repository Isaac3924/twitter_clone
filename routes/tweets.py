from fastapi import APIRouter , HTTPException, Depends
from auth import verify_user
from pydantic import BaseModel
from database import get_db_connection
import psycopg2 

#Create a router for all tweet-related endpoints
router = APIRouter()

#Define the data expected from the user
class TweetCreate(BaseModel):
  body: str

@router.post("/api/v1/tweets", status_code=201)
def create_tweet(tweet: TweetCreate, user_token: dict = Depends(verify_user)):
  #Extract the mathematically verified user ID from the token
  real_user_id = user_token.get("uid")

  #Open the DB connection
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Execute the raw SQL.
    #We use %s to safely inject the variables to prevent SQL injection hacks.
    cursor.execute(
      """
      INSERT INTO Tweets (user_id, body)
      VALUES (%s, %s)
      RETURNING tweet_id;
      """,
      (real_user_id, tweet.body)
    )

    #Fetch the ID of the newly created tweet
    new_tweet_id = cursor.fetchone()[0]

    #Commit the save to the db
    conn.commit()

    return {"tweet_id": new_tweet_id, "message": "Tweet created successfully"}
  
  except Exception as e:
    #If anything goes wrong, undo the db transaction
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    #Always close the connection when finished

    cursor.close()
    conn.close()

@router.get("/api/v1/tweets/explore", status_code=200)
def get_explore_feed():
  """Fetches the 50 most recent tweets globally."""
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    cursor.execute(
      """
      SELECT 
        t.tweet_id, 
        t.body, 
        t.created_at,
        u.user_id,
        u.screen_name
      FROM Tweets t
      JOIN Users u ON t.user_id = u.user_id
      ORDER BY t.created_at DESC
      LIMIT 50;
      """,
    )

    raw_tweets = cursor.fetchall()

    feed = []

    for tweet in raw_tweets:
      feed.append({
        "tweet_id": tweet[0],
        "body": tweet[1],
        "created_at": tweet[2],
        "author_id": tweet[3],
        "author_screen_name": tweet[4]
      })
    
    return {"feed": feed}

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
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

@router.post("/api/v1/tweets/{tweet_id}/like", status_code=201)
def like_tweet(tweet_id: int, user_token: dict = Depends(verify_user)):

  real_user_id = user_token.get("uid")

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Attempt to insert the like.
    cursor.execute(
      """
      INSERT INTO Likes (user_id, tweet_id)
      VALUES (%s, %s);
      """,
      (real_user_id, tweet_id)
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

@router.delete("/api/v1/tweets/{tweet_id}", status_code=204)
def delete_tweet(tweet_id: int, user_token: dict = Depends(verify_user)):

  real_user_id = user_token.get("uid")

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Require BOTH the tweet ID & the author's ID to match
    cursor.execute(
      """
      DELETE FROM Tweets
      WHERE tweet_id = %s AND user_id = %s;
      """,
      (tweet_id, real_user_id)
    )

    #If no rows were updated, the tweet couldn't be found
    if cursor.rowcount == 0:
      conn.rollback()
      raise HTTPException(status_code=404, detail=f"Tweet not found, or lacking permissions to delete")
    
    conn.commit()
    return
  
  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.delete("/api/v1/tweets/{tweet_id}/like", status_code=204)
def unlike_tweet(tweet_id: int, user_token: dict = Depends(verify_user)):

  real_user_id = user_token.get("uid")

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    cursor.execute(
      """
      DELETE FROM Likes
      WHERE tweet_id = %s AND user_id = %s;
      """,
      (tweet_id, real_user_id)
    )
    conn.commit()
    return
  
  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()