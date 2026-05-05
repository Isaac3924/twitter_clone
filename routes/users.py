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
    return {f"message": "Successfully followed user {target_user_id}"}
  
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