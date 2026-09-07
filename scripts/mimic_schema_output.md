Scraping MIMIC-III schema from MIT LCP Schema Spy...
============================================================
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/patients.html...
  ✓ patients: 8 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/admissions.html...
  ✓ admissions: 19 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/icustays.html...
  ✓ icu_stays: 12 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/transfers.html...
  ✓ transfers: 13 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/chartevents.html...
  ✓ chart_events: 15 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/labevents.html...
  ✓ lab_events: 9 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/microbiologyevents.html...
  ✓ microbiology_events: 16 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/noteevents.html...
  ✓ note_events: 11 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/prescriptions.html...
  ✓ prescriptions: 19 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/inputevents_cv.html...
  ✓ input_events_cv: 22 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/inputevents_mv.html...
  ✓ input_events_mv: 31 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/outputevents.html...
  ✓ output_events: 13 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/procedureevents_mv.html...
  ✓ procedure_events_mv: 25 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/procedures_icd.html...
  ✓ procedures_icd: 5 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/cptevents.html...
  ✓ cpt_events: 12 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/diagnoses_icd.html...
  ✓ diagnoses_icd: 5 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/drgcodes.html...
  ✓ drg_codes: 8 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/d_icd_diagnoses.html...
  ✓ d_icd_diagnoses: 4 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/d_icd_procedures.html...
  ✓ d_icd_procedures: 4 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/d_labitems.html...
  ✓ d_labitems: 6 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/callout.html...
  ✓ callout: 24 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/caregivers.html...
  ✓ caregivers: 4 columns
Fetching https://lcp.mit.edu/mimic-schema-spy/tables/services.html...
  ✓ services: 6 columns

============================================================
Schema scraping complete!
Successfully scraped 23 tables

Schema saved to scripts/mimic_schema.json

============================================================
MARKDOWN FORMAT OUTPUT:
============================================================


### patients

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Primary key. Identifies the patient. |
| GENDER | STRING | Gender. |
| DOB | TIMESTAMP | Date of birth. |
| DOD | TIMESTAMP | Date of death. Null if the patient was alive at least 90 days post hospital discharge. |
| DOD_HOSP | TIMESTAMP | Date of death recorded in the hospital records. |
| DOD_SSN | TIMESTAMP | Date of death recorded in the social security records. |
| EXPIRE_FLAG | INT | Flag indicating that the patient has died. |

### admissions

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Primary key. Identifies the hospital stay. |
| ADMITTIME | TIMESTAMP | Time of admission to the hospital. |
| DISCHTIME | TIMESTAMP | Time of discharge from the hospital. |
| DEATHTIME | TIMESTAMP | Time of death. |
| ADMISSION_TYPE | STRING | Type of admission, for example emergency or elective. |
| ADMISSION_LOCATION | STRING | Admission location. |
| DISCHARGE_LOCATION | STRING | Discharge location |
| INSURANCE | STRING | Insurance type. |
| LANGUAGE | STRING | Language. |
| RELIGION | STRING | Religon. |
| MARITAL_STATUS | STRING | Marital status. |
| ETHNICITY | STRING | Ethnicity. |
| EDREGTIME | TIMESTAMP |  |
| EDOUTTIME | TIMESTAMP |  |
| DIAGNOSIS | STRING | Diagnosis. |
| HOSPITAL_EXPIRE_FLAG | SMALLINT |  |
| HAS_CHARTEVENTS_DATA | SMALLINT | Hospital admission has at least one observation in the CHARTEVENTS table. |

### icu_stays

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| ICUSTAY_ID | INT | Primary key. Identifies the ICU stay. |
| DBSOURCE | STRING | Source database of the item. |
| FIRST_CAREUNIT | STRING | First careunit associated with the ICU stay. |
| LAST_CAREUNIT | STRING | Last careunit associated with the ICU stay. |
| FIRST_WARDID | SMALLINT | Identifier for the first ward the patient was located in. |
| LAST_WARDID | SMALLINT | Identifier for the last ward the patient is located in. |
| INTIME | TIMESTAMP | Time of admission to the ICU. |
| OUTTIME | TIMESTAMP | Time of discharge from the ICU. |
| LOS | DOUBLE | Length of stay in the ICU in fractional days. |

