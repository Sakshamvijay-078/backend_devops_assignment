# 🚀 AI-Powered Transaction Processing Pipeline

An asynchronous, event-driven backend system that ingests, cleans, and analyzes financial transaction data. The system uses Large Language Models (LLMs) to categorize transactions, detect anomalies, and generate structured financial summaries while keeping the API responsive through background processing.

# 🏗️ System Architecture

<div align="center">
  <img src="./assets/Pipeline_diagram.png"
       alt="AI Transaction Processing Architecture"
       width="1000">
</div>

<p align="center">
  <em>
  Asynchronous, event-driven pipeline for processing financial transactions
  using FastAPI, Celery, Redis, PostgreSQL, and Groq LLM.
  </em>
</p>

# ✨ Features

- ⚡ **Asynchronous Processing** – Long-running tasks are executed by Celery workers, ensuring low API latency.
- 🧠 **LLM-Powered Transaction Analysis** – Automatically categorizes transactions and generates financial narratives.
- 📦 **Batch Processing Optimization** – Transactions are processed in batches to minimize LLM API calls and reduce costs.
- 🔄 **Fault Tolerance & Retry Mechanism** – External API failures are handled with exponential backoff retries (max 3 attempts) and graceful fallbacks.
- 📊 **Anomaly Detection** – Identifies unusual spending patterns using statistical rules (3× median threshold) and domestic-merchant/foreign-currency checks.
- 🐳 **Containerized Deployment** – Entire infrastructure runs using Docker Compose for easy setup and deployment.
- 🛡️ **Production-Oriented Design** – Built with scalability, maintainability, and resilience in mind.

---

# 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Backend Framework | FastAPI |
| Task Queue | Celery |
| Message Broker | Redis |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| AI/LLM | Groq API (llama-3.1-8b-instant) |
| Containerization | Docker & Docker Compose |
| Data Validation | Pydantic |
| File Processing | Python built-in `csv` + `python-dateutil` |

---

# 📂 Project Structure

```bash
.
├── main.py            # FastAPI application & API endpoints
├── worker.py          # Celery task: data cleaning, anomaly detection, LLM calls
├── database.py        # SQLAlchemy models & DB engine setup
├── transactions.csv   # Sample CSV for testing
├── uploads/           # Uploaded CSVs (shared Docker volume)
├── assets/            # Diagrams and static assets
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env
└── README.md
```

---

# 🚀 Getting Started

## 1️⃣ Clone the Repository

```bash
git clone https://github.com/Sakshamvijay-078/backend_devops_assignment.git
cd backend_devops_assignment
```

---

## 2️⃣ Configure Environment Variables

Create a `.env` file in the root directory. Only the Groq API key needs to be set — the database and Redis connection strings are pre-configured to match the Docker Compose services:

```env
GROQ_API_KEY=your_groq_api_key_here
```

> **Note:** The PostgreSQL connection (`admin:password@db/transactions_db`) and Redis connection (`redis://redis:6379/0`) are already wired up internally via Docker Compose networking.

---

## 3️⃣ Start the Application

```bash
docker compose up -d --build
```

Verify that all services are running:

```bash
docker ps
```

---

## 4️⃣ Access the Services

| Service | URL |
|---------|-----|
| FastAPI | http://localhost:8000 |
| Swagger Documentation | http://localhost:8000/docs |
| PostgreSQL | localhost:5433 |
| Redis | localhost:6379 |

---

# 📡 API Endpoints

## Upload Transactions

Uploads a CSV file and starts background processing.

**Endpoint**

```http
POST /jobs/upload
```

**Request**

```
Content-Type: multipart/form-data
Field: file  (must be a .csv file)
```

**Response**

```json
{
  "job_id": "506e60fe-bd49-4f64-bc55-630251d4e4a4",
  "status": "pending"
}
```

---

## Check Job Status

**Endpoint**

```http
GET /jobs/{job_id}/status
```

**Response (while processing)**

```json
{
  "job_id": "506e60fe-bd49-4f64-bc55-630251d4e4a4",
  "status": "processing"
}
```

**Response (when completed)**

```json
{
  "job_id": "506e60fe-bd49-4f64-bc55-630251d4e4a4",
  "status": "completed",
  "summary": {
    "narrative": "Monthly expenses increased by 15% due to travel spending.",
    "risk_level": "medium",
    "anomaly_count": 5
  }
}
```

---

## Fetch Final Results

**Endpoint**

```http
GET /jobs/{job_id}/results
```

**Response**

```json
{
  "job_id": "506e60fe-bd49-4f64-bc55-630251d4e4a4",
  "status": "completed",
  "summary": {
    "narrative": "Monthly expenses increased by 15% due to travel spending.",
    "risk_level": "medium",
    "anomaly_count": 5,
    "total_spend_inr": 45200.0,
    "total_spend_usd": 320.0,
    "top_merchants": ["Swiggy", "Amazon", "IRCTC"]
  },
  "transactions": []
}
```

---

# 🔄 Processing Workflow

