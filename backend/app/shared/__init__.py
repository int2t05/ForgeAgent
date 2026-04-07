"""跨层复用的纯函数与类型工具（无业务规则、无请求/DB 生命周期）。

模块分组：
- **LLM 输出解析**：JSON 候选提取、ReAct 字段识别
- **消息内容**：LangChain 多模态内容统一提取
- **数据工具**：payload 解析、UTC 时间类型、工作区快照、计划步骤工具解析
- **会话黑板**：跨任务继承的键值存储工具函数
- **工具返回压缩**：Observation JSON 裁剪以控制 prompt 长度
- **工具上下文**：ToolContext 传递用户身份信息
- **工具参数校验**：防止工具调用幻觉

使用场景：
  - execution 域：ReAct 循环输出解析、工具参数规范化
  - planning 域：规划步骤校验与工具名识别
  - memory 域：上下文整形（Observation 压缩、Token 计数）
  - services 层：事件 payload 读取与展示用路径补全

使用方式（按需导入以避免循环依赖）：
  from app.shared.react_llm_output import parse_react_round_json, pick_final_answer
  from app.shared.llm_json_parse import parse_llm_json_object
  from app.shared.blackboard import cap_blackboard_notes, decode_blackboard_json
  from app.shared.tool_observation_compact import shrink_tool_result_data, observation_json_for_llm
  from app.shared.tool_context import ToolContext, get_current_tool_context, with_tool_context
  from app.shared.tool_validation import ToolValidationError, get_tool_args_validator
"""
