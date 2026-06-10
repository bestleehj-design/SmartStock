#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全市场A股日线数据更新 — 从 Tushare 拉取最新日K入库.
用法: python3 update_daily.py
等价于: sudo python3 src/data/new_get_all_stock.py --no-hk
"""

import sys, os, subprocess

_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

DATA_DIR = os.path.join(_SRC_DIR, 'data')


def main():
    print('>>> 全市场 A 股日线数据更新...')
    print('    (需要 sudo 权限, 请在弹出的终端输入密码)')
    print()

    cmd = ['sudo', '-S', 'python3', 'new_get_all_stock.py', '--no-hk']
    try:
        result = subprocess.run(cmd, cwd=DATA_DIR, timeout=600)
        if result.returncode == 0:
            print('\n✅ A 股日线数据更新完成')
        else:
            print(f'\n⚠️ 退出码: {result.returncode}')
    except subprocess.TimeoutExpired:
        print('\n⚠️ 超时 (10分钟), 可能部分完成')
    except KeyboardInterrupt:
        print('\n⏹ 用户中断')


if __name__ == '__main__':
    main()
