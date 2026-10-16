# Panthyr SFTP library CHANGELOG

## Not released yet

- Replace paramiko with the system OpenSSH `sftp` client (SSH key auth only, no dependencies)
- Read server, port, user, key file and remote dir from `/home/panthyr/data/sftp.env`
- `password` argument removed; requires Python >= 3.11

## v0.1.0

- Initial release
