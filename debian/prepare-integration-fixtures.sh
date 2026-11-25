#!/usr/bin/env bash
set -euo pipefail
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ntfs-3g samba
for fs in EXT4 NTFS; do
  dir="/media/validation/MIRIVUE_$fs"
  disk="/dev/disk/by-label/MIRIVUE_$fs"
  mounted_at=$(findmnt --noheadings --output TARGET --source "$(readlink -f "$disk")" || true)
  if [[ "$mounted_at" == "$dir" && "$fs" != NTFS ]]; then
    if [[ "$fs" == EXT4 ]]; then sudo chown "$(id -u):$(id -g)" "$dir"; fi
    continue
  fi
  if [[ -n "$mounted_at" ]]; then sudo umount "$disk"; fi
  sudo install -d "$dir"
  if [[ "$fs" == NTFS ]]; then
    # The test NTFS volume belongs to one user. Make its trash visible to GVfs.
    options="uid=$(id -u),gid=$(id -g),dmask=0077,fmask=0177,x-gvfs-trash"
    printf '%s %s ntfs-3g noauto,%s 0 0\n' "$disk" "$dir" "$options" | sudo tee -a /etc/fstab >/dev/null
    sudo mount "$dir"
  else
    sudo mount -t ext4 "$disk" "$dir"
    sudo chown "$(id -u):$(id -g)" "$dir"
  fi
done
df -T /media/validation/MIRIVUE_*
mkdir -p "$HOME/validation-ssh" /tmp/validation-smb
printf 'sftp-fixture\n' > "$HOME/validation-ssh/exemple.txt"
printf 'smb-fixture\n' > /tmp/validation-smb/exemple.txt
ssh-keygen -q -t ed25519 -N '' -f "$HOME/.ssh/id_ed25519"
cat "$HOME/.ssh/id_ed25519.pub" >> "$HOME/.ssh/authorized_keys"
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new validation@127.0.0.1 true
sudo tee /etc/samba/smb.conf >/dev/null <<'SAMBA'
[global]
interfaces = lo
bind interfaces only = yes
map to guest = Bad User
[mirivue]
path = /tmp/validation-smb
guest ok = yes
read only = yes
SAMBA
sudo systemctl restart smbd
