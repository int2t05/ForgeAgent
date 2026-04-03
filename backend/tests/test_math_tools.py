"""数学运算工具测试。"""

import pytest

from app.modules.tools.math_tools import (
    add,
    divide,
    factorial,
    multiply,
    subtract,
    build_math_tools,
)
from app.modules.tools.builtin_executor import execute_builtin


class TestMathFunctions:
    """数学函数单元测试。"""

    def test_add(self):
        assert add(1, 2) == 3
        assert add(-1, 1) == 0
        assert add(0.1, 0.2) == pytest.approx(0.3)

    def test_subtract(self):
        assert subtract(5, 3) == 2
        assert subtract(0, 5) == -5
        assert subtract(-1, -1) == 0

    def test_multiply(self):
        assert multiply(3, 4) == 12
        assert multiply(-2, 3) == -6
        assert multiply(0, 100) == 0

    def test_divide(self):
        assert divide(10, 2) == 5
        assert divide(7, 2) == 3.5
        assert divide(-6, 2) == -3

    def test_divide_by_zero(self):
        with pytest.raises(ValueError, match="除数不能为零"):
            divide(1, 0)

    def test_factorial(self):
        assert factorial(0) == 1
        assert factorial(1) == 1
        assert factorial(5) == 120
        assert factorial(10) == 3628800

    def test_factorial_negative(self):
        with pytest.raises(ValueError, match="阶乘只支持非负整数"):
            factorial(-1)


class TestMathToolsRegistration:
    """数学工具注册测试。"""

    def test_build_math_tools(self):
        tools = build_math_tools()
        names = [t.name for t in tools]
        assert "add" in names
        assert "subtract" in names
        assert "multiply" in names
        assert "divide" in names
        assert "factorial" in names
        assert len(tools) == 5


@pytest.mark.asyncio
class TestMathToolsExecution:
    """数学工具执行测试。"""

    async def test_add_execution(self):
        # 注意：需要先将 math_tools 注册到 builtin_lc.py
        pass

    async def test_divide_execution(self):
        pass

    async def test_factorial_execution(self):
        pass

    async def test_multiply_execution(self):
        pass

    async def test_subtract_execution(self):
        pass
