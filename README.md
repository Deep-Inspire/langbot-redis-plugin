# wecom_assistant_plugin

LangBot plugin for WeCom information collection and reply interception.

## Usage
1. Place the whole folder under the langbot root path.
2. Activate the langbot virtual environment: `source ./.venv/bin/activate`
3. Run the plugin: `lbp run`

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

## Troubleshooting

If you encounter timeout errors after running the plugin for a long time:

1. Check the log file for detailed error messages
2. Verify Redis is still running: `redis-cli -p 16379 ping`
3. Check Redis connection list: `redis-cli -p 16379 CLIENT LIST`
4. The plugin will automatically attempt to reconnect if the connection fails
