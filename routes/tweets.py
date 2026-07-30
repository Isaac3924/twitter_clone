from fastapi import APIRouter , HTTPException, Depends, Form, File, UploadFile
from typing import Optional
from auth import verify_user, get_optional_user
from database import get_db_connection
import psycopg2 
from utils.storage import upload_file_to_gcs
from pydantic import BaseModel
import re

#Create a router for all tweet-related endpoints
router = APIRouter()

#Regex hashtag helper function
def extract_and_save_hashtags(cursor, tweet_id: int, body: str):
  """
  Parses a tweet body for hashtags, inserts unique tags into the Hashtags table,
  and maps them to the tweet in the Tweet_hashtags junction table.
  """
  if not body:
    return
  
  #Find all words starting with #.
  #.lower() ensures we do not receive duplicates.
  #The regex r"#(\w+)" grabs just the word without the '#' symbol.
  tags = re.findall(r"#(\w+)", body.lower())

  #Convert to a 'set' to instantly remove any duplicates within the same tweet
  #(e.g., if a user types "#coding #coding")
  unique_tags = set(tags)

  for tag in unique_tags:
    #Insert the tag. If it already exists, Postgres normally throws an error.
    #By adding On CONFLICT DO UPDATE, it forces Postgres to safely ignore the conflict
    #but still return the tag_id to use
    cursor.execute(
      """
      INSERT INTO hashtags (tag_text)
      VALUES (%s)
      ON CONFLICT (tag_text) DO UPDATE
      SET tag_text = EXCLUDED.tag_text
      RETURNING tag_id;
      """,
      (tag,)
    )
    tag_id = cursor.fetchone()[0]

    #Insert the mapping into the Junction Table
    cursor.execute(
      """
      INSERT INTO tweet_hashtags (tweet_id, tag_id)
      VALUES(%s, %s)
      ON CONFLICT DO NOTHING;
      """,
      (tweet_id, tag_id)
    )

@router.post("/api/v1/tweets", status_code=201)
def create_tweet(body: Optional[str] = Form(None), media: Optional[UploadFile] = File(None), user_token: dict = Depends(verify_user)):
  #Extract the mathematically verified user ID from the token
  real_user_id = user_token.get("uid")

  #Require at leasst text or media to make a valid tweet
  if not body and not media:
    raise HTTPException(status_code=400, detail="Tweet must contain text or an image/video.")
  
  media_url = None
  if media:
    media_url = upload_file_to_gcs(media)

  #Open the DB connection
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Execute the raw SQL.
    #We use %s to safely inject the variables to prevent SQL injection hacks.
    cursor.execute(
      """
      INSERT INTO Tweets (user_id, body, media_url)
      VALUES (%s, %s, %s)
      RETURNING tweet_id;
      """,
      (real_user_id, body, media_url)
    )

    #Fetch the ID of the newly created tweet
    new_tweet_id = cursor.fetchone()[0]

    #Extract and save hashtags using the same cursor
    extract_and_save_hashtags(cursor, new_tweet_id, body)

    #Commit the save to the db
    conn.commit()

    return {"tweet_id": new_tweet_id, "message": "Tweet created successfully", "media_url": media_url}
  
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
def get_explore_feed(cursor: Optional[int] = None, user_data: dict = Depends(get_optional_user)):
  """Fetches the 50 most recent tweets globally using cursor-based pagination."""
  real_user_id = user_data.get("uid") if user_data else None

  conn = get_db_connection()
  db_cursor = conn.cursor()

  try:
    # 1.) Base Query setup
    query = """
      SELECT 
        -- Main ID for React keys, and the interaction ID for liking/retweeting
        t.tweet_id AS feed_id,
        COALESCE(orig_t.tweet_id, t.tweet_id) AS interactable_tweet_id,

        -- Grab the body and author from the original tweet IF it's a retweet
        COALESCE(orig_t.body, t.body) AS body,

        -- Grab the media URL, routing back to original if it's a retweet
        COALESCE(orig_t.media_url, t.media_url) AS media_url,

        t.created_at,
        COALESCE(orig_u.user_id, u.user_id) AS author_id,
        COALESCE(orig_u.screen_name, u.screen_name) AS author_screen_name,

        -- Route the like counting to the original source material
        COALESCE(lc.like_count, 0) AS like_count,
        EXISTS (
          SELECT 1 FROM Likes l
          WHERE l.tweet_id = COALESCE(orig_t.tweet_id, t.tweet_id) AND l.user_id = %s
        ) AS user_has_liked,

        -- Retweet metadata so React can show the "User Retweeted" label
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

      -- Only fetch original tweets OR explicit retweets (ignore replies)
      WHERE t.parent_tweet_id IS NULL OR t.is_retweet = TRUE

      ORDER BY t.created_at DESC
      LIMIT 50;
    """
    
    query_params = [real_user_id]

    # 2.) Dynamically inject the cursor condition if one was passed in.
    if cursor:
      query += " AND t.tweet_id < %s"
      query_params.append(cursor)

    # 3.) Order strictly by ID for determnistic pagination
    query += " ORDER BY t.tweet_id DESC LIMIT 50;"

    db_cursor.execute(query, tuple(query_params))

    raw_tweets = db_cursor.fetchall()
    feed = []

    for tweet in raw_tweets:
      feed.append({
        "feed_id": tweet[0],              #Used purely for React's key={}
        "tweet_id": tweet[1],             #Used for hitting our Like/Retweet endpoints
        "body": tweet[2],
        "media_url": tweet[3],
        "created_at": tweet[4],
        "author_id": tweet[5],
        "author_screen_name": tweet[6],
        "like_count": tweet[7],
        "user_has_liked": tweet[8],
        "is_retweet": tweet[9],
        "retweeter_name": tweet[10]
      })

      # 4.) Calculate the next cursor token. 
      # If there are exactly 50 tweets, assume thhere's another page.
      # The cursor becomes the feed_id (tweet_id) of the very last item.
      next_cursor = feed[-1]["feed_id"] if len(feed) == 50 else None
    
    return {"feed": feed, "next_cursor": next_cursor}

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    db_cursor.close()
    conn.close()

