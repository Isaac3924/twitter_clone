import os
import uuid
from google.cloud import storage
from fastapi import UploadFile, HTTPException

#Initialize the GCS client
#It will automatically use your local GCP credentials or the Cloud Run service account
storage_client = storage.Client()
BUCKET_NAME = os.getenv("MEDIA_BUCKET_NAME")

# --- SECURITY LIMITS ---
MAX_FILE_SIZE = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp", "video/mp4"]

def upload_file_to_gcs(file: UploadFile) -> str:
  """
  Uploads a file to GCS and returns the public URL.
  """
  if not BUCKET_NAME:
    raise HTTPException(status_code=500, detail="Server misconfiguration: MEDIA_BUCKET_NAME is missing.")
  
  #Validate File Type
  if file.content_type not in ALLOWED_CONTENT_TYPES:
    raise HTTPException(status_code=413, detail="File is too large. Maximum allowed size is 5MB.")
  
  #Validate File Size
  file.file.seek(0, 2) #Move to the end of the file
  file_size = file.file.tell() #Get the byte count
  file.file.seek(0) #Reset the cursor back to the beginning for the upload

  if file_size > MAX_FILE_SIZE:
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}. Please upload an image or MP4 video.")
  
  try:
    bucket = storage_client.bucket(BUCKET_NAME)

    #Generate a secure, unique filename to prevent users from overwriting each other's files
    file_extension = file.filename.split(".")[-1]
    unique_filename = f"{uuid.uuid4()}.{file_extension}"

    #Create a blob in the bucket
    blob = bucket.blob(unique_filename)

    #Upload the file from the memory buffer
    blob.upload_from_file(file.file, content_type=file.content_type)

    #Return the public URL so we can see it in the Neon db
    return blob.public_url
  
  except Exception as e:
    print(f"GCS Upload Error: {e}")
    raise HTTPException(status_code=500, detail="Failed to upload media to cloud storage.")