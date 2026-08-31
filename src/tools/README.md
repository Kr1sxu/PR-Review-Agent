# 工具模块 — PR-Review Agent

注册到 AgentScope Toolkit 的只读工具集。

## 工具清单

| 工具 | 文件 | 只读 | 说明 |
|------|------|------|------|
| read_file | read_file.py | 是 | 读取文件内容并附带行号，支持路径白名单 |
| search_code | search_code.py | 是 | 关键词/正则搜索仓库文件 |
| run_tests | run_tests.py | 否 | 执行测试命令（默认禁用） |

## 使用示例

```python
from src.tools.tool_registry import create_toolkit

# 默认：测试工具禁用
toolkit = create_toolkit(allowed_roots=["/path/to/repo"])

# 启用测试工具（带命令白名单）
toolkit = create_toolkit(
    allowed_roots=["/path/to/repo"],
    enable_tests=True,
    test_commands=["pytest", "python -m pytest"],
)
```

## 安全设计
- 所有文件工具实现 `check_permissions()`，对只读操作返回 ALLOW
- `run_tests` 默认返回 DENIED，需显式设置 `enabled=True`
- 命令白名单防止任意命令执行
- 路径校验防止访问允许目录之外的文件