### transfers

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| ICUSTAY_ID | INT | Foreign key. Identifies the ICU stay. |
| DBSOURCE | STRING | Source database of the item. |
| EVENTTYPE | STRING | Type of event, for example admission or transfer. |
| PREV_CAREUNIT | STRING | Previous careunit. |
| CURR_CAREUNIT | STRING | Current careunit. |
| PREV_WARDID | SMALLINT | Identifier for the previous ward the patient was located in. |
| CURR_WARDID | SMALLINT | Identifier for the current ward the patient is located in. |
| INTIME | TIMESTAMP | Time when the patient was transferred into the unit. |
| OUTTIME | TIMESTAMP | Time when the patient was transferred out of the unit. |
| LOS | DOUBLE | Length of stay in the unit in minutes. |

### chart_events

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| ICUSTAY_ID | INT | Foreign key. Identifies the ICU stay. |
| ITEMID | INT | Foreign key. Identifies the charted item. |
| CHARTTIME | TIMESTAMP | Time when the event occured. |
| STORETIME | TIMESTAMP | Time when the event was recorded in the system. |
| CGID | INT | Foreign key. Identifies the caregiver. |
| VALUE | STRING | Value of the event as a text string. |
| VALUENUM | DOUBLE | Value of the event as a number. |
| VALUEUOM | STRING | Unit of measurement. |
| WARNING | INT | Flag to highlight that the value has triggered a warning. |
| ERROR | INT | Flag to highlight an error with the event. |
| RESULTSTATUS | STRING | Result status of lab data. |
| STOPPED | STRING | Text string indicating the stopped status of an event (i.e. stopped, not stopped). |

### lab_events

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| ITEMID | INT | Foreign key. Identifies the charted item. |
| CHARTTIME | TIMESTAMP | Time when the event occured. |
| VALUE | STRING | Value of the event as a text string. |
| VALUENUM | DOUBLE | Value of the event as a number. |
| VALUEUOM | STRING | Unit of measurement. |
| FLAG | STRING | Flag indicating whether the lab test value is considered abnormal (null if the test was normal). |

### microbiology_events

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| CHARTDATE | TIMESTAMP | Date when the event occured. |
| CHARTTIME | TIMESTAMP | Time when the event occured, if available. |
| SPEC_ITEMID | INT | Foreign key. Identifies the specimen. |
| SPEC_TYPE_DESC | STRING | Description of the specimen. |
| ORG_ITEMID | INT | Foreign key. Identifies the organism. |
| ORG_NAME | STRING | Name of the organism. |
| ISOLATE_NUM | SMALLINT | Isolate number associated with the test. |
| AB_ITEMID | INT | Foreign key. Identifies the antibody. |
| AB_NAME | STRING | Name of the antibody used. |
| DILUTION_TEXT | STRING | The dilution amount tested for and the comparison which was made against it (e.g. <=4). |
| DILUTION_COMPARISON | STRING | The comparison component of DILUTION_TEXT: either <= (less than or equal), = (equal), or >= (greater than or equal), or null when not available. |
| DILUTION_VALUE | DOUBLE | The value component of DILUTION_TEXT: must be a floating point number. |
| INTERPRETATION | STRING | Interpretation of the test. |

### note_events

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| CHARTDATE | TIMESTAMP | Date when the note was charted. |
| CHARTTIME | TIMESTAMP | Date and time when the note was charted. Note that some notes (e.g. discharge summaries) do not have a time associated with them: these notes have NULL in this column. |
| STORETIME | TIMESTAMP |  |
| CATEGORY | STRING | Category of the note, e.g. Discharge summary. |
| DESCRIPTION | STRING | A more detailed categorization for the note, sometimes entered by free-text. |
| CGID | INT | Foreign key. Identifies the caregiver. |
| ISERROR | STRING | Flag to highlight an error with the note. |
| TEXT | STRING | Content of the note. |

