<img src="./icon.png" height="96" />

# jmap-backup

This is a Python program to back up messages from your Fastmail JMAP mailbox.

Based on the amazing [work by Nathan Grigg][1] 🙏

## Prerequisites

- a Fastmail API key (get from https://app.fastmail.com/settings/security/tokens)
- Docker *-or-*
- Python 3 + the `requests` module

To get the module, either install it in a virtualenv, or globally with:

```shell
PIP_REQUIRE_VIRTUALENV=false python3 -m pip install --break-system-packages requests
```

## Setup (run locally)

1. Download the latest [release][4] or clone this repo (if you don't know how to do that, click the green **Code** button above, then **Download ZIP**)

2. Copy the `jmap-backup.py` file to a directory in your `$PATH` (I suggest `/usr/local/bin` if you're unsure) and make sure it's executable (`chmod +x jmap-backup.py`)

3. Export your environment variables. At minimum:

```shell
export JMAP_TOKEN='fmu1-xxxxxx...'
export JMAP_DEST_DIR='/Volumes/storage/backups/Fastmail'
```

4. Finally, start the backup by running

```shell
jmap-backup.py
```

> Backup progress is stored in `~/.jmapbackup/state.json` by default. Override with `JMAP_STATE_FILE` or `--state-file`.

Progress messages will be printed to the console. When the job is finished, you should see your messages in the destination directory, organized in folders in `YYYY-MM` format. The individual messages are saved as standard `.eml` format files with the filename made up of a datestamp, messageid and subject.

This is designed to run quickly and often, so running it daily is no problem and should complete within a minute or two. It's a good idea to stick it in your crontab or set up a LaunchAgent to trigger it at regular intervals. I suggest [LaunchControl][3] (no affiliation) if you're on a Mac and don't want to fiddle about with XML files.

## Setup (Docker)

Some have requested a Docker configuration to make it easier to set up and run, so I'm providing the basic instructions below. I have limited experience creating Docker images, so please make any suggestions or corrections via the [issue tracker][2].

1. Clone the repo on your Docker host

```shell
git clone https://github.com/luckman212/jmap-backup && cd jmap-backup
```

2. Create the directory to persistently store your backups

```shell
mkdir -p backups/Fastmail
```

3. Set your container environment variables (`JMAP_DEST_DIR` should point to your mounted backup path, for example `/backups/Fastmail`).

4. Build the Docker image:

```shell
docker build -t jmap-backup .
```

5. Run it using the command below (adjust the paths as needed!) The first run will take longer. You can tail the logs to see what's happening by running `docker logs -f jmap-backup-1` in another shell.

```shell
docker run --rm \
--name jmap-backup-1 \
-v /root/jmap-backup/backups:/backups \
-v /root/jmap-backup/state:/state \
-e JMAP_TOKEN='fmu1-xxxx...' \
-e JMAP_DEST_DIR='/backups/Fastmail' \
-e JMAP_STATE_FILE='/state/jmap-state.json' \
-e JMAP_DEBUG=true \
jmap-backup
```

## Environment Variables

| Variable           | Required | Description                                                                                                            | Example value                            |
|:------------------ |:-------- |:---------------------------------------------------------------------------------------------------------------------- |:---------------------------------------- |
| `JMAP_TOKEN`       | yes      | Fastmail API token                                                                                                     | `fmu1-xxxx...`                           |
| `JMAP_DEST_DIR`    | yes      | Destination directory for backups                                                                                      | `/backups/Fastmail`                      |
| `JMAP_DELAY_HOURS` | no       | Back up only messages at least this many hours old (default: `24`)                                                    | `24`                                     |
| `JMAP_NOT_BEFORE`  | no       | Cutoff date (`YYYY-MM-DD`) before which messages are skipped (default: `2000-01-01`)                                 | `2018-06-01`                             |
| `JMAP_PRE_CMD`     | no       | Command run before backup starts. Parsed like a shell command.                                                        | `/sbin/mount -t smbfs //user:pw@nas/x /mnt/jmap` |
| `JMAP_POST_CMD`    | no       | Command run after backup finishes. Parsed like a shell command.                                                       | `/sbin/umount -t smbfs /mnt/jmap`        |
| `JMAP_STATE_FILE`  | no       | Path to state file used for incremental runs (default: `~/.jmapbackup/state.json`)                                   | `~/.jmapbackup/state.json`               |
| `JMAP_DEBUG`       | no       | Set to `true`/`1`/`yes`/`on` for debug output                                                                         | `true`                                   |

Example:

```shell
export JMAP_TOKEN='fmu1-xxxx...'
export JMAP_DEST_DIR='/mnt/jmap/Fastmail'
export JMAP_NOT_BEFORE='2020-01-01'
export JMAP_PRE_CMD='/sbin/mount -t smbfs //luckman212:hunter2@nas/backups /mnt/jmap'
export JMAP_POST_CMD='/sbin/umount -t smbfs /mnt/jmap'
jmap-backup.py
```

## Verification

Every so often, it's a good idea to run the script with the additional `--verify` argument. This will be slower, but will thoroughly check that every message in your mailbox exists on the filesystem, and will "fill in the blanks" if any are missing.

## Good luck

I've been using this script for a few months with good success, but it has been tested on exactly _one_ system! So you may encounter issues. If you do, please [report them][2].


[1]: https://nathangrigg.com/2021/08/fastmail-backup
[2]: https://github.com/luckman212/jmap-backup/issues
[3]: https://www.soma-zone.com/LaunchControl/
[4]: https://github.com/luckman212/jmap-backup/releases/latest
