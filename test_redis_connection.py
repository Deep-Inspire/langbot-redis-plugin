#!/usr/bin/env python3
"""
Test script to verify Redis connection and health check mechanism.
Run this script to test the Redis connection before running the plugin.

Usage:
    python3 test_redis_connection.py
    python3 test_redis_connection.py redis://:password@127.0.0.1:16379/0
    REDIS_URL="redis://:password@127.0.0.1:16379/0" python3 test_redis_connection.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def get_redis_url():
    """Get Redis URL from command line args, environment variable, or use default"""
    # Priority: 1. Command line arg, 2. Environment variable, 3. Default
    if len(sys.argv) > 1:
        return sys.argv[1]

    env_url = os.getenv("REDIS_URL")
    if env_url:
        return env_url

    # Default (no password)
    return "redis://127.0.0.1:16379/0"

def mask_password(url: str) -> str:
    """Mask password in Redis URL for display"""
    if ":" in url and "@" in url:
        # Format: redis://:password@host:port/db or redis://user:password@host:port/db
        parts = url.split("@")
        if len(parts) == 2:
            auth_part = parts[0]
            host_part = parts[1]
            if "//" in auth_part and ":" in auth_part:
                prefix = auth_part.split("//")[0] + "//"
                return f"{prefix}***@{host_part}"
    return url

async def test_redis_connection():
    """Test Redis connection with the same parameters used in the plugin"""
    import redis.asyncio as redis

    # Get Redis URL
    redis_url = get_redis_url()
    masked_url = mask_password(redis_url)

    print(f"Testing Redis connection to: {masked_url}")
    print("-" * 50)

    try:
        # Create connection with same parameters as plugin
        client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
            retry_on_timeout=True,
            max_connections=10,
        )

        print("✓ Redis client created successfully")

        # Test ping
        await client.ping()
        print("✓ PING successful")

        # Test basic operations
        test_key = "langbot:test:connection"
        await client.set(test_key, "test_value", ex=60)
        print(f"✓ SET {test_key} successful")

        value = await client.get(test_key)
        print(f"✓ GET {test_key} = {value}")

        await client.delete(test_key)
        print(f"✓ DELETE {test_key} successful")

        # Test stream operation (similar to plugin usage)
        stream_key = "langbot:test:stream"
        stream_id = await client.xadd(
            stream_key,
            {"test": "data", "timestamp": "123456"},
            maxlen=10,
            approximate=True
        )
        print(f"✓ XADD to {stream_key} successful, ID: {stream_id}")

        await client.delete(stream_key)
        print(f"✓ Cleanup successful")

        print("-" * 50)
        print("✅ All tests passed! Redis connection is working properly.")

        # Test health check after wait
        print("\nTesting health check after 5 seconds...")
        await asyncio.sleep(5)
        await client.ping()
        print("✓ Health check after wait: OK")

        await client.close()
        print("✓ Connection closed successfully")

        return True

    except redis.ConnectionError as e:
        print(f"\n❌ Connection Error: {e}")
        print("\nPlease check:")
        print(f"  1. Redis server is running: redis-cli -p 16379 ping")
        print(f"  2. Redis is listening on the correct port (16379)")
        print(f"  3. No firewall blocking the connection")
        return False

    except redis.TimeoutError as e:
        print(f"\n❌ Timeout Error: {e}")
        print("\nPossible causes:")
        print(f"  1. Redis server is too slow to respond")
        print(f"  2. Network issues")
        return False

    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_long_running_connection():
    """Test that connection stays alive over time"""
    import redis.asyncio as redis

    redis_url = get_redis_url()
    masked_url = mask_password(redis_url)

    print("\n" + "=" * 50)
    print(f"Testing long-running connection (30 seconds)...")
    print(f"Redis URL: {masked_url}")
    print("=" * 50)

    try:
        client = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
            retry_on_timeout=True,
            max_connections=10,
        )

        # Test connection every 5 seconds for 30 seconds
        for i in range(6):
            await asyncio.sleep(5)
            try:
                await client.ping()
                print(f"✓ Health check {i+1}/6 (after {(i+1)*5}s): OK")
            except Exception as e:
                print(f"❌ Health check {i+1}/6 failed: {e}")
                await client.close()
                return False

        await client.close()
        print("\n✅ Long-running connection test passed!")
        return True

    except Exception as e:
        print(f"\n❌ Long-running test failed: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Redis Connection Test for wecom_redis_plugin")
    print("=" * 50)
    print()

    # Run basic connection test
    result1 = asyncio.run(test_redis_connection())

    if result1:
        # Run long-running test
        result2 = asyncio.run(test_long_running_connection())

        if result2:
            print("\n" + "=" * 50)
            print("✅ All tests completed successfully!")
            print("Your Redis connection is properly configured.")
            print("=" * 50)
            sys.exit(0)

    print("\n" + "=" * 50)
    print("❌ Tests failed. Please fix the issues above.")
    print("=" * 50)
    sys.exit(1)
