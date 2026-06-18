#!/usr/bin/env python3
"""
系统信息插件
协议：输出一行 JSON {"name":"sysinfo","lines":["hostname | load: 0.5"]}
"""
import json
from pathlib import Path

# 主机名
hostname = Path("/etc/hostname").read_text().strip()

# CPU 负载
load = Path("/proc/loadavg").read_text().split()[0]

line = f"{hostname} | load: {load}"
print(json.dumps({"name": "sysinfo", "lines": [line]}))
