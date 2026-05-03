# 📊 Data Processing & Summary Generation Workflow

## 1. Excel Upload
- User uploads Excel file(s) into the system.
- Uploaded files trigger an asynchronous task.

## 2. Background Processing (Celery Task)
- Celery task is responsible for:
  - Reading Excel file(s)
  - Extracting relevant data
  - Cleaning/transforming data if needed
- Extracted data is stored in the database.

## 3. JSON Export (Optional)
- After data is saved:
  - User has the option to download a JSON file
  - JSON contains all extracted and processed data from Excel

---

## 4. Summary Generation

### Input Filters
User can generate summary based on:
- Buyer (required)
- Factory (required)
- Date Range (required)
- Style Number (optional)
- PO Number (optional)

---

## 5. Excel Summary Creation

### Template Selection Logic
- If **Defect Items = 78**
  → Use **Template A**
- If **Defect Items = 37**
  → Use **Template B**

### Template Structure
- Each template contains **3 sheets**:
  1. Sheet 1 → Standard layout
  2. Sheet 2 → Same layout as Sheet 1
  3. Inline Sheet → Slightly different format but mostly similar

### Data Insertion
- System inserts processed data into:
  - Predefined sheets based on 
  - Predefined cells
  - Based on template structure
- No structural modification, only value replacement

---

## 6. Output
- Final output is a generated Excel summary file
- File is ready for download

---

## 7. Error Handling & Regeneration

### If Errors Found:
- User reviews the generated Excel
- Uses downloaded JSON file to:
  - Identify incorrect data
  - Update database records manually or via system

### Regeneration:
- After correction:
  - Regenerate summary directly from updated database
  - No need to re-upload Excel

---

## 🔁 Workflow Summary

1. Upload Excel  
2. Celery processes & saves data  
3. (Optional) Download JSON  
4. Apply filters → Generate summary  
5. Select template based on defect count  
6. Populate Excel templates  
7. Download summary  
8. Fix errors via JSON → Update DB → Regenerate  

---