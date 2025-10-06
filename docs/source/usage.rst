===============================
Panthyr SFTP Library Usage
===============================



Basic Usage
-----------

Simple File Upload
~~~~~~~~~~~~~~~~~~

The simplest way to upload a file is using a context manager:

.. code-block:: python

    from p_sftp import PSFTP

    # Upload a file with automatic connection and verification
    with PSFTP('sftp.example.com', 'username', 'password') as client:
        client.upload_file('local_file.txt', '/remote/path/file.txt')

The context manager automatically:

* Connects to the SFTP server
* Uploads the file
* Verifies the upload (file size check)
* Closes the connection when done

Manual Connection Management
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can also manage connections manually if needed:

.. code-block:: python

    from p_sftp import PSFTP

    # Create client
    client = PSFTP('sftp.example.com', 'username', 'password', port=22)

    try:
        # Connect to server
        client.connect()

        # Upload file
        client.upload_file('local_file.txt', '/remote/path/file.txt')

    finally:
        # Always disconnect when done
        client.disconnect()

Advanced Usage
--------------

Custom Port
~~~~~~~~~~~

Specify a non-standard SFTP port:

.. code-block:: python

    from p_sftp import PSFTP

    # Connect to server on port 2222
    with PSFTP('sftp.example.com', 'username', 'password', port=2222) as client:
        client.upload_file('file.txt', '/remote/file.txt')

Upload Without Verification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, uploads are verified by comparing file sizes. You can disable this:

.. code-block:: python

    from p_sftp import PSFTP

    with PSFTP('sftp.example.com', 'username', 'password') as client:
        # Upload without verification (faster but not recommended)
        client.upload_file('file.txt', '/remote/file.txt', verify=False)

.. warning::
    Disabling verification is not recommended as it may result in incomplete or corrupted uploads
    going undetected.

Reusing Connections
~~~~~~~~~~~~~~~~~~~

Upload multiple files using a single connection:

.. code-block:: python

    from p_sftp import PSFTP

    files_to_upload = [
        ('data1.csv', '/remote/data/data1.csv'),
        ('data2.csv', '/remote/data/data2.csv'),
        ('data3.csv', '/remote/data/data3.csv'),
    ]

    with PSFTP('sftp.example.com', 'username', 'password') as client:
        for local_file, remote_path in files_to_upload:
            client.upload_file(local_file, remote_path)
            print(f'Uploaded {local_file}')

Using Path Objects
~~~~~~~~~~~~~~~~~~

The library accepts both strings and ``pathlib.Path`` objects:

.. code-block:: python

    from pathlib import Path
    from p_sftp import PSFTP

    local_file = Path('data') / 'measurements.csv'

    with PSFTP('sftp.example.com', 'username', 'password') as client:
        client.upload_file(local_file, '/remote/measurements.csv')

Upload Verification
-------------------

How Verification Works
~~~~~~~~~~~~~~~~~~~~~~

By default, after each upload, the library verifies the upload was successful by:

1. **File Size Check**: Compares the size of the local file with the uploaded remote file
2. If sizes don't match, a ``RuntimeError`` is raised

This verification happens automatically and provides confidence that your files were uploaded
correctly.

.. code-block:: python

    from p_sftp import PSFTP

    with PSFTP('sftp.example.com', 'username', 'password') as client:
        # Verification happens automatically
        client.upload_file('important_data.csv', '/backup/data.csv')
        # If you reach this point, the upload was verified successfully

Disabling Verification
~~~~~~~~~~~~~~~~~~~~~~

For trusted networks or when speed is critical:

.. code-block:: python

    from p_sftp import PSFTP

    with PSFTP('sftp.example.com', 'username', 'password') as client:
        client.upload_file('file.txt', '/remote/file.txt', verify=False)

Error Handling
--------------

Connection Errors
~~~~~~~~~~~~~~~~~

Handle authentication and connection errors:

.. code-block:: python

    from p_sftp import PSFTP
    import paramiko

    try:
        with PSFTP('sftp.example.com', 'username', 'wrong_password') as client:
            client.upload_file('file.txt', '/remote/file.txt')
    except paramiko.AuthenticationException:
        print('Authentication failed: Invalid credentials')
    except paramiko.SSHException as e:
        print(f'SSH error: {e}')
    except Exception as e:
        print(f'Connection error: {e}')

Upload Errors
~~~~~~~~~~~~~

Handle file not found and upload errors:

.. code-block:: python

    from p_sftp import PSFTP

    try:
        with PSFTP('sftp.example.com', 'username', 'password') as client:
            client.upload_file('nonexistent.txt', '/remote/file.txt')
    except FileNotFoundError as e:
        print(f'Local file not found: {e}')
    except RuntimeError as e:
        print(f'Upload verification failed: {e}')
    except Exception as e:
        print(f'Upload error: {e}')

Logging
-------

The library uses Python's standard logging module. Enable logging to see detailed information:

.. code-block:: python

    import logging
    from p_sftp import PSFTP

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Now you'll see detailed logs
    with PSFTP('sftp.example.com', 'username', 'password') as client:
        client.upload_file('file.txt', '/remote/file.txt')

