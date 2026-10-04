#!/bin/sh
# Install the external OpenClaw plugins this setup needs, pinned to the Gateway version.
# Idempotent: an already installed plugin is kept. Runs inside the openclaw-init container.
set -eu
VERSION="${OPENCLAW_PLUGIN_VERSION:-2026.9.6}"
for plugin in discord whatsapp diagnostics-otel; do
  if openclaw plugins list 2>/dev/null | grep -q " ${plugin} "; then
    echo "plugin ${plugin}: already installed"
  else
    echo "plugin ${plugin}: installing @openclaw/${plugin}@${VERSION}"
    openclaw plugins install "npm:@openclaw/${plugin}@${VERSION}"
  fi
done
openclaw config validate
