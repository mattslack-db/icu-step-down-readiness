#!/usr/bin/env python3
"""
Generate Databricks SQL DDL script from the scraped MIMIC-III schema.
"""

import json

# Load the scraped schema
with open("scripts/mimic_schema.json", "r") as f:
    schemas = json.load(f)

# Map document table names to actual MIMIC-III table names (matching Lakebase)
TABLE_NAMES = {
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

# Order tables for creation (considering dependencies)
TABLE_ORDER = [
    # Reference/Dictionary tables first (no dependencies)
    "d_icd_diagnoses",
    "d_icd_procedures",
    "d_labitems",
    "caregivers",
    # Core patient data
    "patients",
    "admissions",
    "icu_stays",
    "transfers",
    "services",
    # Clinical events
    "chart_events",
    "lab_events",
    "microbiology_events",
    "note_events",
    # Medications & inputs
    "prescriptions",
    "input_events_cv",
    "input_events_mv",
    # Outputs & procedures
    "output_events",
    "procedure_events_mv",
    "procedures_icd",
    "cpt_events",
    # Diagnoses & codes
    "diagnoses_icd",
    "drg_codes",
    # Hospital operations
    "callout",
]


def generate_create_table(schema_key: str, table_name: str) -> str:
    """Generate CREATE TABLE statement for a table."""
    if schema_key not in schemas:
        return f"-- Schema not found for {schema_key}\n"
    
    schema = schemas[schema_key]
    columns = schema["columns"]
    
    lines = []
    lines.append(f"CREATE TABLE IF NOT EXISTS mimic_iii.{table_name} (")
    
    col_defs = []
    for col in columns:
        name = col["name"]
        dtype = col["databricks_type"]
        comment = col.get("comment", "")
        
        # Escape single quotes in comments
        comment = comment.replace("'", "''")
        
        if comment:
            col_defs.append(f"    {name} {dtype} COMMENT '{comment}'")
        else:
            col_defs.append(f"    {name} {dtype}")
    
    lines.append(",\n".join(col_defs))
    lines.append(");")
    
    return "\n".join(lines)


def generate_ddl() -> str:
    """Generate the full DDL script."""
    parts = []
    
    # Header
    parts.append("""-- ============================================================================
-- MIMIC-III Database Schema for Databricks SQL
-- ============================================================================
-- 
-- This script creates all MIMIC-III tables in the mimic_iii schema.
-- Schema source: https://lcp.mit.edu/mimic-schema-spy/index.html
-- Data types have been mapped to Databricks SQL equivalents.
--
-- Usage:
--   1. Ensure the catalog and schema exist
--   2. Run this script to create all tables
--
-- ============================================================================

-- Create schema if not exists
CREATE SCHEMA IF NOT EXISTS mimic_iii;

-- Use the schema
USE SCHEMA mimic_iii;

""")
    
    # Generate CREATE TABLE statements
    for schema_key in TABLE_ORDER:
        table_name = TABLE_NAMES.get(schema_key, schema_key)
        parts.append(f"-- ----------------------------------------------------------------------------")
        parts.append(f"-- Table: {table_name}")
        parts.append(f"-- ----------------------------------------------------------------------------")
        parts.append(generate_create_table(schema_key, table_name))
        parts.append("")
    
    # Footer
    parts.append("""
-- ============================================================================
-- End of MIMIC-III Schema DDL
-- ============================================================================
""")
    
    return "\n".join(parts)


# Generate and save the DDL
ddl = generate_ddl()

output_file = "scripts/mimic_iii_ddl.sql"
with open(output_file, "w") as f:
    f.write(ddl)

print(f"DDL script generated: {output_file}")
print(f"Total tables: {len(TABLE_ORDER)}")

