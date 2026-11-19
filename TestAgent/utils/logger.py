import logging
import sys
import os
import datetime
import re


# ── ANSI 颜色 ──
_RESET = "\033[0m"
_COLORS = {
    logging.DEBUG:    "\033[36m",   # 青色
    logging.INFO:     "\033[32m",   # 绿色
    logging.WARNING:  "\033[33m",   # 黄色
    logging.ERROR:    "\033[31m",   # 红色
    logging.CRITICAL: "\033[1;31m", # 加粗红色
}


class ColorFormatter(logging.Formatter):
    """终端彩色日志 Formatter：INFO 绿色、WARNING 黄色、ERROR 红色。"""

    def __init__(self, fmt=None, datefmt=None):
        super().__init__(fmt, datefmt)

    def format(self, record):
        color = _COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname:<5}{_RESET}"
        return super().format(record)


class DualOutput:
    def __init__(self):
        project_root = os.getcwd()
        log_dir = os.path.join(project_root, "logs")
        os.makedirs(log_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"{timestamp}.log"
        self.filepath = os.path.join(log_dir, log_filename)

        self.terminal = sys.stdout
        self.log = open(self.filepath, "a", encoding='utf-8')

        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def write(self, message):
        self.terminal.write(message)

        clean_message = self.ansi_escape.sub('', message)
        self.log.write(clean_message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def isatty(self):
        """CrewAI/Rich 兼容性必须"""
        return self.terminal.isatty()

    def __getattr__(self, attr):
        """CrewAI/Rich 兼容性必须"""
        return getattr(self.terminal, attr)


def setup_logging(level=logging.INFO):
    """配置 logging：彩色输出到 stdout，同时通过 DualOutput 写入日志文件。"""
    fmt = "%(asctime)s %(levelname)s %(message)s"
    datefmt = "%H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColorFormatter(fmt, datefmt))

    logging.basicConfig(level=level, handlers=[handler])


# ── 启用日志系统 ──
sys.stdout = DualOutput()

print(f"日志系统已启动，文件路径: {sys.stdout.filepath}")
