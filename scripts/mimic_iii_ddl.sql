-- ============================================================================
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


-- ----------------------------------------------------------------------------
-- Table: d_icd_diagnoses
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.d_icd_diagnoses (
    ROW_ID INT COMMENT 'Unique row identifier.',
    ICD9_CODE STRING COMMENT 'ICD9 code - note that this is a fixed length character field, as whitespaces are important in uniquely identifying ICD-9 codes.',
    SHORT_TITLE STRING COMMENT 'Short title associated with the code.',
    LONG_TITLE STRING COMMENT 'Long title associated with the code.'
);

-- ----------------------------------------------------------------------------
-- Table: d_icd_procedures
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.d_icd_procedures (
    ROW_ID INT COMMENT 'Unique row identifier.',
    ICD9_CODE STRING COMMENT 'ICD9 code - note that this is a fixed length character field, as whitespaces are important in uniquely identifying ICD-9 codes.',
    SHORT_TITLE STRING COMMENT 'Short title associated with the code.',
    LONG_TITLE STRING COMMENT 'Long title associated with the code.'
);

-- ----------------------------------------------------------------------------
-- Table: d_labitems
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.d_labitems (
    ROW_ID INT COMMENT 'Unique row identifier.',
    ITEMID INT COMMENT 'Foreign key. Identifies the charted item.',
    LABEL STRING COMMENT 'Label identifying the item.',
    FLUID STRING COMMENT 'Fluid associated with the item, for example blood or urine.',
    CATEGORY STRING COMMENT 'Category of item, for example chemistry or hematology.',
    LOINC_CODE STRING COMMENT 'Logical Observation Identifiers Names and Codes (LOINC) mapped to the item, if available.'
);

-- ----------------------------------------------------------------------------
-- Table: caregivers
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.caregivers (
    ROW_ID INT COMMENT 'Unique row identifier.',
    CGID INT COMMENT 'Unique caregiver identifier.',
    LABEL STRING COMMENT 'Title of the caregiver, for example MD or RN.',
    DESCRIPTION STRING COMMENT 'More detailed description of the caregiver, if available.'
);

-- ----------------------------------------------------------------------------
-- Table: patients
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.patients (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Primary key. Identifies the patient.',
    GENDER STRING COMMENT 'Gender.',
    DOB TIMESTAMP COMMENT 'Date of birth.',
    DOD TIMESTAMP COMMENT 'Date of death. Null if the patient was alive at least 90 days post hospital discharge.',
    DOD_HOSP TIMESTAMP COMMENT 'Date of death recorded in the hospital records.',
    DOD_SSN TIMESTAMP COMMENT 'Date of death recorded in the social security records.',
    EXPIRE_FLAG INT COMMENT 'Flag indicating that the patient has died.'
);

-- ----------------------------------------------------------------------------
-- Table: admissions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.admissions (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Primary key. Identifies the hospital stay.',
    ADMITTIME TIMESTAMP COMMENT 'Time of admission to the hospital.',
    DISCHTIME TIMESTAMP COMMENT 'Time of discharge from the hospital.',
    DEATHTIME TIMESTAMP COMMENT 'Time of death.',
    ADMISSION_TYPE STRING COMMENT 'Type of admission, for example emergency or elective.',
    ADMISSION_LOCATION STRING COMMENT 'Admission location.',
    DISCHARGE_LOCATION STRING COMMENT 'Discharge location',
    INSURANCE STRING COMMENT 'Insurance type.',
    LANGUAGE STRING COMMENT 'Language.',
    RELIGION STRING COMMENT 'Religon.',
    MARITAL_STATUS STRING COMMENT 'Marital status.',
    ETHNICITY STRING COMMENT 'Ethnicity.',
    EDREGTIME TIMESTAMP,
    EDOUTTIME TIMESTAMP,
    DIAGNOSIS STRING COMMENT 'Diagnosis.',
    HOSPITAL_EXPIRE_FLAG SMALLINT,
    HAS_CHARTEVENTS_DATA SMALLINT COMMENT 'Hospital admission has at least one observation in the CHARTEVENTS table.'
);

-- ----------------------------------------------------------------------------
-- Table: icu_stays
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.icu_stays (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    ICUSTAY_ID INT COMMENT 'Primary key. Identifies the ICU stay.',
    DBSOURCE STRING COMMENT 'Source database of the item.',
    FIRST_CAREUNIT STRING COMMENT 'First careunit associated with the ICU stay.',
    LAST_CAREUNIT STRING COMMENT 'Last careunit associated with the ICU stay.',
    FIRST_WARDID SMALLINT COMMENT 'Identifier for the first ward the patient was located in.',
    LAST_WARDID SMALLINT COMMENT 'Identifier for the last ward the patient is located in.',
    INTIME TIMESTAMP COMMENT 'Time of admission to the ICU.',
    OUTTIME TIMESTAMP COMMENT 'Time of discharge from the ICU.',
    LOS DOUBLE COMMENT 'Length of stay in the ICU in fractional days.'
);

