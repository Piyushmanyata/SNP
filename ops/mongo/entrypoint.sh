#!/bin/sh
set -eu

keyfile=/data/configdb/keyfile
if [ ! -s "$keyfile" ]; then
  head -c 756 /dev/urandom | base64 > "$keyfile"
  chmod 400 "$keyfile"
  chown 999:999 "$keyfile"
fi

exec docker-entrypoint.sh "$@"
