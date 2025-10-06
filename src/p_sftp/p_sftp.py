# -*- coding: utf-8 -*-
# vim: ts=4:sw=4:expandtab:cuc:autoindent:ignorecase:colorcolumn=99

__author__ = 'Dieter Vansteenwegen'
__project__ = 'Panthyr SFTP library'
__project_link__ = 'https://waterhypernet.org/equipment/'

import logging
import time
from pathlib import Path
from typing import Optional, Union

import paramiko

log = logging.getLogger(__name__)


# Custom Exceptions
class PSFTPError(Exception):
    """Base exception class for all PSFTP errors."""


class PSFTPConnectionError(PSFTPError):
    """Exception raised when connection to SFTP server fails."""


class PSFTPAuthenticationError(PSFTPError):
    """Exception raised when authentication fails."""


class PSFTPNotConnectedError(PSFTPError):
    """Exception raised when attempting operations without an active connection."""


class PSFTPFileNotFoundError(PSFTPError):
    """Exception raised when a local file is not found."""


class PSFTPInvalidPathError(PSFTPError):
    """Exception raised when path is not a valid file."""


class PSFTPUploadError(PSFTPError):
    """Exception raised when file upload fails."""


class PSFTPVerificationError(PSFTPError):
    """Exception raised when upload verification fails."""


