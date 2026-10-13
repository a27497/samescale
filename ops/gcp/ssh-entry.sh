#!/bin/sh
# Root-owned forced command. No shell, SCP/SFTP, forwarding, admin flags or caller-selected paths.
set -eu
command=${SSH_ORIGINAL_COMMAND-}
sha=${command#deploy }
if [ "$command" = "$sha" ] || [ "${#sha}" -ne 40 ]; then
    echo 'Denied: expected deploy followed by a full commit SHA.' >&2
    exit 2
fi
case "$sha" in
    *[!0-9a-f]*) echo 'Denied: invalid commit SHA.' >&2; exit 2 ;;
esac
exec /usr/bin/sudo -n -- /usr/local/sbin/samescale-deploy "$sha"
