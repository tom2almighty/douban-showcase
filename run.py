# run.py - 应用启动脚本
import sys
from pathlib import Path

# 将src目录添加到Python路径
src_path = Path(__file__).parent / "src"
sys.path.append(str(src_path))

# 导入并运行应用
from src.app import main

if __name__ == "__main__":
    main()