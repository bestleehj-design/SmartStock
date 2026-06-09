# -*- coding: utf-8 -*-
"""
题材日历 — 季节性题材窗口管理
根据当前日期自动识别处于炒作窗口的板块，提醒关注相关题材

设计逻辑：
  - 每段时间区间对应一个题材（如 6-8月 → 电力）
  - 提前 2 周进入预热期，末周进入退潮期
  - 返回板块关键词列表，供 smart_screener.py 加权
"""

from datetime import date


class SeasonWindow:
    """单个季节性窗口"""
    def __init__(self, name, start_month, start_day, end_month, end_day,
                 keywords, description, preheat_weeks=2, cooldown_weeks=1):
        self.name = name
        self.start = (start_month, start_day)
        self.end = (end_month, end_day)
        self.keywords = keywords
        self.description = description
        self.preheat_weeks = preheat_weeks
        self.cooldown_weeks = cooldown_weeks

    def status(self, check_date):
        """
        返回当前日期在此窗口中的状态
        返回: (active, status_label, boost)
          active=True 时给板块加权
          status: 'preheat' | 'active' | 'cooldown' | None
          boost: 0.0 ~ 1.0 权重系数
        """
        y = check_date.year

        # 处理跨年窗口 (如 11月~次年3月)
        if self.start > self.end:
            d_start = date(y, *self.start)
            d_end = date(y + 1, *self.end)
        else:
            d_start = date(y, *self.start)
            d_end = date(y, *self.end)

        # 扩大检查范围：预热期和退潮期
        from datetime import timedelta
        preheat_start = d_start - timedelta(weeks=self.preheat_weeks)
        cooldown_end = d_end + timedelta(weeks=self.cooldown_weeks)

        if check_date < preheat_start or check_date > cooldown_end:
            return False, None, 0.0

        # 激活期
        if d_start <= check_date <= d_end:
            return True, 'active', 1.0

        # 预热期: 线性增长
        if preheat_start <= check_date < d_start:
            days_in = (check_date - preheat_start).days
            total_days = (d_start - preheat_start).days
            boost = days_in / max(total_days, 1)
            return True, 'preheat', round(boost, 2)

        # 退潮期: 线性衰减
        if d_end < check_date <= cooldown_end:
            days_left = (cooldown_end - check_date).days
            total_days = (cooldown_end - d_end).days
            boost = days_left / max(total_days, 1)
            return True, 'cooldown', round(boost, 2)

        return False, None, 0.0


# ============================================================
# 题材日历配置
# ============================================================

SEASONAL_WINDOWS = [
    # --- 电力/能源 ---
    SeasonWindow(
        '夏季用电高峰', 6, 1, 8, 31,
        keywords=['电力', '电网', '智能电网', '虚拟电厂', '特高压',
                  '煤电', '风电', '光伏电站'],
        description='夏季用电高峰，电力负荷创新高，电网调度和设备需求增加',
    ),
    SeasonWindow(
        '冬季取暖', 11, 15, 3, 15,
        keywords=['燃气', '煤炭', '供热', '天然气'],
        description='冬季取暖季，天然气和煤炭需求上升',
    ),

    # --- 消费 ---
    SeasonWindow(
        '春节消费', 1, 10, 2, 15,
        keywords=['白酒', '食品饮料', '预制菜', '旅游', '酒店',
                  '影视', '春运', '物流'],
        description='春节假期消费旺季，白酒、食品、旅游、影视受益',
    ),
    SeasonWindow(
        '五一小长假', 4, 20, 5, 10,
        keywords=['旅游', '酒店', '餐饮', '消费', '家电'],
        description='五一假期消费，旅游酒店餐饮板块受益',
        preheat_weeks=1, cooldown_weeks=0,
    ),
    SeasonWindow(
        '十一黄金周', 9, 15, 10, 10,
        keywords=['旅游', '酒店', '消费', '零售', '影视'],
        description='十一黄金周消费旺季，旅游零售受益',
    ),

    # --- 农业 ---
    SeasonWindow(
        '春耕', 3, 1, 4, 30,
        keywords=['种业', '化肥', '农药', '农机', '农业'],
        description='春耕季节，种子和农资需求上升',
    ),

    # --- 基建/工程 ---
    SeasonWindow(
        '春季开工', 3, 1, 5, 31,
        keywords=['水泥', '建材', '工程机械', '钢铁', '基建'],
        description='春季开工旺季，水泥建材需求增加',
    ),

    # --- 科技/电子 (全年) ---
    SeasonWindow(
        'AI 算力基建', 1, 1, 12, 31,
        keywords=['CPO', '光模块', '光通信', 'PCB',
                  '服务器', '算力', '半导体', '存储'],
        description='AI 算力基建全年主线，持续跟踪',
    ),
    SeasonWindow(
        '618 消费电子', 5, 20, 6, 20,
        keywords=['消费电子', '手机', '面板', 'PCB'],
        description='618 电商大促，消费电子销量上升',
        preheat_weeks=1, cooldown_weeks=0,
    ),
    SeasonWindow(
        '新机发布周期', 8, 1, 10, 31,
        keywords=['消费电子', '手机', '苹果概念', '面板', 'PCB'],
        description='秋季新品发布季（苹果/华为新机），供应链备货旺季',
    ),

    # --- 运输/物流 ---
    SeasonWindow(
        '双十一物流', 10, 15, 11, 20,
        keywords=['物流', '快递', '电商', '包装'],
        description='双十一电商旺季，物流快递订单暴增',
        preheat_weeks=2, cooldown_weeks=1,
    ),
]


