# wecom_assistant_plugin

LangBot plugin for WeCom information collection and reply interception.

## Usage
1. Place the whole folder under the langbot root path.
2. Activate the langbot virtual environment: `source ./.venv/bin/activate`
3. Configure Redis URL in LangBot WebUI (Settings -> Plugins -> wecom_assistant_plugin):
   - Without password: `redis://127.0.0.1:16379/0`
   - With password: `redis://:your_password@127.0.0.1:16379/0`
   - With username and password: `redis://username:password@127.0.0.1:16379/0`
4. Run the plugin: `lbp run`

## Logging

The plugin now includes comprehensive file logging for debugging long-running sessions:

- Logs are written to `logs/wecom_redis_plugin_YYYYMMDD.log`
- Each day's logs are stored in a separate file
- Logs include detailed information about Redis connections, health checks, and errors

### Monitor Logs

In a separate terminal, you can monitor the logs in real-time:

```bash
./monitor_logs.sh
```

Or manually:

```bash
tail -f logs/wecom_redis_plugin_$(date +%Y%m%d).log
```

## Features

### Automatic Redis Connection Management

- **Health Check**: Redis connection is checked before each operation
- **Auto-Reconnect**: Automatically reconnects if the connection fails
- **Retry Mechanism**: Retries failed operations up to 3 times
- **Timeout Protection**: Each Redis operation has a 3-second timeout to prevent hanging

### Configuration

Redis connection parameters (optimized for long-running sessions):

- `socket_timeout`: 5 seconds
- `socket_connect_timeout`: 5 seconds
- `socket_keepalive`: Enabled (prevents connection from being closed by network devices)
- `health_check_interval`: 30 seconds (periodic health checks)
- `retry_on_timeout`: Enabled
- `max_connections`: 10

## Testing

Before running the plugin, test your Redis connection:

### Without password:
```bash
python3 test_redis_connection.py
```

### With password:
```bash
python3 test_redis_connection.py "redis://:your_password@127.0.0.1:16379/0"
```

Or use environment variable:
```bash
REDIS_URL="redis://:your_password@127.0.0.1:16379/0" python3 test_redis_connection.py
```

## Troubleshooting

If you encounter timeout errors after running the plugin for a long time:

1. Check the log file for detailed error messages
2. Verify Redis is still running:
   - Without password: `redis-cli -p 16379 ping`
   - With password: `redis-cli -p 16379 -a your_password ping`
3. Check Redis connection list:
   - Without password: `redis-cli -p 16379 CLIENT LIST`
   - With password: `redis-cli -p 16379 -a your_password CLIENT LIST`
4. The plugin will automatically attempt to reconnect if the connection fails

### Common Issues

**Authentication Error**: Make sure the Redis URL in plugin configuration includes the password:
- Format: `redis://:password@host:port/db`
- Example: `redis://:mypassword@127.0.0.1:16379/0`

**Connection Refused**: Check if Redis is running and listening on the correct port:
```bash
redis-cli -p 16379 -a your_password ping
```
