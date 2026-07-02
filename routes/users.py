from fastapi import APIRouter , HTTPException, Depends, File, UploadFile
from pydantic import BaseModel
from database import get_db_connection
import psycopg2
from auth import verify_user, get_optional_user
from utils.storage import upload_file_to_gcs

#Create a router for all user-related endpoints
router = APIRouter()

#Define the data expected from the user
class UserCreate(BaseModel):
  screen_name: str
  name: str

class UserUpdate(BaseModel):
  bio: str

@router.post("/api/v1/users", status_code=201)
def create_user(user: UserCreate, user_token: dict = Depends(verify_user)):
  real_user_id = user_token.get("uid")

  #1. Open the DB connection
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #2. Execute the raw SQL.
    #We use %s to safely inject the variables to prevent SQL injection hacks.
    cursor.execute(
      """
      INSERT INTO Users (user_id, screen_name, name)
      VALUES (%s, %s, %s)
      RETURNING user_id;
      """,
      (real_user_id, user.screen_name, user.name)
    )

    #3. Fetch the ID of the newly created tweet
    new_user_id = cursor.fetchone()[0]

    #4. Commit the save to the db
    conn.commit()

    return {"message": "User created successfully", "user_id": new_user_id}
  
  except Exception as e:
    #If anything goes wrong, undo the db transaction
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    #5. Always close the connection when finished

    cursor.close()
    conn.close()

@router.get("/api/v1/users/search/query", status_code=200)
def search_users(q: str):
  """Searches for users by screen_name or name."""

  #Requires att least 2 characters to prevent massive database dumps
  if len(q) < 2:
    return {"results": []}
  
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Use ILIKE for case-snesitive partial matching.
    #Wrap the query in % to match the text anywhere in the string.
    search_pattern = f"%{q}%"

    cursor.execute(
      """
      SELECT user_id, screen_name, name, bio, profile_img_url
      FROM users
      WHERE screen_name ILIKE %s OR name ILIKE %s
      LIMIT 20;
      """,
      (search_pattern, search_pattern)
    )

    raw_users = cursor.fetchall()

    results = []
    for user in raw_users:
      results.append({
        "user_id": user[0],
        "screen_name": user[1],
        "name": user[2],
        "bio": user[3],
        "profile_img_url": user[4]
      })

    return {"results": results}
    
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.get("/api/v1/users/{user_id}", status_code=200)
def get_user(user_id: str):
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Use 
    cursor.execute(
      """
      SELECT 
        u.user_id, 
        u.screen_name, 
        u.name, 
        u.bio, 
        u.created_at,
        (SELECT COUNT(*) FROM Follows WHERE followee_id = u.user_id) AS followers_count,
        (SELECT COUNT(*) FROM Follows WHERE follower_id = u.user_id) AS following_count,
        u.profile_img_url
      FROM Users u
      WHERE u.user_id = %s;
      """,
      (user_id,) #Pass the ID securely
    )

    user = cursor.fetchone()

    #If the query returns nothing, return a 404 error
    if not user:
      raise HTTPException(status_code=404, detail="User not found")
    
    #Map the returned db tuple back into a readable JSON dict
    return {
      "user_id": user[0],
      "screen_name": user[1],
      "name": user[2],
      "bio": user[3],
      "created_at": user[4], 
      "followers_count": user[5],
      "following_count": user[6],
      "profile_img_url": user[7]

    }

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.post("/api/v1/users/{target_user_id}/follow", status_code=201)
def follow_user(target_user_id: str, user_token: dict = Depends(verify_user)):
  real_user_id = user_token.get("uid")
  
  #1. Logic Check: Prevent self-following
  if target_user_id == real_user_id:
    raise HTTPException(status_code=400, detail="You cannot follow yourself")
  
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #2. Insert the relationship
    cursor.execute(
      """
      INSERT INTO Follows (follower_id, followee_id)
      VALUES (%s, %s);
      """,
      (real_user_id, target_user_id)
    )
    conn.commit()
    return {"message": f"Successfully followed user {target_user_id}"}
  
  except psycopg2.errors.UniqueViolation:
    #Caught if they click follow twice
    conn.rollback()
    raise HTTPException(status_code=400, detail="You are already following this user")
  
  except psycopg2.errors.ForeignKeyViolation:
    #Catches if the follower or the target doesn't exist
    conn.rollback()
    raise HTTPException(status_code=404, detail="One or both users do not exist")
  
  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.get("/api/v1/users/{user_id}/feed", status_code=200)
