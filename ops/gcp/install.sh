#!/bin/sh
# Administrator-only provisioning, from a reviewed checkout. Does not change any service or firewall.
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run the installer as root.' >&2; exit 1; }
[ "$#" = 1 ] || { echo 'Usage: sudo sh ops/gcp/install.sh /absolute/deployment-key.pub' >&2; exit 1; }
root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
public=$1
/usr/bin/python3 - "$public" <<'PY'
import re, sys
from pathlib import Path
p = Path(sys.argv[1])
if p.is_symlink() or not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]*)?', p.read_text().strip()):
    raise SystemExit('Expected exactly one dedicated Ed25519 public key.')
PY
if getent passwd deploy >/dev/null; then
    [ -f /var/lib/samescale-deploy/provisioned ] || { echo 'Refusing to alter an unrelated deploy account.' >&2; exit 1; }
else
    useradd --create-home --user-group --shell /bin/sh --comment 'Restricted SameScale deployment' deploy
fi
[ "$(getent passwd deploy | cut -d: -f6)" = /home/deploy ]
[ "$(id -Gn deploy)" = deploy ] || { echo 'Deploy has unexpected supplementary groups.' >&2; exit 1; }
install -d -o root -g root -m 700 /var/lib/samescale-deploy
install -d -o root -g root -m 755 /usr/local/lib/samescale-deploy/ops/gcp
install -o root -g root -m 644 "$root/ops/__init__.py" /usr/local/lib/samescale-deploy/ops/__init__.py
install -o root -g root -m 644 "$root/ops/gcp/__init__.py" /usr/local/lib/samescale-deploy/ops/gcp/__init__.py
install -o root -g root -m 644 "$root/ops/gcp/ci_gate.py" /usr/local/lib/samescale-deploy/ops/gcp/ci_gate.py
install -o root -g root -m 644 "$root/ops/gcp/host.py" /usr/local/lib/samescale-deploy/ops/gcp/host.py
install -o root -g root -m 644 "$root/ops/gcp/gateway.py" /usr/local/lib/samescale-deploy/ops/gcp/gateway.py
install -o root -g root -m 755 "$root/ops/gcp/ssh-entry.sh" /usr/local/lib/samescale-deploy/ssh-entry.sh
install -o root -g root -m 755 "$root/ops/gcp/samescale-deploy" /usr/local/sbin/samescale-deploy
# Root owns the key file/home: deploy cannot add an unrestricted second login key.
chown root:root /home/deploy
chmod 755 /home/deploy
install -d -o root -g root -m 755 /home/deploy/.ssh
{
    printf 'restrict,command="/usr/local/lib/samescale-deploy/ssh-entry.sh" '
    cat "$public"
    printf '\n'
} > /home/deploy/.ssh/authorized_keys
chown root:root /home/deploy/.ssh/authorized_keys
chmod 644 /home/deploy/.ssh/authorized_keys
# Exact SHA argument only: rollback/rehearsal/admin flags cannot be requested with the deploy key.
policy=$(mktemp)
trap 'rm -f "$policy"' EXIT
printf '%s\n' 'deploy ALL=(root) NOPASSWD: /usr/local/sbin/samescale-deploy ^[0-9a-f]{40}$' > "$policy"
visudo -cf "$policy"
install -o root -g root -m 440 "$policy" /etc/sudoers.d/samescale-deploy
install -o root -g root -m 600 /dev/null /var/lib/samescale-deploy/provisioned
printf '%s\n' 'Installed restricted deploy account; no Docker group, general sudo or service changes.'
