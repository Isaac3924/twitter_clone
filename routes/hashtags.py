from fastapi import APIRouter , HTTPException
from database import get_db_connection

#Create a router for all hashtag-related endpoints
router = APIRouter()

@router.get("/api/v1/hashtags/suggest", status_code=200)
def suggest_hashtags(q: str):
  """Provides autocomplete suggestions for hashtags"""
  #Strip # if it's included
  clean_q = q.replace("#", "").lower()

  if len(clean_q) < 1:
    return {"results": []}
  
  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    #The % acts as a wildcard at the END of the word.
    #This matches anything that starts with the user's query.
    searh_pattern = f"{clean_q}%"

    cursor.execute(
      """
      SELECT tag_text
      FROM hashtags
      WHERE tag_text ILIKE %s
      LIMIT 5;
      """,
      (searh_pattern,)
    )

    raw_tags = cursor.fetchall()
    #Format the response so the frontend knows theses are tags, not users
    results = [{"type": "hashtag", "text": tag[0]} for tag in raw_tags]

    return {"results": results}
  
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()

@router.get("/api/v1/hashtags/trending", status_code=200)
def get_trending_hashtags():
  """Fetches the trending/most popular hashtags globally."""

  conn = get_db_connection()
  cursor = conn.cursor()

  try:
    cursor.execute(
      """
      SELECT h.tag_text as name, COUNT(th.tag_id) as tag_count
      FROM hashtags h
      JOIN tweet_hashtags th ON h.tag_id = th.tag_id
      GROUP BY h.tag_id, name
      ORDER BY tag_count DESC, name ASC
      LIMIT 5;
      """
    )

    raw_hashtags = cursor.fetchall()
    top_hashtags = []

    for hashtag in raw_hashtags:
      top_hashtags.append({
        "name": hashtag[0],
        "tag_count": hashtag[1]
      })

    return {"top_hashtags": top_hashtags}
  
  except Exception as e:
    raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
  
  finally:
    cursor.close()
    conn.close()