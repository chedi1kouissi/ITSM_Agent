import os

# Base Output Dir
BASE_OUTPUT_DIR = "generated_batches"

# Filenames
LOG_LB = "infrastructure.log" # User requested infrastructure.log for k8s, but also mentioned access logs. 
                              # Actually in the prompt "infrastructure.log" is k8s. 
                              # LB/Access logs are not explicitly requested in the "minimal types", 
                              # but let's keep them if helpful, or maybe map them to a separate file if needed.
                              # The user said: "application.log, infrastructure.log, monitoring.log, database.log"
                              # I will stick to these 4.
                              
FILE_APP = "application.log"
FILE_INFRA = "infrastructure.log"
FILE_MONITOR = "monitoring.log"
FILE_DB = "database.log"
FILE_META = "metadata.json"

DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
