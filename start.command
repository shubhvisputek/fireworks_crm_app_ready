#!/bin/sh
# macOS: double-click this file in Finder to open the Fireworks CRM menu in Terminal.
cd "$(dirname "$0")" || exit 1
./start.sh "$@"
status=$?
printf '\nPress Enter to close this window ...'
read -r _
exit $status
