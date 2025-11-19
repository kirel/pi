# TeslaMate Role

TeslaMate is a self-hosted data logger for your Tesla. It requires:
- PostgreSQL database
- Grafana dashboard
- MQTT broker (uses existing mosquitto from homeassistant role)

## Configuration

### Environment Variables to Set (in vault)

1. **teslamate_encryption_key**: Generate with:
   ```bash
   openssl rand -base64 32
   ```

2. **teslamate_database_password**: Secure database password

## Deployment

Deploy to a specific host:
```bash
uv run ansible-playbook setup.yml --tags teslamate --limit homelab
```

## Service Ports

- TeslaMate Web: 4000
- Grafana: 3000

## Tesla API Setup

After deployment:
1. Visit TeslaMate at http://homelab.lan:4000
2. Sign in with your Tesla account
3. Grant permissions in Tesla app
4. Access Grafana dashboards at http://homelab.lan:3000 (admin/your_db_password)