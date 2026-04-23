#!/usr/bin/env bash
# Apply SafeChat branding on top of the sync branch.
# Run this after merging upstream into sync, then commit the result to main.
#
# Usage: ./rebrand.sh [--dry-run]
#
# Replaces only USER-VISIBLE strings. Internal Django app names (zerver,
# zilencer), system user references in puppet, and DB migration files are
# intentionally left unchanged to keep upstream merges conflict-free.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# shellcheck source=../branding/config.sh
source "../branding/config.sh"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  echo "[dry-run] showing what would change, no files modified"
fi

s() {
  # s <file> <old> <new>
  if $DRY_RUN; then
    grep -n "$2" "$1" | sed "s|^|$1: |" || true
  else
    sed -i '' "s|$2|$3|g" "$1"
  fi
}

echo "==> Applying branding: $BRAND_NAME ($BRAND_DOMAIN)"

# ── Page titles ───────────────────────────────────────────────────────────────

echo "  templates/zerver/base.html"
s templates/zerver/base.html \
  '- Zulip</title>' \
  "- $BRAND_NAME</title>"

echo "  templates/zerver/portico-header.html"
s templates/zerver/portico-header.html \
  "alt=\"{{ _('Zulip') }}\"" \
  "alt=\"{{ _('$BRAND_NAME') }}\""
s templates/zerver/portico-header.html \
  "aria-label=\"{{ _('Zulip') }}\"" \
  "aria-label=\"{{ _('$BRAND_NAME') }}\""

# ── Email sender names ────────────────────────────────────────────────────────

echo "  zerver/lib/send_email.py"
s zerver/lib/send_email.py \
  'from_name = "Zulip"' \
  "from_name = \"$BRAND_NAME\""

echo "  zerver/lib/email_notifications.py"
s zerver/lib/email_notifications.py \
  'reply_to_name = "Zulip"' \
  "reply_to_name = \"$BRAND_NAME\""
s zerver/lib/email_notifications.py \
  'why_zulip="https://zulip.com/why-zulip/"' \
  "why_zulip=\"https://$BRAND_DOMAIN/why/\""

# ── Settings ──────────────────────────────────────────────────────────────────

echo "  zproject/default_settings.py"
s zproject/default_settings.py \
  '"Zulip Administrator"' \
  "\"$BRAND_ADMIN_NAME\""

# ── Realm model: default discussion channel name ──────────────────────────────

echo "  zerver/models/realms.py"
s zerver/models/realms.py \
  'ZULIP_DISCUSSION_CHANNEL_NAME = gettext_lazy("Zulip")' \
  "ZULIP_DISCUSSION_CHANNEL_NAME = gettext_lazy(\"$BRAND_NAME\")"

# ── Error pages: status page link ─────────────────────────────────────────────

echo "  templates/500.html"
s templates/500.html \
  'https://status.zulip.com/' \
  "$BRAND_STATUS_URL"

# ── Web app: hardcoded contact/help links ─────────────────────────────────────

echo "  web/src/tippyjs.ts"
s web/src/tippyjs.ts \
  'sales@zulip.com' \
  "$BRAND_SALES_EMAIL"

echo "  web/src/navbar_alerts.ts"
s web/src/navbar_alerts.ts \
  'https://zulip.com/help/demo-organizations' \
  "$BRAND_HELP_URL/demo-organizations"

# ── Email templates: broad phrase replacements ───────────────────────────────
# Only phrase-level replacements, not individual words, to avoid
# touching internal identifiers like "Zulip client" detection strings.

echo "  templates/zerver/emails/"
find templates/zerver/emails -name "*.html" -o -name "*.txt" | while read -r f; do
  s "$f" 'Zulip organization'  "$BRAND_NAME organization"
  s "$f" 'Zulip Cloud Standard' "$BRAND_NAME Standard"
  s "$f" 'Zulip Cloud'         "$BRAND_NAME"
  s "$f" 'your Zulip'          "your $BRAND_NAME"
  s "$f" 'Your Zulip'          "Your $BRAND_NAME"
done

# ── Static assets ─────────────────────────────────────────────────────────────

echo "  static assets"
BRANDING_DIR="$SCRIPT_DIR/../branding"

copy_if_exists() {
  local src="$BRANDING_DIR/$1" dst="$2"
  if [ -f "$src" ] && ! $DRY_RUN; then
    cp "$src" "$dst"
    echo "  copied $1 → $2"
  elif [ -f "$src" ]; then
    echo "  [dry-run] would copy $1 → $dst"
  else
    echo "  [skip] branding/$1 not found"
  fi
}

copy_if_exists "logo-icon.svg"    "static/images/logo/zulip-icon-square.svg"
copy_if_exists "logo-icon.svg"    "static/images/logo/zulip-icon-circle.svg"
copy_if_exists "logo-full.svg"    "static/images/logo/zulip-org-logo.svg"
copy_if_exists "favicon.svg"      "static/images/favicon.svg"
copy_if_exists "favicon.png"      "static/images/favicon.png"
copy_if_exists "email-logo.png"   "static/images/emails/email_logo.png"
copy_if_exists "apple-touch-icon.png" "static/images/logo/apple-touch-icon-precomposed.png"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "Branding applied. Required follow-up steps:"
echo "  1. Place brand assets in ../branding/ (see ../branding/README.md)"
echo "  2. Disable or remove templates/corporate/ (Zulip.com marketing pages)"
echo "  3. Update zproject/prod_settings.py with your domain and email config"
echo "  4. Run the Django management command to update the default realm name"
