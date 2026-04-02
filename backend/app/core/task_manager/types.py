from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Optional, Protocol, runtime_checkable

class TaskStatus(str, Enum):
    """任务状态枚举。"""

    pending = "pending"
    running = "running"
    streaming = "streaming"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class DeliveryMode(str, Enum):
    """结果交付方式。

扩展方式：
- 新增一种模式时：加一个枚举值 + 实现对应 DeliveryStrategy
"""

    streaming = "streaming"
    async_polling = "async_polling"


@runtime_checkable
class BaseTask(Protocol):
    """任务抽象基类。

    要求：
    - 必须实现 run、status、is_done、get_result 四个方法
    - run：执行实际任务逻辑（调用模型 / 外部服务等），参数由 TaskManager.create 传入
    - status：返回任务当前状态（可用于自定义查询接口）
    - is_done：判断任务是否完成
    - get_result：获取任务结果

    run 的两种实现方式：
    - stream 模式：run 返回 AsyncIterator[Any]，调用方直接消费该 iterator
    - 异步获取模式：run 返回 None，最终结果通过 get_result() 获取
    """

    async def run(self, *args: Any, **kwargs: Any) -> AsyncIterator[Any] | None: ...

    async def status(self) -> dict[str, Any]: ...

    async def is_done(self) -> bool: ...

    async def get_result(self) -> Any: ...


@dataclass(slots=True)
class TaskRecord:
    """任务在应用层的统一表示（与存储实现解耦）。"""

    id: str
    mode: DeliveryMode
    status: TaskStatus
    progress: int  # 0-100
    payload: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    error: str = ""

    created_at_ts: Optional[float] = None
    updated_at_ts: Optional[float] = None


@dataclass(slots=True)
class TaskStatusView:
    """轮询接口的轻量视图（性能友好）。"""

    id: str
    status: TaskStatus
    progress: int  # 0-100
    result: Optional[dict[str, Any]] = None
    error: str = ""
    updated_at_ts: Optional[float] = None