def get_active_themes(check_date=None):
    """
    获取 check_date 当天处于活跃窗口的题材列表
    返回: [(name, keywords, status, boost, description), ...]
    """
    if check_date is None:
        check_date = date.today()

    active = []
    for w in SEASONAL_WINDOWS:
        is_active, status, boost = w.status(check_date)
        if is_active:
            active.append({
                'name': w.name,
                'keywords': w.keywords,
                'status': status,
                'boost': boost,
                'description': w.description,
            })

    # 排序：active > preheat > cooldown, boost 高的排前面
    status_order = {'active': 0, 'preheat': 1, 'cooldown': 2}
    active.sort(key=lambda x: (status_order.get(x['status'], 9), -x['boost']))
    return active


def get_keyword_boost_map(check_date=None):
    """
    获取关键词 → boost 系数的映射
    用于快速查找某个关键词是否有季节性加持
    """
    active = get_active_themes(check_date)
    boost_map = {}
    for theme in active:
        for kw in theme['keywords']:
            # 取最大的 boost
            if kw not in boost_map or theme['boost'] > boost_map[kw]:
                boost_map[kw] = theme['boost']
    return boost_map


def print_calendar(check_date=None):
    """打印当前活跃的季节性题材"""
    if check_date is None:
        check_date = date.today()

    status_labels = {'preheat': '🔥预热', 'active': '🟢活跃', 'cooldown': '🌙退潮'}

    active = get_active_themes(check_date)
    if not active:
        print(f"\n  {check_date}: 暂无季节性题材窗口\n")
        return

    print(f"\n{'='*70}")
    print(f"  📅 题材日历 — {check_date}")
    print(f"{'='*70}")
    print(f"{'题材':<16}{'状态':<10}{'强度':<8}{'关键词'}")
    print('-' * 70)

    for t in active:
        label = status_labels.get(t['status'], t['status'])
        strength = '█' * int(t['boost'] * 10) + '░' * (10 - int(t['boost'] * 10))
        keywords_str = ', '.join(t['keywords'][:6])
        if len(t['keywords']) > 6:
            keywords_str += '...'
        print(f"  {t['name']:<16}{label:<10}{strength:<8}{keywords_str}")
        print(f"     {t['description']}")

    print(f"{'='*70}\n")


def main():
    import sys
    if len(sys.argv) > 1:
        from datetime import datetime
        d = datetime.strptime(sys.argv[1], '%Y-%m-%d').date()
        print_calendar(d)
    else:
        print_calendar()


if __name__ == '__main__':
    main()
