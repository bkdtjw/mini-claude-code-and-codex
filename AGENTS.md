# Agent Studio - 项目约束

## 代码规范
- Python 3.11+，全面使用 type hints
- 类型定义统一用 Pydantic v2 BaseModel
- 单文件不超过 200 行，超过必须拆分
- 模块间只通过 __init__.py 暴露的接口通信
- 所有异步函数必须 try-except，错误用自定义 Exception 类
- 函数参数超过 3 个时用 dataclass 或 Pydantic model 封装

## 架构规则
- backend/core/ 不依赖 FastAPI，纯 Python + asyncio
- backend/core/ 不直接调用 LLM API，通过注入的 adapter 调用
- 工具通过 ToolRegistry 注册，禁止硬编码
- 每个 s01-s12 模块的 __init__.py 是唯一公开入口
- backend/api/ 是唯一的 HTTP 入口层，负责请求验证和响应格式化

## 依赖约束
- 能用标准库解决的不引入第三方包
- 新增 pip 依赖前必须说明理由
- 核心依赖: pydantic, fastapi, uvicorn, httpx

## 测试
- 每个公开接口至少一个测试用例
- 用 pytest + pytest-asyncio
- mock 外部 API 调用，不在测试中发真实请求

## 命名约定
- 文件名: snake_case
- 类名: PascalCase
- 函数/变量: snake_case
- 常量: UPPER_SNAKE_CASE