1. User uploads a CSV file via `POST /jobs/upload`.
2. FastAPI saves the file to the shared Docker volume (`/app/uploads/`).
3. A new `Job` record is created in PostgreSQL with status `pending`.
4. A Celery task is dispatched to Redis (fire-and-forget).
5. The Celery worker picks up the task and sets status to `processing`.
6. **Data Cleaning** – Amounts are normalized, dates parsed to ISO 8601, duplicates removed by `txn_id`, and empty categories defaulted to `Uncategorised`.
7. **Anomaly Detection** – Two rules applied: (a) amount exceeds 3× the account median, (b) domestic merchant (Swiggy, Ola, IRCTC) charged in USD.
8. **LLM Batch Categorization** – All `Uncategorised` transactions are sent to Groq in a single batched prompt to minimize API calls.
9. **LLM Narrative Summary** – Spending stats are sent to Groq to generate a narrative, risk level, and top merchants.
10. Cleaned transactions and summary are saved to PostgreSQL; job status is set to `completed`.
11. User polls `GET /jobs/{job_id}/status` or `GET /jobs/{job_id}/results` to retrieve output.

---

# 🐳 Docker Services

| Service | Image / Build | Role |
|---------|--------------|------|
| `api` | Custom build | FastAPI server on port 8000 |
| `worker` | Custom build | Celery background worker |
| `db` | `postgres:15-alpine` | PostgreSQL database |
| `redis` | `redis:7-alpine` | Message broker & result backend |

Start:

```bash
docker compose up -d
```

Stop:

```bash
docker compose down
```

View logs:

```bash
docker compose logs -f
```

View logs for a specific service:

```bash
docker compose logs -f worker
```

---

# 📈 Scaling Considerations (100x Traffic)

## 1. Database Connection Bottleneck

**Problem**

Multiple FastAPI and Celery instances can exhaust PostgreSQL's `max_connections`.

**Solution**

- Add PgBouncer for connection pooling.
- Use SQLAlchemy connection pooling.
- Introduce read replicas for heavy read traffic.

---

## 2. File Storage Bottleneck

**Problem**

Saving uploaded files on local Docker volumes causes disk I/O contention and storage limitations.

**Solution**

- Store files in AWS S3 or Google Cloud Storage.
- Use pre-signed upload URLs.
- Trigger processing through storage events.

---

## 3. Queue Throughput

**Problem**

Single Redis instance becomes a bottleneck under high load.

**Solution**

- Use Redis Cluster.
- Deploy multiple Celery workers.
- Introduce task prioritization with separate queues.

---

## 4. API Scaling

**Problem**

Single FastAPI instance cannot handle large concurrent traffic.

**Solution**

- Deploy multiple API replicas.
- Use Nginx or a cloud load balancer.
- Enable horizontal auto-scaling (e.g., Kubernetes HPA).

---

# 🛡️ Production Improvements

- JWT Authentication & Authorization
- Rate Limiting
- Structured Logging (e.g., structlog)
- OpenTelemetry Tracing
- Metrics with Prometheus & Grafana
- CI/CD Pipeline with GitHub Actions
- Kubernetes Deployment
- Health Checks and Readiness Probes
- Dead Letter Queue (DLQ) for failed Celery tasks
- Automated Database Backups

---

# 🔧 Troubleshooting

### Database Connection Issues

**Error**

```bash
psycopg2.OperationalError: connection refused
```

**Cause**

The API or worker container starts before PostgreSQL is fully initialized.

**Fix**

```bash
docker compose restart api worker
```

---

### Port Already in Use

**Error**

```bash
failed to bind host port 0.0.0.0:5432/tcp: address already in use
```

**Cause**

A local PostgreSQL instance is already running on port 5432.

**Fix**

The `docker-compose.yml` already maps PostgreSQL to host port `5433` to avoid this conflict. If `5433` is also taken, update it in `docker-compose.yml`:

```yaml
ports:
  - "5434:5432"   # change left side to any free port
```

---

### AI Model Deprecation Errors

**Error**

```bash
400 Bad Request: model_decommissioned
```

**Cause**

The configured LLM model is no longer supported by Groq.

**Fix**

Update the model name in `worker.py` to the latest supported version:

```python
model="llama-3.1-8b-instant"
```

---

### Reset Everything

If containers are in an inconsistent state:

```bash
docker compose down -v
docker compose up -d --build
```

---

# 📊 Sample CSV Format

The pipeline expects a CSV with the following columns:

```csv
txn_id,date,merchant,amount,currency,status,category,account_id,notes
TXN001,15-06-2024,Swiggy,450.00,INR,SUCCESS,,ACC001,Lunch order
TXN002,2024/06/16,Amazon,1200.00,INR,SUCCESS,Shopping,ACC001,Books
```

A sample file (`transactions.csv`) is included in the repository for testing.

---

# 👨‍💻 Author

**Saksham Vijay**

- GitHub: https://github.com/Sakshamvijay-078
- LinkedIn: https://www.linkedin.com/in/saksham-vijay

---

# ⭐ If you found this project useful, consider giving it a star!
