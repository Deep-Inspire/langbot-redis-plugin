# components/event_listener/default.py
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional

from langbot_plugin.api.definition.components.common.event_listener import EventListener
from langbot_plugin.api.entities import events, context
from langbot_plugin.api.entities.builtin.platform import message as platform_message

# Debug flag - can be controlled via environment variable
DEBUG_WECOM_REDIS = os.getenv('DEBUG_WECOM_REDIS', 'false').lower() in ('true', '1', 'yes')


def _log(logger: Any, level: str, message: str, **kwargs):
    if logger is None:
        return
    log_method = getattr(logger, level, None)
    if log_method is not None:
        log_method(message, **kwargs)


def _config_int(value: Any, default: int, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None and parsed < minimum:
        return minimum
    return parsed


async def _safe_get_query_var(event_context: context.EventContext, key: str, default=None, logger=None):
    """Safely get query variable with default value, avoiding KeyError exceptions"""
    try:
        value = await event_context.get_query_var(key)
        if DEBUG_WECOM_REDIS:
            _log(logger, "debug", f"Got {key} from query context: {value}")
        return value
    except Exception as e:
        if DEBUG_WECOM_REDIS:
            _log(logger, "debug", f"Failed to get {key}, using default: {default} (error: {e})")
        return default


def _config_bool(value: Any, default: bool = True) -> bool:
    """Parse plugin config booleans from bool, string, or numeric values."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ('true', '1', 'yes', 'y', 'on', 'enable', 'enabled'):
            return True
        if normalized in ('false', '0', 'no', 'n', 'off', 'disable', 'disabled'):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


async def _mark_plugin_redis_unhealthy(plugin: Any, error: BaseException, logger: Any):
    mark_unhealthy = getattr(plugin, "mark_redis_unhealthy", None)
    if mark_unhealthy is None:
        return
    try:
        result = mark_unhealthy(error)
        if asyncio.iscoroutine(result):
            await result
    except Exception as mark_error:
        _log(logger, "warning", f"Failed to mark Redis connection unhealthy: {mark_error}")


def _adapter_looks_like_weworkfinance(adapter: Any) -> bool:
    """Identify WeWork Finance adapters without importing core adapter classes."""
    if adapter is None:
        return False

    target_class_names = {'weworkfinanceadapter', 'weworkfinancemediaadapter'}
    target_adapter_names = {'weworkfinance', 'weworkfinance_media'}

    adapter_class = adapter.__class__
    class_name = getattr(adapter_class, '__name__', '').lower()
    if class_name in target_class_names:
        return True

    module_parts = getattr(adapter_class, '__module__', '').lower().split('.')
    if module_parts and module_parts[-1] in target_adapter_names:
        return True

    for attr_name in ('name', 'adapter_name', 'platform_name'):
        attr_value = getattr(adapter, attr_name, None)
        if isinstance(attr_value, str) and attr_value.strip().lower() in target_adapter_names:
            return True

    metadata = getattr(adapter, 'metadata', None)
    metadata_name = getattr(metadata, 'name', None)
    if isinstance(metadata_name, str) and metadata_name.strip().lower() in target_adapter_names:
        return True

    return False


def _extract_source_platform_object(event: Any) -> Optional[dict]:
    """Return source_platform_object from direct event or nested message_event."""
    source_platform_object = getattr(event, 'source_platform_object', None)
    if source_platform_object is None:
        message_event = getattr(event, 'message_event', None)
        source_platform_object = getattr(message_event, 'source_platform_object', None)
    if isinstance(source_platform_object, dict):
        return source_platform_object
    return None


def _extract_origin_metadata(event: Any) -> Dict[str, List[Any]]:
    """Extract original message ids/times, including aggregated messages."""
    source_platform_object = _extract_source_platform_object(event)
    if not source_platform_object:
        return {'message_ids': [], 'message_times': []}

    raw_items = source_platform_object.get('_aggregated_source_platform_objects')
    if not isinstance(raw_items, list) or not raw_items:
        raw_items = [source_platform_object]

    message_ids: List[Any] = []
    message_times: List[Any] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        msgid = item.get('msgid')
        if msgid is not None:
            message_ids.append(msgid)
        msgtime = item.get('msgtime')
        if msgtime is not None:
            message_times.append(msgtime)

    return {'message_ids': message_ids, 'message_times': message_times}


class DefaultEventListener(EventListener):
    _initialized = False  # Guard against duplicate initialization

    async def initialize(self):
        """
        Register event handlers for incoming messages and LLM responses.
        """
        # Prevent duplicate handler registration
        if DefaultEventListener._initialized:
            return
        DefaultEventListener._initialized = True

        @self.handler(events.PersonNormalMessageReceived)
        @self.handler(events.GroupNormalMessageReceived)
        async def on_normal_message_received(event_context: context.EventContext):
            event = event_context.event
            logger = getattr(self.plugin, "_logger", None)

            # 从原始消息中提取接收者信息
            source_platform_object = _extract_source_platform_object(event)
            origin_metadata = _extract_origin_metadata(event)
            internal_agent_id = None
            external_customer_id = None

            if DEBUG_WECOM_REDIS:
                _log(logger, "debug", "on_normal_message_received called")
                _log(logger, "debug", f"source_platform_object exists: {source_platform_object is not None}")

            if source_platform_object:
                # 从原始消息中获取内部客服 ID
                internal_agent_id = source_platform_object.get('_internal_recipient')
                # 获取外部客户 ID（发送者）
                external_customer_id = source_platform_object.get('from')

                if DEBUG_WECOM_REDIS:
                    _log(logger, "debug", f"_internal_recipient: {internal_agent_id}")
                    _log(logger, "debug", f"from: {external_customer_id}")

            # 保存到 query context 中
            if internal_agent_id:
                await event_context.set_query_var("internal_agent_id", internal_agent_id)
                if DEBUG_WECOM_REDIS:
                    _log(logger, "debug", "Saved internal_agent_id to query context")
            elif DEBUG_WECOM_REDIS:
                _log(logger, "warning", "internal_agent_id is None")

            if external_customer_id:
                await event_context.set_query_var("external_customer_id", external_customer_id)
                if DEBUG_WECOM_REDIS:
                    _log(logger, "debug", "Saved external_customer_id to query context")
            elif DEBUG_WECOM_REDIS:
                _log(logger, "warning", "external_customer_id is None")

            msg_chain: platform_message.MessageChain = event.message_chain

            message_id: Optional[str] = None

            message_type: str = "text"
            text_parts: List[str] = []

            for comp in msg_chain:
                if isinstance(comp, platform_message.Source):
                    for attr in ("id", "message_id", "msg_id", "msgid"):
                        value = getattr(comp, attr, None)
                        if value is not None:
                            message_id = str(value)
                            break

                if isinstance(comp, platform_message.Image):
                    message_type = "image"
                elif isinstance(comp, platform_message.File):
                    message_type = "file"
                elif isinstance(comp, platform_message.Voice):
                    message_type = "voice"
                elif isinstance(comp, platform_message.Plain):
                    text_parts.append(comp.text)

            user_message_text: Optional[str] = "".join(text_parts) if text_parts else None

            await event_context.set_query_var("origin_message_id", message_id)
            await event_context.set_query_var("origin_message_ids", origin_metadata["message_ids"] or ([message_id] if message_id else []))
            await event_context.set_query_var("origin_message_times", origin_metadata["message_times"])
            await event_context.set_query_var("origin_message_type", message_type)
            await event_context.set_query_var("origin_message_text", user_message_text)

    
        @self.handler(events.NormalMessageResponded)
        async def on_llm_responded(event_context: context.EventContext):
            event: events.NormalMessageResponded = event_context.event
            logger = getattr(self.plugin, "_logger", None)

            launcher_id = str(event.launcher_id)
            cfg = self.plugin.get_config() or {}

            if DEBUG_WECOM_REDIS:
                _log(logger, "debug", "on_llm_responded called")
                _log(logger, "debug", f"launcher_id: {launcher_id}")
                _log(logger, "debug", f"sender_id: {event.sender_id}")

            # Get identity info from query context with fallbacks
            internal_agent_id = await _safe_get_query_var(event_context, "internal_agent_id", launcher_id, logger)
            external_customer_id = await _safe_get_query_var(event_context, "external_customer_id", str(event.sender_id), logger)

            reply_text = event.response_text
            ts = int(time.time())
            reply_message_type = "text"

            # Get original message info
            origin_message_id = await _safe_get_query_var(event_context, "origin_message_id", None, logger)
            origin_message_ids = await _safe_get_query_var(event_context, "origin_message_ids", [], logger)
            origin_message_times = await _safe_get_query_var(event_context, "origin_message_times", [], logger)
            origin_message_type = await _safe_get_query_var(event_context, "origin_message_type", "text", logger)
            origin_message_text = await _safe_get_query_var(event_context, "origin_message_text", None, logger)

            # 完整的对话上下文日志对象（移除 conversation_direction）
            log_obj: Dict[str, Any] = {
                "external_customer_id": external_customer_id,
                "internal_agent_id": internal_agent_id,
                "timestamp": ts,
                "user_message_id": origin_message_id,
                "user_message_ids": origin_message_ids or ([origin_message_id] if origin_message_id else []),
                "user_message_times": origin_message_times or [],
                "user_message_text": origin_message_text,
                "user_message_type": origin_message_type,
                "reply_message_text": reply_text,
                "reply_message_type": reply_message_type,
            }

            redis_list_key = cfg.get("redis_key") or "langbot:wecom:llm_replies"

            # 基于内部客服 ID 选择 stream
            stream_prefix = cfg.get("redis_stream_prefix") or "langbot:wecom:stream"
            redis_stream_key = f"{stream_prefix}:{internal_agent_id}"
            stream_maxlen = _config_int(cfg.get("stream_maxlen"), default=100000, minimum=100000)

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    redis = await self.plugin.get_redis()
                    json_str = json.dumps(log_obj, ensure_ascii=False)

                    # Execute Redis operations with timeout
                    await asyncio.wait_for(
                        redis.rpush(redis_list_key, json_str),
                        timeout=3.0
                    )
                    await asyncio.wait_for(
                        redis.xadd(
                            redis_stream_key,
                            {
                                "payload": json_str,
                                "external_customer_id": external_customer_id,
                                "internal_agent_id": internal_agent_id,
                                "timestamp": str(ts),
                                "user_message_type": origin_message_type or "",
                                "reply_message_type": reply_message_type,
                            },
                            maxlen=stream_maxlen,
                            approximate=True,
                        ),
                        timeout=3.0
                    )

                    if DEBUG_WECOM_REDIS:
                        _log(logger, "debug", f"Pushed WeCom Redis log: {external_customer_id} -> {internal_agent_id}")
                        _log(logger, "debug", f"Stream: {redis_stream_key}")
                        _log(logger, "debug", f"Payload: {log_obj}")

                    _log(logger, "info", f"Successfully pushed to Redis: {redis_stream_key}")
                    break  # Success, exit retry loop

                except asyncio.TimeoutError as e:
                    await _mark_plugin_redis_unhealthy(self.plugin, e, logger)
                    _log(
                        logger,
                        "error",
                        f"Redis operation timeout (attempt {attempt + 1}/{max_retries}): {e}",
                        exc_info=True
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)  # Wait before retry
                        _log(logger, "warning", f"Redis timeout, retrying ({attempt + 2}/{max_retries})")
                    else:
                        _log(logger, "error", f"Redis push failed after {max_retries} timeout attempts")
                        _log(logger, "error", f"Payload: {log_obj}")

                except Exception as e:
                    await _mark_plugin_redis_unhealthy(self.plugin, e, logger)
                    _log(
                        logger,
                        "error",
                        f"Redis operation failed (attempt {attempt + 1}/{max_retries}): {e}",
                        exc_info=True
                    )
                    _log(logger, "error", f"Redis push failed: {e}")
                    _log(logger, "error", f"Payload: {log_obj}")

                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)  # Wait before retry
                        _log(logger, "warning", f"Retrying Redis push ({attempt + 2}/{max_retries})")
                    else:
                        _log(logger, "error", "All Redis push retry attempts failed")
                        break

            intercept_reply = _config_bool(cfg.get("intercept_reply"), default=True)
            adapter = getattr(getattr(event, "query", None), "adapter", None)
            if intercept_reply and _adapter_looks_like_weworkfinance(adapter):
                event_context.prevent_default()
                event_context.prevent_postorder()
