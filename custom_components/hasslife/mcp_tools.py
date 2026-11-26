"""
MCP 工具注册器 - 复用 HomeAssistant 内置 LLM 工具
"""
from inspect import signature
import logging
from typing import Any, Dict, List, Optional
from homeassistant.helpers import llm
from homeassistant.helpers.llm import LLMContext
from homeassistant.core import Context, HomeAssistant

try:
    import probatio
except ImportError:
    probatio = None

try:
    from voluptuous_openapi import convert as convert_schema
except ImportError:
    convert_schema = None

_LOGGER = logging.getLogger(__name__)


class MCPToolRegistry:
    """
    MCP 工具注册器
    从 HomeAssistant 的 AssistAPI 加载内置工具并转换为 MCP 格式
    """

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._api: Optional[llm.APIInstance] = None
        self._tools_cache: List[Dict[str, Any]] = []
        self._ha_tool_names: Dict[str, str] = {}

    async def _get_api(self) -> llm.APIInstance:
        """获取 APIInstance 实例"""
        if self._api is None:
            llm_context = self._create_llm_context()
            self._api = await llm.async_get_api(self.hass, llm.LLM_API_ASSIST, llm_context)
            _LOGGER.info(f"API 类型: {type(self._api)}")
            _LOGGER.info(f"API 名称: {self._api.api.name}")
        return self._api

    def _create_llm_context(self) -> LLMContext:
        """
        创建 LLMContext 实例

        参考官方 MCP Server 集成代码的实现方式
        """
        from homeassistant.components import conversation

        arguments = dict(
            platform="hasslife",
            context=Context(),
            language="*",
            assistant=conversation.DOMAIN,
            device_id=None,
        )
        if "user_prompt" in signature(LLMContext).parameters:
            arguments["user_prompt"] = None
        context = LLMContext(**arguments)

        _LOGGER.info(f"创建 LLMContext: platform={context.platform}, assistant={context.assistant}, language={context.language}")
        return context

    def _serialize_schema(self, schema: Any, custom_serializer=None) -> Dict[str, Any]:
        if isinstance(schema, dict):
            parameters = schema
        elif probatio is not None and isinstance(schema, probatio.Schema):
            parameters = probatio.to_openapi(schema, custom_serializer=custom_serializer)
        elif convert_schema is not None:
            parameters = convert_schema(schema, custom_serializer=custom_serializer)
        else:
            raise TypeError("No compatible tool schema converter")

        if parameters.get("type") != "object" or not isinstance(parameters.get("properties", {}), dict):
            raise ValueError("Tool schema is not an object")
        return {"properties": {}, **parameters}

    @staticmethod
    def _public_tool_name(name: str) -> str:
        if name == "homeassistant__GetLiveContext":
            return "GetLiveContext"
        if name.startswith("intent__Hass"):
            return name.removeprefix("intent__")
        return name

    async def get_mcp_tools(self) -> List[Dict[str, Any]]:
        """
        获取 HA 内置工具并转换为 MCP 格式（OpenAI Function 格式）

        返回格式:
        [
            {
                "type": "function",
                "function": {
                    "name": "HassTurnOn",
                    "description": "...",
                    "parameters": {...}
                }
            },
            ...
        ]
        """
        if self._tools_cache:
            return self._tools_cache

        try:
            api = await self._get_api()
            _LOGGER.info("正在从 HA AssistAPI 加载工具...")

            # 先输出 HA 提供的所有工具
            all_tool_names = [tool.name for tool in api.tools]
            _LOGGER.info(f"HA AssistAPI 提供的工具总数: {len(api.tools)}")
            _LOGGER.info(f"HA AssistAPI 工具列表: {all_tool_names}")

            # 输出 custom_serializer 信息
            _LOGGER.info(f"custom_serializer: {api.custom_serializer}")

            mcp_tools = []
            ha_tool_names = {}

            for tool in api.tools:
                name = self._public_tool_name(tool.name)
                if name in ha_tool_names:
                    continue
                try:
                    parameters = self._serialize_schema(tool.parameters, api.custom_serializer)
                except Exception as error:
                    _LOGGER.warning("无法序列化工具 %s 的参数，跳过注册: %s", tool.name, type(error).__name__)
                    continue

                mcp_tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.description or "",
                        "parameters": parameters,
                    }
                })
                ha_tool_names[name] = tool.name
                _LOGGER.debug("注册工具: %s", name)

            # 只有在没有原生 GetLiveContext 时才手动添加
            if "GetLiveContext" not in ha_tool_names:
                _LOGGER.info("HA 未提供可用的原生 GetLiveContext，使用插件实现")
                # 手动添加 GetLiveContext 工具
                get_live_context = {
                    "type": "function",
                    "function": {
                        "name": "GetLiveContext",
                        "description": (
                            "Provides real-time information about the CURRENT state, value, or mode of devices, "
                            "sensors, entities, or areas. Use this tool for: 1. Answering questions about current "
                            "conditions (e.g., 'Is the light on?'). 2. As the first step in conditional actions."
                        ),
                        "parameters": {"type": "object", "properties": {}},
                    }
                }
                mcp_tools.append(get_live_context)
                _LOGGER.info("已手动添加 GetLiveContext 工具")

            self._ha_tool_names = ha_tool_names
            self._tools_cache = mcp_tools
            _LOGGER.info(f"成功加载 {len(mcp_tools)} 个 HA 内置工具")

            # 输出工具名称列表
            tool_names = [t["function"]["name"] for t in mcp_tools]
            _LOGGER.info(f"工具列表: {tool_names}")

            return mcp_tools

        except Exception as e:
            _LOGGER.error(f"加载 HA 工具失败: {e}", exc_info=True)
            return []

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行已注册的 HA 工具。"""
        try:
            await self.get_mcp_tools()
            ha_name = self._ha_tool_names.get(tool_name)
            if tool_name == "GetLiveContext" and ha_name is None:
                return await self._execute_get_live_context()
            if ha_name is None:
                return {"error": f"未注册的工具: {tool_name}"}

            api = await self._get_api()
            tool_input = llm.ToolInput(tool_name=ha_name, tool_args=arguments)
            result = await api.async_call_tool(tool_input)
            tool_result_type = getattr(llm, "ToolResult", None)
            if tool_result_type is not None and isinstance(result, tool_result_type):
                return {"data": result.data, "error": result.error}
            return result
        except Exception as error:
            _LOGGER.error("执行工具 %s 失败: %s", tool_name, error, exc_info=True)
            return {"error": str(error)}

    async def _execute_get_live_context(self) -> Dict[str, Any]:
        """
        手动执行 GetLiveContext 工具
        获取所有实体的当前状态（包含区域信息）

        Returns:
            包含所有实体状态的字典
        """
        try:
            from homeassistant.helpers import entity_registry as er
            from homeassistant.helpers import area_registry as ar
            from homeassistant.helpers import device_registry as dr

            # 获取注册表
            ent_reg = er.async_get(self.hass)
            area_reg = ar.async_get(self.hass)
            dev_reg = dr.async_get(self.hass)

            # 获取所有状态
            states = self.hass.states.async_all()

            # 构建结果
            result = {
                "success": True,
                "result": f"Live Context: 共 {len(states)} 个实体\n\n"
            }

            # 按区域分组
            by_area = {}
            entities_without_area = []

            for state in states:
                entity_id = state.entity_id

                # 获取实体信息（包含区域信息）
                entity_entry = ent_reg.async_get(entity_id)

                # 获取区域名称
                area_name = None
                area_names = []

                if entity_entry and entity_entry.device_id:
                    # 先检查设备的区域
                    device_entry = dev_reg.async_get(entity_entry.device_id)
                    if device_entry and device_entry.area_id:
                        area_entry = area_reg.async_get_area(device_entry.area_id)
                        if area_entry:
                            area_names.append(area_entry.name)
                            # 添加别名
                            if area_entry.aliases:
                                area_names.extend(area_entry.aliases)

                # 如果设备没有区域，检查实体的区域
                if not area_names and entity_entry and entity_entry.area_id:
                    area_entry = area_reg.async_get_area(entity_entry.area_id)
                    if area_entry:
                        area_names.append(area_entry.name)
                        if area_entry.aliases:
                            area_names.extend(area_entry.aliases)

                # 构建实体信息
                entity_info = {
                    "entity_id": entity_id,
                    "name": state.name,
                    "state": state.state,
                    "attributes": dict(state.attributes),
                    "area": ", ".join(area_names) if area_names else None,
                }

                # 按区域分组
                if area_names:
                    area_key = area_names[0]  # 使用主区域名称作为键
                    if area_key not in by_area:
                        by_area[area_key] = []
                    by_area[area_key].append(entity_info)
                else:
                    entities_without_area.append(entity_info)

            # 添加有区域的实体到结果
            for area_name, entities in sorted(by_area.items()):
                result["result"] += f"【{area_name}】({len(entities)} 个设备)\n"
                for entity in entities[:15]:  # 每个区域最多显示 15 个
                    area_str = f" [{entity['area']}]" if entity['area'] else ""
                    result["result"] += f"  - {entity['name']}{area_str}: {entity['state']}\n"
                if len(entities) > 15:
                    result["result"] += f"  ... 还有 {len(entities) - 15} 个\n"
                result["result"] += "\n"

            # 添加没有区域的实体
            if entities_without_area:
                result["result"] += f"【其他区域/未分类】({len(entities_without_area)} 个)\n"
                for entity in entities_without_area[:10]:
                    result["result"] += f"  - {entity['name']}: {entity['state']}\n"
                if len(entities_without_area) > 10:
                    result["result"] += f"  ... 还有 {len(entities_without_area) - 10} 个\n"

            _LOGGER.info(f"GetLiveContext 返回 {len(states)} 个实体，{len(by_area)} 个区域")
            return result

        except Exception as e:
            _LOGGER.error(f"GetLiveContext 执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def register_to_server(self, client) -> bool:
        """
        向服务器注册 MCP 工具

        Args:
            client: TCP 客户端实例

        Returns:
            是否注册成功
        """
        try:
            tools = await self.get_mcp_tools()

            if not tools:
                _LOGGER.warning("没有可注册的工具")
                return False

            # 构建注册消息
            message = {
                "Type": "RegisterMcpTools",
                "Payload": {
                    "tools": tools
                }
            }

            # 发送注册消息
            await client.send_message_async(message)
            _LOGGER.info(f"成功向服务器注册 {len(tools)} 个 MCP 工具")
            return True

        except Exception as e:
            _LOGGER.error(f"注册 MCP 工具失败: {e}", exc_info=True)
            return False

    def clear_cache(self):
        """清除工具缓存（用于重新加载）"""
        self._tools_cache = []
        self._api = None
        self._has_native_get_live_context = False  # 重置标志


# 全局实例
_registry: Optional[MCPToolRegistry] = None


def get_mcp_registry(hass: HomeAssistant) -> MCPToolRegistry:
    """获取 MCP 工具注册表单例"""
    global _registry
    if _registry is None:
        _registry = MCPToolRegistry(hass)
    return _registry
