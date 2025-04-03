# Configuration Troubleshooting Guide

This guide helps you resolve common configuration issues with DocuElevate's various integrations.

## SMTP Email Configuration

### Common Error: "Name or service not known"

This error occurs when the system can't resolve the hostname of your SMTP server.

**Solutions:**
1. Verify the `EMAIL_HOST` value in your `.env` file is correct
2. Check that your DNS is working properly:
   ```bash
   nslookup your-smtp-server.com
   ```
3. If running in Docker, verify the container has network access
4. Try using an IP address instead of a hostname

### Common Error: "Connection refused"

This error indicates the SMTP server is unreachable on the specified port.

**Solutions:**
1. Verify `EMAIL_PORT` is correct (typically 587 for TLS, 465 for SSL)
2. Check if the email server is running and accessible from your network
3. Test connectivity using telnet:
   ```bash
   telnet your-smtp-server.com 587
   ```
4. Check firewall settings to ensure the port is open

## Storage Provider Configuration

### Missing Configuration Attributes

When you see errors like "Settings object has no attribute 'nextcloud_url'" or similar:

**Solutions:**
1. Make sure all required environment variables are defined in your `.env` file
2. Check for typos in variable names
3. Ensure the application has loaded the environment variables
4. Restart the application after making changes to environment variables

### Example Configuration for Common Providers

#### Dropbox
```
DROPBOX_TOKEN=your_oauth2_token
DROPBOX_FOLDER=/DocuElevate
```

#### Nextcloud
```
NEXTCLOUD_URL=https://your-nextcloud-instance.com
NEXTCLOUD_USERNAME=your_username
NEXTCLOUD_PASSWORD=your_secure_password
NEXTCLOUD_FOLDER=/Documents
```

#### SFTP
```
SFTP_HOST=your-sftp-server.com
SFTP_PORT=22
SFTP_USERNAME=your_username
# Use either password or key authentication:
SFTP_PASSWORD=your_secure_password
# Or:
SFTP_PRIVATE_KEY=/path/to/private_key.pem
SFTP_PRIVATE_KEY_PASSPHRASE=optional_passphrase
SFTP_FOLDER=/upload/path
```

## Testing Configuration

You can use the configuration validator to test your settings:

```bash
# Inside the container:
python -c "from app.utils.config_validator import check_all_configs; check_all_configs()"
```

## Debugging Tips

1. Check the application logs for specific error messages
2. Verify network connectivity from your application server to the external services
3. Ensure all required credentials are correct and access permissions are properly set
4. For OAuth services (like Dropbox), verify the token has not expired
5. If using Docker, check that environment variables are properly passed to the container
