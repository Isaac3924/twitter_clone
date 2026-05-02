Authentication & Users:
  POST /api/v1/users (Handled mostly by Firebase, but registers the user in my PostgreSQL DB)
  GET /api/v1/users/{user_id} (Retrieves profile and bio)
  PATCH /api/v1/users/{user_id} (Update/Change bio, screen name, etc.)
  DELETE /api/v1/users/{user_id} (Delete user)

Tweets
  POST /api/v1/tweets (Creates a new post)
  GET /api/v1/tweets/{tweet_id} (View singular post)
  DELETE  /api/v1/tweets/{tweet_id} (Delete post)
  GET  /api/v1/feed (Complex Query: fetch tweets from people the user follows, sorted by created_at descending)
  GET /api/v1/users/{user_id}/tweets (Retrieves tweets authored by a specific user)
  GET /api/v1/tweets/{tweet_id}/Replies (Fetch all tweets where the parent_tweet_id matches the tweet_id)
  POST /api/v1/media/upload (This will handle picture uploads)
  

Interactions
  POST  /api/v1/tweets/{tweet_id}/like (Adds a row to the Like table)
  DELETE  /api/v1/tweets/{tweet_id}/like (Removes the specified row from the Like table)
  POST  /api/v1/users/{target_user_id}/follow (Adds a row to the Follows table)
  DELETE  /api/v1/users/{target_user_id}/follow (Removes the specified row from the Follows table)
  GET  /api/v1/users/{user_id}/followers (Retrieve the list of users following a user)
  GET  /api/v1/users/{user_id}/following (Retrieve the list of users that a user is following)
  GET /api/v1/users/{user_id}/likes (Retrieves the liked tweets of a user)
  GET /api/v1/search/users?q={query} (Search for specific users)
  GET /api/v1/search/tweets?q={query} (Search for specific tweets)