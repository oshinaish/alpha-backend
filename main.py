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

        # Pattern to identify the START of a transaction line (a date at the beginning)
        start_of_transaction_pattern = re.compile(r"^\s*(\d{1,2}\s+\w+\s+\d{4})")

        # Main transaction line regex: designed to capture dates, a broad description part, and the two amounts at the end.
        # This regex is made more flexible with whitespace.
        transaction_line_pattern = re.compile(
            r"^\s*" + # Start of line, optional leading space
            r"(\d{1,2}\s+\w+\s+\d{4})" + # Group 1: Transaction Date (e.g., "4 Mar 2025")
            r"\s+" +
            r"(\d{1,2}\s+\w+\s+\d{4})" + # Group 2: Value Date (e.g., "4 Mar 2025")
            r"\s*(.+?)" + # Group 3: Broad Description (non-greedy, captures everything until the amount patterns are found)
            r"\s+" + # Separator before the first amount
            r"([\d,]+\.\d{2}|-)" + # Group 4: First Amount (could be debit/credit). Made non-optional, assuming one will always be there.
            r"\s+" + # Separator before the second amount
            r"([\d,]+\.\d{2}|\d[\d,]*|-\s*)" + # Group 5: Second Amount (Balance or the other D/C value)
            r"\s*$" # Optional trailing space and end of line
        )

        # Secondary regex to find the Reference/Cheque Number within the broad description
        # Looks for text ending in 11 or 13 digits. This will be applied in post-processing.
        ref_cheque_no_pattern = re.compile(r'([A-Z0-9\s]*?(\d{11}|\d{13}))(?:\s*-|\s*$)', re.IGNORECASE) # Pattern to capture the ref_no and then check for - or end of string


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
                    if not line: # Skip empty lines
                        continue

                    # Determine if this line is the start of a new transaction.
                    # It starts a new transaction if it has a date at the beginning.
                    is_new_transaction_start = start_of_transaction_pattern.search(line)
                    
                    if is_new_transaction_start:
                        if current_transaction_lines:
                            combined_single_transaction_line = " ".join(current_transaction_lines)
                            print(f"Attempting to match combined line: '{combined_single_transaction_line}'")
                            
                            match = transaction_line_pattern.search(combined_single_transaction_line)
                            
                            if match:
                                print(f"MATCH FOUND for combined line: '{combined_single_transaction_line}'")
                                print(f"Groups: {match.groups()}")

                                trans_date_str = match.group(1)
                                value_date_str = match.group(2)
                                description_and_ref_raw = match.group(3) # This now contains the description + potential ref no
                                amount1_str = match.group(4) # First amount from right (Debit/Credit)
                                amount2_str = match.group(5) # Second amount from right (Balance)

                                # --- Date Parsing ---
                                extracted_date = None
                                try:
                                    extracted_date = datetime.strptime(trans_date_str, '%d %b %Y').strftime('%Y-%m-%d')
                                except ValueError: # Add more date formats here if needed based on the PDF
                                    extracted_date = trans_date_str 

                                # --- Extract Reference/Cheque Number & Clean Description ---
                                final_description = description_and_ref_raw.strip()
                                extracted_ref_no = ""
                                
                                ref_match = ref_cheque_no_pattern.search(final_description)
                                if ref_match:
                                    full_ref_text_to_remove = ref_match.group(1).strip()
                                    extracted_ref_no = ref_match.group(2) # The 11 or 13 digit number itself
                                    # Remove the extracted ref text from the description
                                    final_description = final_description.replace(full_ref_text_to_remove, '').strip()
                                
                                # Remove any remaining hyphens from description (Rule: '-' indicates end of description)
                                final_description = final_description.replace('-', '').strip()
                                final_description = re.sub(r'\s+', ' ', final_description).strip() # Consolidate internal spaces


                                # --- Amount Parsing & Debit/Credit Assignment ---
                                # Rule: every line will have either a debit value or a credit value, both will never be present.
                                # Amounts appear as [Debit/Credit Value] [Balance Value]
                                amount1 = parse_amount(amount1_str)
                                balance = parse_amount(amount2_str) # The last number is the balance

                                debit = 0.0
                                credit = 0.0
                                
                                description_upper = final_description.upper()
                                # Common indicators for debit
                                if "DEBIT" in description_upper or "DR" in description_upper or "WITHDRAWAL" in description_upper or "SIP" in description_upper or "PMT" in description_upper or "PAYMENT" in description_upper:
                                    debit = amount1
                                # Common indicators for credit (or if no debit indicator found)
                                elif "CREDIT" in description_upper or "CR" in description_upper or "TRANSFER-INB" in description_upper or "DEPOSIT" in description_upper or "BY TRANSFER" in description_upper:
                                    credit = amount1
                                else:
                                    # Default: If no clear indicator, and an amount is present, assume credit
                                    # based on your sample "TRANSFER T10,000.00" being a credit.
                                    credit = amount1


                                transactions.append({
                                    "date": extracted_date,
                                    "description": final_description if final_description else "No description extracted",
                                    "reference_no": extracted_ref_no, # Add reference number to the output
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
                
                # Process any remaining accumulated lines (for the last transaction on the page)
                if current_transaction_lines:
                    combined_single_transaction_line = " ".join(current_transaction_lines)
                    print(f"Attempting to match final combined line: '{combined_single_transaction_line}'")
                    
                    match = transaction_line_pattern.search(combined_single_transaction_line)
                    
                    if match:
                        print(f"MATCH FOUND for final combined line: '{combined_single_transaction_line}'")
                        print(f"Groups: {match.groups()}")

                        trans_date_str = match.group(1)
                        value_date_str = match.group(2)
                        description_and_ref_raw = match.group(3)
                        amount1_str = match.group(4)
                        amount2_str = match.group(5)

                        extracted_date = None
                        try:
                            extracted_date = datetime.strptime(trans_date_str, '%d %b %Y').strftime('%Y-%m-%d')
                        except ValueError:
                            extracted_date = trans_date_str 

                        final_description = description_and_ref_raw.strip()
                        extracted_ref_no = ""
                        
                        ref_match = ref_cheque_no_pattern.search(final_description)
                        if ref_match:
                            full_ref_text_to_remove = ref_match.group(1).strip()
                            extracted_ref_no = ref_match.group(2)
                            final_description = final_description.replace(full_ref_text_to_remove, '').strip()
                        
                        final_description = final_description.replace('-', '').strip()
                        final_description = re.sub(r'\s+', ' ', final_description).strip()

                        amount1 = parse_amount(amount1_str)
                        balance = parse_amount(amount2_str)

                        debit = 0.0
                        credit = 0.0
                        
                        description_upper = final_description.upper()
                        if "DEBIT" in description_upper or "DR" in description_upper or "WITHDRAWAL" in description_upper or "SIP" in description_upper or "PMT" in description_upper or "PAYMENT" in description_upper:
                            debit = amount1
                        elif "CREDIT" in description_upper or "CR" in description_upper or "TRANSFER-INB" in description_upper or "DEPOSIT" in description_upper or "BY TRANSFER" in description_upper:
                            credit = amount1
                        else:
                            credit = amount1


                        transactions.append({
                            "date": extracted_date,
                            "description": final_description if final_description else "No description extracted",
                            "reference_no": extracted_ref_no,
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
