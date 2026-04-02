"""shell 工具：Windows 预检与 CLIXML 剥离（纯函数，无需启用 AGENT_ENABLE_SHELL）。"""

from __future__ import annotations

from app.modules.tools.builtin_lc import _strip_powershell_clixml, _windows_shell_unsupported


def test_guard_xargs():
    msg = _windows_shell_unsupported("find . -name '*.py' | xargs grep -l foo")
    assert msg is not None
    assert "xargs" in msg
    assert "findstr" in msg or "cmd" in msg.lower()


def test_guard_find_type():
    msg = _windows_shell_unsupported("find backend -type f")
    assert msg is not None
    assert "-type" in msg or "dir" in msg.lower()


def test_guard_find_name():
    msg = _windows_shell_unsupported("find backend -name '*.py'")
    assert msg is not None
    assert "dir" in msg.lower() or "-name" in msg


def test_guard_dev_null():
    msg = _windows_shell_unsupported("some-cmd 2>/dev/null")
    assert msg is not None
    assert "2>nul" in msg or "nul" in msg.lower()


def test_guard_allows_cmdish():
    assert _windows_shell_unsupported('dir /S /B .') is None
    assert _windows_shell_unsupported("findstr /S /M /I agent *.py") is None
    assert _windows_shell_unsupported("python -m pytest") is None


def test_strip_clixml_removes_objs_block():
    raw = """exit 1
#< CLIXML
<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04"><Obj S="progress" RefId="0"><TN RefId="0"><T>System.Management.Automation.PSCustomObject</T><T>System.Object</T></TN><MS><I64 N="SourceId">1</I64></MS></Obj></Objs>
Real error line here"""
    out = _strip_powershell_clixml(raw)
    assert "<Objs" not in out
    assert "CLIXML" not in out
    assert "Real error line here" in out


def test_strip_clixml_noop_without_marker():
    t = "hello\nworld"
    assert _strip_powershell_clixml(t) == t
