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
        
        print(f"--- Processing PDF: {file.filename} ---") 

        # Define a pattern to identify the START of a transaction line (a date at the beginning)
        start_of_transaction_pattern = re.compile(r"^\s*(\d{1,2}\s+\w+\s+\d{4})")

        # Function to safely parse amount strings to float
        def parse_amount(amount_str):
            if amount_str is None or amount_str.strip() == '' or amount_str.strip() == '-':
                return 0.0
            return float(amount_str.replace(',', '')) 

        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            
            print(f"--- Page {i+1} Raw Text ---")
            print(text)
            print("--- End Page Raw Text ---")

            if text:
                lines = re.split(r'\r\n|\n|\r', text)

                # UPDATED COMPREHENSIVE REGEX PATTERN (adapted for concatenated lines):
                # We need to make the separators between description and amounts more flexible
                # because PyPDF2's line breaks can create various whitespace scenarios.
                # Allowing for ANY whitespace (\s+) rather than specific multiples.
                # The regex is defined inside the loop for debugging print but outside for actual use in prod.
                # For this specific trace, it's needed here.
                transaction_line_pattern = re.compile(
                    r"^\s*" + # Start of line, optional leading space
                    r"(\d{1,2}\s+\w+\s+\d{4})" + # Group 1: Transaction Date
                    r"\s+" +
                    r"(?:\d{1,2}\s+\w+\s+\d{4})" + # Consume Value Date (not captured)
                    r"\s*(.+?)" + # Group 2: Description (non-greedy)
                    r"\s{2,}" + # Assuming 2+ spaces separate description from first amount
                    r"([\d,]+\.\d{2}|-)?" + # Group 3: Potential Debit Amount
                    r"\s{2,}" + # Assuming 2+ spaces separate debit from credit
                    r"([\d,]+\.\d{2}|-)?\s*?" + # Group 4: Potential Credit Amount (non-greedy space)
                    r"([\d,]+\.\d{2}|\d[\d,]*|-\s*)?" + # Group 5: Balance (can be float, int with commas, or dash), optional
                    r"\s*$" # Optional trailing space and end of line
                )
                
                current_transaction_lines = []
                
                for j, line in enumerate(all_lines_from_page):
                    line = line.strip()
                    if not line: # Skip empty lines
                        continue

                    if start_of_transaction_pattern.search(line):
                        if current_transaction_lines:
                            combined_single_transaction_line = " ".join(current_transaction_lines)
                            print(f"Attempting to match combined line: '{combined_single_transaction_line}'")
                            
                            match = transaction_line_pattern.search(combined_single_transaction_line)
                            
                            if match:
                                print(f"MATCH FOUND for combined line: '{combined_single_transaction_line}'")
                                print(f"Groups: {match.groups()}")

                                trans_date_str = match.group(1)
                                description_raw = match.group(2)
                                debit_str = match.group(3)
                                credit_str = match.group(4)
                                balance_str = match.group(5)

                                extracted_date = None
                                try:
                                    extracted_date = datetime.strptime(trans_date_str, '%d %b %Y').strftime('%Y-%m-%d')
                                except ValueError:
                                    try:
                                        extracted_date = datetime.strptime(trans_date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
                                    except ValueError:
                                        try:
                                            extracted_date = datetime.strptime(trans_date_str, '%d-%m-%Y').strftime('%Y-%m-%d')
                                        except ValueError:
                                            extracted_date = trans_date_str

                                description = description_raw.strip()
                                description = re.sub(r'\s+', ' ', description).strip()

                                debit = parse_amount(debit_str)
                                credit = parse_amount(credit_str)
                                balance = parse_amount(balance_str)

                                transactions.append({
                                    "date": extracted_date,
                                    "description": description if description else "No description extracted",
                                    "debit": debit,
                                    "credit": credit,
                                    "balance": balance,
                                    "original_line": combined_single_transaction_line
                                })
                            else:
                                print(f"NO MATCH for combined line: '{combined_single_transaction_line}'")
                            
                        current_transaction_lines = [line]
                    else:
                        current_transaction_lines.append(line)
                
                if current_transaction_lines:
                    combined_single_transaction_line = " ".join(current_transaction_lines)
                    print(f"Attempting to match final combined line: '{combined_single_transaction_line}'")
                    
                    match = transaction_line_pattern.search(combined_single_transaction_line)
                    
                    if match:
                        print(f"MATCH FOUND for final combined line: '{combined_single_transaction_line}'")
                        print(f"Groups: {match.groups()}")

                        trans_date_str = match.group(1)
                        description_raw = match.group(2)
                        debit_str = match.group(3)
                        credit_str = match.group(4)
                        balance_str = match.group(5)

                        extracted_date = None
                        try:
                            extracted_date = datetime.strptime(trans_date_str, '%d %b %Y').strftime('%Y-%m-%d')
                        except ValueError:
                            try:
                                extracted_date = datetime.strptime(trans_date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
                            except ValueError:
                                try:
                                    extracted_date = datetime.strptime(trans_date_str, '%d-%m-%Y').strftime('%Y-%m-%d')
                                except ValueError:
                                    extracted_date = trans_date_str

                        description = description_raw.strip()
                        description = re.sub(r'\s+', ' ', description).strip()

                        debit = parse_amount(debit_str)
                        credit = parse_amount(credit_str)
                        balance = parse_amount(balance_str)

                        transactions.append({
                            "date": extracted_date,
                            "description": description if description else "No description extracted",
                            "debit": debit,
                            "credit": credit,
                            "balance": balance,
                            "original_line": combined_single_transaction_line
                        })
                    else:
                        print(f"NO MATCH for final combined line: '{combined_single_transaction_line}'")
        
        if not transactions:
            print("INFO: No transactions found after processing all pages.")
            return {"status": "error", "message": "No transactions found in PDF."}

        print(f"INFO: Successfully extracted {len(transactions)} transactions.")
        return {
            "status": "success",
            "total_transactions": len(transactions),
            "transactions": transactions
        }

    except Exception as e:
        print(f"ERROR: Exception during PDF upload: {e}")
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
                    # FIX START
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
                    # FIX START
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
