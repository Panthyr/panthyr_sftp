# -*- coding: utf-8 -*-
# vim: ts=4:sw=4:expandtab:cuc:autoindent:ignorecase:colorcolumn=99

__author__ = 'Dieter Vansteenwegen'
__project__ = 'Panthyr SFTP library'
__project_link__ = 'https://waterhypernet.org/equipment/'

import logging
import socket
import time
from pathlib import Path
from typing import Optional, Union

import paramiko

log = logging.getLogger(__name__)


# ============================================================================
# Custom Exceptions
# ============================================================================


class PsFTPError(Exception):
    """Base exception class for all PsFTP errors."""


class PsFTPConnectionError(PsFTPError):
    """Exception raised when connection to SFTP server fails."""


class PsFTPAuthenticationError(PsFTPError):
    """Exception raised when authentication fails."""


class PsFTPNotConnectedError(PsFTPError):
    """Exception raised when attempting operations without an active connection."""


class PsFTPFileNotFoundError(PsFTPError):
    """Exception raised when a local file is not found."""


class PsFTPInvalidPathError(PsFTPError):
    """Exception raised when path is not a valid file."""


class PsFTPUploadError(PsFTPError):
    """Exception raised when file upload fails."""


class PsFTPVerificationError(PsFTPError):
    """Exception raised when upload verification fails."""


# ============================================================================
# Main SFTP Client Class
# ============================================================================


