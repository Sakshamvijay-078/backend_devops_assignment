from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
import uuid
import os
import shutil

from database import SessionLocal, Job, Transaction, JobSummary
from worker import process_csv_task

app = FastAPI(title="AI Transaction Pipeline")

# Create a shared directory for file uploads
os.makedirs("/app/uploads", exist_ok=True)

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/jobs/upload")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")
        
    job_id = str(uuid.uuid4())
    file_path = f"/app/uploads/{job_id}.csv"
    
    # 1. Save file to shared Docker volume
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # 2. Create Job in DB
    new_job = Job(id=job_id, filename=file.filename, status="pending")
    db.add(new_job)
    db.commit()
    
    # 3. Fire-and-forget Celery Task
    process_csv_task.delay(job_id, file_path)
    
    return {"job_id": job_id, "status": "pending"}

@app.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    response = {"job_id": job.id, "status": job.status}
    
    # Include AI summary stats if completed
    if job.status == "completed":
        summary = db.query(JobSummary).filter(JobSummary.job_id == job_id).first()
        if summary:
            response["summary"] = {
                "narrative": summary.narrative,
                "risk_level": summary.risk_level,
                "anomaly_count": summary.anomaly_count
            }
    return response

@app.get("/jobs/{job_id}/results")
async def get_job_results(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    transactions = db.query(Transaction).filter(Transaction.job_id == job_id).all()
    summary = db.query(JobSummary).filter(JobSummary.job_id == job_id).first()
    
    return {
        "job_id": job_id,
        "status": job.status,
        "summary": summary,
        "transactions": transactions
    }