Log Levels
~~~~~~~~~~

* ``DEBUG``: Detailed connection information, file sizes, verification details
* ``INFO``: Connection status, upload progress, verification results
* ``ERROR``: Connection failures, upload errors, verification failures

Example output with ``INFO`` level:

.. code-block:: text

    2025-10-03 10:30:15 - p_sftp.p_sftp - INFO - Connecting to SFTP server sftp.example.com:22
    2025-10-03 10:30:16 - p_sftp.p_sftp - INFO - Successfully connected to sftp.example.com
    2025-10-03 10:30:16 - p_sftp.p_sftp - INFO - Uploading file.txt to /remote/file.txt
    2025-10-03 10:30:17 - p_sftp.p_sftp - INFO - Successfully uploaded file.txt
    2025-10-03 10:30:17 - p_sftp.p_sftp - INFO - Verifying upload...
    2025-10-03 10:30:17 - p_sftp.p_sftp - INFO - File size verification passed
    2025-10-03 10:30:17 - p_sftp.p_sftp - INFO - Upload verification successful

API Reference
-------------

PSFTP Class
~~~~~~~~~~~

.. code-block:: python

    class PSFTP(server, user, password, port=22)

Parameters:
    * ``server`` (str): The hostname or IP address of the SFTP server
    * ``user`` (str): The username for authentication
    * ``password`` (str): The password for authentication
    * ``port`` (int, optional): The port number for the SFTP server (default: 22)

Methods
~~~~~~~

connect()
^^^^^^^^^

Establish connection to the SFTP server.

.. code-block:: python

    client.connect()

Raises:
    * ``paramiko.AuthenticationException``: If authentication fails
    * ``paramiko.SSHException``: If there is an SSH-related error
    * ``Exception``: For other connection errors

disconnect()
^^^^^^^^^^^^

Close the SFTP connection.

.. code-block:: python

    client.disconnect()

upload_file()
^^^^^^^^^^^^^

Upload a file to the SFTP server.

.. code-block:: python

    client.upload_file(local_path, remote_path, auto_connect=True, verify=True)

Parameters:
    * ``local_path`` (str or Path): Path to the local file to upload
    * ``remote_path`` (str): Destination path on the remote server
    * ``auto_connect`` (bool, optional): Automatically connect if not already connected (default: True)
    * ``verify`` (bool, optional): Verify the upload after completion (default: True)

Raises:
    * ``FileNotFoundError``: If the local file does not exist
    * ``ValueError``: If the path is not a file
    * ``RuntimeError``: If upload verification fails or not connected
    * ``Exception``: For other upload errors

Best Practices
--------------

1. **Always use context managers** when possible for automatic cleanup:

   .. code-block:: python

       with PSFTP(server, user, password) as client:
           client.upload_file(local, remote)

2. **Keep verification enabled** unless you have a specific reason to disable it

3. **Use logging** during development and debugging to understand what's happening

4. **Handle exceptions** appropriately for production code:

   .. code-block:: python

       try:
           with PSFTP(server, user, password) as client:
               client.upload_file(local, remote)
       except Exception as e:
           logger.error(f'Upload failed: {e}')
           # Handle error appropriately

5. **Reuse connections** when uploading multiple files to improve performance

6. **Use environment variables** for credentials instead of hardcoding them:

   .. code-block:: python

       import os
       from p_sftp import PSFTP

       server = os.environ.get('SFTP_SERVER')
       user = os.environ.get('SFTP_USER')
       password = os.environ.get('SFTP_PASSWORD')

       with PSFTP(server, user, password) as client:
           client.upload_file('file.txt', '/remote/file.txt')

Complete Example
----------------

Here's a complete example showing best practices:

.. code-block:: python

    import logging
    import os
    from pathlib import Path
    from p_sftp import PSFTP

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    def upload_data_files():
        """Upload all data files to the SFTP server."""
        # Get credentials from environment
        server = os.environ.get('SFTP_SERVER', 'sftp.example.com')
        user = os.environ.get('SFTP_USER')
        password = os.environ.get('SFTP_PASSWORD')

        if not user or not password:
            logger.error('SFTP credentials not found in environment')
            return False

        # Define files to upload
        data_dir = Path('data')
        files = [
            (data_dir / 'measurements_2025.csv', '/backup/measurements_2025.csv'),
            (data_dir / 'calibration.json', '/backup/calibration.json'),
            (data_dir / 'metadata.txt', '/backup/metadata.txt'),
        ]

        try:
            with PSFTP(server, user, password) as client:
                logger.info(f'Connected to {server}')

                for local_file, remote_path in files:
                    if not local_file.exists():
                        logger.warning(f'Skipping {local_file}: file not found')
                        continue

                    try:
                        client.upload_file(local_file, remote_path)
                        logger.info(f'Successfully uploaded {local_file.name}')
                    except Exception as e:
                        logger.error(f'Failed to upload {local_file.name}: {e}')
                        # Continue with next file
                        continue

                logger.info('Upload batch completed')
                return True

        except Exception as e:
            logger.error(f'SFTP connection error: {e}')
            return False

    if __name__ == '__main__':
        success = upload_data_files()
        exit(0 if success else 1)