class PsFTP:
    """SFTP client for uploading files to a remote server.

    Supports atomic uploads, bandwidth throttling, automatic verification,
    and configurable timeouts with TCP keepalive.

    Features:
        - Atomic uploads (temporary file + rename after verification)
        - Bandwidth throttling (configurable KB/s limit)
        - Automatic file size verification
        - Configurable connection and socket timeouts
        - TCP keepalive for long-running connections
        - Automatic remote directory creation
        - Comprehensive error handling with custom exceptions

    Example:
        >>> with PsFTP('server.com', 'user', 'pass') as client:
        ...     client.upload_file('file.txt', '/remote/file.txt', max_upload_speed_kb=100)
    """

    def __init__(
        self,
        server: str,
        user: str,
        password: str,
        port: int = 22,
        timeout: int = 20,
    ) -> None:
        """Initialize PsFTP client.

        Args:
            server: The hostname or IP address of the SFTP server
            user: The username for authentication
            password: The password for authentication
            port: The port number for the SFTP server (default: 22)
            timeout: Connection and socket timeout in seconds (default: 20)
        """
        self.server = server
        self.user = user
        self.password = password
        self.port = port
        self.timeout = timeout
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None

    def __enter__(self) -> 'PsFTP':
        """Context manager entry.

        Returns:
            Self instance for use in with statement
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised

        Returns:
            False to propagate any exception
        """
        self.disconnect()
        return False

    # ========================================================================
    # Connection Management
    # ========================================================================

    def connect(self) -> None:
        """Establish connection to the SFTP server.

        Raises:
            PsFTPAuthenticationError: If authentication fails
            PsFTPConnectionError: If connection to SFTP server fails
        """
        try:
            log.info(
                f'Connecting to SFTP server {self.server}:{self.port} (timeout: {self.timeout}s)'
            )
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect with timeout and TCP keepalive settings
            self._client.connect(
                hostname=self.server,
                port=self.port,
                username=self.user,
                password=self.password,
                timeout=self.timeout,
                banner_timeout=self.timeout,
                auth_timeout=self.timeout,
            )

            # Get the underlying transport and configure TCP keepalive
            transport = self._client.get_transport()
            if transport:
                transport.set_keepalive(30)  # Send keepalive packet every 30 seconds
                # Set socket timeout for SFTP operations
                sock = transport.sock
                if sock:
                    sock.settimeout(self.timeout)

            self._sftp = self._client.open_sftp()
            log.info(f'Successfully connected to {self.server}')
        except paramiko.AuthenticationException as e:
            msg = f'Authentication failed for {self.user}@{self.server}: {e}'
            log.error(msg)
            raise PsFTPAuthenticationError(msg) from e
        except (paramiko.SSHException, OSError, TimeoutError) as e:
            msg = f'Failed to connect to {self.server}: {e}'
            log.error(msg)
            raise PsFTPConnectionError(msg) from e

    def disconnect(self) -> None:
        """Close the SFTP connection."""
        if self._sftp:
            self._sftp.close()
        if self._client:
            self._client.close()

    # ========================================================================
    # Public Upload Method
    # ========================================================================

    def upload_file(
        self,
        local_path: Union[str, Path],
        remote_path: str,
        max_upload_speed_kb: Optional[int] = None,
    ) -> None:
        """Upload a file to the SFTP server.

        The file is first uploaded with a temporary name 'uploading.now' to avoid
        partial file visibility. After successful upload and verification, it is
        renamed to the target filename.

        Args:
            local_path: Path to the local file to upload
            remote_path: Destination path on the remote server
            max_upload_speed_kb: Maximum upload speed in KB/s (default: None, unlimited)

        Raises:
            PsFTPFileNotFoundError: If the local file does not exist
            PsFTPInvalidPathError: If the path is not a file
            PsFTPNotConnectedError: If not connected to SFTP server
            PsFTPUploadError: If file upload fails
            PsFTPVerificationError: If upload verification fails
        """
        local_path = Path(local_path)
        self._validate_local_file(local_path)
        self._ensure_connected()
        temp_remote_path = self._get_temp_upload_path(remote_path)

        try:
            # Create remote directory if it doesn't exist
            remote_dir = Path(remote_path).parent.as_posix()
            if remote_dir != '.' and not self._path_exists(remote_dir):
                self._create_remote_directory(remote_dir)

            log.info(
                f'Uploading {local_path} to temporary file {temp_remote_path} with maximum speed '
                f'{max_upload_speed_kb or "unlimited"} KB/s'
            )

            # Upload to temporary filename (this will overwrite if exists)
            if max_upload_speed_kb:
                self._throttled_upload(local_path, temp_remote_path, max_upload_speed_kb)
            else:
                self._sftp.put(str(local_path), temp_remote_path)

            self._verify_upload(local_path, temp_remote_path)
            log.info('Upload verification successful')

            # Rename to final destination (posix_rename will overwrite if exists)
            self._sftp.posix_rename(temp_remote_path, remote_path)

        # except (
        #     PsFTPVerificationError,
        #     PsFTPFileNotFoundError,
        #     PsFTPInvalidPathError,
        #     PsFTPNotConnectedError,
        # ):
        #     raise
        except (socket.timeout, TimeoutError) as e:
            # Handle timeout errors explicitly
            msg = f'Upload timed out after {self.timeout}s while uploading {local_path}: {e}'
            log.error(msg)
            raise PsFTPUploadError(msg) from e
        except (OSError, IOError) as e:
            # Handle network/IO errors explicitly
            msg = f'Network error during upload of {local_path}: {e}'
            log.error(msg)
            raise PsFTPUploadError(msg) from e
        except paramiko.SSHException as e:
            # Handle SSH/SFTP protocol errors explicitly
            msg = f'SSH/SFTP error during upload of {local_path}: {e}'
            log.error(msg)
            raise PsFTPUploadError(msg) from e
        except Exception as e:
            # Clean up temporary file on any other failure
            msg = f'Failed to upload {local_path}: {e}'
            log.error(msg)
            raise PsFTPUploadError(msg) from e

    def _validate_local_file(self, local_path: Path) -> None:
        """Validate that local file exists and is a file.

        Args:
            local_path: Path to the local file

        Raises:
            PsFTPFileNotFoundError: If the local file does not exist
            PsFTPInvalidPathError: If the path is not a file
        """
        if not local_path.exists():
            err_msg = f'Local file not found: {local_path}'
            raise PsFTPFileNotFoundError(err_msg)
        if not local_path.is_file():
            err_msg = f'Path is not a file: {local_path}'
            raise PsFTPInvalidPathError(err_msg)

    def _ensure_connected(self) -> None:
        """Ensure SFTP connection is active.

        Raises:
            PsFTPNotConnectedError: If not connected to SFTP server
        """
        if self._sftp is None:
            err_msg = 'Not connected to SFTP server. Call connect() first.'
            raise PsFTPNotConnectedError(err_msg)

    def _get_temp_upload_path(self, remote_path: str) -> str:
        """Calculate temporary upload path.

        Args:
            remote_path: Final destination path on the remote server

        Returns:
            Temporary upload path (same directory, name 'uploading.now')
        """
        remote_dir = Path(remote_path).parent.as_posix()
        return f'{remote_dir}/uploading.now' if remote_dir != '.' else 'uploading.now'

    def _throttled_upload(self, local_path: Path, remote_path: str, max_speed_kb: int) -> None:
        """Upload a file with bandwidth throttling.

        Args:
            local_path: Path to the local file
            remote_path: Destination path on the remote server
            max_speed_kb: Maximum upload speed in kilobytes per second

        Raises:
            PsFTPNotConnectedError: If not connected to SFTP server
            PsFTPUploadError: For upload errors including timeout
            socket.timeout: If socket timeout occurs during write
        """
        chunk_size = 32768  # 32 KB chunks
        max_bytes_per_sec = max_speed_kb * 1024
        chunks_per_sec = max(1, max_bytes_per_sec // chunk_size)
        sleep_time = 1.0 / chunks_per_sec if chunks_per_sec > 0 else 0

        log.debug(
            f'Throttled upload: {max_speed_kb} KB/s, chunk size: {chunk_size} bytes, '
            f'sleep time: {sleep_time:.4f}s per chunk'
        )

        try:
            with local_path.open('rb') as local_file, self._sftp.file(
                remote_path, 'wb'
            ) as remote_file:
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
        except (socket.timeout, TimeoutError) as e:
            msg = f'Timeout during throttled upload: {e}'
            log.error(msg)
            raise
        except (OSError, IOError) as e:
            msg = f'IO error during throttled upload: {e}'
            log.error(msg)
            raise

    def _verify_upload(self, local_path: Path, remote_path: str) -> bool:
        """Verify that the uploaded file size matches the local file.

        Args:
            local_path: Path to the local file
            remote_path: Path to the remote file

        Returns:
            True if verification succeeds

        Raises:
            PsFTPNotConnectedError: If not connected to SFTP server
            PsFTPVerificationError: If verification fails
        """
        if self._sftp is None:
            msg = 'Not connected to SFTP server.'
            raise PsFTPNotConnectedError(msg)

        try:
            remote_stat = self._sftp.stat(remote_path)
            remote_size = remote_stat.st_size
            local_size = local_path.stat().st_size

            if local_size != remote_size:
                msg = f'File size mismatch: local={local_size}, remote={remote_size}'
                log.error(msg)
                raise PsFTPVerificationError(msg)

        except PsFTPVerificationError:
            # Re-raise verification errors as-is
            raise
        except (socket.timeout, TimeoutError) as e:
            msg = f'Timeout during verification after {self.timeout}s: {e}'
            log.error(msg)
            raise PsFTPVerificationError(msg) from e
        except (OSError, IOError) as e:
            msg = f'Network error during verification: {e}'
            log.error(msg)
            raise PsFTPVerificationError(msg) from e
        except Exception as e:
            msg = f'Upload verification failed: {e}'
            log.error(msg)
            raise PsFTPVerificationError(msg) from e
        else:
            return True

    def _path_exists(self, path: str) -> bool:
        """Check if a path exists on the remote server.

        Args:
            path: Path to check on the remote server

        Returns:
            True if path exists, False otherwise
        """
        try:
            self._sftp.stat(path)
        except FileNotFoundError:
            return False
        else:
            return True

    def _create_remote_directory(self, remote_path: str) -> None:
        """Create directory and all parent directories on remote server.

        Args:
            remote_path: Path to the directory to create

        Raises:
            PsFTPUploadError: If directory creation fails
        """
        is_absolute = remote_path.startswith('/')
        parts = [p for p in remote_path.split('/') if p]
        current_path = '/' if is_absolute else ''

        for part in parts:
            if current_path and not current_path.endswith('/'):
                current_path += '/'
            current_path += part

            if not self._path_exists(current_path):
                try:
                    self._sftp.mkdir(current_path)
                    log.info(f'Created directory: {current_path}')
                except Exception as e:
                    msg = f'Failed to create directory {current_path}: {e}'
                    log.error(msg)
                    raise PsFTPUploadError(msg) from e
