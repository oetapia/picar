#!/usr/bin/env python3
"""
Deploy to Raspberry Pi Pico
============================

This script uses mpremote to sync only updated files to the Pico.
It compares file sizes and timestamps to determine what needs updating.

Supports server mode selection:
    - REST mode (default): Uses main.py — HTTP REST API server
    - WebSocket mode: Uses main_ws.py — Low-latency persistent WebSocket

Requirements:
    pip install mpremote

Usage:
    python deploy_to_pico.py [--dry-run] [--force] [--mode rest|ws]

Options:
    --dry-run    Show what would be copied without actually copying
    --force      Copy all files regardless of changes
    --verbose    Show detailed output
    --mode       Server mode: 'rest' (default) or 'ws' (WebSocket)
"""

import subprocess
import os
import sys
import hashlib
import json
from pathlib import Path
from datetime import datetime


class PicoDeployer:
    """Deploy files to Raspberry Pi Pico using mpremote."""

    # Load configuration from pico_files.json
    _config_path = Path(__file__).parent / 'pico_files.json'
    if _config_path.exists():
        with open(_config_path) as _f:
            _PICO_FILES = json.load(_f)
        INCLUDE_FILES = _PICO_FILES['include_files']
        INCLUDE_DIRS = _PICO_FILES['include_dirs']
    else:
        # Fallback
        INCLUDE_FILES = [
            'main.py',
            'main_ws.py',
            'wifi.py',
            'motor3.py',
            'servo.py',
            'gear.py',
            'display.py',
            'lights.py',
            'icons.py',
            'icons.json',
            'vl53l0x_mp.py',
            'config.py',
            'config.example.py',
            'pico_files.json',
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
        'deploy_to_pico.py',  # Tooling — not for the Pico itself
        'sync_branches.py',  # Tooling — not for the Pico itself
    ]

    # Server mode configuration
    MODE_CONFIG = {
        'rest': {
            'main_file': 'main.py',
            'description': 'REST API (HTTP) — traditional request/response',
            'skip_files': ['main_ws.py', 'main_raw.py'],
        },
        'ws': {
            'main_file': 'main_ws.py',
            'description': 'WebSocket (Microdot) — low-latency persistent connection',
            'skip_files': ['main_raw.py'],
            'rename': {'main_ws.py': 'main.py'},
        },
        'raw': {
            'main_file': 'main_raw.py',
            'description': 'Raw WebSocket — lowest latency, no framework',
            'skip_files': ['main_ws.py'],
            'skip_dirs': ['microdot'],
            'rename': {'main_raw.py': 'main.py'},
        },
    }

    def __init__(self, dry_run=False, force=False, verbose=False, mode=None):
        self.dry_run = dry_run
        self.force = force
        self.verbose = verbose
        self.mode = mode  # None means ask interactively
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

    def select_mode(self):
        """Interactive mode selection if not specified via CLI."""
        if self.mode:
            return self.mode

        print()
        print("╔══════════════════════════════════════════════════╗")
        print("║   Select Server Mode for Pico                   ║")
        print("╠══════════════════════════════════════════════════╣")
        print("║                                                  ║")
        print("║  1. REST API (HTTP)                              ║")
        print("║     Traditional request/response server          ║")
        print("║     Best for: webclient.html, casual control     ║")
        print("║                                                  ║")
        print("║  2. WebSocket (Microdot)                         ║")
        print("║     Low-latency persistent connection            ║")
        print("║     Best for: autonomous FSM, fast control       ║")
        print("║                                                  ║")
        print("║  3. Raw WebSocket (no framework)                 ║")
        print("║     Lowest latency, pre-built responses          ║")
        print("║     Best for: real-time control loops             ║")
        print("║                                                  ║")
        print("╚══════════════════════════════════════════════════╝")
        print()

        while True:
            choice = input("Select mode [1=REST, 2=WS, 3=Raw] (default: 1): ").strip()
            if choice in ('', '1'):
                self.mode = 'rest'
                break
            elif choice == '2':
                self.mode = 'ws'
                break
            elif choice == '3':
                self.mode = 'raw'
                break
            else:
                print("  Invalid choice. Enter 1, 2, or 3.")

        config = self.MODE_CONFIG[self.mode]
        print(f"\n  → Mode: {config['description']}")
        print(f"  → Main file on Pico: main.py ← {config['main_file']}")
        print()
        return self.mode

    def list_pico_files(self, path=':'):
        """List files on Pico at given path."""
        stdout, stderr, returncode = self.run_mpremote(f'ls {path}')

        if returncode != 0:
            return []

        files = []
        for line in stdout.strip().split('\n'):
            if line.strip():
                # Parse mpremote ls output
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
                            files.append({'name': line.strip(), 'type': 'unknown'})

        return files

    def should_exclude(self, filepath):
        """Check if file should be excluded."""
        filepath_str = str(filepath)
        for exclude in self.EXCLUDE_FILES:
            if exclude in filepath_str:
                return True
        return False

    def should_skip_for_mode(self, filepath):
        """Check if file should be skipped for the selected mode."""
        if not self.mode:
            return False
        config = self.MODE_CONFIG[self.mode]
        skip_files = config.get('skip_files', [])
        return str(filepath) in skip_files

    def get_remote_path(self, filepath):
        """Get the remote path for a file, applying mode-specific renames."""
        if not self.mode:
            return str(filepath)
        config = self.MODE_CONFIG[self.mode]
        renames = config.get('rename', {})
        filepath_str = str(filepath)
        return renames.get(filepath_str, filepath_str)

    def get_local_files(self):
        """Get list of local files to deploy."""
        files_to_deploy = []

        # Add individual files
        for filename in self.INCLUDE_FILES:
            filepath = Path(filename)
            if filepath.exists() and not self.should_exclude(filepath):
                if not self.should_skip_for_mode(filepath):
                    files_to_deploy.append(filepath)

        # Add files from directories (skip dirs excluded by mode)
        skip_dirs = []
        if self.mode:
            skip_dirs = self.MODE_CONFIG[self.mode].get('skip_dirs', [])

        for dirname in self.INCLUDE_DIRS:
            if dirname in skip_dirs:
                continue
            dirpath = Path(dirname)
            if dirpath.exists() and dirpath.is_dir():
                for filepath in dirpath.rglob('*'):
                    if filepath.is_file() and not self.should_exclude(filepath):
                        files_to_deploy.append(filepath)

        # In WS/raw modes, skip the original main.py (we rename the variant → main.py)
        if self.mode in ('ws', 'raw'):
            files_to_deploy = [f for f in files_to_deploy if str(f) != 'main.py']

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

    def copy_file(self, local_file, remote_name=None):
        """Copy file to Pico."""
        if remote_name:
            remote_path = f':{remote_name}'
        else:
            remote_path = f':{local_file}'

        # Create parent directory if needed
        remote_parent = Path(remote_name if remote_name else str(local_file)).parent
        if remote_parent != Path('.'):
            self.create_remote_dir(str(remote_parent))

        if self.dry_run:
            if remote_name and str(local_file) != remote_name:
                self.log(f"Would copy: {local_file} -> {remote_path} (renamed)", 'info')
            else:
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

        # Select server mode
        self.select_mode()

        # Check connection
        if not self.check_connection():
            return False

        print()

        # Get local files
        self.log("Scanning local files...")
        local_files = self.get_local_files()
        self.log(f"Found {len(local_files)} local files to deploy", 'info')

        config = self.MODE_CONFIG[self.mode]
        self.log(f"Server mode: {config['description']}", 'info')

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

            # Get the remote path (handles renames like main_ws.py → main.py)
            remote_name = self.get_remote_path(local_file)
            remote_size = remote_files.get(remote_name)

            if self.needs_update(local_file, remote_size):
                rename_note = ""
                if remote_name != str(local_file):
                    rename_note = f" → {remote_name}"
                print(f"\n📤 {local_file}{rename_note}")

                if self.copy_file(local_file, remote_name if remote_name != str(local_file) else None):
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
        print(f"Mode:           {config['description']}")
        print(f"Main file:      {config['main_file']} → main.py on Pico")
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
            if self.mode == 'raw':
                print("🎉 Your Pico is ready! Raw WebSocket server will start on boot.")
                print("   Connect with: python client/picar_ws_client.py")
                print("   Note: No path needed — connects to ws://IP:5000 directly")
            elif self.mode == 'ws':
                print("🎉 Your Pico is ready! WebSocket server will start on boot.")
                print("   Connect with: python client/picar_ws_client.py")
            else:
                print("🎉 Your Pico is ready! REST server will start on boot.")
                print("   Connect with: python client/picar_client.py")
            return True
        else:
            self.log("All files up to date - nothing to copy", 'success')
            return True


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Deploy files to Raspberry Pi Pico using mpremote',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Server Modes:
  rest    Traditional HTTP REST API (main.py)
          Best for: webclient.html, casual/manual control

  ws      WebSocket via Microdot (main_ws.py → main.py)
          Best for: autonomous FSM, fast control loops, sensor streaming

  raw     Raw WebSocket, no framework (main_raw.py → main.py)
          Best for: lowest latency real-time control

Examples:
  python deploy_to_pico.py                    # Interactive mode selection
  python deploy_to_pico.py --mode raw         # Deploy raw WS (lowest latency)
  python deploy_to_pico.py --mode ws          # Deploy WebSocket mode
  python deploy_to_pico.py --mode rest        # Deploy REST mode
  python deploy_to_pico.py --mode raw --force # Force full redeploy in raw mode
  python deploy_to_pico.py --dry-run          # Preview what would be deployed
        """
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
    parser.add_argument(
        '--mode',
        choices=['rest', 'ws', 'raw'],
        default=None,
        help='Server mode: rest (HTTP API), ws (WebSocket/Microdot), or raw (lowest latency). Interactive if not specified.'
    )

    args = parser.parse_args()

    deployer = PicoDeployer(
        dry_run=args.dry_run,
        force=args.force,
        verbose=args.verbose,
        mode=args.mode
    )

    success = deployer.deploy()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
