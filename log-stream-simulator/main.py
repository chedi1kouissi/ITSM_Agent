import argparse
import sys
from batches.definitions import (
    run_batch_001_db_timeout,
    run_batch_002_memory_leak,
    run_batch_003_downstream,
    run_batch_004_disk_full
)

BATCHES = {
    "batch_001": run_batch_001_db_timeout,
    "batch_002": run_batch_002_memory_leak,
    "batch_003": run_batch_003_downstream,
    "batch_004": run_batch_004_disk_full
}

def main():
    parser = argparse.ArgumentParser(description="Realistic Log Generator")
    parser.add_argument("--batch", type=str, help="Batch ID to generate (e.g., 'batch_001' or 'all')")
    parser.add_argument("--list", action="store_true", help="List available batches")
    
    args = parser.parse_args()
    
    if args.list:
        print("Available Batches:")
        for k in BATCHES.keys():
            print(f" - {k}")
        return

    if args.batch:
        if args.batch == "all":
            for name, func in BATCHES.items():
                print(f"[*] Generating {name}...")
                func()
        elif args.batch in BATCHES:
            print(f"[*] Generating {args.batch}...")
            BATCHES[args.batch]()
        else:
            print(f"[!] Batch '{args.batch}' not found.")
    else:
        print("Please specify --batch <id> or --batch all")

if __name__ == "__main__":
    main()
