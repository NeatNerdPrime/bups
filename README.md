Bups
====

Simple GUI for [Bup](https://github.com/bup/bup), a very efficient backup system.

![165_bups](https://cloud.githubusercontent.com/assets/506932/5287192/65b80d76-7b2a-11e4-8f80-eafbfaf884cb.png)

# Purposes

I personaly use it to backup my files to a hard disk drive plugged into my ISP box (it's a Livebox).

Features:
* Multiple directories support
* Backup, with a nice progressbar
* Show current backups in your favorite file manager
* Backups on local filesystem or over Samba

![164_settings](https://cloud.githubusercontent.com/assets/506932/5287195/6f092482-7b2a-11e4-869d-f6d87ada0191.png)

# How to use

Just run `bups.py`.

Requires Python 2, GTK3.

Launchers are available in `apps/`

# Configuration

You can edit config with the GUI. You can also manually edit `config/config.json`.

# Old shell scripts

From a terminal:
* Make a backup: `bin/backup.sh`
* Show backups: `bin/fuse.sh`

All config is stored in `bin/mount.sh`:
```bash
BACKUP_DIRS=("/path/to/dir" "/path/to/another/dir") # Dirs to backup
HOST="livebox" # Samba hostname
SHARE="backups" # Samba share
OPTIONS="guest" # Samba options
ENABLE_NOTIFY=1 # Send a notification when making a backup
```
