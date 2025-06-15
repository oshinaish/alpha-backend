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
                all_lines_from_page = re.split(r'\r\n|\n|\r', text)
                
                current_transaction_lines = []
                
                for j, line in enumerate(all_lines_from_page):
                    line = line.strip()
                    if not line:
                        continue

                    # Rule 1: Every line has 2 dates, description, balance. Rule 6: First date < second (confirming date pattern)
                    # Use this to identify the start of a transaction
                    if start_of_transaction_pattern.search(line):
                        if current_transaction_lines:
                            combined_single_transaction_line = " ".join(current_transaction_lines)
                            print(f"Attempting to match combined line: '{combined_single_transaction_line}'")
                            
                            # Define the regex here, so it uses the 'line' variable scope (for debugging this way)
                            # Regex tailored to all new rules:
                            # 1. Transaction Date
                            # 2. Value Date (consumed)
                            # 3. Description (non-greedy, ends with '-')
                            # 4. Optional Ref No (11 or 13 digits)
                            # 5. Single Transaction Amount (Debit OR Credit)
                            # 6. Balance
                            
                            transaction_line_pattern = re.compile(
                                r"^\s*(\d{1,2}\s+\w+\s+\d{4})" + # Group 1: Transaction Date (e.g., "4 Mar 2025")
                                r"\s+" +
                                r"(\d{1,2}\s+\w+\s+\d{4})" + # Group 2: Value Date (e.g., "4 Mar 2025")
                                r"\s+(.+?)\s*-\s*" + # Group 3: Description (non-greedy, ends with "-")
                                r"(?:(\d{11}|\d{13})\s+)?" + # Group 4: Optional Ref No (11 or 13 digits), non-capturing group with optional capture group inside
                                r"([\d,]+\.\d{2})" + # Group 5: Single Transaction Amount (e.g., "10,000.00")
                                r"\s+([\d,]+\.\d{2}|\d[\d,]*)\s*$" # Group 6: Balance (e.g., "1,92,462" or "1,92,462.97")
                            )

                            match = transaction_line_pattern.search(combined_single_transaction_line)
                            
                            if match:
                                print(f"MATCH FOUND for combined line: '{combined_single_transaction_line}'")
                                print(f"Groups: {match.groups()}")

                                trans_date_str = match.group(1)
                                value_date_str = match.group(2) # Value date, captured but not used in UI
                                description_raw = match.group(3)
                                ref_no = match.group(4) # Ref no, captured but not used in UI
                                transaction_amount_str = match.group(5) # The single debit or credit amount
                                balance_str = match.group(6) # The balance

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
                                description = re.sub(r'\s+', ' ', description).strip() # Consolidate internal spaces

                                transaction_amount = parse_amount(transaction_amount_str)
                                balance = parse_amount(balance_str)

                                # Rule 2: Every line has either debit or credit, never both.
                                # Determine if it's debit or credit based on keywords in description.
                                # You might need to refine these keywords based on your actual statement patterns.
                                debit = 0.0
                                credit = 0.0
                                
                                # Convert description to uppercase for case-insensitive check
                                description_upper = description.upper()

                                # Common indicators for debit
                                if "DEBIT" in description_upper or "DR" in description_upper or "WITHDRAWAL" in description_upper or "SIP" in description_upper:
                                    debit = transaction_amount
                                # Common indicators for credit (or if no debit indicator found)
                                elif "CREDIT" in description_upper or "CR" in description_upper or "TRANSFER-INB" in description_upper or "DEPOSIT" in description_upper:
                                    credit = transaction_amount
                                else:
                                    # Default: If there's an amount and no explicit debit indicator, treat as credit
                                    # This is a heuristic. Adjust based on bank statement specifics.
                                    credit = transaction_amount


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
                    
                    transaction_line_pattern = re.compile(
                        r"^\s*(\d{1,2}\s+\w+\s+\d{4})" + # Group 1: Transaction Date (e.g., "4 Mar 2025")
                        r"\s+" +
                        r"(\d{1,2}\s+\w+\s+\d{4})" + # Group 2: Value Date (e.g., "4 Mar 2025")
                        r"\s+(.+?)\s*-\s*" + # Group 3: Description (non-greedy, ends with "-")
                        r"(?:(\d{11}|\d{13})\s+)?" + # Group 4: Optional Ref No (11 or 13 digits), non-capturing group with optional capture group inside
                        r"([\d,]+\.\d{2})" + # Group 5: Single Transaction Amount (e.g., "10,000.00")
                        r"\s+([\d,]+\.\d{2}|\d[\d,]*)\s*$" # Group 6: Balance (e.g., "1,92,462" or "1,92,462.97")
                    )

                    match = transaction_line_pattern.search(combined_single_transaction_line)
                    
                    if match:
                        print(f"MATCH FOUND for final combined line: '{combined_single_transaction_line}'")
                        print(f"Groups: {match.groups()}")

                        trans_date_str = match.group(1)
                        value_date_str = match.group(2)
                        description_raw = match.group(3)
                        ref_no = match.group(4)
                        transaction_amount_str = match.group(5)
                        balance_str = match.group(6)

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

                        transaction_amount = parse_amount(transaction_amount_str)
                        balance = parse_amount(balance_str)

                        debit = 0.0
                        credit = 0.0
                        
                        description_upper = description.upper()
                        if "DEBIT" in description_upper or "DR" in description_upper or "WITHDRAWAL" in description_upper or "SIP" in description_upper:
                            debit = transaction_amount
                        elif "CREDIT" in description_upper or "CR" in description_upper or "TRANSFER-INB" in description_upper or "DEPOSIT" in description_upper:
                            credit = transaction_amount
                        else:
                            credit = transaction_amount # Default to credit if no clear indicator


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
                    try{cite: 1}
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
