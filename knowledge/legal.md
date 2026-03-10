## Legal Data Fusion Workflow for Chatbot Data Processing

### Step 1 — Ingest
The system starts by selecting input datasets from a catalog or uploaded files (CSV, JSON, XLSX). This defines which data enters the pipeline. When the user proceeds, the pipeline begins automated processing using the selected sources. No transformation happens here; it only establishes the data inputs.

### Step 2 — Discovery
The system prepares the data for understanding and downstream processing by standardizing structure and generating semantic meaning. First, it converts all files into a consistent internal format (flat JSON) by scanning files, flattening nested structures, standardizing values like dates and numbers, and storing source metadata for traceability. Then an LLM analyzes each dataset and its columns to generate descriptions, keywords, types, and example values, creating semantic metadata that explains what the data represents. Basic diagnostics also detect overlapping meanings or inconsistent formats across columns.

### Step 3 — Clustering
Datasets that represent the same business concept are grouped together. The system compares semantic descriptions of each dataset using an LLM that decides whether two datasets represent the same real-world entity type (such as billing or client data). A leader–follower approach assigns similar datasets to the same cluster, creating groups that will later share a unified schema.

### Step 4 — Diagnosis
The system analyzes clusters and metadata to detect deeper data quality issues. An LLM-based agent identifies redundant concepts, mismatched data types or formats, and incorrect semantic alignments between columns. Each issue is classified by type, severity, and context, producing a prioritized list of problems that may affect data accuracy or consistency.

### Step 5 — Resolution
Users review and resolve detected issues through a human-in-the-loop process. They inspect problems, accept or reject mappings, apply fixes, or define rules for handling recurring issues. The system may provide AI-assisted suggestions. Resolutions can update configurations and trigger reprocessing of earlier pipeline steps.

### Step 6 — Golden Record (Golden Schema Fusion)
For each cluster, the system creates a unified data model and merges records. An LLM proposes a standard set of canonical fields called the Golden Schema and maps source columns to these fields. Then normalized records are transformed using these mappings: values are consolidated, conflicts are logged and resolved using simple rules, missing required fields are flagged, and source information is preserved. The result is a set of harmonized records in a consistent schema along with an issue log.

### End-to-End Flow
The pipeline is controlled by a central orchestrator that runs each stage sequentially or via APIs. It converts raw heterogeneous legal data into standardized, semantically understood, validated, and consolidated records while preserving source traceability and maintaining auditability for chatbot or downstream system use.
