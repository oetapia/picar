# Branch Sync Tool Documentation

## Overview

The `sync_branches.py` script automates syncing commits from the `main` branch to the `production-pico` branch, intelligently handling conflicts by removing non-production files.

## Why This Tool?

When developing on `main`, you might add:
- Test files (`test_*.py`)
- Client applications (`client/`)
- Documentation files
- Development utilities

The `production-pico` branch should only contain files needed to run on the Raspberry Pi Pico. This tool automatically:
- ✅ Cherry-picks commits from main
- ✅ Identifies production vs non-production files
- ✅ Auto-resolves conflicts by removing non-production files
- ✅ Maintains clean git history

## Installation

No installation needed! The script is part of the repository.

```bash
# Make it executable (already done)
chmod +x sync_branches.py
```

## Usage

### Basic Sync (Interactive)

Sync the latest commit from main to production-pico:

```bash
python sync_branches.py
```

This will:
1. Show what files will be synced
2. Ask for confirmation
3. Switch to production-pico branch
4. Cherry-pick the commit
5. Auto-resolve conflicts (remove non-production files)

### Dry Run

See what would be synced without making changes:

```bash
python sync_branches.py --dry-run
```

### Sync Specific Commit

Sync a specific commit by hash:

```bash
python sync_branches.py --commit abc1234
```

### Auto-Resolve Mode

Skip confirmation and automatically resolve all conflicts:

```bash
python sync_branches.py --auto-resolve
```

## File Classification

### Production Files (Synced)
These files are needed on the Pico and will be synced:

**Core Application:**
- `main.py` - Main application
- `wifi.py` - WiFi management
- `motor.py` - Motor control
- `servo.py` - Servo control
- `display.py` - OLED display
- `lights.py` - LED control
- `icons.py`, `icons.json` - Display icons
- `vl53l0x_mp.py` - Sensor driver

**Configuration:**
- `config.example.py` - Config template
- `.gitignore` - Git ignore rules

**Directories:**
- `microdot/` - Web framework
- `sensors/` - Sensor modules (core files only)

**Documentation:**
- `README_PRODUCTION.md` - Production docs
- `CONFIG_MIGRATION.md` - Migration guide
- `deploy_to_pico.py` - Deployment script

### Non-Production Files (Ignored)
These files are development-only and will be automatically removed during sync:

- `client/` - Python client applications
- `test_*.py` - Test scripts
- `*_test.py` - Test scripts  
- `main_long.py` - Development version
- `*_README.md` - Sensor documentation
- `images/` - Image assets
- `screen/` - Screen utilities
- `utemplate/` - Template utilities
- `image_to_icon.py` - Icon converter

## Workflow Examples

### Example 1: Sync Latest Config Change

```bash
# You just updated wifi.py on main branch
git add wifi.py
git commit -m "Updated WiFi retry logic"

# Sync to production-pico
python sync_branches.py
# Review what will be synced
# Press 'y' to confirm
# ✓ wifi.py synced to production-pico
```

### Example 2: Sync Multiple Files

```bash
# You updated sensor code and added tests on main
git add sensors/dual_tof.py sensors/dual_tof_test.py
git commit -m "Improved ToF sensor accuracy"

# Sync to production-pico
python sync_branches.py
# ✓ sensors/dual_tof.py will be synced
# ⊘ sensors/dual_tof_test.py will be ignored (test file)
```

### Example 3: Batch Sync Old Commits

```bash
# Sync a specific older commit
git log --oneline main -10
# Find the commit hash you want: abc1234

python sync_branches.py --commit abc1234 --auto-resolve
```

## Conflict Resolution

### Automatic Resolution

