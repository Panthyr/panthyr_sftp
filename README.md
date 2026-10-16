# Panthyr SFTP library

>SFTP library for the Panthyr pan-tilt hyperspectral radiometer.

## Overview

The Panthyr SFTP library provides a simple, Pythonic interface for uploading
files to SFTP servers with automatic upload verification. It uses the system
OpenSSH `sftp` client (no Python dependencies, e.g. for Debian Buster on armv7l)
with SSH key authentication.

## Configuration

Settings are read from `/home/panthyr/data/sftp.env`:

```env
SFTP_SERVER=ftp.example.org
SFTP_PORT=22
SFTP_USER=user
SFTP_KEY_FILE=/home/panthyr/data/sftp_key
SFTP_REMOTE_DIR=TBBE
```

## Usage

```python
from p_sftp import PsFTP

with PsFTP() as client:  # explicit arguments override the env file
    # uploads to /TBBE/2026/file.csv
    client.upload_file('/data/file.csv', '2026/file.csv', max_upload_speed_kb=100)
```

Throttling (`sftp -l`) is only applied when `max_upload_speed_kb` is set.

## Testing the configuration

Run `test_sftp` to log in with the configured key, upload a 50 KB random file
(`test_upload`), report success or failure, and remove the file again.
