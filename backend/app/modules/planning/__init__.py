"""规划域：由用户目标生成可执行步骤列表（计划），支持重规划与技能选择。

核心能力：
  - LLM 规划接口（llm.py）：将用户目标拆解为有序步骤
  - Planner 节点（nodes.py）：加载上下文、选择相关技能、生成/更新计划
  - 技能预选：根据会话内容从配置的 skill 目录中选择相关 SKILL.md

关键产出：
  - plan_created 事件：包含完整步骤列表
  - replan 事件：记录重规划版本号

使用方式：
  from app.modules.planning.nodes import planner_node
  from app.modules.planning.llm import plan_steps_with_llm, select_skills_for_planner
"""
