#!/usr/bin/env python3
"""
Data Migration Script - Convert old single-file format to new individual-file format

USAGE:
    python utils/migrate_data.py

This script will:
1. Read old data/actions.json and data/sequences.json
2. Convert each item to individual file
3. Create backups of old files
4. Show migration summary
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
import pytz

# Paths
ROOT = Path(__file__).parent.parent
OLD_ACTIONS_FILE = ROOT / "data" / "actions.json"
OLD_SEQUENCES_FILE = ROOT / "data" / "sequences.json"
RECORDINGS_DIR = ROOT / "data" / "recordings"
SEQUENCES_DIR = ROOT / "data" / "sequences"
MIGRATION_BACKUP_DIR = ROOT / "data" / "backups" / "migration"

TIMEZONE = pytz.timezone('Australia/Sydney')


def migrate_actions():
    """Migrate actions from single file to individual files"""
    if not OLD_ACTIONS_FILE.exists():
        print("[INFO] No old actions.json found, skipping actions migration")
        return 0
    
    print("[MIGRATE] Reading old actions.json...")
    
    try:
        with open(OLD_ACTIONS_FILE, 'r') as f:
            data = json.load(f)
        
        actions = data.get("actions", {})
        
        if not actions:
            print("[INFO] No actions found in old file")
            return 0
        
        print(f"[MIGRATE] Found {len(actions)} actions to migrate")
        
        # Ensure directories exist
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        
        migrated_count = 0
        
        for action_name, action_data in actions.items():
            try:
                # Build new format
                recording = {
                    "name": action_name,
                    "type": action_data.get("type", "recording"),
                    "speed": action_data.get("speed", 100),
                    "positions": action_data.get("positions", []),
                    "recorded_data": action_data.get("recorded_data", []),
                    "delays": action_data.get("delays", {}),
                    "metadata": {
                        "created": action_data.get("created", datetime.now(TIMEZONE).isoformat()),
                        "modified": action_data.get("modified", datetime.now(TIMEZONE).isoformat()),
                        "version": "1.0",
                        "file_format": "lerobot_recording",
                        "migrated_from": "actions.json"
                    }
                }
                
                # Sanitize filename
                safe_name = action_name.lower().replace(" ", "_").replace("/", "_")
                safe_name = "".join(c for c in safe_name if c.isalnum() or c in ['_', '-'])[:50]
                filename = f"{safe_name}.json"
                filepath = RECORDINGS_DIR / filename
                
                # Save
                with open(filepath, 'w') as f:
                    json.dump(recording, f, indent=2)
                
                print(f"  ✓ Migrated: {action_name} -> {filename}")
                migrated_count += 1
                
            except Exception as e:
                print(f"  ✗ Failed to migrate {action_name}: {e}")
        
        # Backup old file
        if migrated_count > 0:
            MIGRATION_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_path = MIGRATION_BACKUP_DIR / f"actions_{datetime.now(TIMEZONE).strftime('%Y%m%d_%H%M%S')}.json"
            shutil.copy2(OLD_ACTIONS_FILE, backup_path)
            print(f"[MIGRATE] Backed up old actions.json to: {backup_path}")
        
        return migrated_count
        
    except Exception as e:
        print(f"[ERROR] Failed to migrate actions: {e}")
        return 0


def migrate_sequences():
    """Migrate sequences from single file to individual files"""
    if not OLD_SEQUENCES_FILE.exists():
        print("[INFO] No old sequences.json found, skipping sequences migration")
        return 0
    
    print("[MIGRATE] Reading old sequences.json...")
    
    try:
        with open(OLD_SEQUENCES_FILE, 'r') as f:
            data = json.load(f)
        
        sequences = data.get("sequences", {})
        
        if not sequences:
            print("[INFO] No sequences found in old file")
            return 0
        
        print(f"[MIGRATE] Found {len(sequences)} sequences to migrate")
        
        # Ensure directories exist
        SEQUENCES_DIR.mkdir(parents=True, exist_ok=True)
        
        migrated_count = 0
        
        for sequence_name, sequence_data in sequences.items():
            try:
                # Build new format
                sequence = {
                    "name": sequence_name,
                    "steps": sequence_data.get("steps", []),
                    "loop": sequence_data.get("loop", False),
                    "metadata": {
                        "created": sequence_data.get("created", datetime.now(TIMEZONE).isoformat()),
                        "modified": sequence_data.get("modified", datetime.now(TIMEZONE).isoformat()),
                        "version": "1.0",
                        "file_format": "lerobot_sequence",
                        "step_count": len(sequence_data.get("steps", [])),
                        "migrated_from": "sequences.json"
                    }
                }
                
                # Sanitize filename
                safe_name = sequence_name.lower().replace(" ", "_").replace("/", "_")
                safe_name = "".join(c for c in safe_name if c.isalnum() or c in ['_', '-'])[:50]
                filename = f"{safe_name}.json"
                filepath = SEQUENCES_DIR / filename
                
                # Save
                with open(filepath, 'w') as f:
                    json.dump(sequence, f, indent=2)
                
                print(f"  ✓ Migrated: {sequence_name} -> {filename}")
                migrated_count += 1
                
            except Exception as e:
                print(f"  ✗ Failed to migrate {sequence_name}: {e}")
        
        # Backup old file
        if migrated_count > 0:
            MIGRATION_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup_path = MIGRATION_BACKUP_DIR / f"sequences_{datetime.now(TIMEZONE).strftime('%Y%m%d_%H%M%S')}.json"
            shutil.copy2(OLD_SEQUENCES_FILE, backup_path)
            print(f"[MIGRATE] Backed up old sequences.json to: {backup_path}")
        
        return migrated_count
        
    except Exception as e:
        print(f"[ERROR] Failed to migrate sequences: {e}")
        return 0


def main():
    """Run migration"""
    print("=" * 60)
    print("LeRobotGUI Data Migration")
    print("Converting to robust individual-file format")
    print("=" * 60)
    print()
    
    # Migrate actions
    actions_count = migrate_actions()
    print()
    
    # Migrate sequences
    sequences_count = migrate_sequences()
    print()
    
    # Summary
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Actions migrated:   {actions_count}")
    print(f"Sequences migrated: {sequences_count}")
    print()
    
    if actions_count > 0 or sequences_count > 0:
        print("✓ Migration completed successfully!")
        print()
        print("OLD FILES (preserved as backup):")
        if OLD_ACTIONS_FILE.exists():
            print(f"  - {OLD_ACTIONS_FILE}")
        if OLD_SEQUENCES_FILE.exists():
            print(f"  - {OLD_SEQUENCES_FILE}")
        print()
        print("NEW STRUCTURE:")
        print(f"  - Recordings: {RECORDINGS_DIR}/")
        print(f"  - Sequences:  {SEQUENCES_DIR}/")
        print(f"  - Backups:    {MIGRATION_BACKUP_DIR}/")
        print()
        print("You can now delete the old actions.json and sequences.json files")
        print("or keep them as additional backups.")
    else:
        print("No data to migrate.")
    
    print()


if __name__ == "__main__":
    main()