### prescriptions

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| ICUSTAY_ID | INT | Foreign key. Identifies the ICU stay. |
| STARTDATE | TIMESTAMP | Date when the prescription started. |
| ENDDATE | TIMESTAMP | Date when the prescription ended. |
| DRUG_TYPE | STRING | Type of drug. |
| DRUG | STRING | Name of the drug. |
| DRUG_NAME_POE | STRING | Name of the drug on the Provider Order Entry interface. |
| DRUG_NAME_GENERIC | STRING | Generic drug name. |
| FORMULARY_DRUG_CD | STRING | Formulary drug code. |
| GSN | STRING | Generic Sequence Number. |
| NDC | STRING | National Drug Code. |
| PROD_STRENGTH | STRING | Strength of the drug (product). |
| DOSE_VAL_RX | STRING | Dose of the drug prescribed. |
| DOSE_UNIT_RX | STRING | Unit of measurement associated with the dose. |
| FORM_VAL_DISP | STRING | Amount of the formulation dispensed. |
| FORM_UNIT_DISP | STRING | Unit of measurement associated with the formulation. |
| ROUTE | STRING | Route of administration, for example intravenous or oral. |

### input_events_cv

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| ICUSTAY_ID | INT | Foreign key. Identifies the ICU stay. |
| CHARTTIME | TIMESTAMP | Time of that the input was started or received. |
| ITEMID | INT | Foreign key. Identifies the charted item. |
| AMOUNT | DOUBLE | Amount of the item administered to the patient. |
| AMOUNTUOM | STRING | Unit of measurement for the amount. |
| RATE | DOUBLE | Rate at which the item is being administered to the patient. |
| RATEUOM | STRING | Unit of measurement for the rate. |
| STORETIME | TIMESTAMP | Time when the event was recorded in the system. |
| CGID | INT | Foreign key. Identifies the caregiver. |
| ORDERID | INT | Identifier linking items which are grouped in a solution. |
| LINKORDERID | INT | Identifier linking orders across multiple administrations. LINKORDERID is always equal to the first occuring ORDERID of the series. |
| STOPPED | STRING | Event was explicitly marked as stopped. Infrequently used by caregivers. |
| NEWBOTTLE | INT | Indicates when a new bottle of the solution was hung at the bedside. |
| ORIGINALAMOUNT | DOUBLE | Amount of the item which was originally charted. |
| ORIGINALAMOUNTUOM | STRING | Unit of measurement for the original amount. |
| ORIGINALROUTE | STRING | Route of administration originally chosen for the item. |
| ORIGINALRATE | DOUBLE | Rate of administration originally chosen for the item. |
| ORIGINALRATEUOM | STRING | Unit of measurement for the rate originally chosen. |
| ORIGINALSITE | STRING | Anatomical site for the original administration of the item. |

