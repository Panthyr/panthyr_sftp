"""CLI entry point that tests the SFTP configuration by uploading and removing a file."""

import logging
import os
import sys
import tempfile
from pathlib import Path

from p_sftp.p_sftp import PsFTP, PsFTPError

TEST_FILE_NAME = 'test_upload'
TEST_FILE_SIZE = 50 * 1024


def run() -> int:
    """Upload a 50KB random file using the default env file, report, and remove it."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        local_file = Path(tmp_dir) / TEST_FILE_NAME
        local_file.write_bytes(os.urandom(TEST_FILE_SIZE))

        uploaded = False
        client = None
        try:
            client = PsFTP(verbose=True)
            print(f'Connecting to {client.user}@{client.server}:{client.port} ...')
            client.connect()
            print(f'Uploading {TEST_FILE_NAME} ({TEST_FILE_SIZE} bytes) ...')
            client.upload_file(local_file)
            uploaded = True
            print('SUCCESS: upload completed and verified.')
            result = 0
        except PsFTPError as e:
            print(f'FAILURE: {e}')
            result = 1

        if uploaded and client is not None:
            try:
                client.delete_file(TEST_FILE_NAME)
                print(f'Removed {TEST_FILE_NAME} from the server.')
            except PsFTPError as e:
                print(f'WARNING: could not remove {TEST_FILE_NAME} from the server: {e}')
                result = 1
    return result


def main() -> None:
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(name)s: %(message)s')
    sys.exit(run())


if __name__ == '__main__':
    main()
