# MIMIC-III Database Table Reference

This document describes all MIMIC-III source tables available in the Lakebase mimic_iii schema under the mimic_iii catalog. Do not use Unity Catalog to source any data.

## Overview

MIMIC-III (Medical Information Mart for Intensive Care III) is a freely available database comprising de-identified health data associated with approximately 60,000 ICU admissions from Beth Israel Deaconess Medical Center between 2001 and 2012. The database includes demographics, vital signs, laboratory tests, medications, and more.

**Schema Location:** `mimic_iii`

---

## Table Index

| Category | Tables |
|----------|--------|
| **Core Patient Data** | [patients](#patients), [admissions](#admissions), [icu_stays](#icu_stays), [transfers](#transfers) |
| **Clinical Events** | [chart_events](#chart_events), [lab_events](#lab_events), [microbiology_events](#microbiology_events), [note_events](#note_events) |
| **Medications & Inputs** | [prescriptions](#prescriptions), [input_events_cv](#input_events_cv), [input_events_mv](#input_events_mv) |
| **Outputs & Procedures** | [output_events](#output_events), [procedure_events_mv](#procedure_events_mv), [procedures_icd](#procedures_icd), [cpt_events](#cpt_events) |
| **Diagnoses & Codes** | [diagnoses_icd](#diagnoses_icd), [drg_codes](#drg_codes) |
| **Dictionary/Reference** | [d_icd_diagnoses](#d_icd_diagnoses), [d_icd_procedures](#d_icd_procedures), [d_labitems](#d_labitems) |
| **Hospital Operations** | [callout](#callout), [caregivers](#caregivers), [services](#services) |

---

## Core Patient Data

### patients

Contains core demographic information for each patient in the database. Each row represents a unique patient identified by `SUBJECT_ID`.

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

**Key Relationships:**
- Links to all other tables via `SUBJECT_ID`

---

### admissions

Contains information about each hospital admission. A patient may have multiple admissions.

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
| EDREGTIME | TIMESTAMP | Timestamp for when the patient registered in the emergency department |
| EDOUTTIME | TIMESTAMP | Timestamp for when the patient left the emergency department |
| DIAGNOSIS | STRING | Diagnosis. |
| HOSPITAL_EXPIRE_FLAG | SMALLINT | Indicator of whether the patient expired during the hospital stay (1 = died, 0 = survived) |
| HAS_CHARTEVENTS_DATA | SMALLINT | Hospital admission has at least one observation in the CHARTEVENTS table. |

**Key Relationships:**
- Links to `patients` via `SUBJECT_ID`
- Links to most clinical tables via `HADM_ID`

---

### icu_stays

Contains information about each ICU stay. A single hospital admission may include multiple ICU stays.

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

**Care Unit Types:**
- **MICU**: Medical Intensive Care Unit
- **SICU**: Surgical Intensive Care Unit
- **CCU**: Coronary Care Unit
- **CSRU**: Cardiac Surgery Recovery Unit
- **TSICU**: Trauma/Surgical Intensive Care Unit

**Key Relationships:**
- Links to `patients` via `SUBJECT_ID`
- Links to `admissions` via `HADM_ID`
- Primary identifier for ICU-level events

---

### transfers

Records all patient transfers between different care units and wards during their hospital stay.

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

---

## Clinical Events

### chart_events

Contains all charted observations for patients, including vital signs, nursing assessments, and other clinical measurements. This is one of the largest tables in MIMIC-III.

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

**Common Vital Signs ITEMIDs:**
- Heart Rate, Blood Pressure, Temperature, Respiratory Rate, SpO2, etc.

---

### lab_events

Contains all laboratory measurements for patients, including blood tests, chemistry panels, and other diagnostic tests.

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

**Key Relationships:**
- Links to `d_labitems` via `ITEMID` for label/description lookup

---

### microbiology_events

Contains microbiology culture results, including specimen types, organisms found, and antibiotic sensitivities.

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

---

### note_events

Contains clinical notes written by healthcare providers, including nursing notes, physician notes, discharge summaries, radiology reports, and more.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| CHARTDATE | TIMESTAMP | Date when the note was charted. |
| CHARTTIME | TIMESTAMP | Date and time when the note was charted. Note that some notes (e.g. discharge summaries) do not have a time associated with them: these notes have NULL in this column. |
| STORETIME | TIMESTAMP | Indicates when the data was stored in the system, which may differ from the chart date and time |
| CATEGORY | STRING | Category of the note, e.g. Discharge summary. |
| DESCRIPTION | STRING | A more detailed categorization for the note, sometimes entered by free-text. |
| CGID | INT | Foreign key. Identifies the caregiver. |
| ISERROR | STRING | Flag to highlight an error with the note. |
| TEXT | STRING | Content of the note. |

**Note Categories:**
- Nursing, Physician, Discharge summary, ECG, Radiology, Echo, Respiratory, Nutrition, General, Rehab Services, Social Work, Case Management, Pharmacy, Consult

---

## Medications & Inputs

### prescriptions

Contains medication orders for patients, including drug names, dosages, and routes of administration.

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

---

### input_events_cv

Contains input events (fluids, medications administered) from the CareVue system (older ICU monitoring system used before ~2008).

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

---

### input_events_mv

Contains input events from the MetaVision system (newer ICU monitoring system used from ~2008 onwards).

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

---

## Outputs & Procedures

### output_events

Contains all output events for patients, including urine output, drainage, and other fluid outputs.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique identifier for each row in the dataset, allowing for easy reference and tracking of individual records |
| SUBJECT_ID | INT | Identifies the patient associated with the data entry, linking it to their medical records |
| HADM_ID | INT | Represents the unique identifier for a hospital admission, connecting the data to a specific patient visit |
| ICUSTAY_ID | INT | Denotes the unique identifier for an ICU stay, providing context for critical care data |
| CHARTTIME | TIMESTAMP | Records the timestamp of when the data was collected, essential for tracking changes over time |
| ITEMID | INT | Identifies the specific item or measurement being recorded, which can include various clinical parameters |
| VALUE | DOUBLE | Contains the actual recorded value of the measurement or observation, crucial for analysis and interpretation |
| VALUEUOM | STRING | Specifies the unit of measurement for the recorded value, ensuring clarity in data interpretation |
| STORETIME | TIMESTAMP | Indicates the timestamp when the data was stored in the database, useful for auditing and data management |
| CGID | INT | Represents the unique identifier for the category of the item being recorded, aiding in data classification |
| STOPPED | STRING | Indicates whether the measurement or observation has been stopped, providing insight into the status of the data |
| NEWBOTTLE | STRING | Denotes whether a new bottle or container was used for the measurement, relevant for certain types of data collection |
| ISERROR | INT | Flags whether there was an error in the data entry or measurement process, important for data quality assessment |

---

### procedure_events_mv

Contains procedural data from the MetaVision system, including line insertions, intubations, and other procedures.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique identifier for each procedure event |
| SUBJECT_ID | INT | Patient identifier |
| HADM_ID | INT | Hospital admission identifier |
| ICUSTAY_ID | INT | ICU stay identifier |
| STARTTIME | TIMESTAMP | Start time of the procedure |
| ENDTIME | TIMESTAMP | End time of the procedure |
| ITEMID | INT | Item identifier for the procedure type |
| VALUE | DOUBLE | Value associated with the procedure |
| VALUEUOM | STRING | Unit of measurement |
| LOCATION | STRING | Location of the procedure (anatomical site) |
| LOCATIONCATEGORY | STRING | Category of the location |
| STORETIME | TIMESTAMP | Time the data was stored |
| CGID | INT | Caregiver identifier |
| ORDERID | INT | Order identifier |
| LINKORDERID | INT | Linked order identifier |
| ORDERCATEGORYNAME | STRING | Order category name |
| SECONDARYORDERCATEGORYNAME | STRING | Secondary order category |
| ORDERCATEGORYDESCRIPTION | STRING | Description of order category |
| ISOPENBAG | SMALLINT | Open bag indicator |
| CONTINUEINNEXTDEPT | SMALLINT | Continue in next department flag |
| CANCELREASON | SMALLINT | Reason for cancellation |
| STATUSDESCRIPTION | STRING | Status description |
| COMMENTS_EDITEDBY | STRING | Comments edited by |
| COMMENTS_CANCELEDBY | STRING | Comments canceled by |
| COMMENTS_DATE | TIMESTAMP | Date of comments |

---

### procedures_icd

Contains ICD-9 procedure codes assigned to each hospital admission.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| SEQ_NUM | INT | Lower procedure numbers occurred earlier. |
| ICD9_CODE | STRING | ICD9 code associated with the procedure. |

**Key Relationships:**
- Links to `d_icd_procedures` via `ICD9_CODE` for procedure descriptions

---

### cpt_events

Contains Current Procedural Terminology (CPT) codes for procedures and services.

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

---

## Diagnoses & Codes

### diagnoses_icd

Contains ICD-9 diagnosis codes assigned to each hospital admission.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| SEQ_NUM | INT | Priority of the code. Sequence 1 is the primary code. |
| ICD9_CODE | STRING | ICD9 code for the diagnosis. |

**Key Relationships:**
- Links to `d_icd_diagnoses` via `ICD9_CODE` for diagnosis descriptions

---

### drg_codes

Contains Diagnosis Related Group (DRG) codes for hospital admissions, used for billing and reimbursement.

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

---

## Dictionary/Reference Tables

### d_icd_diagnoses

Dictionary table containing descriptions for ICD-9 diagnosis codes.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| ICD9_CODE | STRING | ICD9 code - note that this is a fixed length character field, as whitespaces are important in uniquely identifying ICD-9 codes. |
| SHORT_TITLE | STRING | Short title associated with the code. |
| LONG_TITLE | STRING | Long title associated with the code. |

**Usage:** Join with `diagnoses_icd` table on `ICD9_CODE` to get diagnosis descriptions.

---

### d_icd_procedures

Dictionary table containing descriptions for ICD-9 procedure codes.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| ICD9_CODE | STRING | ICD9 code - note that this is a fixed length character field, as whitespaces are important in uniquely identifying ICD-9 codes. |
| SHORT_TITLE | STRING | Short title associated with the code. |
| LONG_TITLE | STRING | Long title associated with the code. |

**Usage:** Join with `procedures_icd` table on `ICD9_CODE` to get procedure descriptions.

---

### d_labitems

Dictionary table containing information about laboratory items/tests.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| ITEMID | INT | Foreign key. Identifies the charted item. |
| LABEL | STRING | Label identifying the item. |
| FLUID | STRING | Fluid associated with the item, for example blood or urine. |
| CATEGORY | STRING | Category of item, for example chemistry or hematology. |
| LOINC_CODE | STRING | Logical Observation Identifiers Names and Codes (LOINC) mapped to the item, if available. |

**Usage:** Join with `lab_events` table on `ITEMID` to get lab test descriptions.

---

## Hospital Operations

### callout

Contains information about when patients were ready for discharge from the ICU (callout requests).

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

---

### caregivers

Contains information about caregivers (healthcare providers) who interact with patients.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| CGID | INT | Unique caregiver identifier. |
| LABEL | STRING | Title of the caregiver, for example MD or RN. |
| DESCRIPTION | STRING | More detailed description of the caregiver, if available. |

**Usage:** Join with event tables on `CGID` to identify who recorded observations.

---

### services

Contains information about hospital services (medical, surgical, etc.) that patients are admitted under.

| Column | Data Type | Description |
|--------|-----------|-------------|
| ROW_ID | INT | Unique row identifier. |
| SUBJECT_ID | INT | Foreign key. Identifies the patient. |
| HADM_ID | INT | Foreign key. Identifies the hospital stay. |
| TRANSFERTIME | TIMESTAMP | Time when the transfer occured. |
| PREV_SERVICE | STRING | Previous service type. |
| CURR_SERVICE | STRING | Current service type. |

**Common Service Types:**
- MED (Medical), SURG (Surgical), CMED (Cardiac Medical), CSURG (Cardiac Surgery), NSURG (Neurosurgery), TRAUM (Trauma), etc.

---

## Data Source Information

MIMIC-III data comes from two clinical information systems:
1. **CareVue** (Philips) - Used from 2001-2008
2. **MetaVision** (iMDsoft) - Used from 2008-2012

Tables with `_cv` suffix contain CareVue data, while `_mv` suffix indicates MetaVision data. Some tables contain data from both systems.

---

## Common Queries

### Get patient demographics with admission info
```sql
SELECT p.subject_id, p.gender, p.dob, a.admittime, a.diagnosis
FROM mimic_iii.patients p
JOIN mimic_iii.admissions a ON p.subject_id = a.subject_id
LIMIT 100;
```

### Get ICU stays with length of stay
```sql
SELECT subject_id, hadm_id, icustay_id, first_careunit, los
FROM mimic_iii.icu_stays
WHERE los IS NOT NULL
ORDER BY los DESC
LIMIT 50;
```

### Get lab results with descriptions
```sql
SELECT le.subject_id, le.hadm_id, dl.label, le.valuenum, le.valueuom, le.charttime
FROM mimic_iii.lab_events le
JOIN mimic_iii.d_labitems dl ON le.itemid = dl.itemid
WHERE le.valuenum IS NOT NULL
LIMIT 100;
```

---

## References

- [MIMIC-III Official Documentation](https://mimic.mit.edu/docs/iii/)
- [PhysioNet MIMIC-III Clinical Database](https://physionet.org/content/mimiciii/1.4/)
- Johnson, A., Pollard, T., & Mark, R. (2016). MIMIC-III Clinical Database (version 1.4). PhysioNet.

