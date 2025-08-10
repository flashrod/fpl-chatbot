# FPL AI Assistant ⚽️🤖

FPL AI Assistant is a full-stack web application designed to give Fantasy Premier League (FPL) managers a competitive edge. It combines live FPL data with advanced player statistics, offering insights and analysis through an intelligent AI-powered chatbot.

## ✨ Features

- **AI Chatbot**: Get instant, data-driven advice on player transfers, captaincy choices, team strategy, and more.
- **Automated Draft Generation**: Ask the bot to build a full, 15-man squad optimized for value and performance.
- **Fixture Difficulty Analysis**: A dedicated page to visualize team fixture difficulty over the next five gameweeks.
- **AI Chip Strategy**: Get recommendations on the most opportune moments to use your Bench Boost and Triple Captain chips.
- **Live Data Integration**: The backend automatically fetches and processes the latest data from the official FPL API and FBref for up-to-date analysis.

## 🛠️ Tech Stack

- **Frontend**: React, Vite, Tailwind CSS, Framer Motion
- **Backend**: Python, FastAPI
- **AI**: Google Gemini
- **Data**: Official FPL API, FBref (via web scraping)

## 🚀 Getting Started

### Prerequisites

- Python 3.10+ and Node.js 18+
- A Google Gemini API Key.

### Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/flashrod/fpl-chatbot.git](https://github.com/flashrod/fpl-chatbot.git)
    cd fpl-chatbot
    ```

2.  **Setup the Backend:**
    - Navigate to the backend directory: `cd backend`
    - Create a virtual environment: `python -m venv venv`
    - Activate it: `source venv/bin/activate` (macOS/Linux) or `venv\Scripts\activate` (Windows)
    - Install dependencies: `pip install -r requirements.txt`
    - Create a `.env` file and add your Gemini API key:
      ```
      GEMINI_API_KEY="YOUR_API_KEY_HERE"
      ```
    - Run the data pipeline to get the initial FBref stats: `python data_pipeline.py`

3.  **Setup the Frontend:**
    - Navigate to the frontend directory: `cd ../frontend`
    - Install dependencies: `npm install`

### Running the Application

1.  **Start the Backend Server:**
    - In the `backend` directory, run:
      ```bash
      uvicorn main:app --reload
      ```
    - The backend will be running at `http://127.0.0.1:8000`.

2.  **Start the Frontend Development Server:**
    - In the `frontend` directory, run:
      ```bash
      npm run dev
      ```
    - The frontend will be running at `http://localhost:5173`.

---

