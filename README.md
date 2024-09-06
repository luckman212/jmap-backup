<img src="./icon.png" height="96" />

# jmap-backup

This is a Python program to back up messages from your Fastmail JMAP mailbox.

Based on the amazing [work by Nathan Grigg][1] 🙏

## Prerequisites

- a Fastmail API key (get from https://app.fastmail.com/settings/security/tokens)
- Python 3 (`brew install python3` if you're on macOS)
- Python's `requests` and `pyyaml` modules

To get the required modules, either install them in a virtualenv, or globally with:

```shell
PIP_REQUIRE_VIRTUALENV=false python3 -m pip install --break-system-packages requests pyyaml
```

## Setup

1. Clone this repo (if you don't know how to do that, click the green **Code** button above, then **Download ZIP**)

2. Unzip and copy the `jmap-backup.py` file to a directory in your `$PATH` (I suggest `/usr/local/bin` if you're unsure) and make sure it's executable (`chmod +x jmap-backup.py`)

3. Create a configuration file (YAML) to store your API key, destination directory where the backup will be kept, and other settings. You can create multiple config files to back up different accounts or to keep copies on different storage (local, SMB/NFS etc).

> If you don't specify a config file with the `-c` option, the program will assume a default path of `~/.jmapbackup/fastmail.yml`.

A bare minimum config file should look something like:

```yaml
dest_dir: /Volumes/storage/backups/Fastmail
token: {your_api_key_here e.g. fmu1-xxxxxx...}
```

### Other optional parameters for the config file

- `delay_hours` - back up only messages at least this many hours old
- `not_before`  - cut off time before which messages will not be backed up
- `pre_cmd`     - command (and args) to run prior to execution, most often used to mount some remote storage location such as an SMB or NFS share. It is formatted as an array so you can provide additional args as needed.
- `post_cmd`    - command to run post-execution (e.g. unmount the share)

Example of pre/post commands in config file (`~` will be expanded by Python):

```yml
pre_cmd: [ '/sbin/mount', '-t', 'smbfs', '//luckman212:hunter2@nas/backups', '/mnt/jmap' ]
post_cmd: [ '/sbin/umount', '-t', 'smbfs', '/mnt/jmap' ]
```

When Python saves the configuration, the commands will be "unwrapped" and rewritten in this format (which is also valid)

```yml
pre_cmd:
- /sbin/mount
- -t
- smbfs
- //luckman212:hunter2@nas/backups
- /mnt/jmap
```

## Run

```shell
jmap-backup.py -c ~/.jmapbackup/fastmail.yml
```

Progress messages will be printed to the console. When the job is finished, you should see your messages in the destination directory, organized in folders in `YYYY-MM` format. The individual messages are saved as standard `.eml` format files with the filename made up of a datestamp, messageid and subject.

This is designed to run quickly and often, so running it daily is no problem and should complete within a minute or two. It's a good idea to stick it in your crontab or set up a LaunchAgent to trigger it at regular intervals. I suggest [LaunchControl][3] (no affiliation) if you're on a Mac and don't want to fiddle about with XML files.

## Verification

Every so often, it's a good idea to run the script with the `--verify` argument. This will be slower, but will thoroughly check that every message in your mailbox exists on the filesystem, and will "fill in the blanks" if any are missing.

## Environment Variables

- You can export `JMAP_DEBUG` to `1` to see additional debugging info printed to the console
- You can export `NOT_BEFORE` to override the default of `2000-01-01` or whatever date is specified in the config file

## Good luck

I've been using this script for a few months with good success, but it has been tested on exactly _one_ system! So you may encounter issues. If you do, please [report them][2].

[1]: https://nathangrigg.com/2021/08/fastmail-backup
[2]: https://github.com/luckman212/jmap-backup/issues
[3]: https://www.soma-zone.com/LaunchControl/
