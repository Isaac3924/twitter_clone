from fastapi import APIRouter , HTTPException, Depends
from auth import verify_user, get_optional_user
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

@router.post("/api/v1/tweets/{tweet_id}/retweet", status_code=201)
def retweet(tweet_id: int, user_token: dict = Depends(verify_user)):
  real_user_id = user_token.get("uid")

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Check if the tweet exists
    cursor.execute("SELECT tweet_id FROM Tweets WHERE tweet_id = %s;", (tweet_id,))
    if not cursor.fetchone():
      raise HTTPException(status_code=404, detail="Original Tweet not found")
    
    #Check if the user already retweeted this specifc tweet
    cursor.execute(
      """
      SELECT tweet_id FROM Tweets
      WHERE user_id = %s AND parent_tweet_id = %s AND is_retweet = TRUE;
      """,
      (real_user_id, tweet_id)
    )
    if cursor.fetchone():
      raise HTTPException(status_code=400, detail="You already retweeted this tweet")
    
    #Insert the Retweet
    #We pass NULL for the body, and TRUE for is_retweet
    cursor.execute(
      """
      INSERT INTO Tweets (user_id, body, parent_tweet_id, is_retweet)
      VALUES (%s, NULL, %s, TRUE)
      RETURNING tweet_id;
      """,
      (real_user_id, tweet_id)
    )

    new_retweet_id = cursor.fetchone()[0]
    conn.commit()

    return {"message": "Retweet successful", "tweet_id": new_retweet_id}
  
  except HTTPException:
    #Re-raise HTTP exceptions so they don't get caught by the generic Exception block
    conn.rollback()
    raise
  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.delete("/api/v1/tweets/{tweet_id}/retweet", status_code=204)
def un_retweet(tweet_id: int, user_token: dict = Depends(verify_user)):
  real_user_id = user_token.get("uid")

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Find and delete the specific retweet row
    cursor.execute(
      """
      DELETE FROM Tweets
      WHERE user_id = %s AND parent_tweet_id = %s AND is_retweet = TRUE;
      """,
      (real_user_id, tweet_id)
    )

    conn.commit()
    return

  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.get("/api/v1/tweets/explore", status_code=200)
def get_explore_feed(user_data: dict = Depends(get_optional_user)):
  """Fetches the 50 most recent tweets globally."""
  real_user_id = user_data.get("uid") if user_data else None

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    cursor.execute(
      """
      SELECT 
        --1. Main ID for React keys, and the interaction ID for liking/retweeting
        t.tweet_id AS feed_id,
        COALESCE(orig_t.tweet_id, t.tweet_id) AS interactable_tweet_id,

        -- 2. Grab the body and author from the original tweet IF it's a retweet
        COALESCE(orig_t.body, t.body) AS body,
        t.created_at,
        COALESCE(orig_u.user_id, u.user_id) AS author_id,
        COALESCE(orig_u.screen_name, u.screen_name) AS author_screen_name,

        -- 3. Route the like counting to the original source material
        COALESCE(lc.like_count, 0) AS like_count,
        EXISTS (
          SELECT 1 FROM Likes l
          WHERE l.tweet_id = COALESCE(orig_t.tweet_id, t.tweet_id) AND l.user_id = %s
        ) AS user_has_liked,

        -- 4. Retweet metadata so React can show the "User Retweeted" label
        t.is_retweet,
        u.screen_name AS retweeter_name

      FROM Tweets t
      JOIN Users u ON t.user_id = u.user_id

      -- THE SELF JOIN: Link the parent tweet back to the Tweets and Users tables
      LEFT JOIN Tweets orig_t ON t.parent_tweet_id = orig_t.tweet_id
      LEFT JOIN Users orig_u ON orig_t.user_id = orig_u.user_id

      LEFT JOIN (
        SELECT tweet_id, COUNT(*) as like_count
        FROM Likes
        GROUP BY tweet_id
      ) lc ON COALESCE(orig_t.tweet_id, t.tweet_id) = lc.tweet_id

      ORDER BY t.created_at DESC
      LIMIT 50;
      """,
      (real_user_id,)
    )

    raw_tweets = cursor.fetchall()
    feed = []

    for tweet in raw_tweets:
      feed.append({
        "feed_id": tweet[0],              #Used purely for React's key={}
        "tweet_id": tweet[1],             #Used for hitting our Like/Retweet endpoints
        "body": tweet[2],
        "created_at": tweet[3],
        "author_id": tweet[4],
        "author_screen_name": tweet[5],
        "like_count": tweet[6],
        "user_has_liked": tweet[7],
        "is_retweet": tweet[8],
        "retweeter_name": tweet[9]
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