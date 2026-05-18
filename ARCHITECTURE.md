# System Architecture

This document outlines the architectural decisions and data flow for the Twitter Clone API.

## Design Philosophy
The primary goal of this architecture was to build a secure, decoupled microservice that could scale independently of the frontend UI. I prioritized speed of development and type safety by utilizing FastAPI, while ensuring high availability and ero-maintenance database operations via Neon's serverless Postgres.

## 1. The "Two Sources of Truth" Auth Bridge
**The Problem:** The frontend handles user creation directly through Google Firebase for security and speed. However, the relational database requires a user record to enforce Foreign Key constraints on Tweets and Follows.
**The Solution:** The API acts as a secure bridge.
1. The frontend authenticates with Firebase and receives a JWT.
2. The frontend sends a `POST /api/v1/users` request containing the JWT.
3. The API utilizes a custom FastAPI Dependency (`verify_user`) as a middleware "bouncer." It uses the `firebase-admin` SDK to cryptographically veerify the JWT against Google's public keys.
4. Once Verified, the API extracts the Firebase `uid` and creates a mirror record in the Neon database.

This ensures the Postgres database never stores passwords, but maintains strict relational integrity for user-generated content.

## 2. Serverless Database Architecture (Neon)
I opted for Neon over a traditional provisioned RDS instance. By decoupling computing from storage, Neon allows the database to instantly scale to zero during idle development times and spin up dynamically under load.
* **Connection Hanlding:** The API uses `psycopg2` for raw SQL execution.
* **Security:** All queries utilize parameterized inputs (`%s`) to strictly prevent SQL injection vulnerabilities.

## 3. Infrastructure & CI/CD
* **Hosting:** The API is containerized and deployed to Google Cloud Run.
* **CI/CD Pipeline:** A GitHub Action is configured to trigger on every push to the `main` branch. The action authenticates with GCP using Workload Identity Federation, buils the Docker image, pushes it to Google Artifact Registry, and deploys the new revision to Cloud Run with zero downtime.
* **Credentials:** In production, Cloud Run utilizes Application Default Credentials (ADC) to implicitly authenticate with Firebase without exposing raw JSON key fiels in the container.