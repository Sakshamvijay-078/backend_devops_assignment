import os
import csv
import json
import statistics
from celery import Celery
from dateutil import parser
from groq import Groq
from database import SessionLocal, Job, Transaction, JobSummary

# Connect Celery to Redis
celery_app = Celery("worker", broker="redis://redis:6379/0", backend="redis://redis:6379/0")

# Initialize Groq Client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

@celery_app.task(bind=True, max_retries=3)
def process_csv_task(self, job_id, file_path):
    db = SessionLocal()
    job = db.query(Job).filter(Job.id == job_id).first()
    job.status = "processing"
    db.commit()

    try:
        transactions = []
        account_amounts = {}
        
        # --- A. Data Cleaning ---
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Format Currency & Amount
                raw_amount = str(row.get('amount', '0'))
                clean_amount = float(raw_amount.replace('$', '').replace(',', ''))
                currency = str(row.get('currency', 'INR')).upper()
                
                # Format Dates to ISO 8601
                try:
                    raw_date = row.get('date', '')
                    # handle both DD-MM-YYYY and YYYY/MM/DD seamlessly
                    parsed_date = parser.parse(raw_date, dayfirst=True) if '-' in raw_date else parser.parse(raw_date)
                    clean_date = parsed_date.isoformat()
                except:
                    clean_date = None

                # Default empty categories
                category = row.get('category', '').strip()
                if not category:
                    category = 'Uncategorised'

                txn = {
                    "txn_id": row.get('txn_id'),
                    "date": clean_date,
                    "merchant": row.get('merchant', ''),
                    "amount": clean_amount,
                    "currency": currency,
                    "status": row.get('status', '').upper(),
                    "category": category,
                    "account_id": row.get('account_id', ''),
                    "notes": row.get('notes', ''),
                    "is_anomaly": False,
                    "anomaly_reason": None
                }
                
                # De-duplication check based on txn_id (if exists)
                if txn['txn_id'] and any(t['txn_id'] == txn['txn_id'] for t in transactions):
                    continue
                    
                transactions.append(txn)
                
                # Map amounts to calculate the median later
                acc = txn['account_id']
                if acc not in account_amounts:
                    account_amounts[acc] = []
                account_amounts[acc].append(clean_amount)

        # --- B. Anomaly Detection ---
        domestic_brands = ['SWIGGY', 'OLA', 'IRCTC']
        for txn in transactions:
            acc_median = statistics.median(account_amounts.get(txn['account_id'], [0]))
            
            # Rule 1: Exceeds 3x median
            if txn['amount'] > (3 * acc_median) and txn['amount'] > 0:
                txn['is_anomaly'] = True
                txn['anomaly_reason'] = "Exceeds 3x account median"
            
            # Rule 2: Domestic Merchant + USD
            if txn['currency'] == 'USD' and txn['merchant'].upper() in domestic_brands:
                txn['is_anomaly'] = True
                txn['anomaly_reason'] = "Domestic merchant charged in USD"

        # --- C. LLM Classification (Batched) ---
        uncategorised = [t for t in transactions if t['category'] == 'Uncategorised']
        if uncategorised:
            merchants = list(set([t['merchant'] for t in uncategorised]))
            prompt = f"Categorize these merchants into ONE of: Food, Shopping, Travel, Transport, Utilities, Cash Withdrawal, Entertainment, Other. Return strictly a JSON object mapping merchant name to category. Merchants: {json.dumps(merchants)}"
            
            try:
                completion = groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0
                )
                category_map = json.loads(completion.choices[0].message.content)
                for txn in uncategorised:
                    txn['category'] = category_map.get(txn['merchant'], 'Other')
            except Exception as e:
                print("LLM Batch Classification Failed:", e)
        
        # Save clean transactions to DB
        for t in transactions:
            db_txn = Transaction(job_id=job_id, **t)
            db.add(db_txn)
        
        # --- D. LLM Narrative Summary ---
        total_inr = sum(t['amount'] for t in transactions if t['currency'] == 'INR')
        total_usd = sum(t['amount'] for t in transactions if t['currency'] == 'USD')
        anomaly_count = sum(1 for t in transactions if t['is_anomaly'])
        
        stats = {"total_inr": total_inr, "total_usd": total_usd, "anomaly_count": anomaly_count}
        summary_prompt = f"Analyze this financial data: {json.dumps(stats)}. Return ONLY a JSON object with keys: 'narrative' (2-3 sentences explaining the spending behavior), 'risk_level' (low, medium, high based on anomalies), and 'top_merchants' (list of 3 strings)."
        
        try:
            summary_completion = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": summary_prompt}],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            summary_data = json.loads(summary_completion.choices[0].message.content)
        except Exception:
            # Fallback if API completely fails during retries
            summary_data = {"narrative": "Summary generation failed.", "risk_level": "medium", "top_merchants": []}
        
        summary_record = JobSummary(
            job_id=job_id,
            total_spend_inr=total_inr,
            total_spend_usd=total_usd,
            anomaly_count=anomaly_count,
            narrative=summary_data.get('narrative', ''),
            risk_level=summary_data.get('risk_level', 'low'),
            top_merchants=summary_data.get('top_merchants', [])
        )
        db.add(summary_record)
        
        # Mark as finished
        job.status = "completed"
        db.commit()

    except Exception as exc:
        db.rollback()
        # Exponential backoff retry mechanism logic
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        
    finally:
        db.close()