#!/bin/bash
set -euo pipefail

# systemd-oomd setup for Rocky Linux 9 / RHEL 9
# Prevents system freezes from runaway memory consumers (e.g. clangd)
# Requires: root, reboot after running

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[[ $EUID -eq 0 ]] || error "This script must be run as root (use sudo)"

# ── 1. Install systemd-oomd ──────────────────────────────────────────
info "Installing systemd-oomd..."
if rpm -q systemd-oomd &>/dev/null; then
    info "systemd-oomd is already installed"
else
    dnf install -y systemd-oomd
fi

# ── 2. Enable PSI kernel parameter ───────────────────────────────────
# RHEL/Rocky 9 use BootLoader Spec (BLS, GRUB_ENABLE_BLSCFG=true): the kernel
# command line lives in the per-kernel `options` line of /boot/loader/entries/*.conf.
# Editing /etc/default/grub + grub2-mkconfig does NOT update those entries, so the
# param silently fails to take effect after reboot. `grubby` edits the BLS entries
# directly, which is what the bootloader actually reads.
info "Checking PSI kernel boot parameter..."

command -v grubby &>/dev/null || error "grubby not found (expected on RHEL/Rocky 9)"

if grep -q 'psi=1' /proc/cmdline; then
    info "PSI is already active in the running kernel"
elif grubby --info=DEFAULT 2>/dev/null | grep -q 'psi=1'; then
    warn "psi=1 is already staged in the boot entry but not active yet (reboot required)"
else
    info "Adding psi=1 to all kernel boot entries via grubby..."
    grubby --update-kernel=ALL --args="psi=1"
    warn "psi=1 added — REBOOT REQUIRED for PSI to take effect"
fi

# ── 3. Configure oomd.conf ────────────────────────────────────────────
info "Writing /etc/systemd/oomd.conf..."
cat > /etc/systemd/oomd.conf <<'EOF'
[OOM]
SwapUsedLimit=90%
DefaultMemoryPressureLimit=60%
DefaultMemoryPressureDurationSec=20s
EOF

# ── 4. Enable and start systemd-oomd ─────────────────────────────────
info "Enabling and starting systemd-oomd..."
systemctl enable --now systemd-oomd

# ── 5. Verify ────────────────────────────────────────────────────────
echo ""
info "=== Verification ==="
echo ""

echo "── systemd-oomd status ──"
systemctl is-active systemd-oomd && info "Service is running" || warn "Service is not running (may need reboot for PSI)"

echo ""
echo "── PSI status ──"
if [[ -f /proc/pressure/memory ]]; then
    info "PSI is active:"
    cat /proc/pressure/memory
else
    warn "PSI is NOT active yet — reboot required"
fi

echo ""
echo "── oomd.conf ──"
cat /etc/systemd/oomd.conf

echo ""
echo "── Kernel boot args (default entry) ──"
grubby --info=DEFAULT 2>/dev/null | grep '^args=' || warn "could not read grubby default entry"

echo ""
if grep -q 'psi=1' /proc/cmdline; then
    info "All done. systemd-oomd is fully operational."
else
    warn "IMPORTANT: Reboot the server to activate PSI and complete setup."
    warn "After reboot, verify with:"
    echo "  cat /proc/pressure/memory"
    echo "  systemctl status systemd-oomd"
fi
