# 🦘 Aussie EcoLens

A multi-cloud, serverless wildlife observation platform built for automated species detection and tagging. Users upload images or video of Australian wildlife, and the system uses machine learning to analyze, tag, and securely store the media.

Built for **FIT5225 – Cloud Computing, Monash University**.

## Overview

Aussie EcoLens combines a modern React front end with a serverless AWS backend and a GCP-hosted ML classifier, demonstrating a full multi-cloud architecture: upload → store → classify → query.

## Features

- Automated species detection & tagging via a GCP Cloud Function ML model
- Secure upload/query/delete through a serverless REST API
- AWS Cognito authentication
- Client-side image compression before upload
- Automatic thumbnail generation and notifications
- Responsive, glassmorphic web UI

## Architecture

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite, CSS Modules |
| API | AWS API Gateway + 6 AWS Lambda functions (Python) |
| Storage | AWS S3 (media), DynamoDB (metadata) |
| Auth | AWS Cognito |
| ML Classification | GCP Cloud Function |

**Lambda functions:** Upload · Query · Delete · Tagging · Notifications · Thumbnail Generation

## Project Structure

```
Aussie_EcoLens_FIT5225/
├── frontend/      # React + Vite + TypeScript UI
├── backend/       # AWS Lambda functions (Python)
├── gcp/           # GCP Cloud Function (ML species classifier)
├── test_images/   # Sample wildlife images/video for testing
└── .gitignore
```

## Getting Started

### Prerequisites

- Node.js v16+
- AWS CLI configured with valid credentials
- Python 3.9+ (for local backend testing)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open the URL shown in your terminal (typically `http://localhost:5173`).

### Backend

```bash
pip install -r backend/requirements.txt
```

Deploy each function in `backend/` to AWS Lambda, and set the following environment variables in the AWS Console:

| Variable | Purpose |
|---|---|
| `BUCKET_NAME` | S3 bucket for media storage |
| `DYNAMODB_TABLE` | DynamoDB table for metadata |
| `GCP_FUNCTION_URL` | Endpoint of the GCP ML classification function |

## Tech Stack

**Frontend:** React · TypeScript · Vite · CSS Modules · Lucide React
**Backend / Cloud:** AWS Lambda (Python) · API Gateway · S3 · DynamoDB · Cognito
**Machine Learning:** Google Cloud Platform (GCP) Cloud Functions

## Author

**Sri Vishnu Ram Aethu Venkatesan** — [LinkedIn](https://www.linkedin.com/in/sri-vishnu-ram-aethu-venkatesan-3028a532a)
