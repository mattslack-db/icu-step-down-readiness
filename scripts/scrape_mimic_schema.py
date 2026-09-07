#!/usr/bin/env python3
"""
Script to scrape MIMIC-III schema from MIT LCP Schema Spy website
and output Databricks SQL compatible data types.
"""

import requests
from bs4 import BeautifulSoup
import re
import json

BASE_URL = "https://lcp.mit.edu/mimic-schema-spy/tables"

# Mapping from document table names to schema spy table names
TABLE_NAME_MAP = {
    "patients": "patients",
    "admissions": "admissions",
    "icu_stays": "icustays",
    "transfers": "transfers",
    "chart_events": "chartevents",
    "lab_events": "labevents",
    "microbiology_events": "microbiologyevents",
    "note_events": "noteevents",
    "prescriptions": "prescriptions",
    "input_events_cv": "inputevents_cv",
    "input_events_mv": "inputevents_mv",
    "output_events": "outputevents",
    "procedure_events_mv": "procedureevents_mv",
    "procedures_icd": "procedures_icd",
    "cpt_events": "cptevents",
    "diagnoses_icd": "diagnoses_icd",
    "drg_codes": "drgcodes",
    "d_icd_diagnoses": "d_icd_diagnoses",
    "d_icd_procedures": "d_icd_procedures",
    "d_labitems": "d_labitems",
    "callout": "callout",
    "caregivers": "caregivers",
    "services": "services",
}

# PostgreSQL to Databricks SQL type mapping
PG_TO_DATABRICKS_TYPE_MAP = {
    "int2": "SMALLINT",
    "int4": "INT",
    "int8": "BIGINT",
    "smallint": "SMALLINT",
    "integer": "INT",
    "bigint": "BIGINT",
    "serial": "INT",
    "smallserial": "SMALLINT",
    "bigserial": "BIGINT",
    "float4": "FLOAT",
    "float8": "DOUBLE",
    "real": "FLOAT",
    "double precision": "DOUBLE",
    "numeric": "DECIMAL",
    "decimal": "DECIMAL",
    "varchar": "STRING",
    "character varying": "STRING",
    "char": "STRING",
    "character": "STRING",
    "text": "STRING",
    "bpchar": "STRING",
    "timestamp": "TIMESTAMP",
    "timestamp without time zone": "TIMESTAMP",
    "timestamp with time zone": "TIMESTAMP",
    "timestamptz": "TIMESTAMP",
    "date": "DATE",
    "time": "STRING",
    "time without time zone": "STRING",
    "time with time zone": "STRING",
    "boolean": "BOOLEAN",
    "bool": "BOOLEAN",
    "bytea": "BINARY",
    "json": "STRING",
    "jsonb": "STRING",
    "uuid": "STRING",
    "interval": "STRING",
}


def normalize_pg_type(pg_type: str) -> str:
    """Normalize PostgreSQL type to Databricks SQL type."""
    pg_type = pg_type.lower().strip()
    
    # Handle types with precision/scale like numeric(10,2) or varchar(255)
    base_type = re.sub(r'\(.*\)', '', pg_type).strip()
    
    # Check for array types
    if '[]' in pg_type or 'array' in pg_type:
        inner_type = base_type.replace('[]', '').replace('array', '').strip()
        inner_databricks = PG_TO_DATABRICKS_TYPE_MAP.get(inner_type, "STRING")
        return f"ARRAY<{inner_databricks}>"
    
    # Direct mapping
    if base_type in PG_TO_DATABRICKS_TYPE_MAP:
        return PG_TO_DATABRICKS_TYPE_MAP[base_type]
    
    # Handle special cases
    if 'int' in base_type:
        return "INT"
    if 'char' in base_type or 'text' in base_type:
        return "STRING"
    if 'float' in base_type or 'double' in base_type or 'real' in base_type:
        return "DOUBLE"
    if 'timestamp' in base_type:
        return "TIMESTAMP"
    if 'bool' in base_type:
        return "BOOLEAN"
    if 'numeric' in base_type or 'decimal' in base_type:
        return "DECIMAL"
    
    # Default to STRING for unknown types
    return "STRING"


def scrape_table_schema(table_name: str) -> dict | None:
    """Scrape schema for a single table from Schema Spy website."""
    url = f"{BASE_URL}/{table_name}.html"
    
    try:
        print(f"Fetching {url}...")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        columns = []
        
        # Find the columns table by id='columns'
        columns_table = soup.find('table', id='columns')
        
        if not columns_table:
            print(f"  Warning: No columns table found for {table_name}")
            return None
        
        # Get all rows in tbody
        tbody = columns_table.find('tbody')
        if not tbody:
            print(f"  Warning: No tbody found for {table_name}")
            return None
        
        for row in tbody.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                # First cell contains column name (may have class like 'primaryKey' or 'indexedColumn')
                col_name_cell = cells[0]
                col_name = col_name_cell.get_text(strip=True)
                
                # Skip relationship references (contain a dot like "TABLE.COLUMN")
                if '.' in col_name:
                    continue
                
                # Second cell contains PostgreSQL type
                col_type_cell = cells[1]
                pg_type = col_type_cell.get_text(strip=True)
                
                # Get comment if available (usually 9th cell with class 'comment detail')
                comment = ""
                for cell in cells:
                    if 'comment' in cell.get('class', []):
                        comment = cell.get_text(strip=True)
                        break
                
                if col_name and pg_type:
                    databricks_type = normalize_pg_type(pg_type)
                    columns.append({
                        'name': col_name.upper(),  # MIMIC uses uppercase column names
                        'pg_type': pg_type,
                        'databricks_type': databricks_type,
                        'comment': comment
                    })
        
        if columns:
            return {
                'table_name': table_name,
                'columns': columns
            }
        else:
            print(f"  Warning: No columns found for {table_name}")
            return None
            
    except requests.RequestException as e:
        print(f"  Error fetching {table_name}: {e}")
        return None


def main():
    """Main function to scrape all tables."""
    all_schemas = {}
    
    print("Scraping MIMIC-III schema from MIT LCP Schema Spy...")
    print("=" * 60)
    
    for doc_name, schema_name in TABLE_NAME_MAP.items():
        result = scrape_table_schema(schema_name)
        if result:
            all_schemas[doc_name] = result
            print(f"  ✓ {doc_name}: {len(result['columns'])} columns")
        else:
            print(f"  ✗ {doc_name}: Failed to scrape")
    
    print("\n" + "=" * 60)
    print("Schema scraping complete!")
    print(f"Successfully scraped {len(all_schemas)} tables\n")
    
    # Output the results
    output_file = "scripts/mimic_schema.json"
    with open(output_file, 'w') as f:
        json.dump(all_schemas, f, indent=2)
    print(f"Schema saved to {output_file}")
    
    # Also print a summary in markdown format for easy copying
    print("\n" + "=" * 60)
    print("MARKDOWN FORMAT OUTPUT:")
    print("=" * 60 + "\n")
    
    for doc_name, schema in all_schemas.items():
        print(f"\n### {doc_name}\n")
        print("| Column | Data Type | Description |")
        print("|--------|-----------|-------------|")
        for col in schema['columns']:
            comment = col.get('comment', '') or ''
            # Escape pipe characters in comments
            comment = comment.replace('|', '\\|')
            print(f"| {col['name']} | {col['databricks_type']} | {comment} |")


if __name__ == "__main__":
    main()
