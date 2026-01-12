import os
import sys
from pathlib import Path

# 让 tests 能直接 import src 下的包
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# 测试用单独数据库文件，避免污染 app.db
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

# 标记 pytest 运行中（用于配置加载逻辑避免 .env 覆盖）
os.environ["PYTEST_RUNNING"] = "1"

# 测试强制走 debug_code（不依赖真实 SMTP），避免本机/.env 设置影响单测
os.environ["EMAIL_DEBUG_RETURN_CODE"] = "true"
