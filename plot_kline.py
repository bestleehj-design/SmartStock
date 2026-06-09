# -*- coding: utf-8 -*-
"""
K线图绘制工具
用法: python plot_kline.py 600863.SH      # 指定股票
      python plot_kline.py 600863.SH 90   # 指定回看天数
"""
import sys
import os
import datetime
import warnings
warnings.filterwarnings('ignore')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import numpy as np
import pandas as pd
import mplfinance as mpf
from newstocklib import initMySQL


def plot_kline(code, lookback_days=90, show_ma_convergence=True):
    """绘制K线图，标注均线粘合和发散区域"""
    db = initMySQL()
    c = db.cursor()

    # 获取股票名称
    c.execute("SELECT name FROM stock_basic_info_tbl WHERE code = %s", (code,))
    name_row = c.fetchone()
    name = name_row[0] if name_row else code

    # 获取日线数据
    c.execute("""
        SELECT tradedate, open, high, low, close, volume, amount, adj_factor
        FROM daily_info_tbl
        WHERE code = %s
        ORDER BY tradedate ASC
    """, (code,))
    rows = c.fetchall()

    if len(rows) < 60:
        print(f"{code} 数据不足")
        c.close(); db.close()
        return

    # 取最近N天
    rows = rows[-lookback_days:]

    # 构建DataFrame
    data = []
    for i, r in enumerate(rows):
        td, op, hi, lo, cl, vol, amt, adj = r
        adj = float(adj) if adj else 1.0
        data.append({
            'Date': td,
            'Open': float(op) * adj,
            'High': float(hi) * adj,
            'Low': float(lo) * adj,
            'Close': float(cl) * adj,
            'Volume': float(vol) if vol else 0,
        })

    df = pd.DataFrame(data)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)

    # 计算均线
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA10'] = df['Close'].rolling(10).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA30'] = df['Close'].rolling(30).mean()

    # 计算量比 (V / V37)
    df['V37'] = df['Volume'].rolling(37).mean()
    df['VolRatio'] = df['Volume'] / df['V37']

    # 计算均线粘合度 (MA5-MA30) / MA30
    df['Convergence'] = abs(df['MA5'] - df['MA30']) / df['MA30']

    # 均线发散度 (正值=多头发散, 负值=空头)
    df['Divergence'] = (df['MA5'] - df['MA30']) / df['MA30']

    # 成交量颜色
    vol_colors = []
    for i in range(len(df)):
        if df['Close'].iloc[i] >= df['Open'].iloc[i]:
            vol_colors.append('red')
        else:
            vol_colors.append('green')

    # 标注信号
    # 找到粘合区域 (Convergence < 5%)
    convergence_periods = df['Convergence'] < 0.05
    # 找到放量日 (VolRatio >= 1.5)
    volume_surge_days = df['VolRatio'] >= 1.5
    # 找到涨停日 (涨幅 >= 9.88% 主板)
    df['Change'] = df['Close'].pct_change()
    limit_up_days = df['Change'] >= 0.098

    # 构建信号标注点
    markers = []
    for date in df.index:
        if limit_up_days.get(date, False):
            markers.append(date)

    # 绘制K线图
    mc = mpf.make_marketcolors(
        up='red', down='green',
        edge='inherit', wick='inherit',
        volume='inherit'
    )
    s = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle=':', gridcolor='gray',
        y_on_right=False,
        rc={'font.sans-serif': ['Arial Unicode MS', 'SimHei', 'DejaVu Sans'],
            'axes.unicode_minus': False}
    )

    # 添加均线
    apds = [
        mpf.make_addplot(df['MA5'], color='blue', width=0.8, label='MA5'),
        mpf.make_addplot(df['MA10'], color='orange', width=0.8, label='MA10'),
        mpf.make_addplot(df['MA20'], color='purple', width=0.8, label='MA20'),
        mpf.make_addplot(df['MA30'], color='brown', width=0.8, label='MA30'),
    ]

    title = f'{name} ({code}) - {len(df)}日K线'
    if show_ma_convergence:
        # 计算粘合期
        conv_mask = df['Convergence'] < 0.05
        conv_date_count = conv_mask.sum()
        if conv_date_count > 0:
            # 找到最近的粘合期
            recent_conv = df[df.index > df.index[-60]]
            recent_conv_count = (recent_conv['Convergence'] < 0.05).sum()
            title += f'  [近60日粘合: {recent_conv_count}天]'

    # 绘制
    fig, axes = mpf.plot(
        df, type='candle', style=s,
        addplot=apds,
        volume=True,
        title=title,
        ylabel='Price', ylabel_lower='Volume',
        figsize=(16, 9),
        returnfig=True,
        warn_too_much_data=len(df) + 100
    )

    # 在图上标注均线粘合区域
    if show_ma_convergence:
        ax = axes[0]
        y_min = df['Low'].min() * 0.98
        y_max = df['High'].max() * 1.02
        y_range = y_max - y_min
        x_range = len(df)

        # 标注最近的粘合区域
        label_added = False
        for i in range(len(df) - 1, -1, -1):
            if i >= len(df):
                continue
            if df['Convergence'].iloc[i] < 0.05 and df['MA5'].iloc[i] < df['MA10'].iloc[i]:
                if not label_added:
                    ax.annotate(u'均线粘合',
                               xy=(i, df['Low'].iloc[i] * 0.96),
                               fontsize=9, color='darkred',
                               bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.6))
                    label_added = True
                break

        # 标注最近发散
        for i in range(len(df) - 1, max(len(df) - 15, 0), -1):
            if i >= len(df):
                continue
            if (df['Divergence'].iloc[i] > 0.1 and
                df['MA5'].iloc[i] > df['MA10'].iloc[i] > df['MA20'].iloc[i]):
                ax.annotate(u'多头发散\n主升启动',
                           xy=(i, df['High'].iloc[i] * 1.02),
                           fontsize=10, color='red', fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.3', facecolor='lightgreen', alpha=0.7))
                break

        # 标注放量涨停
        for i in range(len(df) - 1, max(len(df) - 15, 0), -1):
            if i >= len(df):
                continue
            if df['VolRatio'].iloc[i] >= 2.0:
                ax.annotate(f"放量{df['VolRatio'].iloc[i]:.1f}x",
                           xy=(i, df['High'].iloc[i] * 1.01),
                           fontsize=8, color='darkred',
                           ha='center')
            elif df['VolRatio'].iloc[i] >= 1.5:
                ax.annotate(f"量{df['VolRatio'].iloc[i]:.1f}x",
                           xy=(i, df['High'].iloc[i] * 1.01),
                           fontsize=7, color='red',
                           ha='center')

    # 保存图片
    output_dir = os.path.join(SCRIPT_DIR, 'charts')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f'{code}_{datetime.date.today()}.png')
    fig.savefig(output_path, dpi=120, bbox_inches='tight')
    print(f"K线图已保存: {output_path}")

    c.close()
    db.close()
    return output_path


if __name__ == '__main__':
    code = sys.argv[1] if len(sys.argv) > 1 else '600863.SH'
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    plot_kline(code, days)
