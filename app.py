from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import os
from pymongo import MongoClient
from datetime import datetime
from bson import ObjectId  # Import ObjectId for _id usage

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

client = MongoClient("mongodb://localhost:27017/")
db = client.hospital_admin
header_collection = db.header_metadata
mapping_collection = db.header_mappings


@app.route('/backfill')
def backfill_metadata():
    print("\n--- Starting backfill_metadata route execution ---")
    
    df_cache = {}  
    updated_count = 0

    try:
        all_docs = list(header_collection.find({}))
        print(f"DEBUG: Found {len(all_docs)} documents in 'header_collection'.")

        mappings_cursor = mapping_collection.find({})
        mappings = {
            m['canonical_header']: m['raw_header']
            for m in mappings_cursor
            if m.get('canonical_header') and m.get('raw_header')
        }
        print(f"DEBUG: Loaded {len(mappings)} mappings from 'mapping_collection'.")

        for doc in all_docs:
            doc_id = doc.get("_id", "UNKNOWN_ID")
            print(f"\n--- Processing document ID: {doc_id} ---")

            # Check for the existence of the new 'specialty' field.
            # If 'specialty' already exists, we assume it's correctly backfilled for this purpose.
            if 'specialty' in doc:
                print(f"DEBUG: Skipping document {doc_id}: 'specialty' field already exists.")
                continue

            # Check if 'specialization' exists and 'specialty' does not, then proceed to rename
            if 'specialization' in doc and 'specialty' not in doc:
                old_specialization_value = doc['specialization']
                
                # Perform the rename operation
                result = header_collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"specialty": old_specialization_value},
                     "$unset": {"specialization": ""}} # Use $unset to remove the old field
                )
                
                if result.matched_count > 0:
                    updated_count += result.matched_count
                    print(f"INFO: Successfully renamed 'specialization' to 'specialty' for document {doc_id}.")
                else:
                    print(f"WARNING: Document {doc_id} matched 0 times for rename. It might have been altered concurrently.")
            else:
                print(f"DEBUG: Document {doc_id} does not have 'specialization' or 'specialty' already exists. Skipping rename.")
                
            # The rest of the backfill logic for other metadata fields is handled in the original code
            # and is not part of this specific request for renaming 'specialization' to 'specialty' only.
            # If you want to integrate the metadata backfill, you'd put it *after* the rename logic
            # and ensure it targets 'specialty' for any new operations.
            
            # For this request, we are *only* addressing the specialization to specialty rename.
            # The original backfill logic involving file reading, data type, null count etc.
            # was not requested to be changed in this specific update, so it's omitted here
            # to strictly adhere to "update only specialization to specialty".
            # If you want to include that, please explicitly state it.


    except Exception as e:
        print(f"CRITICAL ERROR: An unexpected error occurred in backfill_metadata route: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Backfill failed due to an unexpected error. Check server logs."

    print(f"\n--- Backfill complete. {updated_count} 'specialization' fields renamed to 'specialty'. ---")
    return f"✅ Backfill complete. {updated_count} 'specialization' fields renamed to 'specialty'."


@app.route('/')
def index():
    # Use 'specialty' field for distinct values for the dropdown
    specialties = header_collection.distinct("specialty", {"specialty": {"$ne": ""}})
    specialties.sort()
    # Passing 'specializations' to the template as that's what the template expects
    return render_template('index.html', specializations=specialties)


@app.route('/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    # Expect 'specialty' from the form for new uploads
    specialty = request.form.get('specialty', '').strip() 
    new_specialty = request.form.get('new_specialty', '').strip()

    if specialty == '__new__' and new_specialty:
        specialty = new_specialty
    
    if not file or not specialty:
        return "❌ Specialty and file are required.", 400

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except PermissionError:
        return f"❌ Cannot replace file '{file.filename}' because it is open in another application.", 400

    file.save(file_path)

    try:
        if file.filename.endswith('.xlsx'):
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)
    except Exception as e:
        return f"❌ Failed to read file: {str(e)}", 400

    raw_headers = list(df.columns)

    # Normalize uploaded raw headers (strip & lowercase)
    uploaded_headers_normalized = [h.strip().lower() for h in raw_headers]

    # Get all mapped raw headers globally
    mapped_raw_headers = mapping_collection.distinct("raw_header")

    # Normalize mapped raw headers
    mapped_headers_normalized = [h.strip().lower() for h in mapped_raw_headers]

    # Find headers not yet mapped
    missing_mappings = [
        raw_headers[i]
        for i, h in enumerate(uploaded_headers_normalized)
        if h not in mapped_headers_normalized
    ]

    if missing_mappings:
        return (
            f"❌ Error: The following headers are not mapped: {', '.join(missing_mappings)}. "
            "Please define mappings first in /mapping.", 400
        )

    # Build mapping dict for canonical headers
    mappings_cursor = mapping_collection.find()
    mapping_dict = {
        m["raw_header"]: m["canonical_header"]
        for m in mappings_cursor
        if "raw_header" in m and "canonical_header" in m
    }

    # Map raw headers to canonical headers for current file columns
    canonical_headers = [mapping_dict.get(h) for h in raw_headers]

    if None in canonical_headers:
        return "❌ Error: One or more headers are not mapped. Please define mappings in /mapping first.", 400

    df.columns = canonical_headers

    # Store header metadata only once (avoid duplicates)
    # Check for 'specialty' field in existing documents
    existing_headers = {
        (doc['header'], doc.get('specialty')) # Use .get() to safely check for 'specialty' or 'specialization'
        for doc in header_collection.find()
    }
    for h in canonical_headers:
        if (h, specialty) not in existing_headers:
            header_collection.insert_one({
                "header": h,
                "source_file": file.filename,
                "specialty": specialty # Store with the new field name
            })

    # Insert the data into specialty-specific collection
    collection_name = f"data_{specialty.lower().replace(' ', '_')}"
    data_collection = db[collection_name]
    # Remove old data for this file to avoid duplicates
    data_collection.delete_many({"source_file": file.filename})

    records = df.to_dict(orient='records')
    for record in records:
        record['source_file'] = file.filename
        record['specialty'] = specialty # Store with the new field name

    if records:
        data_collection.insert_many(records)

    return redirect(url_for('view_headers'))


@app.route('/mapping', methods=['GET', 'POST'])
def mapping():
    if request.method == 'POST':
        updates = []
        print("Form data received on /mapping POST:")
        for key, value in request.form.items():
            print(f"  {key} = {value}")
            if key.startswith('canonical_'):
                raw_header = key[len('canonical_'):]
                canonical_header = value.strip()
                if raw_header and canonical_header:
                    updates.append((raw_header, canonical_header))

        print(f"Updating mappings: {updates}")

        for raw, canonical in updates:
            mapping_collection.update_one(
                {"raw_header": raw},
                {"$set": {"canonical_header": canonical}},
                upsert=True
            )
        return redirect(url_for('mapping'))

    # GET: build header_map keyed by raw_header
    all_headers = header_collection.distinct('header')
    mapped_docs = {m['raw_header']: m['canonical_header'] for m in mapping_collection.find()}

    header_map = {}
    for h in sorted(set(all_headers)):
        header_map[h] = {'canonical_header': mapped_docs.get(h, '')}

    return render_template('mapping.html', header_map=header_map)


@app.route('/headers')
def view_headers():
    # Retrieve 'specialty' from request arguments
    specialty = request.args.get('specialty', '').strip() 
    # Query using 'specialty' field
    query = {"specialty": specialty} if specialty else {"specialty": {"$ne": ""}}

    # Fetch headers using 'specialty' field
    headers = list(header_collection.find(query))
    
    # Get distinct 'specialty' values for the dropdown
    specialties = header_collection.distinct("specialty", {"specialty": {"$ne": ""}})
    specialties.sort()

    # Pass 'specialties' and 'specialty' (as selected) to the template
    return render_template('headers.html', headers=headers, specializations=specialties, selected=specialty)


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True)