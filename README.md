# Aussie EcoLens 🦘🌿

**Aussie EcoLens** is a full-stack Wildlife Observation Platform built for automated species detection and tagging. Users can upload images or videos of Australian wildlife, and the system uses machine learning to automatically analyze, tag, and securely store the media.

## 📂 Project Structure

This repository is organized into distinct components:

- **`frontend/`**: The user interface, built with React, Vite, and TypeScript. Features a premium glassmorphic UI, responsive layouts, client-side image compression, and AWS Cognito authentication.
- **`backend/`**: Contains the 6 essential AWS Lambda functions that power the serverless backend API (Upload, Query, Delete, Tagging, Notifications, and Thumbnail Generation).
- **`test_images/`**: A curated set of sample images (Koalas, Kangaroos, etc.) used for testing the ML detection capabilities.
- **`sample_wildlife_video.mp4`**: A test video file for verifying multimedia upload processing.

## 🚀 Getting Started

### Prerequisites
- Node.js (v16+)
- AWS CLI configured with your credentials
- Python 3.9+ (for backend local testing)

### Running the Frontend
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
4. Open your browser to the URL provided (usually `http://localhost:5173`).

### Backend Deployment
The backend consists of AWS Lambda functions written in Python. They integrate with AWS S3 for media storage, DynamoDB for metadata, and a GCP Cloud Function for the ML classification model.
1. Install requirements: `pip install -r backend/requirements.txt`
2. Deploy the functions in the `backend/` folder directly to AWS Lambda. Ensure the respective environment variables (`BUCKET_NAME`, `DYNAMODB_TABLE`, `GCP_FUNCTION_URL`) are set in your AWS Console.

## 🛠️ Tech Stack
- **Frontend**: React, TypeScript, Vite, CSS Modules (Custom Premium Styling), Lucide React
- **Backend / Cloud**: AWS Lambda (Python), API Gateway, S3, DynamoDB, AWS Cognito
- **Machine Learning**: Google Cloud Platform (GCP) Cloud Functions

## 📝 License
Created for FIT5225 - Monash University.