-- ----------------------------------------------------------------------------
-- Table: transfers
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.transfers (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    ICUSTAY_ID INT COMMENT 'Foreign key. Identifies the ICU stay.',
    DBSOURCE STRING COMMENT 'Source database of the item.',
    EVENTTYPE STRING COMMENT 'Type of event, for example admission or transfer.',
    PREV_CAREUNIT STRING COMMENT 'Previous careunit.',
    CURR_CAREUNIT STRING COMMENT 'Current careunit.',
    PREV_WARDID SMALLINT COMMENT 'Identifier for the previous ward the patient was located in.',
    CURR_WARDID SMALLINT COMMENT 'Identifier for the current ward the patient is located in.',
    INTIME TIMESTAMP COMMENT 'Time when the patient was transferred into the unit.',
    OUTTIME TIMESTAMP COMMENT 'Time when the patient was transferred out of the unit.',
    LOS DOUBLE COMMENT 'Length of stay in the unit in minutes.'
);

-- ----------------------------------------------------------------------------
-- Table: services
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.services (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    TRANSFERTIME TIMESTAMP COMMENT 'Time when the transfer occured.',
    PREV_SERVICE STRING COMMENT 'Previous service type.',
    CURR_SERVICE STRING COMMENT 'Current service type.'
);

-- ----------------------------------------------------------------------------
-- Table: chart_events
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.chart_events (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    ICUSTAY_ID INT COMMENT 'Foreign key. Identifies the ICU stay.',
    ITEMID INT COMMENT 'Foreign key. Identifies the charted item.',
    CHARTTIME TIMESTAMP COMMENT 'Time when the event occured.',
    STORETIME TIMESTAMP COMMENT 'Time when the event was recorded in the system.',
    CGID INT COMMENT 'Foreign key. Identifies the caregiver.',
    VALUE STRING COMMENT 'Value of the event as a text string.',
    VALUENUM DOUBLE COMMENT 'Value of the event as a number.',
    VALUEUOM STRING COMMENT 'Unit of measurement.',
    WARNING INT COMMENT 'Flag to highlight that the value has triggered a warning.',
    ERROR INT COMMENT 'Flag to highlight an error with the event.',
    RESULTSTATUS STRING COMMENT 'Result status of lab data.',
    STOPPED STRING COMMENT 'Text string indicating the stopped status of an event (i.e. stopped, not stopped).'
);

-- ----------------------------------------------------------------------------
-- Table: lab_events
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.lab_events (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    ITEMID INT COMMENT 'Foreign key. Identifies the charted item.',
    CHARTTIME TIMESTAMP COMMENT 'Time when the event occured.',
    VALUE STRING COMMENT 'Value of the event as a text string.',
    VALUENUM DOUBLE COMMENT 'Value of the event as a number.',
    VALUEUOM STRING COMMENT 'Unit of measurement.',
    FLAG STRING COMMENT 'Flag indicating whether the lab test value is considered abnormal (null if the test was normal).'
);

-- ----------------------------------------------------------------------------
-- Table: microbiology_events
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.microbiology_events (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    CHARTDATE TIMESTAMP COMMENT 'Date when the event occured.',
    CHARTTIME TIMESTAMP COMMENT 'Time when the event occured, if available.',
    SPEC_ITEMID INT COMMENT 'Foreign key. Identifies the specimen.',
    SPEC_TYPE_DESC STRING COMMENT 'Description of the specimen.',
    ORG_ITEMID INT COMMENT 'Foreign key. Identifies the organism.',
    ORG_NAME STRING COMMENT 'Name of the organism.',
    ISOLATE_NUM SMALLINT COMMENT 'Isolate number associated with the test.',
    AB_ITEMID INT COMMENT 'Foreign key. Identifies the antibody.',
    AB_NAME STRING COMMENT 'Name of the antibody used.',
    DILUTION_TEXT STRING COMMENT 'The dilution amount tested for and the comparison which was made against it (e.g. <=4).',
    DILUTION_COMPARISON STRING COMMENT 'The comparison component of DILUTION_TEXT: either <= (less than or equal), = (equal), or >= (greater than or equal), or null when not available.',
    DILUTION_VALUE DOUBLE COMMENT 'The value component of DILUTION_TEXT: must be a floating point number.',
    INTERPRETATION STRING COMMENT 'Interpretation of the test.'
);

