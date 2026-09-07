#!/usr/bin/env python3
"""
Script to update the 01-source-data.md file with correct Databricks SQL data types
scraped from the MIT LCP Schema Spy website.
"""

import json
import re

# Load the scraped schema
with open("scripts/mimic_schema.json", "r") as f:
    schemas = json.load(f)

# Read the original document
with open("instructions/01-source-data.md", "r") as f:
    content = f.read()

# Build a mapping of table markdown sections to their schemas
# We'll replace each table definition with the scraped schema

# Map document table names to schema keys
DOC_TO_SCHEMA_MAP = {
    "patients": "patients",
    "admissions": "admissions",
    "icu_stays": "icu_stays",
    "transfers": "transfers",
    "chart_events": "chart_events",
    "lab_events": "lab_events",
    "microbiology_events": "microbiology_events",
    "note_events": "note_events",
    "prescriptions": "prescriptions",
    "input_events_cv": "input_events_cv",
    "input_events_mv": "input_events_mv",
    "output_events": "output_events",
    "procedure_events_mv": "procedure_events_mv",
    "procedures_icd": "procedures_icd",
    "cpt_events": "cpt_events",
    "diagnoses_icd": "diagnoses_icd",
    "drg_codes": "drg_codes",
    "d_icd_diagnoses": "d_icd_diagnoses",
    "d_icd_procedures": "d_icd_procedures",
    "d_labitems": "d_labitems",
    "callout": "callout",
    "caregivers": "caregivers",
    "services": "services",
}


def generate_table_markdown(schema_key: str, existing_descriptions: dict = None) -> str:
    """Generate markdown table for a schema, preserving existing descriptions where useful."""
    if schema_key not in schemas:
        return None
    
    schema = schemas[schema_key]
    columns = schema["columns"]
    
    lines = []
    lines.append("| Column | Data Type | Description |")
    lines.append("|--------|-----------|-------------|")
    
    for col in columns:
        name = col["name"]
        dtype = col["databricks_type"]
        
        # Use scraped comment if available, otherwise use existing description
        comment = col.get("comment", "")
        if existing_descriptions and name in existing_descriptions and not comment:
            comment = existing_descriptions[name]
        
        # Escape pipe characters
        comment = comment.replace("|", "\\|")
        
        lines.append(f"| {name} | {dtype} | {comment} |")
    
    return "\n".join(lines)


def extract_existing_descriptions(table_section: str) -> dict:
    """Extract existing descriptions from a markdown table section."""
    descriptions = {}
    # Match table rows
    pattern = r'\|\s*(\w+)\s*\|\s*\w+\s*\|\s*(.*?)\s*\|'
    for match in re.finditer(pattern, table_section):
        col_name = match.group(1).upper()
        description = match.group(2).strip()
        if description:
            descriptions[col_name] = description
    return descriptions


def update_table_section(content: str, table_name: str, schema_key: str) -> str:
    """Update a specific table section in the document."""
    
    # Pattern to find the table definition
    # Look for ### table_name followed by any text, then a markdown table, up to the next ---
    pattern = rf'(### {table_name}\n\n)((?:.*?\n)*?)(\| Column \| Data Type \| Description \|\n\|[-|\s]+\|\n(?:\|.*?\|\n)*)'
    
    match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
    
    if not match:
        print(f"  Could not find table section for {table_name}")
        return content
    
    # Extract existing descriptions to preserve them if scraped ones are empty
    existing_table = match.group(3)
    existing_descriptions = extract_existing_descriptions(existing_table)
    
    # Generate new table
    new_table = generate_table_markdown(schema_key, existing_descriptions)
    if not new_table:
        print(f"  No schema found for {schema_key}")
        return content
    
    # Replace the table in the content
    new_section = match.group(1) + match.group(2) + new_table + "\n"
    content = content[:match.start()] + new_section + content[match.end():]
    
    return content


# Update each table
print("Updating 01-source-data.md with correct Databricks SQL data types...")
print("=" * 60)

for doc_name, schema_key in DOC_TO_SCHEMA_MAP.items():
    print(f"  Updating {doc_name}...")
    content = update_table_section(content, doc_name, schema_key)

# Write the updated content
with open("instructions/01-source-data.md", "w") as f:
    f.write(content)

print("\n" + "=" * 60)
print("Update complete!")
print("The data types have been updated to match Databricks SQL types.")
print("Schema source: https://lcp.mit.edu/mimic-schema-spy/index.html")

