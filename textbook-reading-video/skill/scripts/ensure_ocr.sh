#!/bin/zsh
# Compile (once) the macOS Vision OCR helper and print its path.
# Usage: OCR=$(ensure_ocr.sh); "$OCR" [--chars] img1.png img2.png ...  -> one JSON line per image
# JSON: {"file","W","H","items":[{"t","x","y","w","h","c","chars"?}]}  (normalised, origin bottom-left)
set -e
SRC="${0:A:h}/ocr.swift"
CACHE="${TBV_CACHE:-$HOME/.cache/textbook-reading-video}"
BIN="$CACHE/ocr"
mkdir -p "$CACHE"
if [[ ! -x "$BIN" || "$SRC" -nt "$BIN" ]]; then
  swiftc -O "$SRC" -o "$BIN" >&2
fi
echo "$BIN"
