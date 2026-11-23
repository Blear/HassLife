import asyncio
from collections import OrderedDict

from .utils import LOGGER


class ConversationBridge:
    def __init__(self, hass, send):
        self._hass = hass
        self._send = send
        self._tasks = set()
        self._sessions = OrderedDict()
        self._lock = asyncio.Lock()

    async def dispatch(self, message):
        request_id = message.get("RequestID")
        if not isinstance(request_id, str) or not request_id:
            return
        if len(self._tasks) >= 16:
            await self._reply(request_id, {"error": "HA 对话请求繁忙，请稍后再试"})
            return
        task = asyncio.create_task(self._process(request_id, message.get("Payload")))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def cancel_pending(self):
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _reply(self, request_id, payload):
        await self._send({
            "Type": "ProcessConversation",
            "RequestID": request_id,
            "Payload": payload,
        })

    async def _process(self, request_id, payload):
        try:
            result = await self._converse(payload)
        except TimeoutError:
            result = {"error": "HA Agent 响应超时"}
        except Exception as error:
            LOGGER.warning("HA Conversation failed (%s)", type(error).__name__)
            result = {"error": "HA 对话执行失败，请检查 Agent 配置"}
        await self._reply(request_id, result)

    async def _converse(self, payload):
        if not isinstance(payload, dict):
            return {"error": "HA 对话参数无效"}
        agent_id, text, bot, sender = (
            payload.get(field) for field in ("agent_id", "text", "bot", "sender")
        )
        if not all(isinstance(value, str) and value.strip() for value in (agent_id, text, bot, sender)):
            return {"error": "HA 对话参数无效"}
        if not agent_id.startswith("conversation.") or len(text.encode()) > 16000:
            return {"error": "HA 对话参数无效"}
        if not self._hass.states.get(agent_id):
            return {"error": "所选 HA Agent 不存在，请重新选择"}

        session_key = (bot, sender, agent_id)
        async with asyncio.timeout(60), self._lock:
            data = {"text": text, "agent_id": agent_id}
            if conversation_id := self._sessions.get(session_key):
                data["conversation_id"] = conversation_id
            result = await self._hass.services.async_call(
                "conversation", "process", data, blocking=True, return_response=True
            )
            response = result.get("response", {})
            speech = response.get("speech", {}).get("plain", {}).get("speech", "")
            if response.get("response_type") == "error":
                return {"error": speech or "HA Agent 无法处理这条消息"}
            if conversation_id := result.get("conversation_id"):
                self._sessions[session_key] = conversation_id
                self._sessions.move_to_end(session_key)
                if len(self._sessions) > 256:
                    self._sessions.popitem(last=False)
            else:
                self._sessions.pop(session_key, None)
            return {"text": speech, "conversation_id": conversation_id}
