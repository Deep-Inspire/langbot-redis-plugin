# components/event_listener/default.py
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from langbot_plugin.api.definition.components.common.event_listener import EventListener
from langbot_plugin.api.entities import events, context
from langbot_plugin.api.entities.builtin.platform import message as platform_message


class DefaultEventListener(EventListener):
    async def initialize(self):
        """
        Register event handlers for incoming messages and LLM responses.
        """

     
        @self.handler(events.PersonNormalMessageReceived)
        @self.handler(events.GroupNormalMessageReceived)
        async def on_normal_message_received(event_context: context.EventContext):
            event = event_context.event

            # 从原始消息中提取接收者信息
            source_platform_object = getattr(event, 'source_platform_object', None)
            internal_agent_id = None
            external_customer_id = None

            if source_platform_object:
                # 从原始消息中获取内部客服 ID
                internal_agent_id = source_platform_object.get('_internal_recipient')
                # 获取外部客户 ID（发送者）
                external_customer_id = source_platform_object.get('from')

            # 保存到 query context 中
            if internal_agent_id:
                await event_context.set_query_var("internal_agent_id", internal_agent_id)
            if external_customer_id:
                await event_context.set_query_var("external_customer_id", external_customer_id)

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
            await event_context.set_query_var("origin_message_type", message_type)
            await event_context.set_query_var("origin_message_text", user_message_text)

    
        @self.handler(events.NormalMessageResponded)
        async def on_llm_responded(event_context: context.EventContext):
            event: events.NormalMessageResponded = event_context.event

            launcher_id = str(event.launcher_id)
            cfg = self.plugin.get_config() or {}

            # 从 query context 获取双方身份信息
            try:
                internal_agent_id = await event_context.get_query_var("internal_agent_id")
            except Exception:
                internal_agent_id = launcher_id  # 降级方案

            try:
                external_customer_id = await event_context.get_query_var("external_customer_id")
            except Exception:
                external_customer_id = str(event.sender_id)  # 降级方案

            reply_text = event.response_text
            ts = int(time.time())
            reply_message_type = "text"

            try:
                origin_message_id = await event_context.get_query_var("origin_message_id")
            except Exception:
                origin_message_id = None

            try:
                origin_message_type = await event_context.get_query_var("origin_message_type")
            except Exception:
                origin_message_type = None

            try:
                origin_message_text = await event_context.get_query_var("origin_message_text")
            except Exception:
                origin_message_text = None

            # 完整的对话上下文日志对象（移除 conversation_direction）
            log_obj: Dict[str, Any] = {
                "external_customer_id": external_customer_id,
                "internal_agent_id": internal_agent_id,
                "timestamp": ts,
                "user_message_id": origin_message_id,
                "user_message_text": origin_message_text,
                "user_message_type": origin_message_type,
                "reply_message_text": reply_text,
                "reply_message_type": reply_message_type,
            }

            redis_list_key = cfg.get("redis_key") or "langbot:wecom:llm_replies"

            # 基于内部客服 ID 选择 stream
            stream_prefix = cfg.get("redis_stream_prefix") or "langbot:wecom:stream"
            redis_stream_key = f"{stream_prefix}:{internal_agent_id}"

            try:
                redis = await self.plugin.get_redis()
                json_str = json.dumps(log_obj, ensure_ascii=False)
                await redis.rpush(redis_list_key, json_str)
                await redis.xadd(
                    redis_stream_key,
                    {
                        "payload": json_str,
                        "external_customer_id": external_customer_id,
                        "internal_agent_id": internal_agent_id,
                        "timestamp": str(ts),
                        "user_message_type": origin_message_type or "",
                        "reply_message_type": reply_message_type,
                    },
                    maxlen=1000,
                    approximate=True,
                )

                print(f"[WeComRedisLogger] ✅ 推送成功")
                print(f"[WeComRedisLogger] 对话: {external_customer_id} -> {internal_agent_id}")
                print(f"[WeComRedisLogger] Stream: {redis_stream_key}")
            except Exception as e:
                print(f"[WeComRedisLogger] ❌ 推送失败: {e}")
                print(f"[WeComRedisLogger] Payload: {log_obj}")


            event_context.prevent_default()
            event_context.prevent_postorder()
