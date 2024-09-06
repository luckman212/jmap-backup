#!/usr/bin/env python3

"""
Back up messages from a JMAP mailbox (e.g. Fastmail)

https://nathangrigg.com/2021/08/fastmail-backup/
https://www.fastmail.com/for-developers/integrating-with-fastmail/
https://www.fastmail.com/for-developers/
https://jmap.io/crash-course.html

"""

import argparse
import collections
import datetime
import os
import requests
import string
import sys
import subprocess

try:
    import yaml
except ImportError:
    print(f"yaml module could not be loaded: try `pip install pyyaml`")
    exit(1)

Session         = collections.namedtuple('Session', 'headers account_id api_url download_template')
Email           = collections.namedtuple('Email', 'id blob_id date subject')
DEBUG           = os.getenv('JMAP_DEBUG', False)
NOT_BEFORE      = os.getenv('NOT_BEFORE', '2000-01-01')
CONNECT_TIMEOUT = 3
READ_TIMEOUT    = 20
UNMOUNT_ON_EXIT = False
MOUNT_COMMANDS  = {
    'mount':   [ os.path.expanduser('~/Sync/Scripts/smbmount.sh'), '--unattended', '--mount', 'nas/unattended' ],
    'unmount': [ os.path.expanduser('~/Sync/Scripts/smbmount.sh'), '--unmount', 'nas/unattended' ]
}

def dbg(*args, newline=True):
    if not DEBUG:
        return
    s = ' '.join(map(str, args))
    if newline:
        print(s, file=sys.stderr)
    else:
        print(s, file=sys.stderr, end='')

