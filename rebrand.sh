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

# Replace inline Zulip SVG wordmark with brand logo from branding/logo-full.svg
echo "  templates/zerver/portico-header.html (inline SVG → brand logo)"
BRAND_LOGO_SVG="$SCRIPT_DIR/../branding/logo-full.svg"
if [ -f "$BRAND_LOGO_SVG" ]; then
  if $DRY_RUN; then
    echo "  [dry-run] would replace inline Zulip SVG with $BRAND_LOGO_SVG"
  else
    python3 - templates/zerver/portico-header.html "$BRAND_LOGO_SVG" "$BRAND_NAME" <<'PYEOF'
import sys, re

template_path, brand_svg_path, brand_name = sys.argv[1], sys.argv[2], sys.argv[3]

with open(template_path) as f:
    content = f.read()

with open(brand_svg_path) as f:
    brand_svg = f.read()

inner = re.sub(r'^<svg[^>]*>', '', brand_svg.strip(), count=1)
inner = inner[:inner.rfind('</svg>')].strip()

# Use a tight viewBox that crops the whitespace in logo-full.svg (content
# spans roughly x=125-1365, y=15-355 in the original 0 0 1450.33 441.34 space)
viewbox = '125 15 1240 340'

aria_match = re.search(r'aria-label="([^"]*)"', content)
aria_label = aria_match.group(1) if aria_match else "{{ _('" + brand_name + "') }}"

new_svg = (
    '<svg class="brand-logo" role="img" aria-label="' + aria_label + '" '
    'xmlns="http://www.w3.org/2000/svg" viewBox="' + viewbox + '" height="25">\n'
    '                        ' + inner + '\n'
    '                    </svg>'
)

new_content = re.sub(
    r'<svg class="brand-logo".*?</svg>',
    lambda m: new_svg,
    content,
    flags=re.DOTALL,
)

with open(template_path, 'w') as f:
    f.write(new_content)
PYEOF
  fi
else
  echo "  [skip] branding/logo-full.svg not found"
fi

# ── OG thumbnail ──────────────────────────────────────────────────────────────

echo "  templates/zerver/meta_tags.html (og:image)"
s templates/zerver/meta_tags.html \
  "static('images/logo/zulip-icon-128x128.png')" \
  "static('images/favicon.png')"

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

# ── About dialog (web/templates/about_zulip.hbs) ─────────────────────────────
# .hbs files are not covered by the broad template sweep, so patch explicitly.

echo "  web/templates/about_zulip.hbs"
s web/templates/about_zulip.hbs \
  'href="https://zulip.com"' \
  "href=\"https://$BRAND_DOMAIN\""
s web/templates/about_zulip.hbs \
  "alt=\"{{t 'Zulip' }}\"" \
  "alt=\"{{t '$BRAND_NAME' }}\""
s web/templates/about_zulip.hbs \
  'Zulip Server' \
  "$BRAND_NAME"

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

# ── Comprehensive sweep ───────────────────────────────────────────────────────
# Catches everything the surgical replacements above missed.
#
# PO files:  msgstr lines only — msgid (source keys) stay as "Zulip" so the
#            translation lookup chain still resolves correctly.
# Templates: broad replace — "Zulip" in HTML is always the brand name.
# Python:    quoted string literals only — leaves class names (ZulipApp etc.)
#            and import paths untouched.
# TypeScript: same as Python.
#
# Excluded: migrations (DB schema), puppet (system user/paths), .git, *.mo

echo "  locale/ — $(find locale -name '*.po' | wc -l | tr -d ' ') PO files (msgstr only)"

PO_SCRIPT='
import sys
path, brand = sys.argv[1], sys.argv[2]
lines = open(path).readlines()
result = []
in_msgstr = False
for line in lines:
    if line.startswith("msgstr"):
        in_msgstr = True
        result.append(line.replace("Zulip", brand))
    elif line.startswith("msgid"):
        in_msgstr = False
        result.append(line)
    elif in_msgstr and line.startswith("\""):
        result.append(line.replace("Zulip", brand))
    else:
        in_msgstr = False
        result.append(line)
open(path, "w").writelines(result)
'

find locale -name "*.po" | while read -r po; do
    if $DRY_RUN; then
        echo "  [dry-run] $po"
    else
        python3 -c "$PO_SCRIPT" "$po" "$BRAND_NAME"
    fi
done

echo "  templates/ — HTML and text files"
find templates -type f \( -name "*.html" -o -name "*.txt" \) | while read -r f; do
    s "$f" 'Zulip' "$BRAND_NAME"
done

echo "  Python source — quoted string literals (migrations excluded)"
find zerver zilencer analytics corporate -name "*.py" \
    -not -path "*/migrations/*" | while read -r f; do
    s "$f" '"Zulip"'  "\"$BRAND_NAME\""
    s "$f" "'Zulip'"  "'$BRAND_NAME'"
done

echo "  TypeScript/JavaScript — quoted string literals"
find web/src -type f \( -name "*.ts" -o -name "*.js" \) | while read -r f; do
    s "$f" '"Zulip"'  "\"$BRAND_NAME\""
    s "$f" "'Zulip'"  "'$BRAND_NAME'"
done

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "Branding applied. Required follow-up steps:"
echo "  1. Place brand assets in ../branding/ (see ../branding/README.md)"
echo "  2. Disable or remove templates/corporate/ (Zulip.com marketing pages)"
echo "  3. Update zproject/prod_settings.py with your domain and email config"
echo "  4. Run the Django management command to update the default realm name"