-- ----------------------------------------------------------------------------
-- Table: note_events
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.note_events (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    CHARTDATE TIMESTAMP COMMENT 'Date when the note was charted.',
    CHARTTIME TIMESTAMP COMMENT 'Date and time when the note was charted. Note that some notes (e.g. discharge summaries) do not have a time associated with them: these notes have NULL in this column.',
    STORETIME TIMESTAMP,
    CATEGORY STRING COMMENT 'Category of the note, e.g. Discharge summary.',
    DESCRIPTION STRING COMMENT 'A more detailed categorization for the note, sometimes entered by free-text.',
    CGID INT COMMENT 'Foreign key. Identifies the caregiver.',
    ISERROR STRING COMMENT 'Flag to highlight an error with the note.',
    TEXT STRING COMMENT 'Content of the note.'
);

-- ----------------------------------------------------------------------------
-- Table: prescriptions
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.prescriptions (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    ICUSTAY_ID INT COMMENT 'Foreign key. Identifies the ICU stay.',
    STARTDATE TIMESTAMP COMMENT 'Date when the prescription started.',
    ENDDATE TIMESTAMP COMMENT 'Date when the prescription ended.',
    DRUG_TYPE STRING COMMENT 'Type of drug.',
    DRUG STRING COMMENT 'Name of the drug.',
    DRUG_NAME_POE STRING COMMENT 'Name of the drug on the Provider Order Entry interface.',
    DRUG_NAME_GENERIC STRING COMMENT 'Generic drug name.',
    FORMULARY_DRUG_CD STRING COMMENT 'Formulary drug code.',
    GSN STRING COMMENT 'Generic Sequence Number.',
    NDC STRING COMMENT 'National Drug Code.',
    PROD_STRENGTH STRING COMMENT 'Strength of the drug (product).',
    DOSE_VAL_RX STRING COMMENT 'Dose of the drug prescribed.',
    DOSE_UNIT_RX STRING COMMENT 'Unit of measurement associated with the dose.',
    FORM_VAL_DISP STRING COMMENT 'Amount of the formulation dispensed.',
    FORM_UNIT_DISP STRING COMMENT 'Unit of measurement associated with the formulation.',
    ROUTE STRING COMMENT 'Route of administration, for example intravenous or oral.'
);

-- ----------------------------------------------------------------------------
-- Table: input_events_cv
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.input_events_cv (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    ICUSTAY_ID INT COMMENT 'Foreign key. Identifies the ICU stay.',
    CHARTTIME TIMESTAMP COMMENT 'Time of that the input was started or received.',
    ITEMID INT COMMENT 'Foreign key. Identifies the charted item.',
    AMOUNT DOUBLE COMMENT 'Amount of the item administered to the patient.',
    AMOUNTUOM STRING COMMENT 'Unit of measurement for the amount.',
    RATE DOUBLE COMMENT 'Rate at which the item is being administered to the patient.',
    RATEUOM STRING COMMENT 'Unit of measurement for the rate.',
    STORETIME TIMESTAMP COMMENT 'Time when the event was recorded in the system.',
    CGID INT COMMENT 'Foreign key. Identifies the caregiver.',
    ORDERID INT COMMENT 'Identifier linking items which are grouped in a solution.',
    LINKORDERID INT COMMENT 'Identifier linking orders across multiple administrations. LINKORDERID is always equal to the first occuring ORDERID of the series.',
    STOPPED STRING COMMENT 'Event was explicitly marked as stopped. Infrequently used by caregivers.',
    NEWBOTTLE INT COMMENT 'Indicates when a new bottle of the solution was hung at the bedside.',
    ORIGINALAMOUNT DOUBLE COMMENT 'Amount of the item which was originally charted.',
    ORIGINALAMOUNTUOM STRING COMMENT 'Unit of measurement for the original amount.',
    ORIGINALROUTE STRING COMMENT 'Route of administration originally chosen for the item.',
    ORIGINALRATE DOUBLE COMMENT 'Rate of administration originally chosen for the item.',
    ORIGINALRATEUOM STRING COMMENT 'Unit of measurement for the rate originally chosen.',
    ORIGINALSITE STRING COMMENT 'Anatomical site for the original administration of the item.'
);

