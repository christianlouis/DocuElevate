#!/bin/zsh
set -euo pipefail

if [[ $# -ne 1 ]]; then
  print -u2 "usage: $0 <booted-simulator-udid>"
  exit 64
fi

sdk="$(xcrun --sdk iphonesimulator --show-sdk-path)"
work_dir="${TMPDIR:-/tmp}/docuelevate-share-harness-$$"
mkdir -p "$work_dir"
binary="$work_dir/share-extension-harness"
trap 'rm -r "$work_dir"' EXIT
xcrun swiftc -parse-as-library -sdk "$sdk" -target arm64-apple-ios26.0-simulator -D SHARE_EXTENSION_HARNESS \
  modules/docuelevate-share/ios/ShareViewController.swift -o "$binary"
xcrun simctl spawn "$1" "$binary"
