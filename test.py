"""用于测试插件或适配器的脚本。"""

import sys

import structlog
from alicebot.bot import Bot

_, TYPE, MODULE_NAME = sys.argv


class PrintLogger:
    """用于在异常时直接退出的 logger factory。"""

    def msg(self, *args: object, **kwargs: object) -> None:
        """处理普通日志。"""
        print(*args, kwargs)  # noqa: T201

    def exception_msg(self, *args: object, **kwargs: object) -> None:
        """处理异常日志。"""
        self.msg(*args, **kwargs)
        sys.exit(1)  # 出现异常直接退出

    log = debug = info = warn = warning = msg
    fatal = failure = err = error = critical = exception = exception_msg


structlog.configure(logger_factory=PrintLogger)


bot = Bot(config_file=None)

if TYPE == "plugin":
    bot.load_plugins(MODULE_NAME)
elif TYPE == "adapter":
    bot.load_adapters(MODULE_NAME)


@bot.bot_run_hook
async def bot_run_hook(_bot: Bot) -> None:
    """在 Bot 启动后直接退出。"""
    if TYPE == "plugin":
        bot.should_exit.set()
    sys.exit()


if __name__ == "__main__":
    bot.run()