### input_events_mv

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| ICUSTAY_ID | INT | Foreign key. Identifies the ICU stay. |
| STARTTIME | TIMESTAMP | Time when the event started. |
| ENDTIME | TIMESTAMP | Time when the event ended. |
| ITEMID | INT | Foreign key. Identifies the charted item. |
| AMOUNT | DOUBLE | Amount of the item administered to the patient. |
| AMOUNTUOM | STRING | Unit of measurement for the amount. |
| RATE | DOUBLE | Rate at which the item is being administered to the patient. |
| RATEUOM | STRING | Unit of measurement for the rate. |
| STORETIME | TIMESTAMP | Time when the event was recorded in the system. |
| CGID | INT | Foreign key. Identifies the caregiver. |
| ORDERID | INT | Identifier linking items which are grouped in a solution. |
| LINKORDERID | INT | Identifier linking orders across multiple administrations. LINKORDERID is always equal to the first occuring ORDERID of the series. |
| ORDERCATEGORYNAME | STRING | A group which the item corresponds to. |
| SECONDARYORDERCATEGORYNAME | STRING | A secondary group for those items with more than one grouping possible. |
| ORDERCOMPONENTTYPEDESCRIPTION | STRING | The role of the item administered in the order. |
| ORDERCATEGORYDESCRIPTION | STRING | The type of item administered. |
| PATIENTWEIGHT | DOUBLE | For drugs dosed by weight, the value of the weight used in the calculation. |
| TOTALAMOUNT | DOUBLE | The total amount in the solution for the given item. |
| TOTALAMOUNTUOM | STRING | Unit of measurement for the total amount in the solution. |
| ISOPENBAG | SMALLINT | Indicates whether the bag containing the solution is open. |
| CONTINUEINNEXTDEPT | SMALLINT | Indicates whether the item will be continued in the next department where the patient is transferred to. |
| CANCELREASON | SMALLINT | Reason for cancellation, if cancelled. |
| STATUSDESCRIPTION | STRING | The current status of the order: stopped, rewritten, running or cancelled. |
| COMMENTS_EDITEDBY | STRING | The title of the caregiver who edited the order. |
| COMMENTS_CANCELEDBY | STRING | The title of the caregiver who canceled the order. |
| COMMENTS_DATE | TIMESTAMP | Time at which the caregiver edited or cancelled the order. |
| ORIGINALAMOUNT | DOUBLE | Amount of the item which was originally charted. |
| ORIGINALRATE | DOUBLE | Rate of administration originally chosen for the item. |

### output_events

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT |  |
| SUBJECT_ID | INT |  |
| HADM_ID | INT |  |
| ICUSTAY_ID | INT |  |
| CHARTTIME | TIMESTAMP |  |
| ITEMID | INT |  |
| VALUE | DOUBLE |  |
| VALUEUOM | STRING |  |
| STORETIME | TIMESTAMP |  |
| CGID | INT |  |
| STOPPED | STRING |  |
| NEWBOTTLE | STRING |  |
| ISERROR | INT |  |

### procedure_events_mv

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT |  |
| SUBJECT_ID | INT |  |
| HADM_ID | INT |  |
| ICUSTAY_ID | INT |  |
| STARTTIME | TIMESTAMP |  |
| ENDTIME | TIMESTAMP |  |
| ITEMID | INT |  |
| VALUE | DOUBLE |  |
| VALUEUOM | STRING |  |
| LOCATION | STRING |  |
| LOCATIONCATEGORY | STRING |  |
| STORETIME | TIMESTAMP |  |
| CGID | INT |  |
| ORDERID | INT |  |
| LINKORDERID | INT |  |
| ORDERCATEGORYNAME | STRING |  |
| SECONDARYORDERCATEGORYNAME | STRING |  |
| ORDERCATEGORYDESCRIPTION | STRING |  |
| ISOPENBAG | SMALLINT |  |
| CONTINUEINNEXTDEPT | SMALLINT |  |
| CANCELREASON | SMALLINT |  |
| STATUSDESCRIPTION | STRING |  |
| COMMENTS_EDITEDBY | STRING |  |
| COMMENTS_CANCELEDBY | STRING |  |
| COMMENTS_DATE | TIMESTAMP |  |

### procedures_icd

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| SEQ_NUM | INT | Lower procedure numbers occurred earlier. |
| ICD9_CODE | STRING | ICD9 code associated with the procedure. |

### cpt_events

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| COSTCENTER | STRING | Center recording the code, for example the ICU or the respiratory unit. |
| CHARTDATE | TIMESTAMP | Date when the event occured, if available. |
| CPT_CD | STRING | Current Procedural Terminology code. |
| CPT_NUMBER | INT | Numerical element of the Current Procedural Terminology code. |
| CPT_SUFFIX | STRING | Text element of the Current Procedural Terminology, if any. Indicates code category. |
| TICKET_ID_SEQ | INT | Sequence number of the event, derived from the ticket ID. |
| SECTIONHEADER | STRING | High-level section of the Current Procedural Terminology code. |
| SUBSECTIONHEADER | STRING | Subsection of the Current Procedural Terminology code. |
| DESCRIPTION | STRING | Description of the Current Procedural Terminology, if available. |

