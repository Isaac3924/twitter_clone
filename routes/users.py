from fastapi import APIRouter , HTTPException
from pydantic import BaseModel
from database import get_db_connection
import psycopg2

#Create a router for all user-related endpoints
router = APIRouter()

#Define the data expected from the user
class UserCreate(BaseModel):
  user_id: str #This will come from Firebase
  screen_name: str
  name: str

class UserUpdate(BaseModel):
  bio: str

class UnfollowCreate(BaseModel):
  follower_id: str

@router.post("/api/v1/users", status_code=201)
def create_user(user: UserCreate):
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
      (user.user_id, user.screen_name, user.name)
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

@router.get("/api/v1/users/{user_id}", status_code=200)
def get_user(user_id: str):
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #Fetch the specific tweet using the ID from the URL
    cursor.execute(
      """
      SELECT user_id, screen_name, name, bio, created_at
      FROM Users
      WHERE user_id = %s;
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
      "created_at": user[4]
    }

  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

#Pydantic model for the person initiating the follow
class FollowCreate(BaseModel):
  follower_id: str

@router.post("/api/v1/users/{target_user_id}/follow", status_code=201)
def follow_user(target_user_id: str, follow_data: FollowCreate):
  #1. Logic Check: Prevent self-following
  if target_user_id == follow_data.follower_id:
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
      (follow_data.follower_id, target_user_id)
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
def get_user_feed(user_id: str):
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #JOIN query
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
      WHERE t.user_id = %s -- 1. Get the user's own tweets
      OR t.user_id IN ( -- 2. OR get tweets from people they follow
        SELECT followee_id
        FROM Follows
        WHERE follower_id = %s
      )
      ORDER BY t.created_at DESC -- 3. Sort chronologically (newest first)
      LIMIT 50; -- 4. Limit the amount of tweets to ensure a ludicrous amount doesn't crash the server
      """,
      (user_id, user_id) #ID is passed twice to satisfy both condition in WHERE clause
    )

    #fetchall is used here since we expect multiple rows back
    raw_tweets = cursor.fetchall()

    #Map list of db tuples into a clean JSON array
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

@router.patch("/api/v1/users/{user_id}", status_code=200)
def update_user_bio(user_id: str, update_data: UserUpdate):
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    cursor.execute(
      """
      UPDATE Users
      SET bio = %s
      WHERE user_id = %s;
      """,
      (update_data.bio, user_id)
    )

    #If no rows were updated, the user doesn't exist
    if cursor.rowcount == 0:
      raise HTTPException(status_code=404, detail=f"User not found")
    
    conn.commit()
    return {"message": "Profile updated successfully"}
  
  except Exception as e:
    conn.rollback()
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.delete("/api/v1/users/{target_user_id}/follow", status_code=204)
def unfollow_user(target_user_id: str, unfollow_data: UnfollowCreate):  
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    cursor.execute(
      """
      DELETE FROM Follows
      WHERE follower_id = %s AND followee_id = %s;
      """,
      (unfollow_data.follower_id, target_user_id)
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