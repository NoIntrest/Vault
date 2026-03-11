Vault is a full-stack personal finance web app you can deploy for free on Render. Track income and expenses, set monthly budgets by category, watch your spending progress in real time, and get AI-powered advice from a built-in chat advisor backed by Groq's free LLM API.
Features

Income & expense tracking with categories, notes, and date filtering
Monthly budget planner — set goals per category with sliders, track progress with colour-coded bars
Live currency conversion across 15+ currencies using real exchange rates
AI advisor chat (powered by Groq + Llama 3) that reads your actual transaction history
Secure auth with bcrypt password hashing and session management
PostgreSQL backend with a connection pool tuned for Render's free tier

Tech stack: Python · Flask · PostgreSQL · Chart.js · Groq API
Deploy: Add a PostgreSQL database in Render, set DATABASE_URL, SECRET_KEY, and optionally GROQ_API_KEY, then deploy. The schema is created automatically on first boot.

