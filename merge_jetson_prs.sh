#!/bin/bash
#
# Jetson Orin Nano PR Merge Automation Script
# Repository: Girgis1/NiceBotUI
# Date: November 5, 2025
#
# This script automates the merging of Jetson-related PRs in the recommended order
# and closes redundant PRs with appropriate comments.
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    print_error "GitHub CLI (gh) is not installed!"
    print_status "Install with: sudo apt install gh"
    print_status "Or visit: https://cli.github.com/"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    print_error "Not authenticated with GitHub!"
    print_status "Run: gh auth login"
    exit 1
fi

# Repository info
REPO="Girgis1/NiceBotUI"
BRANCH="dev"

print_status "========================================"
print_status "Jetson Orin Nano PR Merge Automation"
print_status "Repository: $REPO"
print_status "Target Branch: $BRANCH"
print_status "========================================"
echo ""

# Create backup branch
print_status "Creating backup branch..."
BACKUP_BRANCH="dev-backup-$(date +%Y%m%d-%H%M%S)"
if gh api repos/$REPO/git/refs/heads/$BRANCH &> /dev/null; then
    gh api repos/$REPO/git/refs \
        -f ref="refs/heads/$BACKUP_BRANCH" \
        -f sha="$(gh api repos/$REPO/git/refs/heads/$BRANCH --jq .object.sha)" &> /dev/null || true
    print_success "Backup branch created: $BACKUP_BRANCH"
else
    print_warning "Could not create backup branch (non-critical)"
fi
echo ""

# Function to merge PR
merge_pr() {
    local PR_NUM=$1
    local DESCRIPTION=$2
    
    print_status "Merging PR #$PR_NUM: $DESCRIPTION"
    
    if gh pr merge $PR_NUM --repo $REPO --merge --delete-branch --body "✅ $DESCRIPTION"; then
        print_success "PR #$PR_NUM merged successfully!"
        return 0
    else
        print_error "Failed to merge PR #$PR_NUM"
        return 1
    fi
}

# Function to close PR
close_pr() {
    local PR_NUM=$1
    local REASON=$2
    
    print_status "Closing PR #$PR_NUM: $REASON"
    
    if gh pr close $PR_NUM --repo $REPO --comment "🚫 Closing: $REASON"; then
        print_success "PR #$PR_NUM closed"
        return 0
    else
        print_warning "Failed to close PR #$PR_NUM (may already be closed)"
        return 1
    fi
}

# Main merge sequence
print_status "Starting merge sequence..."
echo ""
sleep 2

# PHASE 1: Core Jetson Support
print_status "📦 PHASE 1: Core Jetson Support"
print_status "================================"
echo ""

# PR #53: Foundation
if merge_pr 53 "Core Jetson support with GPU detection, system package management, and Jetson platform helper"; then
    print_success "✓ Foundation merged (PR #53)"
else
    print_error "✗ Failed to merge foundation (PR #53)"
    print_error "Aborting merge sequence. Please resolve conflicts manually."
    exit 1
fi
echo ""
sleep 3

# PR #48: Camera Support
print_status "Merging camera compatibility..."
if merge_pr 48 "CSI camera support with NVArgus pipelines and GStreamer integration"; then
    print_success "✓ Camera support merged (PR #48)"
else
    print_warning "⚠ PR #48 may have conflicts. Check manually."
    print_status "Continuing with remaining PRs..."
fi
echo ""
sleep 3

# PR #51: Pipeline Optimizations
print_status "Merging pipeline optimizations..."
if merge_pr 51 "GStreamer pipeline detection and low-latency buffer optimizations"; then
    print_success "✓ Pipeline optimizations merged (PR #51)"
else
    print_warning "⚠ PR #51 may have conflicts. Check manually."
    print_status "Continuing with remaining PRs..."
fi
echo ""
sleep 2

# PHASE 2: Setup Automation
print_status "📦 PHASE 2: Setup Automation"
print_status "============================="
echo ""

# PR #55: Setup automation
print_status "Merging setup automation..."
if merge_pr 55 "Automated Jetson setup with platform detection and dependency bootstrapping"; then
    print_success "✓ Setup automation merged (PR #55)"
else
    print_warning "⚠ PR #55 may have conflicts. Check manually."
fi
echo ""
sleep 2

# PHASE 3: Close Redundant PRs
print_status "📦 PHASE 3: Closing Redundant PRs"
print_status "=================================="
echo ""

close_pr 49 "Functionality covered by #53 and #48. V4L2 forcing would break non-Linux platforms."
sleep 1

close_pr 50 "Superseded by #55 which has better integration with setup.sh. SSH -t flag issue noted."
sleep 1

close_pr 52 "Superseded by #55. Batch wrapper path resolution issues noted."
sleep 1

close_pr 54 "Superseded by #55 which is more streamlined."
sleep 1

echo ""
print_status "========================================"
print_success "Merge sequence completed!"
print_status "========================================"
echo ""

# Summary
print_status "📊 SUMMARY"
print_status "==========="
print_status "Merged PRs:"
print_status "  • PR #53: Jetson optimization (GPU, system packages, platform helper)"
print_status "  • PR #48: Camera compatibility (CSI, NVArgus, GStreamer)"
print_status "  • PR #51: Pipeline optimizations (low-latency, detection)"
print_status "  • PR #55: Setup automation (one-click Jetson setup)"
echo ""
print_status "Closed PRs:"
print_status "  • PR #49: Redundant (covered by #53 + #48)"
print_status "  • PR #50: Superseded by #55"
print_status "  • PR #52: Superseded by #55"
print_status "  • PR #54: Superseded by #55"
echo ""
print_status "Backup branch: $BACKUP_BRANCH"
echo ""

# Post-merge instructions
print_status "📋 NEXT STEPS"
print_status "============="
print_status "1. Pull latest changes:"
print_status "   git checkout $BRANCH && git pull origin $BRANCH"
echo ""
print_status "2. Test on Jetson Orin Nano:"
print_status "   ./setup.sh"
print_status "   python test_device_discovery.py"
print_status "   python app.py"
echo ""
print_status "3. Verify critical features:"
print_status "   • GPU detection (should show cuda:0)"
print_status "   • CSI camera detection"
print_status "   • GStreamer pipeline functionality"
print_status "   • Safety monitor GPU inference"
echo ""
print_status "4. If issues occur, rollback with:"
print_status "   git checkout $BACKUP_BRANCH"
print_status "   git push origin $BRANCH --force (⚠️  use with caution)"
echo ""

print_success "🎉 Jetson integration complete!"
print_status "Review JETSON_MERGE_PLAN.md for detailed documentation."
echo ""

