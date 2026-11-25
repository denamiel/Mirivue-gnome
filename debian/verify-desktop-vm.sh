#!/usr/bin/env bash
set -euo pipefail
image=$1
edition=$2
package_dir=$(realpath -- "$3")
(cd "$package_dir" && sha256sum --check SHA256SUMS)
repo=$PWD
out=$repo/validation-vm
work=$(mktemp -d)
mkdir -p "$out"
case "$image" in
  ubuntu-24.04) url=https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img ;;
  ubuntu-26.04) url=https://cloud-images.ubuntu.com/resolute/current/resolute-server-cloudimg-amd64.img ;;
  debian-13) url=https://cloud.debian.org/images/cloud/trixie/latest/debian-13-generic-amd64.qcow2 ;;
  *) exit 2 ;;
esac
cd "$work"
cleanup() {
  if [[ -f qemu.pid ]]; then kill "$(cat qemu.pid)" 2>/dev/null || true; fi
  cd /
  rm -rf -- "$work"
}
trap cleanup EXIT
curl --fail --show-error --silent --location --retry 3 -o system.img "$url"
qemu-img resize -f qcow2 system.img 18G
ssh-keygen -q -t ed25519 -N '' -f key
cat >user-data <<EOF
#cloud-config
users:
  - name: validation
    groups: [sudo, video, render]
    shell: /bin/bash
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    lock_passwd: true
    ssh_authorized_keys:
      - $(cat key.pub)
ssh_pwauth: false
EOF
cloud-localds seed.img user-data
truncate -s 512M test-usb.img
mkfs.ext4 -q -F -L MIRIVUE_EXT4 test-usb.img
truncate -s 512M test-ntfs.img
mkfs.ntfs --fast --force --label MIRIVUE_NTFS test-ntfs.img
accel=tcg
cpu=max
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
  accel=kvm
  cpu=host
fi
qemu-system-x86_64 -machine "q35,accel=$accel" -cpu "$cpu" -m 6144 -smp 4 \
  -drive file=system.img,if=virtio,format=qcow2 \
  -drive file=seed.img,format=raw,media=cdrom \
  -drive if=none,id=usb,format=raw,file=test-usb.img \
  -drive if=none,id=usb_ntfs,format=raw,file=test-ntfs.img \
  -device qemu-xhci -device usb-storage,drive=usb,removable=on -device usb-storage,drive=usb_ntfs,removable=on \
  -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:2222-:22 \
  -vga virtio -display none -qmp unix:qmp.sock,server=on,wait=off \
  -serial "file:$out/console-serie.log" -daemonize -pidfile qemu.pid
vm=(ssh -i key -p 2222 -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=5
    -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$work/known_hosts" validation@127.0.0.1)
printf 'Machine QEMU démarrée (%s), attente de SSH.\n' "$accel"
ready=false
for ((attempt=0; attempt<100; attempt++)); do
  if "${vm[@]}" true 2>/dev/null; then ready=true; break; fi
  sleep 5
done
if [[ "$ready" != true ]]; then tail -n 80 "$out/console-serie.log"; exit 1; fi
timeout 300 "${vm[@]}" sudo cloud-init status --wait
git -C "$repo" archive HEAD | "${vm[@]}" 'mkdir -p ~/source && tar -x -C ~/source'
tar -C "$package_dir" -cf - . | "${vm[@]}" 'mkdir -p ~/package && tar -x -C ~/package'
set +e
"${vm[@]}" "bash ~/source/debian/verify-desktop-guest.sh '$edition'" 2>&1 | tee "$out/session.log"
guest_result=${PIPESTATUS[0]}
set -e
python3 - "$out/fenetre.ppm" <<'PY'
import json
import socket
import sys

with socket.socket(socket.AF_UNIX) as monitor:
    monitor.settimeout(15)
    monitor.connect("qmp.sock")
    with monitor.makefile("rw", encoding="utf-8") as command:
        json.loads(command.readline())
        for request in (
            {"execute": "qmp_capabilities"},
            {"execute": "screendump", "arguments": {"filename": sys.argv[1]}},
        ):
            command.write(json.dumps(request) + "\n")
            command.flush()
            while True:
                response = json.loads(command.readline())
                if "error" in response:
                    raise RuntimeError(response["error"])
                if "return" in response:
                    break
PY
convert "$out/fenetre.ppm" "$out/fenetre.png"
rm "$out/fenetre.ppm"
exit "$guest_result"