-- ----------------------------------------------------------------------------
-- Table: input_events_mv
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.input_events_mv (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    ICUSTAY_ID INT COMMENT 'Foreign key. Identifies the ICU stay.',
    STARTTIME TIMESTAMP COMMENT 'Time when the event started.',
    ENDTIME TIMESTAMP COMMENT 'Time when the event ended.',
    ITEMID INT COMMENT 'Foreign key. Identifies the charted item.',
    AMOUNT DOUBLE COMMENT 'Amount of the item administered to the patient.',
    AMOUNTUOM STRING COMMENT 'Unit of measurement for the amount.',
    RATE DOUBLE COMMENT 'Rate at which the item is being administered to the patient.',
    RATEUOM STRING COMMENT 'Unit of measurement for the rate.',
    STORETIME TIMESTAMP COMMENT 'Time when the event was recorded in the system.',
    CGID INT COMMENT 'Foreign key. Identifies the caregiver.',
    ORDERID INT COMMENT 'Identifier linking items which are grouped in a solution.',
    LINKORDERID INT COMMENT 'Identifier linking orders across multiple administrations. LINKORDERID is always equal to the first occuring ORDERID of the series.',
    ORDERCATEGORYNAME STRING COMMENT 'A group which the item corresponds to.',
    SECONDARYORDERCATEGORYNAME STRING COMMENT 'A secondary group for those items with more than one grouping possible.',
    ORDERCOMPONENTTYPEDESCRIPTION STRING COMMENT 'The role of the item administered in the order.',
    ORDERCATEGORYDESCRIPTION STRING COMMENT 'The type of item administered.',
    PATIENTWEIGHT DOUBLE COMMENT 'For drugs dosed by weight, the value of the weight used in the calculation.',
    TOTALAMOUNT DOUBLE COMMENT 'The total amount in the solution for the given item.',
    TOTALAMOUNTUOM STRING COMMENT 'Unit of measurement for the total amount in the solution.',
    ISOPENBAG SMALLINT COMMENT 'Indicates whether the bag containing the solution is open.',
    CONTINUEINNEXTDEPT SMALLINT COMMENT 'Indicates whether the item will be continued in the next department where the patient is transferred to.',
    CANCELREASON SMALLINT COMMENT 'Reason for cancellation, if cancelled.',
    STATUSDESCRIPTION STRING COMMENT 'The current status of the order: stopped, rewritten, running or cancelled.',
    COMMENTS_EDITEDBY STRING COMMENT 'The title of the caregiver who edited the order.',
    COMMENTS_CANCELEDBY STRING COMMENT 'The title of the caregiver who canceled the order.',
    COMMENTS_DATE TIMESTAMP COMMENT 'Time at which the caregiver edited or cancelled the order.',
    ORIGINALAMOUNT DOUBLE COMMENT 'Amount of the item which was originally charted.',
    ORIGINALRATE DOUBLE COMMENT 'Rate of administration originally chosen for the item.'
);

-- ----------------------------------------------------------------------------
-- Table: output_events
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.output_events (
    ROW_ID INT,
    SUBJECT_ID INT,
    HADM_ID INT,
    ICUSTAY_ID INT,
    CHARTTIME TIMESTAMP,
    ITEMID INT,
    VALUE DOUBLE,
    VALUEUOM STRING,
    STORETIME TIMESTAMP,
    CGID INT,
    STOPPED STRING,
    NEWBOTTLE STRING,
    ISERROR INT
);