### diagnoses_icd

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| SEQ_NUM | INT | Priority of the code. Sequence 1 is the primary code. |
| ICD9_CODE | STRING | ICD9 code for the diagnosis. |

### drg_codes

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| DRG_TYPE | STRING | Type of Diagnosis-Related Group, for example APR is All Patient Refined |
| DRG_CODE | STRING | Diagnosis-Related Group code |
| DESCRIPTION | STRING | Description of the Diagnosis-Related Group |
| DRG_SEVERITY | SMALLINT | Relative severity, available for type APR only. |
| DRG_MORTALITY | SMALLINT | Relative mortality, available for type APR only. |

### d_icd_diagnoses

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| ICD9_CODE | STRING | ICD9 code - note that this is a fixed length character field, as whitespaces are important in uniquely identifying ICD-9 codes. |
| SHORT_TITLE | STRING | Short title associated with the code. |
| LONG_TITLE | STRING | Long title associated with the code. |

### d_icd_procedures

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| ICD9_CODE | STRING | ICD9 code - note that this is a fixed length character field, as whitespaces are important in uniquely identifying ICD-9 codes. |
| SHORT_TITLE | STRING | Short title associated with the code. |
| LONG_TITLE | STRING | Long title associated with the code. |

### d_labitems

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| ITEMID | INT | Foreign key. Identifies the charted item. |
| LABEL | STRING | Label identifying the item. |
| FLUID | STRING | Fluid associated with the item, for example blood or urine. |
| CATEGORY | STRING | Category of item, for example chemistry or hematology. |
| LOINC_CODE | STRING | Logical Observation Identifiers Names and Codes (LOINC) mapped to the item, if available. |

### callout

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| SUBMIT_WARDID | INT | Identifies the ward where the call out request was submitted. |
| SUBMIT_CAREUNIT | STRING | If the ward where the call was submitted was an ICU, the ICU type is listed here. |
| CURR_WARDID | INT | Identifies the ward where the patient is currently residing. |
| CURR_CAREUNIT | STRING | If the ward where the patient is currently residing is an ICU, the ICU type is listed here. |
| CALLOUT_WARDID | INT | Identifies the ward where the patient is to be discharged to. A value of 1 indicates the first available ward. A value of 0 indicates home. |
| CALLOUT_SERVICE | STRING | Identifies the service that the patient is called out to. |
| REQUEST_TELE | SMALLINT | Indicates if special precautions are required. |
| REQUEST_RESP | SMALLINT | Indicates if special precautions are required. |
| REQUEST_CDIFF | SMALLINT | Indicates if special precautions are required. |
| REQUEST_MRSA | SMALLINT | Indicates if special precautions are required. |
| REQUEST_VRE | SMALLINT | Indicates if special precautions are required. |
| CALLOUT_STATUS | STRING | Current status of the call out request. |
| CALLOUT_OUTCOME | STRING | The result of the call out request; either a cancellation or a discharge. |
| DISCHARGE_WARDID | INT | The ward to which the patient was discharged. |
| ACKNOWLEDGE_STATUS | STRING | The status of the response to the call out request. |
| CREATETIME | TIMESTAMP | Time at which the call out request was created. |
| UPDATETIME | TIMESTAMP | Last time at which the call out request was updated. |
| ACKNOWLEDGETIME | TIMESTAMP | Time at which the call out request was acknowledged. |
| OUTCOMETIME | TIMESTAMP | Time at which the outcome (cancelled or discharged) occurred. |
| FIRSTRESERVATIONTIME | TIMESTAMP | First time at which a ward was reserved for the call out request. |
| CURRENTRESERVATIONTIME | TIMESTAMP | Latest time at which a ward was reserved for the call out request. |

### caregivers

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| CGID | INT | Unique caregiver identifier. |
| LABEL | STRING | Title of the caregiver, for example MD or RN. |
| DESCRIPTION | STRING | More detailed description of the caregiver, if available. |

### services

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| TRANSFERTIME | TIMESTAMP | Time when the transfer occured. |
| PREV_SERVICE | STRING | Previous service type. |
| CURR_SERVICE | STRING | Current service type. |