@router.get("/api/v1/tweets/search", status_code=200)
def search_tweets(q: str, user_data: dict = Depends(get_optional_user)):
  """Searches for tweets by hashtag using the optimized junction tables"""
  real_user_id = user_data.get("uid") if user_data else None
  
  #Clean the query: Remove the '#' if the user typed it, and make it lowercase
  clean_q = q.replace("#", "").lower()

  #Requires at least 2 characters to prevent massive database dumps
  if len(clean_q) < 2:
    return {"results": []}

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    search_pattern = f"%{q}%"

    #Using the same SELECT layout as the Explore Feed so React can render it easily.
    #The actual search logic will occur via the JOIN clauses at the bottom
    cursor.execute(
      """
      SELECT 
        t.tweet_id AS feed_id,
        COALESCE(orig_t.tweet_id, t.tweet_id) AS interactable_tweet_id,
        COALESCE(orig_t.body, t.body) AS body,
        COALESCE(orig_t.media_url, t.media_url) AS media_url,
        t.created_at,
        COALESCE(orig_u.user_id, u.user_id) AS author_id,
        COALESCE(orig_u.screen_name, u.screen_name) AS author_screen_name,
        COALESCE(lc.like_count, 0) AS like_count,
        EXISTS (
          SELECT 1 FROM Likes l
          WHERE l.tweet_id = COALESCE(orig_t.tweet_id, t.tweet_id) AND l.user_id = %s
        ) AS user_has_liked,

        -- Retweet metadata so React can show the "User Retweeted" label
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

      -- Optimized Search Algorithm
      -- Join the junction table
      JOIN tweet_hashtags th ON t.tweet_id = th.tweet_id
      -- Join the master hashtags table
      JOIN hashtags h ON th.tag_id = h.tag_id

      -- Instant indexed lookup
      WHERE h.tag_text = %s

      ORDER BY t.created_at DESC
      LIMIT 50;
      """,
      (real_user_id, clean_q)
    )

    raw_tweets = cursor.fetchall()
    results = []

    for tweet in raw_tweets:
      results.append({
        "feed_id": tweet[0],
        "tweet_id": tweet[1],
        "body": tweet[2],
        "media_url": tweet[3],
        "created_at": tweet[4],
        "author_id": tweet[5],
        "author_screen_name": tweet[6],
        "like_count": tweet[7],
        "user_has_liked": tweet[8],
        "is_retweet": tweet[9],
        "retweeter_name": tweet[10]
      })
    
    return {"results": results}

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.get("/api/v1/tweets/{tweet_id}", status_code=200)
def get_tweet_thread(tweet_id: int, user_data: dict = Depends(get_optional_user)):
  """Fetches a single main tweet and all of its direct replies."""
  real_user_id = user_data.get("uid") if user_data else None

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Fetch the main tweet
    cursor.execute(
      """
      SELECT 
        t.tweet_id AS feed_id,
        t.tweet_id AS interactable_tweet_id,
        t.body, 
        t.media_url, 
        t.created_at,
        u.user_id AS author_id,
        u.screen_name AS author_screen_name,
        COALESCE(lc.like_count, 0) AS like_count,
        EXISTS (
          SELECT 1 FROM Likes l
          WHERE l.tweet_id = t.tweet_id AND l.user_id = %s
        ) AS user_has_liked,
        False AS is_retweet,
        NULL AS retweeter_name
      FROM Tweets t
      JOIN Users u ON t.user_id = u.user_id
      LEFT JOIN (
        SELECT tweet_id, COUNT(*) as like_count
        FROM Likes
        GROUP BY tweet_id
      ) lc ON t.tweet_id = lc.tweet_id
      WHERE t.tweet_id = %s;
      """,
      (real_user_id, tweet_id)
    )

    raw_main = cursor.fetchone()

    #If the query returns nothing, return a 404 error
    if not raw_main:
      raise HTTPException(status_code=404, detail="Tweet not found")
    
    #Map the returned db tuple back into a readable JSON dict
    main_tweet = {
      "feed_id": raw_main[0],
      "tweet_id": raw_main[1],
      "body": raw_main[2],
      "media_url": raw_main[3],
      "created_at": raw_main[4],
      "author_id": raw_main[5],
      "author_screen_name": raw_main[6],
      "like_count": raw_main[7],
      "user_has_liked": raw_main[8],
      "is_retweet": raw_main[9],
      "retweeter_name": raw_main[10],
    }

    #Fetch the replies chronologically
    cursor.execute(
      """
      SELECT 
        t.tweet_id AS feed_id,
        t.tweet_id AS interactable_tweet_id,
        t.body, 
        t.media_url, 
        t.created_at,
        u.user_id AS author_id,
        u.screen_name AS author_screen_name,
        COALESCE(lc.like_count, 0) AS like_count,
        EXISTS (
          SELECT 1 FROM Likes l
          WHERE l.tweet_id = t.tweet_id AND l.user_id = %s
        ) AS user_has_liked,
        False AS is_retweet,
        NULL AS retweeter_name
      FROM Tweets t
      JOIN Users u ON t.user_id = u.user_id
      LEFT JOIN (
        SELECT tweet_id, COUNT(*) as like_count
        FROM Likes
        GROUP BY tweet_id
      ) lc ON t.tweet_id = lc.tweet_id
      WHERE t.parent_tweet_id = %s
        AND (t.is_retweet IS FALSE OR t.is_retweet IS NULL)
      ORDER BY t.created_at ASC;
      """,
      (real_user_id, tweet_id)
    )

    raw_replies = cursor.fetchall()

    replies = []
    for tweet in raw_replies:
      replies.append({
        "feed_id": tweet[0],
        "tweet_id": tweet[1],
        "body": tweet[2],
        "media_url": tweet[3],
        "created_at": tweet[4],
        "author_id": tweet[5],
        "author_screen_name": tweet[6],
        "like_count": tweet[7],
        "user_has_liked": tweet[8],
        "is_retweet": tweet[9],
        "retweeter_name": tweet[10],
      })

    return {"main_tweet": main_tweet, "replies": replies}

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.post("/api/v1/tweets/{tweet_id}/reply", status_code=201)
def create_reply(tweet_id: int, body: Optional[str] = Form(None), media: Optional[UploadFile] = File(None), user_token: dict = Depends(verify_user)):
  real_user_id = user_token.get("uid")

  #Require at leasst text or media to make a valid tweet
  if not body and not media:
    raise HTTPException(status_code=400, detail="Reply must contain text or an image/video.")
  
  media_url = None
  if media:
    media_url = upload_file_to_gcs(media)

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Insert the tweet nd link it to its parent tweet
    cursor.execute(
      """
      INSERT INTO Tweets (user_id, body, media_url, parent_tweet_id)
      VALUES (%s, %s, %s, %s)
      RETURNING tweet_id;
      """,
      (real_user_id, body, media_url, tweet_id)
    )
    new_tweet_id = cursor.fetchone()[0]

    #Extract and save hashtags for replies
    extract_and_save_hashtags(cursor, new_tweet_id, body)

    conn.commit()

    return {"message": "Replay posted succesfully", "media_url": media_url, "tweet_id": new_tweet_id}
  
  except Exception as e:
    conn.rollback()
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