-- ----------------------------------------------------------------------------
-- Table: procedure_events_mv
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.procedure_events_mv (
    ROW_ID INT,
    SUBJECT_ID INT,
    HADM_ID INT,
    ICUSTAY_ID INT,
    STARTTIME TIMESTAMP,
    ENDTIME TIMESTAMP,
    ITEMID INT,
    VALUE DOUBLE,
    VALUEUOM STRING,
    LOCATION STRING,
    LOCATIONCATEGORY STRING,
    STORETIME TIMESTAMP,
    CGID INT,
    ORDERID INT,
    LINKORDERID INT,
    ORDERCATEGORYNAME STRING,
    SECONDARYORDERCATEGORYNAME STRING,
    ORDERCATEGORYDESCRIPTION STRING,
    ISOPENBAG SMALLINT,
    CONTINUEINNEXTDEPT SMALLINT,
    CANCELREASON SMALLINT,
    STATUSDESCRIPTION STRING,
    COMMENTS_EDITEDBY STRING,
    COMMENTS_CANCELEDBY STRING,
    COMMENTS_DATE TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- Table: procedures_icd
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.procedures_icd (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    SEQ_NUM INT COMMENT 'Lower procedure numbers occurred earlier.',
    ICD9_CODE STRING COMMENT 'ICD9 code associated with the procedure.'
);

-- ----------------------------------------------------------------------------
-- Table: cpt_events
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.cpt_events (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    COSTCENTER STRING COMMENT 'Center recording the code, for example the ICU or the respiratory unit.',
    CHARTDATE TIMESTAMP COMMENT 'Date when the event occured, if available.',
    CPT_CD STRING COMMENT 'Current Procedural Terminology code.',
    CPT_NUMBER INT COMMENT 'Numerical element of the Current Procedural Terminology code.',
    CPT_SUFFIX STRING COMMENT 'Text element of the Current Procedural Terminology, if any. Indicates code category.',
    TICKET_ID_SEQ INT COMMENT 'Sequence number of the event, derived from the ticket ID.',
    SECTIONHEADER STRING COMMENT 'High-level section of the Current Procedural Terminology code.',
    SUBSECTIONHEADER STRING COMMENT 'Subsection of the Current Procedural Terminology code.',
    DESCRIPTION STRING COMMENT 'Description of the Current Procedural Terminology, if available.'
);

-- ----------------------------------------------------------------------------
-- Table: diagnoses_icd
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.diagnoses_icd (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    SEQ_NUM INT COMMENT 'Priority of the code. Sequence 1 is the primary code.',
    ICD9_CODE STRING COMMENT 'ICD9 code for the diagnosis.'
);

-- ----------------------------------------------------------------------------
-- Table: drg_codes
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.drg_codes (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    DRG_TYPE STRING COMMENT 'Type of Diagnosis-Related Group, for example APR is All Patient Refined',
    DRG_CODE STRING COMMENT 'Diagnosis-Related Group code',
    DESCRIPTION STRING COMMENT 'Description of the Diagnosis-Related Group',
    DRG_SEVERITY SMALLINT COMMENT 'Relative severity, available for type APR only.',
    DRG_MORTALITY SMALLINT COMMENT 'Relative mortality, available for type APR only.'
);

-- ----------------------------------------------------------------------------
-- Table: callout
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mimic_iii.callout (
    ROW_ID INT COMMENT 'Unique row identifier.',
    SUBJECT_ID INT COMMENT 'Foreign key. Identifies the patient.',
    HADM_ID INT COMMENT 'Foreign key. Identifies the hospital stay.',
    SUBMIT_WARDID INT COMMENT 'Identifies the ward where the call out request was submitted.',
    SUBMIT_CAREUNIT STRING COMMENT 'If the ward where the call was submitted was an ICU, the ICU type is listed here.',
    CURR_WARDID INT COMMENT 'Identifies the ward where the patient is currently residing.',
    CURR_CAREUNIT STRING COMMENT 'If the ward where the patient is currently residing is an ICU, the ICU type is listed here.',
    CALLOUT_WARDID INT COMMENT 'Identifies the ward where the patient is to be discharged to. A value of 1 indicates the first available ward. A value of 0 indicates home.',
    CALLOUT_SERVICE STRING COMMENT 'Identifies the service that the patient is called out to.',
    REQUEST_TELE SMALLINT COMMENT 'Indicates if special precautions are required.',
    REQUEST_RESP SMALLINT COMMENT 'Indicates if special precautions are required.',
    REQUEST_CDIFF SMALLINT COMMENT 'Indicates if special precautions are required.',
    REQUEST_MRSA SMALLINT COMMENT 'Indicates if special precautions are required.',
    REQUEST_VRE SMALLINT COMMENT 'Indicates if special precautions are required.',
    CALLOUT_STATUS STRING COMMENT 'Current status of the call out request.',
    CALLOUT_OUTCOME STRING COMMENT 'The result of the call out request; either a cancellation or a discharge.',
    DISCHARGE_WARDID INT COMMENT 'The ward to which the patient was discharged.',
    ACKNOWLEDGE_STATUS STRING COMMENT 'The status of the response to the call out request.',
    CREATETIME TIMESTAMP COMMENT 'Time at which the call out request was created.',
    UPDATETIME TIMESTAMP COMMENT 'Last time at which the call out request was updated.',
    ACKNOWLEDGETIME TIMESTAMP COMMENT 'Time at which the call out request was acknowledged.',
    OUTCOMETIME TIMESTAMP COMMENT 'Time at which the outcome (cancelled or discharged) occurred.',
    FIRSTRESERVATIONTIME TIMESTAMP COMMENT 'First time at which a ward was reserved for the call out request.',
    CURRENTRESERVATIONTIME TIMESTAMP COMMENT 'Latest time at which a ward was reserved for the call out request.'
);


-- ============================================================================
-- End of MIMIC-III Schema DDL
-- ============================================================================
