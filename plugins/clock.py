#!/usr/bin/env python3
"""
时钟插件 — 显示当前时间
协议：输出一行 JSON {"name":"clock","lines":["14:30:00"]}

支持配置文件：
  ~/.config/my-greeter/config.toml
    [plugins.clock]
    format = "%H:%M:%S"
"""

import json
import os
import sys
from datetime import datetime

# 如果有 config.toml 里的插件配置，可以读
# 这里简单处理，直接用默认格式

fmt = "%H:%M:%S"
time_str = datetime.now().strftime(fmt)

# 输出单行 JSON
print(json.dumps({"name": "clock", "lines": [time_str]}))