The script automatically resolves conflicts when:
- A file was deleted in production-pico (because it's non-production)
- The same file was modified in main
- Solution: Keep it deleted (remove from sync)

### Manual Resolution Needed

If conflicts occur with production files, you'll see:

```
⚠ Conflicts detected
→ Conflict needs manual resolution: main.py
✗ Manual conflicts detected. Use --auto-resolve to force, or resolve manually.
```

In this case:
1. The script aborts the cherry-pick
2. You need to manually resolve conflicts
3. Or investigate why a production file has conflicts

## Output Colors

The script uses colors for clarity:
- 🟢 **Green**: Success, files being synced
- 🟡 **Yellow**: Warnings, files being ignored
- 🔴 **Red**: Errors, manual action needed
- 🔵 **Blue**: Informational messages
- 🟣 **Cyan**: Progress updates

## Common Scenarios

### Scenario 1: Added New Sensor Module

```bash
# On main branch
git add sensors/new_sensor.py sensors/new_sensor_test.py
git commit -m "Added new sensor support"

# Sync
python sync_branches.py
# ✓ sensors/new_sensor.py → production-pico
# ⊘ sensors/new_sensor_test.py → ignored
```

### Scenario 2: Updated Config System

```bash
# On main branch (already done)
git commit -m "Migrated to config.py"

# Sync
python sync_branches.py
# ✓ config.example.py → synced
# ✓ wifi.py → synced
# ✓ .gitignore → synced
# ⊘ client/picar_client.py → ignored
# ⊘ test_*.py → ignored
```

### Scenario 3: Updated Client Only

```bash
# On main branch
git add client/picar_client.py
git commit -m "Improved client error handling"

# Sync
python sync_branches.py
# ⊘ client/picar_client.py → ignored (non-production)
# ℹ Nothing to sync to production-pico
```

## Troubleshooting

### "You have uncommitted changes"

```bash
# Commit your changes first
git add .
git commit -m "Your changes"

# Or stash them
git stash

# Then run sync
python sync_branches.py
```

### "Failed to switch to production-pico"

```bash
# Make sure branch exists
git branch -a | grep production-pico

# Fetch from remote if needed
git fetch origin production-pico

# Create local branch if missing
git checkout -b production-pico origin/production-pico
```

### "Cherry-pick failed"

If auto-resolution fails:

```bash
# Check what went wrong
git status

# Abort and try manual resolution
git cherry-pick --abort

# Or investigate the specific files
git diff
```

## Tips & Best Practices

1. **Always use --dry-run first** when syncing important commits
   ```bash
   python sync_branches.py --dry-run
   ```

2. **Commit atomically** on main - one logical change per commit makes syncing cleaner

3. **Keep production docs updated** - Update README_PRODUCTION.md when needed

4. **Test on production-pico** after syncing before pushing:
   ```bash
   # After sync, test locally
   git checkout production-pico
   # Upload to Pico and test
   ```

5. **Push both branches** when you're confident:
   ```bash
   git push origin main
   git push origin production-pico
   ```

## Advanced Usage

### Sync Multiple Commits

```bash
# Get list of commits to sync
git log main --oneline | head -5

# Sync them one by one (oldest first)
python sync_branches.py --commit def5678 --auto-resolve
python sync_branches.py --commit abc1234 --auto-resolve
python sync_branches.py --auto-resolve  # Latest
```

### Customize File Rules

Edit `sync_branches.py` and modify:

```python
# Add more production files
PRODUCTION_FILES = {
    'main.py',
    'your_new_file.py',  # Add here
    # ...
}

# Add more non-production patterns
NON_PRODUCTION_PATTERNS = {
    'test_*.py',
    'your_dev_pattern*',  # Add here
    # ...
}
```

## Integration with Git Workflow

### Recommended Workflow

```bash
# 1. Develop on main
git checkout main
# ... make changes ...
git commit -m "Feature X"

# 2. Sync to production
python sync_branches.py

# 3. Test on production-pico
git checkout production-pico
# ... test on actual Pico ...

# 4. Push both branches
git push origin main
git push origin production-pico

# 5. Back to development
git checkout main
```

### Git Aliases

Add to your `.git/config` or `~/.gitconfig`:

```ini
[alias]
    sync-prod = !python sync_branches.py
    sync-dry = !python sync_branches.py --dry-run
```

Then use:
```bash
git sync-prod
git sync-dry
```

## Script Architecture

The script follows this flow:

```
1. Check Prerequisites
   ├─ No uncommitted changes?
   ├─ Valid commit hash?
   └─ Branch exists?

2. Analyze Commit
   ├─ Get changed files
   ├─ Classify: production vs non-production
   └─ Show preview

3. User Confirmation (unless --auto-resolve)

4. Execute Sync
   ├─ Switch to production-pico
   ├─ Cherry-pick commit
   ├─ Detect conflicts
   └─ Auto-resolve (remove non-production files)

5. Report Results
   └─ Success/Failure + next steps
```

## Exit Codes

- `0` - Success
- `1` - Error (uncommitted changes, invalid commit, sync failed)

## Dependencies

- Python 3.6+
- Git 2.0+
- No external Python packages required (uses only stdlib)

## See Also

- `CONFIG_MIGRATION.md` - Details on config.py migration
- `README_PRODUCTION.md` - Production branch documentation
- `deploy_to_pico.py` - Deployment script

## Support

If you encounter issues:
1. Run with `--dry-run` to see what would happen
2. Check `git status` for uncommitted changes
3. Review the conflict files manually
4. Consult this documentation

---

**Happy syncing!** 🚀
