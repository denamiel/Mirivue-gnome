#!/usr/bin/env bash
set -euo pipefail
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ntfs-3g samba
for fs in EXT4 NTFS; do
  dir="/media/validation/MIRIVUE_$fs"
  sudo install -d "$dir"
  disk="/dev/disk/by-label/MIRIVUE_$fs"
  if findmnt --mountpoint "$dir" >/dev/null; then
    continue
  fi
  if [[ "$fs" == NTFS ]]; then
    sudo mount -t ntfs-3g -o "uid=$(id -u),gid=$(id -g),umask=022" "$disk" "$dir"
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