class PSFTP:
    """SFTP client for uploading files to a remote server.

    Args:
        server: The hostname or IP address of the SFTP server
        user: The username for authentication
        password: The password for authentication
        port: The port number for the SFTP server (default: 22)
        max_upload_speed_kb: Maximum upload speed in kilobytes per second (default: None, unlimited)
    """

    def __init__(
        self,
        server: str,
        user: str,
        password: str,
        port: int = 22,
    ):
        self.server = server
        self.user = user
        self.password = password
        self.port = port
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False

    def connect(self) -> None:
        """Establish connection to the SFTP server.

        Raises:
            PSFTPAuthenticationError: If authentication fails
            PSFTPConnectionError: If connection to SFTP server fails
        """
        try:
            log.info(f'Connecting to SFTP server {self.server}:{self.port}')
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self._client.connect(
                hostname=self.server, port=self.port, username=self.user, password=self.password
            )

            self._sftp = self._client.open_sftp()
            log.info(f'Successfully connected to {self.server}')
        except paramiko.AuthenticationException as e:
            msg = f'Authentication failed for {self.user}@{self.server}: {e}'
            log.error(msg)
            raise PSFTPAuthenticationError(msg) from e
        except (paramiko.SSHException, OSError, TimeoutError) as e:
            msg = f'Failed to connect to {self.server}: {e}'
            log.error(msg)
            raise PSFTPConnectionError(msg) from e

    def upload_file(
        self,
        local_path: Union[str, Path],
        remote_path: str,
        auto_connect: bool = True,
        verify: bool = True,
        max_upload_speed_kb: Optional[int] = None,
    ) -> None:
        """Upload a file to the SFTP server.

        Args:
            local_path: Path to the local file to upload
            remote_path: Destination path on the remote server
            auto_connect: Automatically connect if not already connected (default: True)
            verify: Verify the upload after completion (default: True)
            max_upload_speed_kb: Maximum upload speed in KB/s (default: None, unlimited)

        Raises:
            PSFTPFileNotFoundError: If the local file does not exist
            PSFTPInvalidPathError: If the path is not a file
            PSFTPNotConnectedError: If not connected to SFTP server
            PSFTPUploadError: If file upload fails
            PSFTPVerificationError: If upload verification fails
        """
        local_path = Path(local_path)

        if not local_path.exists():
            msg = f'Local file not found: {local_path}'
            raise PSFTPFileNotFoundError(msg)

        if not local_path.is_file():
            msg = f'Path is not a file: {local_path}'
            raise PSFTPInvalidPathError(msg)

        if auto_connect and self._sftp is None:
            self.connect()

        if self._sftp is None:
            msg = 'Not connected to SFTP server. Call connect() first.'
            raise PSFTPNotConnectedError(msg)

        try:
            log.info(f'Uploading {local_path} to {remote_path}')

            if max_upload_speed_kb:
                self._throttled_upload(local_path, remote_path, max_upload_speed_kb)
            else:
                self._sftp.put(str(local_path), remote_path)

            log.info(f'Successfully uploaded {local_path.name}')

            if verify:
                log.info('Verifying upload...')
                self._verify_upload(local_path, remote_path)
                log.info('Upload verification successful')

        except PSFTPVerificationError:
            # Re-raise verification errors as-is
            raise
        except (PSFTPFileNotFoundError, PSFTPInvalidPathError, PSFTPNotConnectedError):
            # Re-raise our custom exceptions as-is
            raise
        except Exception as e:
            msg = f'Failed to upload {local_path}: {e}'
            log.error(msg)
            raise PSFTPUploadError(msg) from e

    def _throttled_upload(self, local_path: Path, remote_path: str, max_speed_kb: int) -> None:
        """Upload a file with bandwidth throttling.

        Args:
            local_path: Path to the local file
            remote_path: Destination path on the remote server
            max_speed_kb: Maximum upload speed in kilobytes per second

        Raises:
            PSFTPNotConnectedError: If not connected to SFTP server
            PSFTPUploadError: For upload errors
        """
        if self._sftp is None:
            msg = 'Not connected to SFTP server.'
            raise PSFTPNotConnectedError(msg)

        chunk_size = 32768  # 32 KB chunks
        max_bytes_per_sec = max_speed_kb * 1024
        chunks_per_sec = max(1, max_bytes_per_sec // chunk_size)
        sleep_time = 1.0 / chunks_per_sec if chunks_per_sec > 0 else 0

        log.debug(
            f'Throttled upload: {max_speed_kb} KB/s, chunk size: {chunk_size} bytes, '
            f'sleep time: {sleep_time:.4f}s per chunk'
        )

        with local_path.open('rb') as local_file, self._sftp.file(remote_path, 'wb') as remote_file:
            bytes_transferred = 0
            start_time = time.time()

            while True:
                chunk_start = time.time()
                chunk = local_file.read(chunk_size)
                if not chunk:
                    break

                remote_file.write(chunk)
                bytes_transferred += len(chunk)

                # Calculate actual speed and sleep if needed
                if sleep_time > 0:
                    elapsed = time.time() - chunk_start
                    if elapsed < sleep_time:
                        time.sleep(sleep_time - elapsed)

            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                actual_speed = (bytes_transferred / 1024) / elapsed_time
                log.debug(
                    f'Upload completed: {bytes_transferred / 1024:.2f} KB in '
                    f'{elapsed_time:.2f}s (avg: {actual_speed:.2f} KB/s)'
                )

    def _verify_upload(self, local_path: Path, remote_path: str) -> bool:
        """Verify that the uploaded file matches the local file.

        Args:
            local_path: Path to the local file
            remote_path: Path to the remote file

        Returns:
            True if verification succeeds

        Raises:
            PSFTPNotConnectedError: If not connected to SFTP server
            PSFTPVerificationError: If verification fails
        """
        if self._sftp is None:
            msg = 'Not connected to SFTP server.'
            raise PSFTPNotConnectedError(msg)

        try:
            remote_stat = self._sftp.stat(remote_path)
            remote_size = remote_stat.st_size
            local_size = local_path.stat().st_size

            log.debug(f'Local size: {local_size}, Remote size: {remote_size}')

            if local_size != remote_size:
                msg = f'File size mismatch: local={local_size}, remote={remote_size}'
                log.error(msg)
                raise PSFTPVerificationError(msg)

            log.info('File size verification passed')

        except PSFTPVerificationError:
            # Re-raise verification errors as-is
            raise
        except Exception as e:
            msg = f'Upload verification failed: {e}'
            log.error(msg)
            raise PSFTPVerificationError(msg) from e
        else:
            return True

    def disconnect(self) -> None:
        """Close the SFTP connection."""
        if self._sftp:
            self._sftp.close()
            log.debug('SFTP connection closed')
        if self._client:
            self._client.close()
            log.debug('SSH client closed')
