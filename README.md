# 🚀 JobFit AI: Autonomous Lead Intelligence & Executive Outreach Engine

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic_AI-FF6F00?style=for-the-badge)](https://langchain-ai.github.io/langgraph/)
[![Redis](https://img.shields.io/badge/Redis-L2_Cache-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![SQLite](https://img.shields.io/badge/SQLite-L3_Disk-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Azure](https://img.shields.io/badge/Azure-Cloud_VM-0089D6?style=for-the-badge&logo=microsoftazure&logoColor=white)](https://azure.microsoft.com/)

An enterprise-grade, asynchronous lead intelligence and hyper-personalized cold outreach engine designed for high-conversion executive recruitment. Built with a production **LangGraph** multi-agent orchestration pipeline, a **2-Tier Caching system (Redis L2 + SQLite L3)**, **Redis Sliding Window Rate Limiting**, and **Composite Idempotency Guards**.

---

## 🏗️ System Architecture

```
                                  +-----------------------+
                                  |   Chrome Extension /  |
                                  |   Web Dashboard UI    |
                                  +-----------+-----------+
                                              |
                                              | POST /api/generate-draft
                                              v
                                  +-----------+-----------+
                                  |    FastAPI Gateway    |
                                  | (Sliding Rate Limiter)|
                                  +-----------+-----------+
                                              |
                        +---------------------+---------------------+
                        | HTTP 202 Accepted                         |
                        v                                           v
            +-----------+-----------+                   +-----------+-----------+
            |  Composite Idempotency|                   | Async Task Queue Worker   |
            |     Redis L2 RAM      |                   |   (Background Thread)     |
            +-----------+-----------+                   +-----------+-----------+
                        |                                           |
                        | Key: idempotency:draft:*                  v
                        v                               +-----------+-----------+
            +-----------+-----------+                   |   LangGraph Agentic    |
            |  SQLite L3 Disk DB    | <---------------- |   Orchestrator Engine |
            | (Audit Trail & Leads) |                   +-----------+-----------+
            +-----------------------+                               |
                                                                    v
                                                        +-----------+-----------+
                                                        | Hunter.io / Groq LLaMA3|
                                                        |  External API Tools   |
                                                        +-----------------------+
```

---

## 🔥 Key Production System Design Features

### 1. ⚡ Asynchronous Producer-Consumer Architecture (HTTP 202)
- Fast response loop (`HTTP 202 Accepted`) returns an immediate `task_id` within `< 15ms`.
- Client polls `/api/task/{task_id}` for real-time status updates without blocking browser threads or timing out HTTP connections during LLM inference.

### 2. 🛡️ 2-Tier Caching System (Redis L2 RAM + SQLite L3 Disk)
- **L2 RAM Cache (Redis 7)**: Provides sub-millisecond retrieval for hot lead queries, active task states, and session tokens.
- **L3 Disk Storage (SQLite)**: Ensures zero data loss with long-term persistence for generated executive drafts, lead histories, and application metrics.

### 3. 🔒 Composite Idempotency Guard
- Built-in Redis idempotency locks (`idempotency:draft:{company_id}:{contact_id}:{role_target}`) prevent race conditions, duplicate email generation, and API token burn under concurrent client clicks.

### 4. 🛑 Redis Atomic Sliding Window Rate Limiter
- Implements an atomic sliding window counter in Redis (capped at `10 req/min` per IP) to prevent downstream API abuse and quota exhaustion on third-party scrapers and LLM providers.

### 5. 🤖 Multi-Agent LangGraph Pitch Engine
- Contextual proof-of-work generator that formulates crisp, high-converting 5-bullet outreach pitches tailored to engineering leaders, highlighting open-source contributions (TensorFlow, Podman, pandas) and offering zero-risk trial assignments.

---

## 🛠️ Tech Stack

- **Backend Framework**: Python 3.11, FastAPI, Uvicorn
- **Agent Orchestration**: LangGraph, LangChain
- **Caching & Rate Limiting**: Redis 7 (Alpine)
- **Data Persistence**: SQLite 3, SQLAlchemy ORM
- **Third-Party APIs**: Groq (LLaMA 3.3 70B), Hunter.io, Tavily Search
- **Containerization & Cloud**: Docker, Docker Compose, Azure Virtual Machines (Ubuntu 22.04 LTS)

---

## 🚀 Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/Mahajan-Sachin/job_finder_cheat_extension.git
cd job_finder_cheat_extension
```

### 2. Setup Environment Variables
Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```
Populate your API keys in `.env`:
```env
GROQ_API_KEY=your_groq_api_key
HUNTER_API_KEY=your_hunter_api_key
TAVILY_API_KEY=your_tavily_api_key
REDIS_HOST=localhost
REDIS_PORT=6379
```

### 3. Run via Docker Compose (Recommended)
```bash
docker-compose up -d --build
```
The FastAPI server will be available at `http://localhost:8000`. Interactive API documentation can be accessed at `http://localhost:8000/docs`.

### 4. Local Development Setup (Manual)
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

---

## 📡 API Reference Highlights

| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/generate-draft` | Queues outreach pitch generation task | `202 Accepted` |
| `GET` | `/api/task/{task_id}` | Polls async task execution status | `200 OK` |
| `GET` | `/health` | System health check & Redis/DB status | `200 OK` |

---

## 📄 License
Distributed under the **MIT License**. See `LICENSE` for details.
