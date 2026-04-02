"""执行域：Agent 按步骤推进、ReAct 循环、流式应答与可观测事件落盘。

核心流程：
  1. Actor 节点（nodes.py）按计划步顺序调用
  2. 单步执行器（step_executor.py）负责 step_start/ReAct/step_end 生命周期
  3. ReAct 循环（step_react_loop.py）实现工具调用与终答判断
  4. 工具运行器（tool_runner.py）处理单次工具调用的重试与超时
  5. 流式回复（llm_reply.py）将执行结果总结为用户可读输出

关键产出：
  - task_events：step_start / tool_call / tool_result / react_turn / step_end / llm_stream_delta
  - actor_tool_trace：供 Learner 与 Assistant Reply 使用的结构化轨迹

使用方式（按需导入以避免循环依赖）：
  from app.modules.execution.nodes import actor_node
  from app.modules.execution.step_executor import execute_plan_step_react
  from app.modules.execution.step_react_loop import run_step_react_loop
"""
