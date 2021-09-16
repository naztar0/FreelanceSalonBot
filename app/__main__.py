#!/usr/bin/env python
import os
from app import bot, config


def debug_check():
    if config.DEBUG:
        bot.start_pooling()
        exit()


def nt_main():
    bot.start_webhook()
    exit()


def posix_main():
    bot.start_webhook()
    exit()


if __name__ == '__main__':
    debug_check()
    if os.name == 'nt':
        nt_main()
    elif os.name == 'posix':
        posix_main()