def get_user_feed(user_id: str, user_token: dict = Depends(verify_user)):
  real_user_id = user_token.get("uid")

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #JOIN query
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
        t.is_retweet,
        u.screen_name AS retweeter_name
      FROM Tweets t
      JOIN Users u ON t.user_id = u.user_id
      LEFT JOIN Tweets orig_t ON t.parent_tweet_id = orig_t.tweet_id
      LEFT JOIN Users orig_u ON orig_t.user_id = orig_u.user_id
      LEFT JOIN (
        SELECT tweet_id, COUNT(*) as like_count
        FROM Likes
        GROUP BY tweet_id
      ) lc ON COALESCE(orig_t.tweet_id, t.tweet_id) = lc.tweet_id
      WHERE t.user_id = %s -- 1. Get the user's own tweets
      OR t.user_id IN ( -- 2. OR get tweets from people they follow
        SELECT followee_id
        FROM Follows
        WHERE follower_id = %s
      )
      ORDER BY t.created_at DESC -- 3. Sort chronologically (newest first)
      LIMIT 50; -- 4. Limit the amount of tweets to ensure a ludicrous amount doesn't crash the server
      """,
      (real_user_id, real_user_id, real_user_id) #ID is passed twice to satisfy both condition in WHERE clause
    )

    #fetchall is used here since we expect multiple rows back
    raw_tweets = cursor.fetchall()

    #Map list of db tuples into a clean JSON array
    feed = []
    for tweet in raw_tweets:
      feed.append({
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

    return {"feed": feed}
    
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.patch("/api/v1/users/profile-image", status_code=200)
def update_profile_image(
  file: UploadFile = File(...),
  user_token: dict = Depends(verify_user)
):
  real_user_id = user_token.get("uid")

  #Security Check: 10 MB File Limit
  MAX_SIZE =  10 * 1024 * 1024
  file.file.seek(0, 2)
  file_size = file.file.tell()
  file.file.seek(0)

  if file_size > MAX_SIZE:
    raise HTTPException(status_code=413, detail="File too large. MAximum size is 10MB.")
  
  #Upload to GCS
  try:
    new_image_url = upload_file_to_gcs(file)
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Failed to upload image to cloud storage: {str(e)}")
  
  #Save the new URL to the Neon Database
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    cursor.execute(
      """
      UPDATE Users
      SET profile_img_url = %s
      WHERE user_id = %s
      RETURNING profile_img_url;
      """,
      (new_image_url, real_user_id)
    )

    updated_row = cursor.fetchone()

    if not updated_row:
      raise HTTPException(status_code=404, detail="User not found")
    
    conn.commit()

    return {
      "message": "Profile image updated successfully",
      "profile_img_url": updated_row[0]
    }
  
  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.patch("/api/v1/users/{user_id}", status_code=200)
def update_user_bio(user_id: str, update_data: UserUpdate, user_token: dict = Depends(verify_user)):
  real_user_id = user_token.get("uid")

  #Security check: You can only edit your own bio
  if user_id != real_user_id:
    raise HTTPException(status_code=403, detail="You do not have permission to edit this profile")

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Use RETURNING to grab the newly saved bio to send to React
    cursor.execute(
      """
      UPDATE Users
      SET bio = %s
      WHERE user_id = %s
      RETURNING bio;
      """,
      (update_data.bio, real_user_id)
    )

    updated_row = cursor.fetchone()

    #If no rows were updated, the user doesn't exist
    if not updated_row:
      raise HTTPException(status_code=404, detail=f"User not found")
    
    conn.commit()
    return {"message": "Profile updated successfully", "bio": updated_row[0]}
  
  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.delete("/api/v1/users/{target_user_id}/follow", status_code=204)
def unfollow_user(target_user_id: str, user_token: dict = Depends(verify_user)):
  real_user_id = user_token.get("uid")

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    cursor.execute(
      """
      DELETE FROM Follows
      WHERE follower_id = %s AND followee_id = %s;
      """,
      (real_user_id, target_user_id)
    )
    conn.commit()

    #A 204 status code (No Content) usually doesn't return a JSON body,
    #but the client will know it succeeded.
    return
  
  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.get("/api/v1/users/{target_user_id}/tweets", status_code=200)
def get_user_profile_tweets(target_user_id: str, user_data: dict = Depends(get_optional_user)):
  """Fetches the 50 most recent tweets for a single specific user"""

  #If Guest, real_user_id becomes None. If Authenticated, it gets the string ID.
  real_user_id = user_data.get("uid") if user_data else None

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
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
        t.is_retweet,
        u.screen_name AS retweeter_name
      FROM Tweets t
      JOIN Users u ON t.user_id = u.user_id
      LEFT JOIN Tweets orig_t ON t.parent_tweet_id = orig_t.tweet_id
      LEFT JOIN Users orig_u ON orig_t.user_id = orig_u.user_id
      LEFT JOIN (
        SELECT tweet_id, COUNT(*) as like_count
        FROM Likes
        GROUP BY tweet_id
      ) lc ON COALESCE(orig_t.tweet_id, t.tweet_id) = lc.tweet_id
      WHERE t.user_id = %s
      ORDER BY t.created_at DESC
      LIMIT 50;
      """,
      (real_user_id, target_user_id,)
    )

    raw_tweets = cursor.fetchall()

    tweets = []
    for tweet in raw_tweets:
      tweets.append({
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

    return {"tweets": tweets}
    
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  finally:
    cursor.close()
    conn.close()

@router.get("/api/v1/users/{target_user_id}/is_following", status_code=200)
def get_user_is_following(target_user_id: str, user_data: dict = Depends(get_optional_user)):
  #1. Fast-fail for Guests
  if not user_data:
    return {"following": False}
  
  #2. Proceed normally for logged-in users
  real_user_id = user_data.get("uid")
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Look for following relationship using the two ids.
    #We will just have it return a '1' as there is no need for actual data to be returned
    cursor.execute(
      """
      SELECT 1
      FROM Follows
      WHERE follower_id = %s AND followee_id = %s;
      """,
      (real_user_id, target_user_id)
    )

    #If the row exists, result will be (1,). If not, result will be None.
    result = cursor.fetchone()

    #This evaluates to True if result has data, and False if result is None
    is_following = result is not None

    return {"following": is_following}
  
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()