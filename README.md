Core Features:
1. File Upload & Specialization
Users can upload hospital datasets (doctors, departments, etc.).

Each file is tagged with a specialization (e.g., Orthopedics, Pulmonology).

Duplicate uploads are handled by replacing existing files.

2. Header Mapping Interface
Uploaded files often have inconsistent header names (e.g., doc_name, Doctor Name).

A /mapping interface allows admins to map raw headers to canonical (standardized) headers.

These mappings are saved in MongoDB and applied during file processing.

3. Canonical Data Storage
After mapping, raw headers in the uploaded file are replaced with canonical headers.

Data is stored in collections named like data_<specialization> (e.g., data_orthopedics).

Headers and their metadata are stored in a shared header_metadata collection.

4. Metadata Extraction (Backfill)
The /backfill route scans header metadata and fills missing fields:

Upload date

Data type (e.g., string, int)

Null value count

Unique value count

Sample values

Backfill uses raw headers from the original file (via mapping) to extract data accurately.

5. Header Viewer
/headers route displays existing headers and their metadata for review and filtering by specialization.

💾 Data Storage (MongoDB Collections)
header_metadata: Stores metadata about canonical headers per file and specialization.

header_mappings: Stores mappings between raw headers and canonical headers.

data_<specialization>: Stores cleaned records for each specialization (one collection per specialization).

📁 Folder Structure
uploads/: Stores uploaded raw files temporarily.

Flask app serves HTML templates (index.html, mapping.html, headers.html) for interaction.

✅ Key Improvements Implemented
Prevents re-upload of unmapped files.

Maps headers consistently.

Handles duplicate uploads cleanly.

Ensures metadata is accurate via backfill.

Fixes for issues like double header storage and incorrect column references.

"# Hospital-Metadata-Management-System" 
