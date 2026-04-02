"""跨层复用的纯函数与类型工具（无业务规则、无请求/DB 生命周期）。

模块分组：
- **LLM 输出解析**：JSON 候选提取、ReAct 字段识别
- **消息内容**：LangChain 多模态内容统一提取
- **数据工具**：payload 解析、UTC 时间类型、工作区快照、计划步骤工具解析

使用场景：
  - execution 域：ReAct 循环输出解析、工具参数规范化
  - planning 域：规划步骤校验与工具名识别
  - memory 域：Observation 压缩时的 JSON 安全序列化
  - services 层：事件 payload 读取与展示用路径补全

使用方式（按需导入以避免循环依赖）：
  from app.shared.react_llm_output import parse_react_round_json, pick_final_answer
  from app.shared.llm_json_parse import parse_llm_json_object
"""
