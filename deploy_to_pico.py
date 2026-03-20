#!/usr/bin/env python3
"""
Deploy to Raspberry Pi Pico
============================

This script uses mpremote to sync only updated files to the Pico.
It compares file sizes and timestamps to determine what needs updating.

Requirements:
    pip install mpremote

Usage:
    python deploy_to_pico.py [--dry-run] [--force]
    
Options:
    --dry-run    Show what would be copied without actually copying
    --force      Copy all files regardless of changes
    --verbose    Show detailed output
"""

import subprocess
import os
import sys
import hashlib
from pathlib import Path
from datetime import datetime


class PicoDeployer:
    """Deploy files to Raspberry Pi Pico using mpremote."""
    
    # Files and directories to include in deployment
    INCLUDE_FILES = [
        'main.py',
        'wifi.py',
        'motor.py',
        'motor2.py',
        'servo.py',
        'display.py',
        'config.py',
        'lights.py',
        'icons.py',
        'icons.json',
        'vl53l0x_mp.py',
    ]
    
    INCLUDE_DIRS = [
        'microdot',
        'sensors',
    ]
    
    # Files to exclude (even if in included directories)
    EXCLUDE_FILES = [
        '__pycache__',
        '.pyc',
        '.git',
        '.DS_Store',
        'secrets.py',  # Don't sync secrets - must be created manually on Pico
        'secrets-template.py',  # Template, not actual code
    ]
    
    def __init__(self, dry_run=False, force=False, verbose=False):
        self.dry_run = dry_run
        self.force = force
        self.verbose = verbose
        self.stats = {
            'copied': 0,
            'skipped': 0,
            'errors': 0,
            'total': 0
        }
    
    def log(self, message, level='info'):
        """Print log message."""
        prefix = {
            'info': '📋',
            'success': '✅',
            'skip': '⏭️ ',
            'error': '❌',
            'warning': '⚠️ ',
        }.get(level, '  ')
        print(f"{prefix} {message}")
    
    def verbose_log(self, message):
        """Print verbose log message."""
        if self.verbose:
            print(f"   {message}")
    
    def run_mpremote(self, command):
        """Run mpremote command and return output."""
        try:
            result = subprocess.run(
                ['mpremote'] + command.split(),
                capture_output=True,
                text=True,
                check=False
            )
            return result.stdout, result.stderr, result.returncode
        except FileNotFoundError:
            self.log("mpremote not found. Install with: pip install mpremote", 'error')
            sys.exit(1)
    
    def check_connection(self):
        """Check if Pico is connected."""
        self.log("Checking Pico connection...")
        stdout, stderr, returncode = self.run_mpremote('version')
        
        if returncode != 0:
            self.log("Failed to connect to Pico. Is it plugged in?", 'error')
            self.log(f"Error: {stderr}", 'error')
            return False
        
        self.log("Pico connected successfully!", 'success')
        return True
    
    def list_pico_files(self, path=':'):
        """List files on Pico at given path."""
        stdout, stderr, returncode = self.run_mpremote(f'ls {path}')
        
        if returncode != 0:
            return []
        
        files = []
        for line in stdout.strip().split('\n'):
            if line.strip():
                # Parse mpremote ls output
                # Format can vary, but typically: "   123 main.py" or "dir sensors"
                parts = line.strip().split(None, 1)
                if len(parts) >= 2:
                    if parts[0] == 'dir':
                        files.append({'name': parts[1], 'type': 'dir'})
                    else:
                        try:
                            size = int(parts[0])
                            name = parts[1] if len(parts) > 1 else parts[0]
                            files.append({'name': name, 'type': 'file', 'size': size})
                        except ValueError:
                            # Couldn't parse as size, treat as filename
                            files.append({'name': line.strip(), 'type': 'unknown'})
        
        return files
    
    def should_exclude(self, filepath):
        """Check if file should be excluded."""
        filepath_str = str(filepath)
        for exclude in self.EXCLUDE_FILES:
            if exclude in filepath_str:
                return True
        return False
    
    def get_local_files(self):
        """Get list of local files to deploy."""
        files_to_deploy = []
        
        # Add individual files
        for filename in self.INCLUDE_FILES:
            filepath = Path(filename)
            if filepath.exists() and not self.should_exclude(filepath):
                files_to_deploy.append(filepath)
        
        # Add files from directories
        for dirname in self.INCLUDE_DIRS:
            dirpath = Path(dirname)
            if dirpath.exists() and dirpath.is_dir():
                for filepath in dirpath.rglob('*'):
                    if filepath.is_file() and not self.should_exclude(filepath):
                        files_to_deploy.append(filepath)
        
        return sorted(files_to_deploy)
    
    def get_file_hash(self, filepath):
        """Get MD5 hash of local file."""
        md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5.update(chunk)
        return md5.hexdigest()
    
    def needs_update(self, local_file, remote_size=None):
        """Check if local file needs to be copied to Pico."""
        if self.force:
            return True
        
        if not local_file.exists():
            return False
        
        # If we have remote size, compare with local size
        if remote_size is not None:
            local_size = local_file.stat().st_size
            if local_size != remote_size:
                self.verbose_log(f"Size differs: local={local_size}, remote={remote_size}")
                return True
            else:
                self.verbose_log(f"Size matches: {local_size} bytes")
                return False
        
        # No remote file, needs update
        return True
    
    def create_remote_dir(self, remote_path):
        """Create directory on Pico."""
        self.verbose_log(f"Creating directory: {remote_path}")
        stdout, stderr, returncode = self.run_mpremote(f'mkdir :{remote_path}')
        return returncode == 0
    
    def copy_file(self, local_file):
        """Copy file to Pico."""
        remote_path = f':{local_file}'
        
        # Create parent directory if needed
        parent_dir = local_file.parent
        if parent_dir != Path('.'):
            self.create_remote_dir(str(parent_dir))
        
        if self.dry_run:
            self.log(f"Would copy: {local_file} -> {remote_path}", 'info')
            return True
        
        self.verbose_log(f"Copying: {local_file} -> {remote_path}")
        stdout, stderr, returncode = self.run_mpremote(f'cp {local_file} {remote_path}')
        
        if returncode == 0:
            return True
        else:
            self.log(f"Failed to copy {local_file}: {stderr}", 'error')
            return False
    
    def deploy(self):
        """Main deployment function."""
        print("=" * 60)
        print("🚀 Raspberry Pi Pico Deployment Tool")
        print("=" * 60)
        print()
        
        if self.dry_run:
            self.log("DRY RUN MODE - No files will be copied", 'warning')
            print()
        
        # Check connection
        if not self.check_connection():
            return False
        
        print()
        
        # Get local files
        self.log("Scanning local files...")
        local_files = self.get_local_files()
        self.log(f"Found {len(local_files)} local files to check", 'info')
        
        print()
        
        # Get remote files
        self.log("Scanning Pico files...")
        remote_files = {}
        
        # List root files
        for item in self.list_pico_files(':'):
            if item['type'] == 'file':
                remote_files[item['name']] = item.get('size')
        
        # List directory files
        for dirname in self.INCLUDE_DIRS:
            dir_path = f':{dirname}'
            for item in self.list_pico_files(dir_path):
                if item['type'] == 'file':
                    remote_path = f"{dirname}/{item['name']}"
                    remote_files[remote_path] = item.get('size')
        
        self.log(f"Found {len(remote_files)} files on Pico", 'info')
        
        print()
        print("-" * 60)
        print("Syncing files...")
        print("-" * 60)
        
        # Process each local file
        for local_file in local_files:
            self.stats['total'] += 1
            
            remote_size = remote_files.get(str(local_file))
            
            if self.needs_update(local_file, remote_size):
                print(f"\n📤 {local_file}")
                
                if self.copy_file(local_file):
                    self.log(f"Copied successfully", 'success')
                    self.stats['copied'] += 1
                else:
                    self.stats['errors'] += 1
            else:
                if self.verbose:
                    print(f"\n⏭️  {local_file}")
                    self.log("File unchanged, skipping", 'skip')
                self.stats['skipped'] += 1
        
        # Print summary
        print()
        print("=" * 60)
        print("📊 Deployment Summary")
        print("=" * 60)
        print(f"Total files:    {self.stats['total']}")
        print(f"Copied:         {self.stats['copied']}")
        print(f"Skipped:        {self.stats['skipped']}")
        print(f"Errors:         {self.stats['errors']}")
        print()
        
        if self.stats['errors'] > 0:
            self.log("Deployment completed with errors", 'warning')
            return False
        elif self.stats['copied'] > 0:
            self.log("Deployment completed successfully!", 'success')
            print()
            print("🎉 Your Pico is ready! Run main.py to start the server.")
            return True
        else:
            self.log("All files up to date - nothing to copy", 'success')
            return True


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Deploy files to Raspberry Pi Pico using mpremote',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be copied without actually copying'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Copy all files regardless of changes'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed output'
    )
    
    args = parser.parse_args()
    
    deployer = PicoDeployer(
        dry_run=args.dry_run,
        force=args.force,
        verbose=args.verbose
    )
    
    success = deployer.deploy()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
