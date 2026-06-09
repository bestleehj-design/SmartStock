# -*- coding: utf-8 -*-
"""
上涨逻辑验证器
对候选股进行结构化逻辑验证：政策→产业→个股 三环链条 + 逻辑硬伤检查
"""

import sys
import os
import json
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import pymysql

DB_CONFIG = {
    'host': 'localhost', 'port': 3306,
    'user': 'root', 'password': '12345678',
    'database': 'gp2', 'charset': 'utf8mb4',
}


class LogicValidator:
    """上涨逻辑验证器"""

    # 政策关键词（板块名匹配）
    POLICY_SECTORS = {
        '半导体': {'keywords': ['大基金', '国产替代', '自主可控'], 'score': 5},
        'AI': {'keywords': ['算力基建', '人工智能', '东数西算'], 'score': 5},
        '新能源': {'keywords': ['碳中和', '新能源', '光伏'], 'score': 5},
        'CPO': {'keywords': ['算力基建', '国家算力网'], 'score': 5},
        'PCB': {'keywords': ['AI基建', '数据中心'], 'score': 4},
        '光模块': {'keywords': ['算力基建', '5G'], 'score': 5},
        '电力': {'keywords': ['电力改革', '新型电力系统'], 'score': 4},
        '存储': {'keywords': ['国产替代', '自主可控'], 'score': 4},
    }

    # 逻辑硬伤关键词
    HARD_FAULT_KEYWORDS = {
        '减持': {'kw': ['减持', '套现'], 'severity': 'high'},
        '问询': {'kw': ['问询函', '监管函', '关注函'], 'severity': 'high'},
        '立案': {'kw': ['立案调查', '证监会'], 'severity': 'critical'},
        'ST': {'kw': ['ST', '*ST', '退市风险'], 'severity': 'critical'},
        '业绩变脸': {'kw': ['预亏', '亏损', '业绩下滑'], 'severity': 'medium'},
        '质押': {'kw': ['质押', '爆仓', '平仓'], 'severity': 'medium'},
        '商誉': {'kw': ['商誉减值', '计提'], 'severity': 'medium'},
        '解禁': {'kw': ['限售解禁', '解禁'], 'severity': 'low'},
    }

    def __init__(self):
        pass

    def _db(self):
        return pymysql.connect(**DB_CONFIG)

    # ================================================================
    # 核心验证
    # ================================================================

    def validate(self, code, name, sector, news_list=None, fundamental=None):
        """
        对一只候选股进行逻辑验证
        返回: {
            'logic_chain': str,
            'chain_completeness': float,
            'chain_detail': {...},
            'hard_faults': [...],
            'verdict': str,
            'verdict_label': str,
        }
        """
        # 1. 检查逻辑链条
        chain = self._check_logic_chain(name, sector, news_list or [], fundamental or {})

        # 2. 检查逻辑硬伤
        faults = self._check_hard_faults(code, name, news_list or [])

        # 3. 综合判断
        completeness = chain['completeness']
        has_critical = any(f['severity'] == 'critical' for f in faults)
        has_high = any(f['severity'] == 'high' for f in faults)

        if has_critical:
            verdict = 'reject'
            label = '❌ 一票否决'
        elif completeness >= 0.7 and not faults:
            verdict = 'strong'
            label = '✅ 逻辑扎实'
        elif completeness >= 0.5:
            verdict = 'ok'
            label = '⚠️ 逻辑尚可'
        else:
            verdict = 'weak'
            label = '❓ 逻辑薄弱'

        return {
            'chain_completeness': completeness,
            'chain_detail': chain,
            'hard_faults': faults,
            'verdict': verdict,
            'verdict_label': label,
        }

    def _check_logic_chain(self, name, sector, news_list, fundamental):
        """检查 政策→产业→个股 三环链条"""

        # 政策面
        policy_match = None
        policy_score = 0
        for kw, info in self.POLICY_SECTORS.items():
            if kw in sector or kw in name:
                policy_match = info
                policy_score = info['score']
                break

        # 如果没有匹配，检查新闻中是否有政策关键词
        if not policy_match:
            for news in news_list:
                title = news.get('title', '')
                if any(k in title for k in ['政策', '发改委', '国务院', '工信部']):
                    policy_score = 3
                    break

        # 产业面（从新闻看）
        industry_buzzwords = ['景气', '回暖', '涨价', '需求', '扩产', '订单']
        industry_score = 0
        for news in news_list:
            title = news.get('title', '')
            if any(k in title for k in industry_buzzwords):
                industry_score = 4
                break
        if industry_score == 0 and sector not in ('其他', '', None):
            industry_score = 2  # 有板块归属，给基础分

        # 个股面
        company_score = 3  # 默认基础分（策略1/2筛过的，基本面不会太差）
        roe = fundamental.get('roe')
        if roe and float(roe) > 15:
            company_score = 5
        elif roe and float(roe) < 5:
            company_score = 1

        # 计算完整度
        max_score = 13  # 5+4+4
        total = policy_score + industry_score + company_score
        completeness = round(total / max_score, 2)

        links = []
        links.append(f"政策: {'✅' if policy_score>=3 else '⚠️' if policy_score>0 else '❌'} "
                     f"({policy_score}/5)")
        links.append(f"产业: {'✅' if industry_score>=3 else '⚠️' if industry_score>0 else '❌'} "
                     f"({industry_score}/4)")
        links.append(f"个股: {'✅' if company_score>=3 else '⚠️' if company_score>0 else '❌'} "
                     f"({company_score}/4)")

        return {
            'completeness': completeness,
            'links': links,
            'policy_score': policy_score,
            'industry_score': industry_score,
            'company_score': company_score,
        }

    def _check_hard_faults(self, code, name, news_list):
        """检查逻辑硬伤"""
        faults = []

        # 从新闻中扫描硬伤关键词
        for news in news_list:
            title = news.get('title', '')
            for fault_name, info in self.HARD_FAULT_KEYWORDS.items():
                for kw in info['kw']:
                    if kw in title:
                        faults.append({
                            'type': fault_name,
                            'keyword': kw,
                            'severity': info['severity'],
                            'source': title[:60],
                        })
                        break

        # 去重
        seen = set()
        unique_faults = []
        for f in faults:
            key = f['type']
            if key not in seen:
                seen.add(key)
                unique_faults.append(f)

        return unique_faults

    # ================================================================
    # 输出
    # ================================================================

    def print_report(self, result, code, name):
        """打印逻辑验证报告"""
        if not result:
            return

        print(f"\n  ┌─ 逻辑验证 ────────────────────────────")
        print(f"  │ {result['verdict_label']}")

        # 逻辑链
        chain = result.get('chain_detail', {})
        links = chain.get('links', [])
        if links:
            print(f"  │ 逻辑链: {' → '.join(links)}")

        # 硬伤
        faults = result.get('hard_faults', [])
        if faults:
            severity_labels = {'critical': '🔴', 'high': '🟠', 'medium': '🟡', 'low': '⚪'}
            print(f"  │ ⚠️ 硬伤:")
            for f in faults:
                sev = severity_labels.get(f['severity'], '')
                print(f"  │   {sev} {f['type']}: {f['source']}")

        if not faults:
            print(f"  │ ✅ 未发现逻辑硬伤")

        print(f"  │ 链条完整度: {result['chain_completeness']:.0%}")
        print(f"  └──────────────────────────────────────────")


def main():
    # 测试
    validator = LogicValidator()
    test_news = [
        {'title': '国务院印发算力基础设施高质量发展行动计划，相关公司受益'},
        {'title': 'CPO光模块需求旺盛，新易盛业绩超预期'},
    ]
    result = validator.validate('300502.SH', '新易盛', '光模块/CPO', test_news)
    validator.print_report(result, '300502.SH', '新易盛')


if __name__ == '__main__':
    main()
