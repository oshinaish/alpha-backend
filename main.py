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
                lines = re.split(r'\r\n|\n|\r', text)

                # UPDATED COMPREHENSIVE REGEX PATTERN:
                # This pattern assumes:
                # 1. Start of line, then Transaction Date.
                # 2. Followed by an optional Value Date (which we'll consume).
                # 3. Then the Description, which can be multi-word and contain various chars.
                # 4. Followed by TWO distinct amount columns (Debit and Credit), which might contain '0.00' or be empty/dash.
                # 5. Finally, the Balance amount at the end of the line.
                #
                # Components:
                # ^\s* : Start of line, optional leading whitespace
                # (\d{1,2}\s+\w+\s+\d{4}) : Group 1: Transaction Date (e.g., "4 Mar 2025")
                # \s+ : One or more spaces
                # (?:\d{1,2}\s+\w+\s+\d{4})? : Non-capturing optional Group for Value Date (e.g., "4 Mar 2025"), consumes it.
                # \s+ : One or more spaces
                # (.+?) : Group 2: Description (NON-GREEDY, captures everything until the next pattern matches)
                # \s{2,} : Two or more spaces (often separates description from amounts reliably)
                # ([\d,]+\.\d{2}|-)? : Group 3: Debit Amount (e.g., "10,000.00" or "-"), optional.
                # \s{2,} : Two or more spaces
                # ([\d,]+\.\d{2}|-)? : Group 4: Credit Amount (e.g., "10,000.00" or "-"), optional.
                # \s* : Optional spaces
                # ([\d,]+\.\d{2}|\d[\d,]*|-\s*)?$ : Group 5: Balance (e.g., "1,92,462" or "100.00" or "-"), optional end of line.
                #
                # The assumption of '\s{2,}' (two or more spaces) separating the description from amounts, and amounts from each other,
                # is critical. Adjust this if your actual PDFs use different consistent separators.
                
                transaction_line_pattern = re.compile(
                    r"^\s*" + # Start of line, optional leading space
                    r"(\d{1,2}\s+\w+\s+\d{4})" + # Group 1: Transaction Date
                    r"\s+" +
                    r"(?:\d{1,2}\s+\w+\s+\d{4})" + # Consume Value Date (not captured)
                    r"\s+(.+?)" + # Group 2: Description (non-greedy, captures everything until the next pattern)
                    r"\s{2,}" + # Assumed separator after description (2+ spaces)
                    r"([\d,]+\.\d{2}|-)?" + # Group 3: Debit Amount (can be number or dash)
                    r"\s{2,}" + # Assumed separator between Debit and Credit (2+ spaces)
                    r"([\d,]+\.\d{2}|-)?\s*?" + # Group 4: Credit Amount (can be number or dash), non-greedy space
                    r"([\d,]+\.\d{2}|\d[\d,]*|-\s*)?" + # Group 5: Balance (can be float, int with commas, or dash), optional
                    r"\s*$" # Optional trailing space and end of line
                )

                # Function to safely parse amount strings to float
                def parse_amount(amount_str):
                    if amount_str is None or amount_str.strip() == '-' or amount_str.strip() == '':
                        return 0.0
                    return float(amount_str.replace(',', '')) # Remove commas for parsing

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    match = transaction_line_pattern.search(line)

                    if match:
                        trans_date_str = match.group(1)
                        description_raw = match.group(2)
                        debit_str = match.group(3)
                        credit_str = match.group(4)
                        balance_str = match.group(5) # Note: Balance is now group 5

                        # --- Date Parsing ---
                        extracted_date = None
                        try:
                            extracted_date = datetime.strptime(trans_date_str, '%d %b %Y').strftime('%Y-%m-%d')
                        except ValueError:
                            extracted_date = trans_date_str # Fallback

                        # --- Description Cleaning ---
                        # Keep it simple, as the regex now captures the exact span
                        description = description_raw.strip()
                        description = re.sub(r'\s+', ' ', description).strip() # Replace multiple spaces with single

                        # --- Amount Parsing ---
                        debit = parse_amount(debit_str)
                        credit = parse_amount(credit_str)
                        balance = parse_amount(balance_str)

                        transactions.append({
                            "date": extracted_date,
                            "description": description if description else "No description extracted",
                            "debit": debit,
                            "credit": credit,
                            "balance": balance,
                            "original_line": line # For debugging
                        })

        if not transactions:
            return {"status": "error", "message": "No transactions found in PDF."}

        return {
            "status": "success",
            "total_transactions": len(transactions),
            "transactions": transactions
        }

    except Exception as e:
        print(f"Error during PDF upload: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Server error during PDF processing: {str(e)}"}

@app.post("/save-category")
async def save_category(payload: dict):
    description = payload.get("description")
    category = payload.get("category")

    if not description or not category:
        return {"status": "error", "message": "Missing description or category"}

    try:
        memory = {}
        if os.path.exists(CATEGORIZATION_FILE):
            with open(CATEGORIZATION_FILE, "r") as f:
                content = f.read()
                if content:
                    try:
                        memory = json.loads(content)
                    except json.JSONDecodeError:
                        print(f"Warning: {CATEGORIZATION_FILE} is corrupted or invalid JSON. Starting with empty memory.")
                else:
                    print(f"Info: {CATEGORIZATION_FILE} is empty. Starting with empty memory.")

        memory[description] = category

        with open(CATEGORIZATION_FILE, "w") as f:
            json.dump(memory, f)

        return {"status": "success"}

    except Exception as e:
        print(f"Error saving category: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Server error saving category: {str(e)}"}

@app.get("/get-categories")
async def get_categories():
    try:
        memory = {}
        if os.path.exists(CATEGORIZATION_FILE):
            with open(CATEGORIZATION_FILE, "r") as f:
                content = f.read()
                if content:
                    try:
                        memory = json.loads(content)
                    except json.JSONDecodeError:
                        print(f"Warning: {CATEGORIZATION_FILE} is corrupted or invalid JSON. Starting with empty memory.")
                else:
                    print(f"Info: {CATEGORIZATION_FILE} is empty. Starting with empty memory.")

        return {"status": "success", "memory": memory}

    except Exception as e:
        print(f"Error getting categories: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"Server error getting categories: {str(e)}"}
