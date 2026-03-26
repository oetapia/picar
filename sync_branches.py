#!/usr/bin/env python3
"""
Branch Sync Tool for PiCar Project
===================================

This script intelligently syncs commits from main to production-pico branch,
handling conflicts by automatically removing non-production files.

Usage:
    python sync_branches.py [options]

Options:
    --dry-run       Show what would be synced without making changes
    --commit HASH   Sync specific commit (default: latest)
    --auto-resolve  Automatically resolve conflicts by removing non-production files
"""

import subprocess
import sys
import argparse
from pathlib import Path
from typing import List, Set, Tuple

# Production files - these should exist in production-pico branch
PRODUCTION_FILES = {
    # Core application files
    'main.py',
    'wifi.py',
    'motor.py',
    'motor2.py',
    'motor3.py',
    'servo.py',
    'display.py',
    'lights.py',
    'icons.py',
    'icons.json',
    'vl53l0x_mp.py',
    
    # Configuration
    'config.example.py',
    '.gitignore',
    
    # Documentation
    'README_PRODUCTION.md',
    'CONFIG_MIGRATION.md',
    'deploy_to_pico.py',
    
    # Directories
    'microdot/',
    'sensors/',
}

# Non-production files - these should NOT exist in production-pico
NON_PRODUCTION_PATTERNS = {
    'client/',
    'test_*.py',
    '*_test.py', 
    'main_long.py',
    'ACCELEROMETER_README.md',
    'DUAL_TOF_README.md',
    'ULTRASONIC_README.md',
    'images/',
    'screen/',
    'utemplate/',
    'image_to_icon.py',
    'sync_branches.py',
    '*.md',
}


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def run_command(cmd: List[str], check: bool = True) -> Tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)"""
    import os
    env = os.environ.copy()
    env['GIT_EDITOR'] = 'true'  # suppress editor prompts (e.g. cherry-pick --continue)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if check and result.returncode != 0:
            print(f"{Colors.RED}✗ Command failed: {' '.join(cmd)}{Colors.ENDC}")
            print(f"{Colors.RED}  Error: {result.stderr}{Colors.ENDC}")
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        print(f"{Colors.RED}✗ Exception running command: {e}{Colors.ENDC}")
        return 1, "", str(e)


def get_current_branch() -> str:
    """Get the current git branch name"""
    code, stdout, _ = run_command(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    return stdout.strip() if code == 0 else ""


def get_uncommitted_changes() -> List[str]:
    """Get list of uncommitted changes"""
    code, stdout, _ = run_command(['git', 'status', '--porcelain'])
    if code == 0 and stdout:
        return [line.strip() for line in stdout.split('\n') if line.strip()]
    return []


def is_non_production_file(filepath: str) -> bool:
    """Check if a file should NOT be in production-pico"""
    from fnmatch import fnmatch
    
    for pattern in NON_PRODUCTION_PATTERNS:
        if fnmatch(filepath, pattern) or filepath.startswith(pattern.rstrip('/')):
            return True
    return False


def get_commit_files(commit_hash: str) -> List[str]:
    """Get list of files changed in a commit"""
    code, stdout, _ = run_command([
        'git', 'show', '--name-only', '--pretty=format:', commit_hash
    ])
    if code == 0:
        return [f.strip() for f in stdout.split('\n') if f.strip()]
    return []


def cherry_pick_with_auto_resolve(commit_hash: str, auto_resolve: bool = False) -> bool:
    """Cherry-pick a commit and auto-resolve conflicts"""

    # Get commit message
    code, commit_msg, _ = run_command([
        'git', 'log', '--format=%s', '-n', '1', commit_hash
    ])
    commit_msg = commit_msg.strip()

    print(f"\n{Colors.CYAN}📝 Cherry-picking commit {commit_hash}...{Colors.ENDC}")
    print(f"   Message: {commit_msg}")

    # Attempt cherry-pick
    code, stdout, stderr = run_command(['git', 'cherry-pick', commit_hash], check=False)
    
    if code == 0:
        print(f"{Colors.GREEN}✓ Cherry-pick successful (no conflicts){Colors.ENDC}")
        return True
    
    # Check if there are conflicts
    if 'CONFLICT' in stderr or 'CONFLICT' in stdout:
        print(f"{Colors.YELLOW}⚠ Conflicts detected{Colors.ENDC}")
        
        # Get list of conflicted files
        code, status_output, _ = run_command(['git', 'status', '--porcelain'])
        
        files_to_remove = []    # non-production conflicted files to drop
        files_to_take = []      # production conflicted files to take from incoming
        files_to_keep = []      # production conflicts needing manual resolution

        # Conflict status codes: UU=both modified, AA=both added,
        # DU=deleted by us, UD=deleted by them, AU/UA=add conflicts
        CONFLICT_STATUSES = {'UU', 'AA', 'DD', 'DU', 'UD', 'AU', 'UA'}

        for line in status_output.split('\n'):
            if not line.strip():
                continue
            status = line[:2]
            filepath = line[3:].strip()
            if status not in CONFLICT_STATUSES:
                continue
            if is_non_production_file(filepath):
                files_to_remove.append(filepath)
                print(f"   {Colors.YELLOW}→ Will remove (non-production): {filepath}{Colors.ENDC}")
            elif auto_resolve:
                files_to_take.append(filepath)
                print(f"   {Colors.CYAN}→ Will take incoming (auto-resolve): {filepath}{Colors.ENDC}")
            else:
                files_to_keep.append(filepath)
                print(f"   {Colors.RED}→ Conflict needs manual resolution: {filepath}{Colors.ENDC}")

        if files_to_keep:
            print(f"\n{Colors.RED}✗ Manual conflicts detected. Use --auto-resolve to force, or resolve manually.{Colors.ENDC}")
            run_command(['git', 'cherry-pick', '--abort'], check=False)
            return False

        # Remove non-production files
        for filepath in files_to_remove:
            run_command(['git', 'rm', '--force', '-q', filepath], check=False)

        # Take incoming version for production conflicts
        for filepath in files_to_take:
            run_command(['git', 'checkout', '--theirs', filepath], check=False)
            run_command(['git', 'add', filepath], check=False)

        # Stage everything and continue
        run_command(['git', 'add', '.'])
        code, stdout, stderr = run_command(['git', 'cherry-pick', '--continue'], check=False)

        if code == 0:
            print(f"{Colors.GREEN}✓ Cherry-pick completed with auto-resolution{Colors.ENDC}")
            return True

        # Empty commit after resolution (all changes were non-production) — skip it
        if 'nothing to commit' in stdout or 'nothing to commit' in stderr or \
                'now empty' in stderr or 'now empty' in stdout:
            run_command(['git', 'cherry-pick', '--skip'], check=False)
            print(f"{Colors.YELLOW}⊘ Skipped (empty after removing non-production files){Colors.ENDC}")
            return True

        print(f"{Colors.RED}✗ Cherry-pick failed even after auto-resolution{Colors.ENDC}")
        print(f"  stdout: {stdout.strip()}")
        print(f"  stderr: {stderr.strip()}")
        run_command(['git', 'cherry-pick', '--abort'], check=False)
        return False
    
    # Already applied (empty result without explicit CONFLICT)
    if 'nothing to commit' in stdout or 'nothing to commit' in stderr or \
            'now empty' in stderr or 'now empty' in stdout:
        run_command(['git', 'cherry-pick', '--skip'], check=False)
        print(f"{Colors.YELLOW}⊘ Skipped (already applied){Colors.ENDC}")
        return True

    print(f"{Colors.RED}✗ Cherry-pick failed{Colors.ENDC}")
    print(f"  stdout: {stdout.strip()}")
    print(f"  stderr: {stderr.strip()}")
    run_command(['git', 'cherry-pick', '--abort'], check=False)
    return False


def main():
    parser = argparse.ArgumentParser(
        description='Sync commits from main to production-pico branch',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync_branches.py --dry-run
  python sync_branches.py --commit abc1234
  python sync_branches.py --auto-resolve
        """
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be synced without making changes')
    parser.add_argument('--commit', type=str,
                       help='Specific commit hash to sync (default: latest from main)')
    parser.add_argument('--auto-resolve', action='store_true',
                       help='Automatically resolve conflicts by removing non-production files')
    
    args = parser.parse_args()
    
    print(f"{Colors.BOLD}{Colors.HEADER}╔══════════════════════════════════════════════════╗{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}║   PiCar Branch Sync Tool                         ║{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}╚══════════════════════════════════════════════════╝{Colors.ENDC}\n")
    
    # Check for uncommitted changes
    current_branch = get_current_branch()
    uncommitted = get_uncommitted_changes()
    
    if uncommitted:
        print(f"{Colors.RED}✗ You have uncommitted changes. Please commit or stash them first.{Colors.ENDC}")
        print(f"  Current branch: {current_branch}")
        print(f"  Uncommitted files:")
        for change in uncommitted[:5]:
            print(f"    {change}")
        if len(uncommitted) > 5:
            print(f"    ... and {len(uncommitted) - 5} more")
        sys.exit(1)
    
    print(f"{Colors.CYAN}Current branch: {current_branch}{Colors.ENDC}")
    
    # Get commits to sync
    if args.commit:
        commits = [args.commit]
    else:
        # Get all commits in main not yet in production-pico, oldest first
        code, stdout, _ = run_command([
            'git', 'log', 'production-pico..main', '--format=%H', '--reverse'
        ])
        if code != 0 or not stdout.strip():
            print(f"{Colors.GREEN}✓ production-pico is already up to date with main{Colors.ENDC}")
            sys.exit(0)
        commits = [h for h in stdout.strip().split('\n') if h.strip()]

    print(f"{Colors.CYAN}Commits to sync: {len(commits)}{Colors.ENDC}\n")

    for commit_hash in commits:
        # Get commit info
        code, commit_info, _ = run_command([
            'git', 'log', '--format=%H %s', '-n', '1', commit_hash
        ])
        if code != 0:
            print(f"{Colors.RED}✗ Invalid commit: {commit_hash}{Colors.ENDC}")
            sys.exit(1)

        print(f"{Colors.CYAN}Commit: {commit_info.strip()}{Colors.ENDC}")

        files = get_commit_files(commit_hash)
        production_files = [f for f in files if not is_non_production_file(f)]
        non_production_files = [f for f in files if is_non_production_file(f)]

        if production_files:
            print(f"{Colors.GREEN}  ✓ Will sync:{Colors.ENDC}")
            for f in production_files:
                print(f"    • {f}")
        else:
            print(f"  (no production files changed)")

        if non_production_files:
            print(f"{Colors.YELLOW}  ⊘ Will skip (non-production):{Colors.ENDC}")
            for f in non_production_files:
                print(f"    • {f}")
        print()

    if args.dry_run:
        print(f"{Colors.BLUE}ℹ Dry run mode - no changes made{Colors.ENDC}")
        sys.exit(0)

    # Confirm
    if not args.auto_resolve:
        response = input(f"{Colors.BOLD}Proceed with sync of {len(commits)} commit(s)? (y/N): {Colors.ENDC}")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    # Switch to production-pico if not already there
    if current_branch != 'production-pico':
        print(f"\n{Colors.CYAN}🔄 Switching to production-pico branch...{Colors.ENDC}")
        code, _, _ = run_command(['git', 'checkout', 'production-pico'])
        if code != 0:
            print(f"{Colors.RED}✗ Failed to switch to production-pico{Colors.ENDC}")
            sys.exit(1)

    # Cherry-pick all commits that have at least one production file
    for commit_hash in commits:
        files = get_commit_files(commit_hash)
        if not any(not is_non_production_file(f) for f in files):
            continue  # nothing to apply to production-pico
        success = cherry_pick_with_auto_resolve(commit_hash, args.auto_resolve)
        if not success:
            print(f"\n{Colors.RED}{Colors.BOLD}✗ Sync failed at {commit_hash}{Colors.ENDC}")
            print(f"{Colors.YELLOW}You may need to manually resolve conflicts.{Colors.ENDC}")
            sys.exit(1)

    print(f"\n{Colors.GREEN}{Colors.BOLD}✓ Sync completed successfully! ({len(commits)} commit(s)){Colors.ENDC}")
    print(f"\n{Colors.CYAN}Next steps:{Colors.ENDC}")
    print(f"  1. Review changes: git log --oneline -10")
    print(f"  2. Test the changes")
    print(f"  3. Push: git push origin production-pico")
    if current_branch != 'production-pico':
        print(f"  4. Switch back: git checkout {current_branch}")


if __name__ == '__main__':
    main()
