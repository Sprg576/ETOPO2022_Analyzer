"""发行版成果写入用户目录；源码直接运行仍兼容项目 outputs。"""

import os
from pathlib import Path


def output_directory():
    configured = os.environ.get("ETOPO_USER_DIR")
    root = Path(configured) if configured else Path(__file__).resolve().parents[2] / "outputs"
    root.mkdir(parents=True, exist_ok=True)
    return root
