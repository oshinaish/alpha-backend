from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PyPDF2 import PdfReader
import json
import os
import re
from datetime import datetime


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



CATEGORIZATION_FILE = "categorized_memory.json"

@app.get("/")
async def read_root():
    return {"message": "BahiKhata Backend API is running!"}


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        reader = PdfReader(file.file)
        transactions = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                # Attempt to split text into lines, handling various line endings
                lines = re.split(r'\r\n|\n|\r', text)

                # Define common date patterns to look for.
                # These are examples and might need to be expanded based on your PDFs.
                # Pattern for DD Mon YYYY (e.g., 01 Jan 2023)
                date_pattern_1 = r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})'
                # Pattern for MM/DD/YYYY or DD/MM/YYYY
                date_pattern_2 = r'(\d{1,2}/\d{1,2}/\d{4})'
                # Pattern for YYYY-MM-DD
                date_pattern_3 = r'(\d{4}-\d{1,2}-\d{1,2})'
                
                # Combine date patterns
                combined_date_pattern = re.compile(f"{date_pattern_1}|{date_pattern_2}|{date_pattern_3}", re.IGNORECASE)

                # Keywords to identify a line as a potential transaction
                transaction_keywords = ["DEBIT", "CREDIT", "TRANSFER", "IMPS", "NEFT", "PAYMENT", "PURCHASE", "SALE", "WITHDRAWAL", "DEPOSIT"]

                # Heuristic for full description and date extraction:
                # We'll look for lines containing a date and a transaction keyword.
                # Then, we'll try to extract the date and treat the rest as description.
                for i, line in enumerate(lines):
                    line = line.strip()
                    if not line:
                        continue

                    # Check for keywords to narrow down transaction lines
                    is_transaction_line = any(keyword in line.upper() for keyword in transaction_keywords)
                    
                    # Also look for presence of common numbers (amounts) to confirm it's a transaction
                    contains_number = bool(re.search(r'\d{1,3}(?:,\d{3})*\.\d{2}|\d+', line))

                    if is_transaction_line and contains_number:
                        date_match = combined_date_pattern.search(line)
                        
                        extracted_date = None
                        description = line # Start with full line as description

                        if date_match:
                            # Use the matched date string (which ever group matched)
                            date_str = next(g for g in date_match.groups() if g is not None)
                            extracted_date = date_str
                            
                            # Remove the date part from the line to get a cleaner description
                            description = line[date_match.end():].strip()

                            # Attempt to parse date to YYYY-MM-DD for consistency
                            try:
                                # Try common formats for parsing
                                if re.match(date_pattern_1, date_str, re.IGNORECASE):
                                    extracted_date = datetime.strptime(date_str, '%d %b %Y').strftime('%Y-%m-%d')
                                elif re.match(date_pattern_2.replace('\\', ''), date_str): # Need to remove regex special chars for direct match
                                    try:
                                        extracted_date = datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
                                    except ValueError: # Try MM/DD/YYYY
                                        extracted_date = datetime.strptime(date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
                                elif re.match(date_pattern_3, date_str):
                                    extracted_date = date_str # Already in YYYY-MM-DD
                            except ValueError:
                                # If parsing fails, keep original string or set to None
                                extracted_date = date_str 

                        # Further clean the description: remove common transaction types/amounts if they are still in description
                        description = re.sub(r'\b(?:DEBIT|CREDIT|TRANSFER|IMPS|NEFT|DR|CR)\b', '', description, flags=re.IGNORECASE).strip()
                        # Remove common currency symbols and large numbers at the end that might be amounts/balances
                        description = re.sub(r'\b(?:INR|USD|EUR)?\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b', '', description).strip()
                        description = re.sub(r'\s+', ' ', description).strip() # Replace multiple spaces with single
                        
                        transactions.append({
                            "date": extracted_date,
                            "description": description if description else "No description extracted",
                            "original_line": line # Keep original for debugging/fallback categorization key
                        })

        if not transactions:
            return {"status": "error", "message": "No transactions found in PDF."}

        return {
            "status": "success",
            "total_transactions": len(transactions),
            "transactions": transactions # Changed from 'raw_transactions' to 'transactions'
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/save-category")
async def save_category(payload: dict):
    # Now expecting 'description' for the categorization key from frontend
    description = payload.get("description") 
    category = payload.get("category")

    if not description or not category:
        return {"status": "error", "message": "Missing description or category"}

    try:
        if os.path.exists(CATEGORIZATION_FILE):
            with open(CATEGORIZATION_FILE, "r") as f:
                memory = json.load(f)
        else:
            memory = {}

        # Use description as the key for categorization memory
        memory[description] = category

        with open(CATEGORIZATION_FILE, "w") as f:
            json.dump(memory, f)

        return {"status": "success"}

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/get-categories")
async def get_categories():
    try:
        if os.path.exists(CATEGORIZATION_FILE):
            with open(CATEGORIZATION_FILE, "r") as f:
                memory = json.load(f)
        else:
            memory = {}

        return {"status": "success", "memory": memory}

    except Exception as e:
        return {"status": "error", "message": str(e)}
