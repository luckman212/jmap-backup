#!/usr/bin/env python3

"""
Back up a Fastmail JMAP mailbox in .eml format

https://nathangrigg.com/2021/08/fastmail-backup/
https://www.fastmail.com/for-developers/integrating-with-fastmail/
https://www.fastmail.com/for-developers/
https://jmap.io/crash-course.html

"""

import argparse
import collections
import datetime as dt
import importlib
import json
import os
import shlex
import string
import subprocess
import sys

ADDITIONAL_MODULES = ["requests"]

# prereqs
for module in ADDITIONAL_MODULES:
    try:
        m = importlib.import_module(module)
        globals()[module] = m
    except ImportError:
        sys.exit(
            f"{module} module could not be loaded, check README for installation requirements"
        )


def str_to_bool(s):
    return s and s.lower() in ["true", "1", "yes", "on"]


Session = collections.namedtuple(
    "Session", "headers account_id api_url download_template"
)
Email = collections.namedtuple("Email", "id blob_id date subject")
DEBUG = str_to_bool(os.getenv("JMAP_DEBUG"))
DEFAULT_NOT_BEFORE = os.getenv("JMAP_NOT_BEFORE", os.getenv("NOT_BEFORE", "2000-01-01"))
DEFAULT_STATE_FILE = "~/.jmapbackup/state.json"
CONNECT_TIMEOUT = 3
READ_TIMEOUT = 20


def dbg(*args, newline=True):
    if not DEBUG:
        return
    s = " ".join(map(str, args))
    if newline:
        print(s, file=sys.stderr)
    else:
        print(s, file=sys.stderr, end="")


def get_session(token):
    headers = {"Authorization": "Bearer " + token}
    r = requests.get(
        "https://api.fastmail.com/.well-known/jmap",
        headers=headers,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
    )
    dbg("Status code (get_session):", r.status_code)
    dbg("Response text (get_session):", r.text)
    [account_id] = list(r.json()["accounts"])
    api_url = r.json()["apiUrl"]
    download_template = r.json()["downloadUrl"]
    return Session(headers, account_id, api_url, download_template)


def query(session, start, end):
    json_request = {
        "using": ["urn:ietf:params:jmap:core", "urn:ietf:params:jmap:mail"],
        "methodCalls": [
            [
                "Email/query",
                {
                    "accountId": session.account_id,
                    "sort": [{"property": "receivedAt", "isAscending": False}],
                    "filter": {
                        "after": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "before": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                    "limit": 50,
                },
                "0",
            ],
            [
                "Email/get",
                {
                    "accountId": session.account_id,
                    "#ids": {
                        "name": "Email/query",
                        "path": "/ids/*",
                        "resultOf": "0",
                    },
                    "properties": ["blobId", "receivedAt", "subject"],
                },
                "1",
            ],
        ],
    }

    dbg("JSON request:", json_request)

    while True:
        response = requests.post(
            session.api_url, json=json_request, headers=session.headers
        )
        dbg("Status code (query):", response.status_code)
        dbg("Response text (query):", response.text)
        if response.status_code == 403:
            sys.exit(
                "Permission denied: Disallowed capabilities: urn:ietf:params:jmap:mail"
            )
        full_response = response.json()

        if any(x[0].lower() == "error" for x in full_response["methodResponses"]):
            sys.exit(f"Error received from server: {full_response!r}")

        response = [x[1] for x in full_response["methodResponses"]]

        if not response[0]["ids"]:
            return

        for item in response[1]["list"]:
            date = dt.datetime.fromisoformat(item["receivedAt"].rstrip("Z"))
            yield Email(item["id"], item["blobId"], date, item["subject"])

        query_request = json_request["methodCalls"][0][1]
        query_request["anchor"] = response[0]["ids"][-1]
        query_request["anchorOffset"] = 1


def email_filename(email):
    subject = (
        email.subject.translate(str.maketrans("", "", string.punctuation))[:50]
        if email.subject
        else ""
    )
    date = email.date.strftime("%Y%m%d_%H%M%S")
    directory = email.date.strftime("%Y-%m")
    filename = f"{date}_{email.id}_{subject.strip()}.eml"
    return directory, filename


def run_if(cmd):
    if cmd:
        if os.path.exists(cmd[0]):
            dbg(f"executing: `{' '.join(cmd)}`")
            subprocess.run(cmd)
        else:
            print(f"invalid command: {cmd}", file=sys.stderr)


def env_or_exit(name):
    value = os.getenv(name)
    if not value:
        sys.exit(f"Error: environment variable '{name}' is required")
    return value


def cmd_from_env(name):
    raw = os.getenv(name, "").strip()
    if not raw:
        return []
    return [os.path.expanduser(part) for part in shlex.split(raw)]


def load_state(state_path):
    if not os.path.exists(state_path):
        return {}
    try:
        with open(state_path, "r") as fh:
            state = json.load(fh)
            if not isinstance(state, dict):
                raise ValueError("state file must contain a JSON object")
            return state
    except Exception as e:
        sys.exit(f"error reading state file '{state_path}': {e}")


def save_state(state_path, state):
    try:
        state_dir = os.path.dirname(state_path)
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)
        with open(state_path, "w") as fh:
            json.dump(state, fh, indent=4)
    except Exception as e:
        sys.exit(f"error writing state file '{state_path}': {e}")


