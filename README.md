# SMTP Relay Service

A robust SMTP relay service that supports multiple SMTP configurations and automatic fallback.

## Features

- Multiple SMTP configuration support
- Automatic fallback to alternative configurations
- Health monitoring
- Logging with rotation
- Docker containerization
- Systemd service integration

## Prerequisites

- Linux server (tested on Ubuntu 20.04+)
- Sudo access
- Port 5000 available

## Deployment Instructions

1. Upload to server:
   ```bash
   scp -r smtp-relay user@your-hetzner-server:/opt/
   ```

2. SSH into server:
   ```bash
   ssh user@your-hetzner-server
   ```

3. Deploy:
   ```bash
   cd /opt/smtp-relay
   chmod +x deploy.sh
   ./deploy.sh
   sudo cp smtp-relay.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable smtp-relay
   sudo systemctl start smtp-relay
   ```

4. Verify deployment:
   ```bash
   # Check service status
   sudo systemctl status smtp-relay
   
   # Check health endpoint
   curl http://localhost:5000/health
   
   # Check Docker container
   docker ps
   
   # Check logs
   docker logs smtp-relay
   tail -f logs/app.log
   ```

## API Usage

Send a POST request to `/api/send_email` with the following JSON body:

```json
{
    "smtp_server": "smtp.example.com",
    "smtp_port": 587,
    "smtp_user": "your_username",
    "smtp_password": "your_password",
    "from_email": "sender@example.com",
    "to_email": "recipient@example.com",
    "subject": "Test Email",
    "body": "This is a test email"
}
```

## Monitoring

- Health check endpoint: `GET /health`
- Logs location: `/opt/smtp-relay/logs/app.log`
- Docker logs: `docker logs smtp-relay`

## Maintenance

- View logs: `tail -f /opt/smtp-relay/logs/app.log`
- Restart service: `sudo systemctl restart smtp-relay`
- Update application: Pull new code and run `./deploy.sh` again

## Troubleshooting

1. If logs are not being written:
   ```bash
   sudo chown -R $USER:$USER /opt/smtp-relay/logs
   sudo chmod 755 /opt/smtp-relay/logs
   ```

2. If service fails to start:
   ```bash
   sudo journalctl -u smtp-relay -f
   ```

3. If Docker container fails:
   ```bash
   docker logs smtp-relay
   docker-compose down
   docker-compose up -d --build
   ``` 