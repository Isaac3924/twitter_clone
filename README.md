# Twitter Clone API 🐦

A high-performance, containerized REST API built to power a modern social media platform. This serves as the backend service for the [Twitter Clone UI](https://github.com/Isaac3924/twitter-clone-ui), handling user authentication bridging, tweet management, and personalized feed generation.

## 🛠 Tech Stack
* **Framework:** Python/FastAPI
* **Database:** PostgreSQL (Hosted on Neon serverless)
* **Authentication:** Firebase Auth (JWT Bearer Token verification)
* **Deployment:** Google Cloud Run (Fully managed serverless container)
* **CI/CD:** GitHub Actions

## 🚀 Local Development Setup
To run this backend locally, you will need Python 3.9+ and a Neon Postgres connection string.

### 1. Clone the repository
```bash
git clone https://github.com/Isaac3924/twitter_clone.git
cd twitter_clone
```

### 2. Set up the virtual environment
```bash
python3 -m venv venv
source venv/bin/activate # On Windows use `venv\Scripts\activate`
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Variables
Create a `.env` file in the root directory and add your Neon database connection string:
```env
DATABASE_URL="postgresql://[user]:[password]@[neon_hostname]/[dbname]?sslmode=require"
```

*(Note: If testing Firebase Auth Locally, you will also need to generate a  `firebase-credentials.json` service account key from your Firebase Console and place it in the root directory).*

### 5. Run the server
```bash
uvicorn main:app --reload
```
The API will be available at `http://127.0.0.1:8000`. You can view the interactive Swagger documentation by navigating to `http://127.0.0.1:8000/docs`.

## 🐳 Docker Setup (Coming Soon)
A `Dockerfile` is being implemented to standardize local development and testing environments alongside the production Cloud Run containers.

## ✨ Key Technical Achievements
* **Relational Data Modeling:** Implemented a many-to-many Follows table to generate personalized, chronological user feeds.
* **Optimized Queries:** Utilized SQL subqueries and PostgreSQL ```RETURNING``` clauses to bundle user profile data and follower statistics into highly efficient, single-trip API responses.

## 🗺️ Future Roadmap
* **V1.1 - Interaction Layer:** Implement `POST` and `DELETE` endpoints to support scalable Tweet Liking and Retweeting functionality.
* **V2.0 - Media Support:** Integrate Google Cloud Storage buckets to hqandle secure, multipart form data uploads for images, GIFs, and videos.
* **V3.0 - AI Integration:** Leverage the Gemini/Vertex AI API to automatically generate accessible alt-text for uploaded media and provide intelligent feed summaries.