def check_dest_dir(dest_dir, retry=True):
    dir_exists = os.path.exists(dest_dir)
    if retry or dir_exists:
        return dir_exists
    else:
        sys.exit(
            f"Error: destination path '{dest_dir}' does not exist (you may need to mount it?)"
        )


def download_email(session, email, base_dir):
    try:
        directory, filename = email_filename(email)
        full_directory = os.path.join(base_dir, directory)
        if not os.path.exists(full_directory):
            os.makedirs(full_directory)
        full_path = os.path.join(full_directory, filename)

        r = requests.get(
            session.download_template.format(
                accountId=session.account_id,
                blobId=email.blob_id,
                name="email",
                type="application/octet-stream",
            ),
            headers=session.headers,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
        r.raise_for_status()
        with open(full_path, "wb") as fh:
            fh.write(r.content)
        dbg(f"Downloaded {email.id} {email.date.strftime('%Y-%m-%d %H:%M:%S')}")
    except requests.RequestException as e:
        dbg(f"Failed to download {email.id}: {e}")
        return False
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Back up a Fastmail JMAP mailbox in .eml format", add_help=False
    )
    parser.add_argument("-h", "--help", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "-v",
        "--verify",
        action="store_true",
        help="Fully verify backed up emails and redownload if missing",
    )
    parser.add_argument(
        "-o",
        "--open",
        action="store_true",
        help="Open the configured dest_dir in Finder",
    )
    parser.add_argument(
        "-s",
        "--state-file",
        help=f"Path to state file (default: {DEFAULT_STATE_FILE} or JMAP_STATE_FILE)",
        nargs=1,
    )
    args = parser.parse_args()
    if args.help:
        parser.print_help()
        sys.exit(0)

    if args.state_file:
        state_file = os.path.expanduser(args.state_file[0])
    else:
        state_file = os.path.expanduser(
            os.getenv("JMAP_STATE_FILE", DEFAULT_STATE_FILE)
        )
    state = load_state(state_file)

    # load configuration from environment variables
    token = env_or_exit("JMAP_TOKEN")
    dest_dir = os.path.expanduser(env_or_exit("JMAP_DEST_DIR"))
    try:
        delay_hours = int(os.getenv("JMAP_DELAY_HOURS", "24"))
    except ValueError:
        sys.exit("Error: JMAP_DELAY_HOURS must be an integer")
    if delay_hours < 0:
        sys.exit("Error: JMAP_DELAY_HOURS must be >= 0")
    PRE_COMMAND = cmd_from_env("JMAP_PRE_CMD")
    POST_COMMAND = cmd_from_env("JMAP_POST_CMD")

    run_if(PRE_COMMAND)

    check_dest_dir(dest_dir, False)

    if args.open:
        subprocess.run(["open", dest_dir])
        # subprocess.run(POST_COMMAND)
        sys.exit(0)

    # calculate date window
    session = get_session(token)

    end_window = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) - dt.timedelta(
        hours=delay_hours
    )

    not_before_str = os.getenv("JMAP_NOT_BEFORE", DEFAULT_NOT_BEFORE)
    dbg(f"Will not archive email prior to {not_before_str}")
    not_before = dt.datetime.strptime(not_before_str, "%Y-%m-%d").replace(
        tzinfo=dt.timezone.utc
    )

    if args.verify:
        dbg("Verification enabled (this will take longer)")
        start_window = not_before
        last_verify_count = state.get("last_verify_count", None)
    else:
        start_window = state.get("last_end_time")
        if start_window and isinstance(start_window, str):
            start_window = dt.datetime.fromisoformat(start_window)
        else:
            start_window = not_before

    num_results = 0
    num_verified = 0
    failed_downloads = []

    for email in query(session, start_window, end_window):
        directory, filename = email_filename(email)
        full_directory = os.path.join(dest_dir, directory)
        full_path = os.path.join(full_directory, filename)

        if os.path.exists(full_path):
            dbg(f"{full_path} ok")
        else:
            if download_email(session, email, dest_dir):
                num_results += 1
            else:
                failed_downloads.append(email)
                continue

        if args.verify:
            num_verified += 1
            if num_verified % 100 == 0:
                if last_verify_count and last_verify_count > 0:
                    pct = "{:.1f}".format((num_verified / last_verify_count) * 100)
                    dbg(
                        f"\rVerified {pct}% ({num_verified} of {last_verify_count})",
                        newline=False,
                    )
                else:
                    dbg(f"\rVerified {num_verified}", newline=False)
            dbg("\n")

    dbg("Done!")

    # retry failed downloads
    if failed_downloads:
        dbg(f"Retrying {len(failed_downloads)} failed downloads")
        for email in failed_downloads:
            if download_email(session, email, dest_dir):
                num_results += 1
                if args.verify:
                    num_verified += 1
            else:
                dbg(f"Failed to download {email.id} after retry")

    if args.verify:
        print(f"Verified: {num_verified}")
    print(f"Archived: {num_results}")

    if isinstance(end_window, dt.datetime):
        end_window = end_window.strftime("%Y-%m-%dT%H:%M:%SZ")
    state["last_end_time"] = end_window
    if num_verified > 0:
        state["last_verify_count"] = num_verified
    save_state(state_file, state)
    run_if(POST_COMMAND)
