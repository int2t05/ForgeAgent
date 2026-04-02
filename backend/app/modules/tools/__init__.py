"""工具域：内置工具、MCP 客户端、Skill 元数据与统一注册表。

核心组件：
  - 注册表（registry.py）：工具发现、列举、查找的统一入口
  - 内置工具执行器（builtin_executor.py）：文件读写、目录列举、搜索、Python REPL、Shell
  - MCP 客户端（mcp_client.py）：MCP 服务连接管理与工具动态加载
  - MCP 数据源（mcp_sources.py）：MCP server 配置持久化与传输层适配
  - Skill 来源（skill_sources.py）：SKILL.md 文件读取与路径解析

工具分类：
  - builtin：内置实现（forge_file_tools.py, builtin_lc.py）
  - mcp：通过 MCP 协议接入的外部工具

关键接口：
  - tool_registry.list_tools_public()：获取前端可展示的工具列表
  - tool_registry.get_tool(name)：按名称查找可调用工具

使用方式：
  from app.modules.tools.registry import tool_registry
  from app.modules.tools.mcp_client import mcp_client_manager
"""