def get_session(token):
    headers = {'Authorization': 'Bearer ' + token}
    r = requests.get('https://api.fastmail.com/.well-known/jmap',
        headers=headers,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    dbg("Status code (get_session):", r.status_code)
    dbg("Response text (get_session):", r.text)
    [account_id] = list(r.json()['accounts'])
    api_url = r.json()['apiUrl']
    download_template = r.json()['downloadUrl']
    return Session(headers, account_id, api_url, download_template)

def query(session, start, end):
    json_request = {
        'using': ['urn:ietf:params:jmap:core', 'urn:ietf:params:jmap:mail'],
        'methodCalls': [
            [
                'Email/query',
                {
                    'accountId': session.account_id,
                    'sort': [{'property': 'receivedAt', 'isAscending': False}],
                    'filter': {
                        'after': start.strftime('%Y-%m-%dT%H:%M:%SZ'),
                        'before': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
                    },
                    'limit': 50,
                },
                '0',
            ],
            [
                'Email/get',
                {
                    'accountId': session.account_id,
                    '#ids': {
                        'name': 'Email/query',
                        'path': '/ids/*',
                        'resultOf': '0',
                    },
                    'properties': ['blobId', 'receivedAt', 'subject'],
                },
                '1',
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
            sys.exit("Permission denied: Disallowed capabilities: urn:ietf:params:jmap:mail")
        full_response = response.json()

        if any(x[0].lower() == 'error' for x in full_response['methodResponses']):
            sys.exit(f'Error received from server: {full_response!r}')

        response = [x[1] for x in full_response['methodResponses']]

        if not response[0]['ids']:
            return

        for item in response[1]['list']:
            date = datetime.datetime.fromisoformat(item['receivedAt'].rstrip('Z'))
            yield Email(item['id'], item['blobId'], date, item['subject'])

        # Set anchor to get the next set of emails.
        query_request = json_request['methodCalls'][0][1]
        query_request['anchor'] = response[0]['ids'][-1]
        query_request['anchorOffset'] = 1

def email_filename(email):
    subject = (
            email.subject.translate(str.maketrans('', '', string.punctuation))[:50]
            if email.subject else '')
    date = email.date.strftime('%Y%m%d_%H%M%S')
    directory = email.date.strftime('%Y-%m')
    filename = f'{date}_{email.id}_{subject.strip()}.eml'
    return directory, filename

def check_dest_dir(dest_dir, retry=True):
    dir_exists = os.path.exists(dest_dir)
    if retry or dir_exists:
        return dir_exists
    else:
        sys.exit(f"Error: destination path '{dest_dir}' does not exist (you may need to mount it?)")

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
                name='email',
                type='application/octet-stream',
            ),
            headers=session.headers,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT)
        )
        r.raise_for_status()
        with open(full_path, 'wb') as fh:
            fh.write(r.content)
        dbg(f'Downloaded {email.id} {email.date.strftime('%Y-%m-%d %H:%M:%S')}')
    except requests.RequestException as e:
        dbg(f"Failed to download {email.id}: {e}")
        return False
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Back up a JMAP mailbox in .eml format', add_help=False)
    parser.add_argument('-h','--help', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('-v','--verify', action='store_true', help='Fully verify backed up emails and redownload if missing')
    parser.add_argument('-o','--open', action='store_true', help='Open the configured dest_dir in Finder')
    parser.add_argument('-c','--config', help='Path to config file', nargs=1)
    args = parser.parse_args()
    if args.help:
        parser.print_help()
        sys.exit(0)
    if not args.config:
        sys.exit(f'you must specify a config file (run with -h for help)')

    cfg_file = os.path.expanduser(args.config[0])
    if not os.path.exists(cfg_file):
        sys.exit(f"Error: configuration file '{cfg_file}' does not exist")
    with open(cfg_file, 'r') as fh:
        config = yaml.safe_load(fh)

    dest_dir = config['dest_dir']
    if not check_dest_dir(dest_dir, True):
        subprocess.run(MOUNT_COMMANDS['mount'])
        check_dest_dir(dest_dir, False)
        UNMOUNT_ON_EXIT = True

    if args.open:
        subprocess.run(['open', dest_dir])
        sys.exit(0)

    #calculate date window
    session = get_session(config['token'])
    delay_hours = config.get('delay_hours', 24)

    end_window = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0) - datetime.timedelta(
        hours=delay_hours
    )

    # On first run, use 'not_before' if set in config (YYYY-MM-DD); otherwise use NOT_BEFORE var
    not_before_str = str(config.get('not_before', NOT_BEFORE))
    dbg(f'Will not archive email prior to {not_before_str}')
    not_before = datetime.datetime.strptime(not_before_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
    
    if args.verify:
        start_window = not_before
        last_verify_count = config.get('last_verify_count', None)
    else:
        start_window = config.get('last_end_time', not_before)

    # Start backup
    num_results = 0
    num_verified = 0
    failed_downloads = []

    for email in query(session, start_window, end_window):
        directory, filename = email_filename(email)
        full_directory = os.path.join(dest_dir, directory)
        full_path = os.path.join(full_directory, filename)

        if os.path.exists(full_path):
            dbg(f'{full_path} ok')
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
                    pct = '{:.1f}'.format((num_verified / last_verify_count) * 100)
                    dbg(f'\rVerified {pct}% ({num_verified} of {last_verify_count})', newline=False)
                else:
                    dbg(f'\rVerified {num_verified}', newline=False)
            dbg('\n')

    dbg('Done!')

    # Retry failed downloads
    if failed_downloads:
        dbg(f'Retrying {len(failed_downloads)} failed downloads')
        for email in failed_downloads:
            if download_email(session, email, dest_dir):
                num_results += 1
                if args.verify:
                    num_verified += 1
            else:
                dbg(f'Failed to download {email.id} after retry')

    if args.verify:
        print(f'Verified: {num_verified}')
    print(f'Archived: {num_results}')

    # Write config
    config['last_end_time'] = end_window
    if num_verified > 0:
        config['last_verify_count'] = num_verified
    with open(cfg_file, 'w') as fh:
        yaml.dump(config, fh)
    if UNMOUNT_ON_EXIT:
        subprocess.run(MOUNT_COMMANDS['unmount'])
