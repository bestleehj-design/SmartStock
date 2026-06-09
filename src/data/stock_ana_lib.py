# -*- coding: utf-8 -*-
"""
Created on Sun Dec 19 19:35:59 2021

@author: hao
"""
from data.newstocklib import *
import time as _time
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties  # 导入FontProperties
import socket
import struct
import numpy as np

color_list = ('red','blue','green','black','orange','purple','lime')
rmv_ths_concept = ('创历史','昨日','同花顺','陆股通','证金持股','机构','深股通')

# 获取价格列表中的最大和最小值
# 返回最大和最小价格的索引位置
def look_for_max_min_price(price_list):
    max_price=-1
    max_price_index = -1
    min_price=999999999
    min_price_index = -1
    
    total_price=0
    for i in range(0,len(price_list)):
        if price_list[i][1] >max_price:
            max_price_index = i
            max_price = price_list[i][1]
        if price_list[i][1] < min_price:
            min_price = price_list[i][1]
            min_price_index = i
        total_price += price_list[i][1]
    
    return max_price_index, min_price_index, total_price/len(price_list)

# 显示增长率图表信息
def display_inc_rate_list(labelstr,inc_rate_list, linecolor=None, is_focus=False ):
    x_list = []
    y_list = []        

    length = len(inc_rate_list)
    for i in range(length-1,-1,-1):
        x_list.append(inc_rate_list[i][0])
        y_list.append(inc_rate_list[i][1])
    
    lw = 1
    if is_focus:
        lw = 2
        
    if linecolor == None:
        plt.plot(x_list,y_list,label=labelstr, lw=lw)
    else:
        plt.plot(x_list,y_list,label=labelstr, lw=lw, color = linecolor)
    return

def process_single_stock_info(sql_result,exchange_day_result):
    latest_adj_factor = sql_result[0][8]
    single_code_price_list = []
    single_code_trade_amount_list = []
    single_code_all_price_list = []
    single_code_amount_volume_list = []
    exg_day_len = len(exchange_day_result)
    
    cur_stock_index = 0
    for i in range(0,exg_day_len):
        if cur_stock_index >= len(sql_result):
            break
        
        trade_date = exchange_day_result[i]
        cur_tradedate = sql_result[cur_stock_index][1] 
        trade_amount = sql_result[cur_stock_index][7]     
        volume = sql_result[cur_stock_index][6]     
        single_code_trade_amount_list.append(trade_amount)        
        
        if trade_date.__eq__(cur_tradedate):
            t_index = cur_stock_index
            t_date = cur_tradedate
            
            #adj_factor = sql_result[cur_stock_index][8]/latest_adj_factor
            
            #adj_price_open = sql_result[cur_stock_index][2] * adj_factor
            #adj_price_high = sql_result[cur_stock_index][3] * adj_factor
            #adj_price_low = sql_result[cur_stock_index][4] * adj_factor
            #adj_price_close = sql_result[cur_stock_index][5] * adj_factor
            
            #single_code_price_list.append((cur_tradedate, adj_price_close))
            #single_code_all_price_list.append((cur_tradedate,adj_price_open,adj_price_high,adj_price_low,adj_price_close,trade_amount))
            cur_stock_index +=1
        elif cur_stock_index +1 < len(sql_result):
            t_index = cur_stock_index + 1
            t_date = trade_date
            #adj_factor = sql_result[cur_stock_index+1][8]/latest_adj_factor
            
            #adj_price_open = sql_result[cur_stock_index+1][2] * adj_factor
            #adj_price_high = sql_result[cur_stock_index+1][3] * adj_factor
            #adj_price_low = sql_result[cur_stock_index+1][4] * adj_factor
            #adj_price_close = sql_result[cur_stock_index+1][5] * adj_factor
            
            #single_code_price_list.append((trade_date, adj_price_close))
            #single_code_all_price_list.append((trade_date,adj_price_open,adj_price_high,adj_price_low,adj_price_close,trade_amount))
        else:
            break
        
        adj_factor = sql_result[t_index][8]/latest_adj_factor
        adj_price_open = sql_result[t_index][2] * adj_factor
        adj_price_high = sql_result[t_index][3] * adj_factor
        adj_price_low = sql_result[t_index][4] * adj_factor
        adj_price_close = sql_result[t_index][5] * adj_factor
        if volume == 0:
            adj_price_ave = 0
            print(f'volume is 0, {sql_result[t_index][0]}, {t_date}, {trade_amount}')
        else:
            adj_price_ave = (trade_amount*1000)*adj_factor / (volume*100)
        
        single_code_price_list.append((t_date, adj_price_close))
        single_code_all_price_list.append((t_date,adj_price_open,adj_price_high,adj_price_low,adj_price_close,trade_amount,volume,adj_price_ave,adj_factor))
        
        single_code_amount_volume_list.append((t_date,trade_amount*1000,volume*100))
        
    
    return single_code_price_list, single_code_trade_amount_list, single_code_all_price_list, single_code_amount_volume_list


#计算所有股票的涨幅, 也包括etf， 概念
#从start_days_ahead 开始，计算到end_days_ahead的涨幅。特别的，当end_days_ahead设置为0时，即到最新的涨幅
#输出格式：
#    code_to_inc_rate_list
#    inc_rate_list = [(date, inc_rate)]
#    0是最新的
def get_stock_increase_rate_by_day(code_to_price_list, start_days_ahead, end_days_ahead):
    code_to_inc_rate_list = {}
    
    for code in code_to_price_list:
        stock_data = code_to_price_list[code]
        
        if len(stock_data) <= start_days_ahead:
            continue
        
        inc_rate_list = []        
        price_start = stock_data[start_days_ahead][1]
        for i in range(end_days_ahead,start_days_ahead+1):
            price_i = stock_data[i][1]
            inc_rate = (price_i-price_start)/price_start
            inc_rate_list.append((stock_data[i][0], inc_rate ))        
        
        code_to_inc_rate_list[code] = inc_rate_list
        
    return code_to_inc_rate_list

def get_stock_increase_rate_by_date(code_to_price_list, start_date):
    code_to_inc_rate_list = {}
    for code in code_to_price_list:
        stock_data = code_to_price_list[code]
        length = len(stock_data)
        
        last_date_index = length-1
        for i in range(length-1, -1,-1):
            cur_date = stock_data[i][0]
            if start_date <= cur_date:
                break
            last_date_index = i
        
        inc_rate_list = []        
        price_start = stock_data[last_date_index][1]
        for i in range(0,last_date_index+1):
            price_i = stock_data[i][1]
            inc_rate = (price_i-price_start)/price_start
            inc_rate_list.append((stock_data[i][0], inc_rate ))        
        
        code_to_inc_rate_list[code] = inc_rate_list
        
    return code_to_inc_rate_list

def get_reportdate_list(x_list):
    result = []
    for x in x_list:
        reportdate = x[1]
        if reportdate not in result:
            result.append(reportdate)
    return result

def get_holder_amount(x_list, reportdate):
    result = 0
    for x in x_list:
        if x[1] == reportdate:
            result += x[3]
    return result

def remove_duplicate_item(oldlist):
    result = []
    for x in oldlist:
        if x not in result:
            result.append(x)
    return result

def encode_string_to_nt_packet(normal_string, c_struct_type):
    gb2312_str = normal_string.encode('gb2312')
    return c_struct_type.pack()

class all_stock_info:
    mydb = None
    dbcursor = None
    
    code_to_info = {}
    name_to_code = {}
    stock_to_info = None
    etf_to_info = None
    ths_concept_to_info = None
    x_to_info = {}
    xtype_str = {0:'Code', 1:'ETF', 2:'THS Concept'}
    
    exchange_day_result = None
    code_to_price_list = None
    code_to_all_price_list = None
    code_to_inc_rate_list = None
    
    code_to_trade_amount_list = None
    code_to_amount_volume_list = None
    
    code_to_daily_basic_info = None
    code_to_holder_info = {}
    code_to_fina_info = None
    code_to_daily_money_flow_info = None
    code_to_daily_money_flow_info_2 = {}
    code_to_daily_cyq_perf_info = {}
    
    code_to_choice_concept_list = {}
    choice_concept_to_code_list = {}    
    code_to_etf_list = {}
    etf_to_code_list = {}
    code_to_ths_concept_list = {}
    ths_concept_to_code_list = {}
    
    sw_to_code_list = {}
    
    hot_ths_concepts_list = []
    hot_choice_concepts_list = []
    hot_sw_list = {'1':[],'2':[],'3':[]}
    hot_manmade_block_list = []
    
    hot_all_block_list = []
    
    #for network transfer
    client_socket = None
    # int msg_type
    # int msg_length
    # int line_count
    # STRING_ENCODE title_desc  --- int, char[256]
    # LINE_INFO line_info[5]    --- int, STRING_ENCODE desc
    c_head_struct = None
    c_line_info_struct = None
    c_body_struct = None
    packed_head = None
    packed_line_info_list = []
    packed_body_list = []
    nt_line_count = 0
    nt_title_desc = ''
    nt_line_info = []
    
    
    def __init__(self, db, cursor):
        self.mydb = db
        self.dbcursor = cursor
        self.exchange_day_result = get_exchange_day_from_db(cursor)
        
        self.c_head_struct = struct.Struct('iiii256s')
        self.c_line_info_struct = struct.Struct('ii256s')
        self.c_body_struct = struct.Struct('id')
        return
    
    # ths, choice, sw1, sw2, sw3, manmade 等，都是包括的名字，而不是code
    def set_hot_block_list(self, ths, choice, sw1,sw2,sw3, manmade, code_list):
        self.hot_ths_concepts_list = ths
        self.hot_choice_concepts_list = choice
        self.hot_sw_list[1] = sw1
        self.hot_sw_list[2] = sw2
        self.hot_sw_list[3] = sw3
        self.hot_manmade_block_list = manmade
        
        hot_code_list = []
        for ths_concept_name in ths:
            if ths_concept_name in self.name_to_code:
                ths_concept_code = self.name_to_code[ths_concept_name]             
                if ths_concept_code in self.ths_concept_to_code_list:
                    hot_code_list += self.ths_concept_to_code_list[ths_concept_code]
        
        for choice_concept in choice:
            if choice_concept in self.choice_concept_to_code_list:
                hot_code_list += self.choice_concept_to_code_list[choice_concept]
        
        for i in range(1,4):
            for sw_name in self.hot_sw_list[i]:
                if sw_name in self.sw_to_code_list[i]:
                    hot_code_list += self.sw_to_code_list[i][sw_name]
        
        hot_code_list += code_list
        
        self.hot_all_block_list =  remove_duplicate_item(hot_code_list)
        return

    def generate_ths_concept_info(self):
        self.code_to_ths_concept_list = {}
        self.ths_concept_to_code_list = {}
        
        for ths_concept in self.ths_concept_to_info:
            ths_concept_basic_info = self.ths_concept_to_info[ths_concept]
            code_list_str = ths_concept_basic_info[6]
            if len(code_list_str) ==0:
                continue
            code_list = code_list_str.split(';')
            length = len(code_list)
            if code_list[length-1] == '':
                code_list = code_list[0:length-1]
            self.ths_concept_to_code_list[ths_concept] = code_list
            
            for code in code_list:
                if code in self.code_to_ths_concept_list:
                    if ths_concept not in self.code_to_ths_concept_list[code]:
                        self.code_to_ths_concept_list[code].append(ths_concept)
                else:
                    self.code_to_ths_concept_list[code] = [ths_concept]
        return

    def generate_etf_info(self):
        self.code_to_etf_list = {}
        self.etf_to_code_list = {}
        
        for etf_code in self.etf_to_info:
            etf_basic_info = self.etf_to_info[etf_code]
            code_list_str = etf_basic_info[6]
            if len(code_list_str) ==0:
                continue
            code_list = code_list_str.split(';')
            length = len(code_list)
            if code_list[length-1] == '':
                code_list = code_list[0:length-1]
            self.etf_to_code_list[etf_code] = code_list
            
            for code in code_list:
                if code in self.code_to_etf_list:
                    if etf_code not in self.code_to_etf_list[code]:
                        self.code_to_etf_list[code].append(etf_code)
                else:
                    self.code_to_etf_list[code] = [etf_code]
        return

    def generate_sw_info(self):
        self.sw_to_code_list[1] = {}
        self.sw_to_code_list[2] = {}
        self.sw_to_code_list[3] = {}
        
        for code in self.stock_to_info:
            stock_basic_info = self.stock_to_info[code]
            for i in range(1,4):
                sw_i = stock_basic_info[i+1]
                if sw_i != '':
                    if sw_i in self.sw_to_code_list[i]:
                        if code not in self.sw_to_code_list[i][sw_i]:
                            self.sw_to_code_list[i][sw_i].append(code)
                    else:
                        self.sw_to_code_list[i][sw_i] = [code]
        return
            
            
    def generate_choice_concept_info(self):
        self.code_to_choice_concept_list = {}
        for code in self.stock_to_info:
            stock_basic_info = self.stock_to_info[code]
            choice_concept_list = stock_basic_info[5]
            self.code_to_choice_concept_list[code] = choice_concept_list.split(',')
        
        self.choice_concept_to_code_list = {}
        for code in self.code_to_choice_concept_list:
            choice_concept_list = self.code_to_choice_concept_list[code]
            for choice_concept in choice_concept_list:
                if choice_concept == '':
                    continue
                if choice_concept in self.choice_concept_to_code_list:
                    code_list = self.choice_concept_to_code_list[choice_concept]
                    if code not in code_list:
                        code_list.append(code)
                else:
                    self.choice_concept_to_code_list[choice_concept] = [code]
        
        return
    
    def get_all_basic_info(self):
        self.code_to_info, self.stock_to_info, self.etf_to_info, self.ths_concept_to_info, self.name_to_code = \
            get_all_stock_basic_info_from_db(self.dbcursor)
        self.x_to_info = {'stock':self.stock_to_info, 'etf':self.etf_to_info, 'ths':self.ths_concept_to_info }
        return
    
    def read_all_stock_info(self):
        self.code_to_price_list = {}
        self.code_to_all_price_list = {}
        self.code_to_trade_amount_list = {}
        self.code_to_amount_volume_list = {}
        #self.code_to_daily_cyq_perf_info = {}
        
        for code in self.code_to_info:
            sql = f'select * from daily_info_tbl where code="{code}" order by tradedate desc'
            self.dbcursor.execute(sql)
            result1 = self.dbcursor.fetchall()
            if result1 == None or len(result1)==0:
                continue
            
            #sql = f'select * from cyq_perf_tbl where code="{code}" order by tradedate desc'
            #self.dbcursor.execute(sql)
            #result2 = self.dbcursor.fetchall()
            #if result2 == None or len(result2)==0:
            #    continue
            
            single_code_price_list, single_code_trade_amount_list,\
                single_code_all_price_list, single_code_amount_volume_list,\
                = process_single_stock_info(result1, self.exchange_day_result)
                
            self.code_to_price_list[code] = single_code_price_list
            self.code_to_all_price_list[code] = single_code_all_price_list
            self.code_to_trade_amount_list[code] = single_code_trade_amount_list
            self.code_to_amount_volume_list[code] = single_code_amount_volume_list
            #self.code_to_daily_cyq_perf_info[code] = single_code_cyq_perf_list
        
        return self.code_to_price_list, self.code_to_trade_amount_list, \
            self.code_to_all_price_list, self.code_to_amount_volume_list
    
    def find_all_stock_bigger_than_trade_amount(self, days_count, ave_trade_amount):
        result = []
        for code in self.code_to_trade_amount_list:
            single_code_trade_amount_list = self.code_to_trade_amount_list[code]
            if len(single_code_trade_amount_list) < days_count:
                continue
            ave_amount = sum(single_code_trade_amount_list[0:days_count]) / days_count
            if ave_amount>=ave_trade_amount:
                result.append(code)
        
        return result
            

    def get_stock_increase_rate_by_day(self, start_days_ahead, end_days_ahead):
        self.code_to_inc_rate_list = \
            get_stock_increase_rate_by_day(self.code_to_price_list,start_days_ahead, end_days_ahead)
        return self.code_to_inc_rate_list
    
    def get_stock_increase_rate_by_date(self,start_date):
        self.code_to_inc_rate_list = \
            get_stock_increase_rate_by_date(self.code_to_price_list,start_date)
        return self.code_to_inc_rate_list

    def read_all_daily_basic_info(self):
        self.code_to_daily_basic_info = {}
        
        for code in self.code_to_info:
            sql = f'select * from daily_basic_tbl where code="{code}" order by tradedate desc'
            self.dbcursor.execute(sql)
            result = self.dbcursor.fetchall()
            if result == None or len(result)==0:
                continue
            self.code_to_daily_basic_info[code] = result
        
        return self.code_to_daily_basic_info
    
    #----------------------获取十大流通股东信息------------------------------
    #获取机构持股者数量
    def get_jigou_holers_num(self, code):
        if code not in self.code_to_holder_info:
            return 0
        holders_data = self.code_to_holder_info[code]
        latest_reportdate = holders_data[0][1]
        jigou_count = 0            
        for x in holders_data:
            if latest_reportdate == x[1]:
                holder_name = x[2]
                if len(holder_name) > 4:
                    jigou_count += 1
        
        return jigou_count
    
    # 获取机构持股者大于某个数量的股票列表
    def find_jigou_holders(self, min_jigou_count):
        result = []
        for code in self.code_to_holder_info:
            holders_data = self.code_to_holder_info[code]
            
            latest_reportdate = holders_data[0][1]
            jigou_count = 0            
            for x in holders_data:
                if latest_reportdate == x[1]:
                    #报告期相同，则看是否是机构
                    holder_name = x[2]
                    if len(holder_name) > 4:
                        jigou_count += 1
                else:
                    #如果不同了，那么就跳出
                    break
            
            if jigou_count>= min_jigou_count:
                result.append(code)
        
        return result
    
    # 确定某个股票10大流通持股比例是否增加
    def if_top10_amount_increase(self,code):
        if code not in self.code_to_holder_info:
            return 0
        holders_data = self.code_to_holder_info[code]
        reportdate_list = get_reportdate_list(holders_data)
        if len(reportdate_list) < 2:
            return 0
        amount0 = get_holder_amount(holders_data, reportdate_list[0])
        amount1 = get_holder_amount(holders_data, reportdate_list[1])
        if amount0 > amount1:
            return 1
        return 0
    
    # 获取最新一个季度10大流通股持股比例大于前一个季度的股票列表
    def find_top10_amount_increase(self):
        result = []
        for code in self.code_to_holder_info:
            holders_data = self.code_to_holder_info[code]
            reportdate_list = get_reportdate_list(holders_data)
            if len(reportdate_list) < 2:
                continue
            
            amount0 = get_holder_amount(holders_data, reportdate_list[0])
            amount1 = get_holder_amount(holders_data, reportdate_list[1])
            if amount0 > amount1:
                result.append((code, amount0-amount1))
        
        result.sort(key=lambda x:x[1], reverse=True)
        return result
        
    
    def read_all_holder_info(self):
        self.code_to_holder_info = {}
        
        for code in self.code_to_info:
            sql = f'select * from holder_info_tbl where code="{code}" order by reportdate desc'
            self.dbcursor.execute(sql)
            result = self.dbcursor.fetchall()
            if result == None or len(result)==0:
                continue
            self.code_to_holder_info[code] = result
        
        return self.code_to_holder_info
    
    #本季度 x 同比增长大于某个阈值
    # x = 0, 单季度扣非净利润
    # x = 1, 单季度净利润
    # x = 2, 单季度归母净利润
    def find_fina_x_increase(self, x_indicator, threshold, years_num):
        result = []
        for code in self.code_to_fina_info:
            fina_data = self.code_to_fina_info[code]
            reportdate_list = get_reportdate_list(fina_data)
            if len(reportdate_list) < 1 + years_num*4:
                continue
            
            found = True
            for i in range(0,years_num*4, 4):
                if x_indicator == 1:
                    q_profit_yoy= fina_data[i][7]
                    if q_profit_yoy < threshold:
                        found = False
                        break
                elif x_indicator == 2:
                    q_netprofit_yoy = fina_data[i][8]
                    if q_netprofit_yoy < threshold:
                        found = False
                        break
                elif x_indicator == 0:
                    q_dtprofit_cur = fina_data[i][3]
                    q_dtprofit_last = fina_data[i+4][3]
                    if q_dtprofit_cur < q_dtprofit_last or not \
                        (q_dtprofit_last == 0 or (q_dtprofit_cur-q_dtprofit_last)*100/abs(q_dtprofit_last) >=threshold):
                        found = False
                        break
            if found:
                result.append(code)
        return result
    
    def read_all_fina_info(self):
        self.code_to_fina_info = {}
        
        for code in self.code_to_info:
            sql = f'select * from fina_info_tbl where code="{code}" order by reportdate desc'
            self.dbcursor.execute(sql)
            result = self.dbcursor.fetchall()
            if result == None or len(result)==0:
                continue
            self.code_to_fina_info[code] = result
        
        return self.code_to_fina_info
    
    def get_money_flow_value(self, code, N, start_day_index = 0):
        if code not in self.code_to_daily_money_flow_info:
            return 0
        code_moneyflow = self.code_to_daily_money_flow_info[code]
        length = N
        if len(code_moneyflow) < N:
            length = len(code_moneyflow)
        money = 0
        for i in range(start_day_index,start_day_index+length):
            money += code_moneyflow[i][3] + code_moneyflow[i][5]
        
        return money
    
    def get_money_flow_between_date(self, code, start_date, end_date):
        if code not in self.code_to_daily_money_flow_info:
            return 0
        code_moneyflow = self.code_to_daily_money_flow_info[code]
        length = len(code_moneyflow)
        money = 0
        for i in range(0,length):
            tradedate = code_moneyflow[i][1] 
            if tradedate>=start_date and tradedate<=end_date:
                money += code_moneyflow[i][3] + code_moneyflow[i][5]
        
        return money
    
    def find_money_flow_increase(self, N, amount, less_amount=None):
        result = []
        for code in self.code_to_daily_money_flow_info:
            money = self.get_money_flow_value(code, N)
            if money >= amount:
                if less_amount == None or money <= less_amount:
                    result.append(code)
        return result
    
    def get_money_flow_value_v2(self, code, N):
        if code not in self.code_to_daily_money_flow_info:
            return 0
        code_moneyflow = self.code_to_daily_money_flow_info[code]
        length = N
        if len(code_moneyflow) < N:
            length = len(code_moneyflow)
        money = 0
        rate = 1
        for i in range(0,length):
            money += (code_moneyflow[i][3] + code_moneyflow[i][5])*rate
            rate -= 0.1
        
        return money
    
    def get_money_flow_value_v3(self, code, N, start_day_index = 0):
        if code not in self.code_to_daily_money_flow_info_2:
            return 0
        code_moneyflow = self.code_to_daily_money_flow_info_2[code]
        #length = N
        #if len(code_moneyflow) < N:
        #    length = len(code_moneyflow)
        money = code_moneyflow[start_day_index+N-1][11] + code_moneyflow[start_day_index+N-1][15]
        for i in range(start_day_index,start_day_index+N-1):
            money += (code_moneyflow[i][11] + code_moneyflow[i][15]) - \
                (code_moneyflow[i][13] + code_moneyflow[i][17])
        
        return money
    
    def average_cost_of_big_buy_deal(self, code, day_index):
        if code not in self.code_to_daily_money_flow_info_2:
            return 0
        code_moneyflow = self.code_to_daily_money_flow_info_2[code]
        money = code_moneyflow[day_index][11] + code_moneyflow[day_index][15]
        lot = code_moneyflow[day_index][10] + code_moneyflow[day_index][14]
        if lot == 0:
            return 0
        return (money*10000)/(lot*100)
    
    def look_for_correct_day(self, code, price):
        currect_day_index = -1
        for i in range(0,30):
            cost = self.average_cost_of_big_buy_deal(code,i)
            #if cost < price:
            if bigger_or_equal(price,cost):
                break
            currect_day_index = i
        
        return currect_day_index
    
    def get_zhuli_last_money(self, code, currect_day_index, use_orig_mf_func=True, start_day_index=0):
        if use_orig_mf_func:
            money = self.get_money_flow_value(code,currect_day_index+1, start_day_index)
        else:
            money = self.get_money_flow_value_v3(code,currect_day_index+1, start_day_index)
        
        return money
        
    
    def find_money_flow_increase_v2(self, N, amount):
        result = []
        for code in self.code_to_daily_money_flow_info:
            money = self.get_money_flow_value_v2(code, N)
            if money >= amount:
                result.append(code)
        return result
    
    def find_mf_increase_in_list(self, N_amount_tuple):
        result = []
        for N_amount in N_amount_tuple:
            N = N_amount[0]
            amount = N_amount[1]
            mf_increase = self.find_money_flow_increase(N,amount)
            if len(result) == 0:
                result = mf_increase
            else:
                result = list_jiaoji(result, mf_increase)
        
        return result
    
    
    def read_all_daily_money_flow_info(self):
        self.code_to_daily_money_flow_info = {}
        
        for code in self.code_to_info:
            sql = f'select * from daily_moneyflow_tbl where code="{code}" order by tradedate desc'
            self.dbcursor.execute(sql)
            result = self.dbcursor.fetchall()
            if result == None or len(result)==0:
                continue
            self.code_to_daily_money_flow_info[code] = result
        
        return self.code_to_daily_money_flow_info
    
    def read_all_daily_money_flow_info_2(self):
        self.code_to_daily_money_flow_info_2 = {}
        
        for code in self.code_to_info:
            sql = f'select * from daily_moneyflow_tbl_2 where code="{code}" order by tradedate desc'
            self.dbcursor.execute(sql)
            result = self.dbcursor.fetchall()
            if result == None or len(result)==0:
                continue
            self.code_to_daily_money_flow_info_2[code] = result
        
        return self.code_to_daily_money_flow_info_2
    
    def read_all_daily_cyq_perf_info(self):
        self.code_to_daily_cyq_perf_info = {}
        
        for code in self.code_to_info:
            sql = f'select * from cyq_perf_tbl where code="{code}" order by tradedate desc'
            self.dbcursor.execute(sql)
            result = self.dbcursor.fetchall()
            if result == None or len(result)==0:
                continue
            self.code_to_daily_cyq_perf_info[code] = result
        
        return self.code_to_daily_cyq_perf_info
    
    def create_socket(self):
        if self.client_socket == None:
            self.client_socket = socket.socket()
            if self.client_socket != None:
                self.client_socket.connect(("127.0.0.1",32768))
                print('connect to 127.0.0.1:32768')
        return
    
    def close_socket(self):
        if self.client_socket != None:
            self.client_socket.close()
            self.client_socket = None
        return
    
    def send_socket_info(self):
        if self.client_socket != None and self.nt_line_count>0:
            self.client_socket.send(self.packed_head)
            for x in self.packed_line_info_list:
                self.client_socket.send(x)
            for x in self.packed_body_list:
                self.client_socket.send(x)
            _time.sleep(1)
                
        return
    
    def begin_network_transfer(self, title):
        self.nt_line_count = 0
        self.nt_title_desc = title
        self.nt_line_info = []
        return
    
    def add_nt_line(self, pair_desc, data_list ):
        self.nt_line_count += 1
        self.nt_line_info.append((pair_desc, data_list))
        return
    
    def end_network_transfer(self):
        gb2312_str = self.nt_title_desc.encode('gb18030')
        self.packed_head = self.c_head_struct.pack(0,0,\
                                    self.nt_line_count,len(gb2312_str),gb2312_str)
        
        self.packed_line_info_list  = []
        for i in range(0,6):
            if i<self.nt_line_count:
                x = self.nt_line_info[i]
            else:
                x = ('',[])
                
            gb2312_str = x[0].encode('gb18030')
            tuple_data = self.c_line_info_struct.pack(len(x[1]), len(gb2312_str),gb2312_str)
            self.packed_line_info_list.append(tuple_data)
        
        self.packed_body_list  = []
        for x in self.nt_line_info:
            for y in x[1]:
                date_int = y[0].year*10000+y[0].month*100+y[0].day
                tuple_data = self.c_body_struct.pack(date_int, y[1])
                self.packed_body_list.append(tuple_data)
        return
    
    def create_display_canvas(self, titlestr):
        plt.figure(figsize=(20,10), dpi=50)
        plt.title(titlestr)
        plt.xlabel('Date')
        plt.ylabel('Increase Rate')
        
        return
    
    def show_canvas(self):
        font = FontProperties(fname="c:\\windows\\Fonts\\SimHei.ttf", size=14)  # 设置字体
        plt.legend(prop=font)
        plt.grid()
        plt.show()
        return
    
    # 显示单个代码、ETF、THS概念 的增长率信息
    def display_single_code(self, code, linecolor=None, is_focus=False):
        if code not in self.code_to_info or code not in self.code_to_inc_rate_list:
            return
            
        code_info = self.code_to_info[code]
        name = code_info[0]
        inc_rate_list = self.code_to_inc_rate_list[code]
            
        labelstr = code + ' ' + name            
        display_inc_rate_list(labelstr,inc_rate_list,linecolor, is_focus)
        return
    
    def nt_send_single_code_cyq_perf(self, code,length=-1, b_adjust_factor=True):
        if code not in self.code_to_info \
            or code not in self.code_to_daily_cyq_perf_info \
            or code not in self.code_to_all_price_list:
            return
        
        name = self.code_to_info[code][0]
        tiaozheng = '不调整'
        if b_adjust_factor:
            tiaozheng = '调整'
        self.begin_network_transfer(f'{code} {name} {length} {tiaozheng} 筹码分布曲线')
        
        pricelist = self.code_to_price_list[code]
        all_pricelist = self.code_to_all_price_list[code]
        cyq_info = self.code_to_daily_cyq_perf_info[code]
        cyq_list = {4:[],5:[],6:[],7:[],8:[]}
        labelstr = {4:'5%',5:'15%',6:'50%',7:'85%',8:'95%'}
        
        if length >= len(cyq_info) or length==-1:
            length = len(cyq_info)
            
        self.add_nt_line('收盘价',pricelist[0:length])
        for i in range(4,9):
            for j in range(0,length):
                if b_adjust_factor:
                    value = cyq_info[j][i]*all_pricelist[j][8]
                else:
                    value = cyq_info[j][i]
                cyq_list[i].append((cyq_info[j][1],value))
            self.add_nt_line(labelstr[i],cyq_list[i])
        self.end_network_transfer()
        self.send_socket_info()
        
        return
    
    def nt_send_single_code(self, code):
        if code not in self.code_to_info or code not in self.code_to_inc_rate_list:
            return
            
        code_info = self.code_to_info[code]
        name = code_info[0]
        inc_rate_list = self.code_to_inc_rate_list[code]
        
        money_flow_str = ''
        prev_mf = 0
        if code in self.code_to_daily_money_flow_info:
            for i in [1,2,4,6,10,15,20,30,40,50,60]:
                mf = self.get_money_flow_value(code,i)
                mf_inc = mf - prev_mf
                money_flow_str += f' ,{i}:{mf_inc:0.0f}'
                prev_mf = mf
        
        labelstr = code + ' ' + name + money_flow_str
        self.add_nt_line(labelstr,inc_rate_list)

        return
    
    #显示code_list对应的增长率信息
    def display_x_inc_rate_list(self, code_list, name_index_list, start_color_index=0):
        color_index = start_color_index
    
        #titlestr = f'{x_type} {name_index_list}'
        #self.create_display_canvas(titlestr)

        #for codex in result:
        for name_index in name_index_list:
            if name_index<0 or name_index>=len(code_list):
                continue
        
            code = code_list[name_index]
            self.display_single_code(code,color_list[color_index], False)

            color_index+=1
            if color_index>=len(color_list):
                color_index = 0
        
        #self.show_canvas()
        return
    
    def nt_send_x_inc_rate_list(self, code_list, name_index_list):
        #for codex in result:
        for name_index in name_index_list:
            if name_index<0 or name_index>=len(code_list):
                continue
        
            code = code_list[name_index]
            self.nt_send_single_code(code)
        
        return
    
    #显示code_list对应的增长率信息
    def display_raw_x_inc_rate_list(self, code_list, name_index_list):
        titlestr = f'Display raw x inc rate list @{name_index_list}'
        self.create_display_canvas(titlestr)
        
        self.display_x_inc_rate_list(code_list, name_index_list)
        
        self.show_canvas()
        return
    
    def nt_display_raw_x_inc_rate_list(self, titlestr, code_list, name_index_list):
        self.begin_network_transfer(f'{titlestr} @{name_index_list}')
        
        self.nt_send_x_inc_rate_list(code_list, name_index_list)
        
        self.end_network_transfer()
        self.send_socket_info()
        return
    
    def nt_full_display_raw_x_inc_rate_list(self, titlestr, code_list, name_index_list):
        for i in range(0,len(code_list),5):
            if i in name_index_list:
                self.nt_display_raw_x_inc_rate_list(titlestr, code_list,range(i,i+5))
        return
    
    #显示单个股票以及此股票对应的ths概念信息
    def display_single_code_and_ths_concept(self, code, name_index_list):
        titlestr = f'{code} THS concept {name_index_list}'
        self.create_display_canvas(titlestr)
        
        self.display_single_code(code,color_list[0],True )
        if code in self.code_to_ths_concept_list:
            ths_concept_list = self.code_to_ths_concept_list[code]
            self.display_x_inc_rate_list(ths_concept_list,name_index_list,1)
        
        self.show_canvas()
        return
    
    def nt_display_single_code_and_ths_concept(self, code, name_index_list):
        titlestr = f'显示股票 {code} {self.code_to_info[code][0]} 和对应的同花顺概念 {name_index_list}'
        self.begin_network_transfer(titlestr)
        
        self.nt_send_single_code(code)
        
        if code in self.code_to_ths_concept_list:
            ths_concept_list = self.code_to_ths_concept_list[code]
            self.nt_send_x_inc_rate_list(ths_concept_list,name_index_list)
        
        self.end_network_transfer()
        self.send_socket_info()
        return
    
    def nt_full_display_single_code_and_ths_concept(self, code, name_index_list):
        if code in self.code_to_ths_concept_list:
            ths_concept_list = self.code_to_ths_concept_list[code]
            length = len(ths_concept_list)
            for i in range(0,length,5):
                if i in name_index_list:
                    self.nt_display_single_code_and_ths_concept(code,range(i,i+5))
        return
    
    #显示单个股票以及此股票对应的ETF概念信息
    def display_single_code_and_ETF(self, code, name_index_list):
        titlestr = f'{code} ETF {name_index_list}'
        self.create_display_canvas(titlestr)
        
        self.display_single_code(code,color_list[0],True )
        if code in self.code_to_etf_list:
            etf_list = self.code_to_etf_list[code]
            self.display_x_inc_rate_list(etf_list,name_index_list,1)
        
        self.show_canvas()
        return
    
    def nt_display_single_code_and_ETF(self, code, name_index_list):
        titlestr = f'显示股票 {code} {self.code_to_info[code][0]} 和对应的ETF {name_index_list}'
        self.begin_network_transfer(titlestr)
        
        self.nt_send_single_code(code)

        if code in self.code_to_etf_list:
            etf_list = self.code_to_etf_list[code]
            self.nt_send_x_inc_rate_list(etf_list,name_index_list)
        
        self.end_network_transfer()
        self.send_socket_info()
        return
    
    def nt_full_display_single_code_and_ETF(self, code, name_index_list):
        if code in self.code_to_etf_list:
            etf_list = self.code_to_etf_list[code]
            length = len(etf_list)
            for i in range(0,length,5):
                if i in name_index_list:
                    self.nt_display_single_code_and_ETF(code,range(i,i+5))
        return
    
    #显示单个ths concept以及对应的股票信息
    def display_single_ths_concept_and_stock(self, ths_concept, name_index_list):
        titlestr = f'{ths_concept} Stock {name_index_list}'
        self.create_display_canvas(titlestr)
        
        self.display_single_code(ths_concept,color_list[0],True )
        if ths_concept in self.ths_concept_to_code_list:
            code_list = self.ths_concept_to_code_list[ths_concept]
            self.display_x_inc_rate_list(code_list,name_index_list,1)
        
        self.show_canvas()
        return
    
    def nt_display_single_ths_concept_and_stock(self, ths_concept, name_index_list):
        titlestr = f'显示同花顺概念 {ths_concept} {self.code_to_info[ths_concept][0]} 和对应的股票 {name_index_list}'
        self.begin_network_transfer(titlestr)
        
        self.nt_send_single_code(ths_concept)
        if ths_concept in self.ths_concept_to_code_list:
            code_list = self.ths_concept_to_code_list[ths_concept]
            self.nt_send_x_inc_rate_list(code_list,name_index_list)
        
        self.end_network_transfer()
        self.send_socket_info()
        return
    
    def nt_full_display_single_ths_concept_and_stock(self, ths_concept, name_index_list):
        if ths_concept in self.ths_concept_to_code_list:
            code_list = self.ths_concept_to_code_list[ths_concept]
            length = len(code_list)
            for i in range(0,length,5):
                if i in name_index_list:
                    self.nt_display_single_ths_concept_and_stock(ths_concept,range(i,i+5))
        return
    
    #显示单个ETF以及对应的股票信息
    def display_single_ETF_and_stock(self, etf_code, name_index_list):
        titlestr = f'{etf_code} Stock {name_index_list}'
        self.create_display_canvas(titlestr)
        
        self.display_single_code(etf_code,color_list[0],True )
        if etf_code in self.etf_to_code_list:
            code_list = self.etf_to_code_list[etf_code]
            self.display_x_inc_rate_list(code_list,name_index_list,1)
        
        self.show_canvas()
        return
    
    def nt_display_single_ETF_and_stock(self, etf_code, name_index_list):
        titlestr = f'显示ETF {etf_code} {self.code_to_info[etf_code][0]} 和对应的股票 {name_index_list}'
        self.begin_network_transfer(titlestr)
        
        self.nt_send_single_code(etf_code)
        if etf_code in self.etf_to_code_list:
            code_list = self.etf_to_code_list[etf_code]
            self.nt_send_x_inc_rate_list(code_list,name_index_list)
        
        self.end_network_transfer()
        self.send_socket_info()
        return
    
    def nt_full_display_single_ETF_and_stock(self, etf_code, name_index_list):
        if etf_code in self.etf_to_code_list:
            code_list = self.etf_to_code_list[etf_code]
            length = len(code_list)
            for i in range(0,length,5):
                if i in name_index_list:
                    self.nt_display_single_ETF_and_stock(etf_code,range(i,i+5))
        return
    
    #根据code_list的最近若干天增长率排序
    def get_code_list_inc_rate_list_by_order(self, code_list, last_days_count):
        tmp_list = []
        
        for code in code_list:
            '''
            if code not in self.code_to_inc_rate_list:
                continue
            inc_rate_list = self.code_to_inc_rate_list[code]
            if last_days_count <2 or len(inc_rate_list) < last_days_count:
                continue
            increase_rate = inc_rate_list[0][1] - inc_rate_list[last_days_count-1][1]
            '''
            if code not in self.code_to_price_list:
                continue
            stock_data = self.code_to_price_list[code]
            if last_days_count <2 or len(stock_data) < last_days_count:
                continue
            price0 = stock_data[0][1]
            price1 = stock_data[last_days_count-1][1]
            increase_rate = (price0 - price1)/price1
            
            tmp_list.append((code, increase_rate))
        
        tmp_list.sort(key=lambda x:x[1], reverse=True)
        
        result = []
        for x in tmp_list:
            result.append(x[0])
        
        return result        
    
    def zt_rate_by_code(self, code):
        return zt_rate(self.code_to_info[code][7])
    
    #找到若干个zt的票
    def get_zt_code_list(self, code_list, last_days_count, zt_count, prev_day_count=0, zt_threshold=0.1, count_more=False):
        tmp_list = []
        
        for code in code_list:
            if code not in self.code_to_price_list:
                continue
            stock_data = self.code_to_price_list[code]
            if last_days_count <2 or len(stock_data) < last_days_count + prev_day_count:
                continue
            count = 0
            for i in range(0+prev_day_count,last_days_count-1+prev_day_count):
                price0 = stock_data[i][1]
                price1 = stock_data[i+1][1]
                increase_rate = (price0 - price1)/price1
                if increase_rate>=self.zt_rate_by_code(code):
                    count += 1
            
            if count == zt_count or ( count_more and count>=zt_count ):
                tmp_list.append(code)
        
        return tmp_list        
    
    def get_dragon_head_code_list(self, code_list, last_days_count):
        tmp_list = []
        result = []
        
        for code in code_list:
            if code not in self.code_to_price_list:
                continue
            stock_data = self.code_to_price_list[code]
            if last_days_count <2: # or len(stock_data) < last_days_count:
                continue
            count = 0
            code_zt_rate = 0
            for i in range(0,last_days_count-1):
                if i >= len(stock_data)-1:
                    break
                price0 = stock_data[i][1]
                price1 = stock_data[i+1][1]
                increase_rate = (price0 - price1)/price1
                this_zt_rate = self.zt_rate_by_code(code)
                if increase_rate>=this_zt_rate:
                    count += this_zt_rate
                    code_zt_rate += this_zt_rate*(last_days_count-i)/last_days_count
            
            if count >= 0.1976:
                tmp_list.append((code_zt_rate,count,code))
        
        tmp_list.sort(key=lambda x:x[0], reverse=True)
        for x in tmp_list:
            result.append(x[2])
        
        return result, tmp_list
    
    #找到若干个zt的票，且按照连扳以及zt数量排序
    def get_zt_code_list_by_count(self, code_list, last_days_count, zt_threshold=0.099):
        tmp_list = []
        
        for code in code_list:
            if code not in self.code_to_price_list:
                continue
            name = self.code_to_info[code][0]
            if name.find('ST')>=0 or name.find('st')>=0:
                continue
            
            stock_data = self.code_to_price_list[code]
            if last_days_count <2 or len(stock_data) < last_days_count or len(stock_data) < 120:
                continue
            count = 0
            cont_zt = 0
            is_last_zt = False
            cont_zt_has_stoped = False
            for i in range(0,last_days_count-1):
                price0 = stock_data[i][1]
                price1 = stock_data[i+1][1]
                increase_rate = (price0 - price1)/price1
                if increase_rate>=self.zt_rate_by_code(code):
                    count += 1
                    if is_last_zt and not cont_zt_has_stoped:
                        if cont_zt == 0:
                            cont_zt = 2
                        else:
                            cont_zt += 1
                    is_last_zt = True
                else:
                    is_last_zt = False
                    if cont_zt>0:
                        cont_zt_has_stoped = True
            
            if count>0:
                tmp_list.append((count, cont_zt,code))
        
        total_zt_count = 0
        total_cont_zt = 0

        for x in tmp_list:
            total_zt_count += x[0]
            total_cont_zt += x[1]
        
        #tmp_list.sort(key=lambda x:x[1]*7+x[0]*3, reverse=True)
        tmp_list.sort(key=lambda x:x[0], reverse=True)
        
        return tmp_list[0:10], total_zt_count,total_cont_zt
    
    #在所有概念中搜索连扳和涨停数量最多的概念，然后按此概念排序
    def get_zt_concept(self, last_days_count, zt_threshold=0.099):
        concept_tmp_list = []
        code_result = []
        for concept_code in self.ths_concept_to_code_list:
            code_list = self.ths_concept_to_code_list[concept_code]
            tmp_list, concept_zt_count, concept_cont_zt = \
                self.get_zt_code_list_by_count(code_list,last_days_count,zt_threshold)
            length = len(tmp_list)
            if length > 0:
                concept_tmp_list.append((concept_zt_count, concept_cont_zt, tmp_list,\
                    concept_code, self.code_to_info[concept_code][0]))
        
        #concept_tmp_list.sort(key=lambda x:x[1]*7+x[0]*3, reverse=True)
        concept_tmp_list.sort(key=lambda x:x[0], reverse=True)
        
        for x in concept_tmp_list:
            tmp_list = x[2]
            for y in tmp_list:
                code_result.append(y[2])
        
        return code_result,concept_tmp_list
            
    
    #按最近若干天的增长率排序，输出code list
    def get_x_inc_rate_list_by_order(self, xtype_index, last_days_count):
        code_list = self.x_to_info[xtype_index]
        return self.get_code_list_inc_rate_list_by_order(code_list,last_days_count)
    
    def detect_hengpan(self, xtype_index, days_start, days_ahead,threshold_hp, threshold_raise ):
        result = []
        for code in self.x_to_info[xtype_index]:
            if code not in self.code_to_price_list:
                continue
            code_price_list = self.code_to_price_list[code]
            if len(code_price_list) < days_ahead:
                continue
            
            price_list = code_price_list[days_start:days_ahead]
            prev_max_price_index, prev_min_price_index, ave_price = look_for_max_min_price(price_list)
            prev_max_price = price_list[prev_max_price_index][1]
            prev_min_price = price_list[prev_min_price_index][1]
            
            if prev_min_price_index<prev_max_price_index and self.MA(code,3,days_start) >= ave_price and\
                prev_max_price/ave_price <=threshold_hp and ave_price/prev_min_price <=threshold_hp :
                if (threshold_raise>0 and code_price_list[0][1]/ave_price >= threshold_raise) \
                    or \
                    (threshold_raise<0 and ave_price/code_price_list[0][1] >= -threshold_raise) \
                    or threshold_raise==0:
                    result.append(code)
        
        return result
    
    def find_low_to_high_price(self, xtype_index, days_ahead,rate_high_low, rate_raise_low,rate_raise_high ):
        result = []
        for code in self.x_to_info[xtype_index]:
            if code not in self.code_to_price_list:
                continue
            code_price_list = self.code_to_price_list[code]
            if len(code_price_list) < days_ahead:
                continue
            
            price_list = code_price_list[0:days_ahead]
            latest_price = price_list[0][1]
            
            prev_max_price_index, prev_min_price_index, _ = look_for_max_min_price(price_list)
            prev_max_price = price_list[prev_max_price_index][1]
            prev_min_price = price_list[prev_min_price_index][1]
            
            if latest_price/prev_min_price >=rate_raise_low and  latest_price/prev_min_price <=rate_raise_high \
                and prev_min_price_index<prev_max_price_index \
                and prev_max_price/prev_min_price >=rate_high_low :
                    result.append(code)
        
        return result
    
  
    #在当前到days_ahead之间，找到价格最低的，然后看在inc_rate之间
    def find_lowest_price(self, xtype_index, days_ahead,inc_rate_low,inc_rate_high  ):
        result = []
        tmp = []
        for code in self.x_to_info[xtype_index]:
            if code not in self.code_to_price_list:
                continue
            code_price_list = self.code_to_price_list[code]
            if len(code_price_list) < days_ahead:
                continue
            
            price_list = code_price_list[0:days_ahead]
            latest_price = price_list[0][1]
            
            _, prev_min_price_index, _ = look_for_max_min_price(price_list)
            #prev_max_price = price_list[prev_max_price_index][1]
            prev_min_price = price_list[prev_min_price_index][1]
            
            inc_rate = latest_price / prev_min_price
            if inc_rate>=inc_rate_low and inc_rate<=inc_rate_high:
                    tmp.append((code,inc_rate ))
        
        tmp.sort(key=lambda x:x[1], reverse=False)
        for x in tmp:
            result.append(x[0])
        
        return result
    
    #在当前到days_ahead之间，找到价格最高的，然后看在inc_rate之间
    def find_highest_price(self, xtype_index, days_ahead,inc_rate_low,inc_rate_high  ):
        result = []
        tmp = []
        for code in self.x_to_info[xtype_index]:
            if code not in self.code_to_price_list:
                continue
            code_price_list = self.code_to_price_list[code]
            if len(code_price_list) < days_ahead:
                continue
            
            first_price = code_price_list[len(code_price_list)-1][1]
            
            prev_max_price_index, _, _ = look_for_max_min_price(code_price_list)
            prev_max_price = code_price_list[prev_max_price_index][1]
            
            inc_rate = prev_max_price / first_price
            if inc_rate>=inc_rate_low and inc_rate<=inc_rate_high:
                    tmp.append((code,inc_rate ))
        
        tmp.sort(key=lambda x:x[1], reverse=True)
        for x in tmp:
            result.append(x[0])
        
        return result
    
    def find_concept_or_sw(self, block_name):
        print(f'Look for "{block_name}" in ETF')
        for etf_code in self.etf_to_info:
            etf_info = self.etf_to_info[etf_code]
            etf_name = etf_info[0]
            if etf_name.find(block_name)>=0:
                print('\t',etf_code,etf_name)
        
        print(f'Look for "{block_name}" in THS concept')
        for ths_code in self.ths_concept_to_info:
            ths_info = self.ths_concept_to_info[ths_code]
            ths_name = ths_info[0]
            if ths_name.find(block_name)>=0:
                print('\t',ths_code,ths_name)
        
        print(f'Look for "{block_name}" in SW2021')
        for i in range(1,4):
            for sw_name in self.sw_to_code_list[i]:
                if sw_name.find(block_name)>=0:
                    print('\t',f'SW{i}',sw_name)
                    
        print(f'Look for "{block_name}" in Choice concept')
        for choice_concept in self.choice_concept_to_code_list:
            if choice_concept.find(block_name)>=0:
                print('\t',choice_concept)
                
        return
    
    def MA(self,code, days_count, prev_day_count=0):
        if code not in self.code_to_price_list:
            return 0
        price_list = self.code_to_price_list[code]
        if len(price_list) < prev_day_count:
            return 0
        price_list = price_list[prev_day_count:len(price_list)]
        count = 0
        total_price = 0
        prev_date = None
        for x in price_list:
            tradedate = x[0]
            adj_price = x[1]
            if tradedate != prev_date:
                prev_date = tradedate
                total_price += adj_price
                count += 1
                if count == days_count:
                    return total_price/days_count
        if count >0:
            return total_price/count
        return 0
    
    def MA_v2(self,code, days_count, prev_day_count=0):
        if code not in self.code_to_amount_volume_list:
            return 0
        price_list = self.code_to_amount_volume_list[code]
        if len(price_list) < prev_day_count:
            return 0
        price_list = price_list[prev_day_count:len(price_list)]
        count = 0
        total_amount = 0
        total_volume = 0
        prev_date = None
        for x in price_list:
            tradedate = x[0]
            amount = x[1]
            volume = x[2]
            
            if tradedate != prev_date:
                prev_date = tradedate
                total_amount += amount
                total_volume += volume
                
                count += 1
                if count == days_count:
                    return total_amount/total_volume
        return 0
    
    def avg_trade_amount(self, code, days_count, prev_day_count=0):
        if code not in self.code_to_trade_amount_list :
            return 0
        amount_list = self.code_to_trade_amount_list[code]
        if len(amount_list) < prev_day_count:
            return 0
        amount_list = amount_list[prev_day_count:len(amount_list)]
        if len(amount_list)<days_count+1:
            return 0
        
        return sum(amount_list[1:days_count+1])/days_count
    
    def look_for_up_MA(self, if_include_MA30=False, if_force_MA5 = True, if_include_MA20=True):
        result = []
        for code in self.x_to_info['stock']:
            if code not in self.code_to_price_list:
                continue
            price_list = self.code_to_price_list[code]
            if len(price_list)<30:
                continue
            MA5 = self.MA(code, 5, 0)
            if MA5 <=0 :
                continue
            
            MA10 = self.MA(code, 10, 0)
            MA20 = self.MA(code, 20, 0)
            MA30 = self.MA(code, 30, 0)
            
            if not if_include_MA20:
                MA20 = MA10
            if not if_include_MA30:
                MA30 = MA20
        
            if if_force_MA5 and bigger_or_equal_4(MA5, MA10, MA20, MA30):
                result.append(code)
            elif not if_force_MA5 and bigger_or_equal_3(MA5, MA20, MA30) and bigger_or_equal_3(MA10, MA20, MA30):
                result.append(code)
                
        return result
    
    def look_for_big_trade_amount(self, last_day_count, trade_amount):
        result = []
        for code in self.x_to_info['stock']:
            if code not in self.code_to_trade_amount_list:
                continue
            trade_amount_list = self.code_to_trade_amount_list[code]
            if len(trade_amount_list) < 2:
                continue
            for x in trade_amount_list[0:last_day_count]:
                if x*1000>= trade_amount*100000000:
                    result.append(code)
                    break
                
        return result
    
    def get_stock_list_from_ths_list(self, ths_list):
        result = []
        for x in ths_list:
            if x not in self.ths_concept_to_code_list:
                continue
            code_list = self.ths_concept_to_code_list[x]
            result += code_list
        
        return remove_duplicate_item_in_list(result)
    
    def get_sing_day_mf(self, code, day_index):
        if code not in self.code_to_daily_money_flow_info:
            return 0
        code_moneyflow = self.code_to_daily_money_flow_info[code]
        if day_index >= len(code_moneyflow):
            return 0
        money = code_moneyflow[day_index][3] + code_moneyflow[day_index][5]
        return money
    
    def predict_MA(self,code, MA_day, day_index ):
        MA_value = self.MA(code,MA_day,day_index)
        prev_MA = self.MA(code,MA_day,day_index+1)
        return MA_value*2 - prev_MA
    
    # day_index date close_price ave_price -3 -5 -7 MA5+5 MA5+3 MA10+5 MA10+3 MA20+5 MA20+3 MA30+5 MA30+3
    def get_code_value(self,code, day_index, i):
        all_price_list = self.code_to_all_price_list
        single_all_price_list = all_price_list[code]
    
        predict_MA5 = self.predict_MA(code,5,day_index)
        predict_MA10 = self.predict_MA(code,10,day_index)
        predict_MA20 = self.predict_MA(code,20,day_index)
        predict_MA30 = self.predict_MA(code,30,day_index)
    
        close_price = single_all_price_list[day_index][4]
        ave_price = single_all_price_list[day_index][7]
        cur_date = single_all_price_list[day_index][0]
        
        choose_price = close_price
        if ave_price < close_price:
            choose_price = ave_price
    
        value = 0
        if i==0:
            value = cur_date
        elif i==1:
            value = close_price
        elif i==2:
            value = ave_price
        elif i==3:
            value = choose_price*0.97
        elif i==4:
            value = choose_price*0.95
        elif i==5:
            value = choose_price*0.93
        elif i==6:
            value = predict_MA5*1.05
        elif i==7:
            value = predict_MA5*1.03
        elif i==8:
            value = predict_MA10*1.05
        elif i==9:
            value = predict_MA10*1.03
        elif i==10:
            value = predict_MA20*1.05
        elif i==11:
            value = predict_MA20*1.03
        elif i==12:
            value = predict_MA30*1.05
        elif i==13:
            value = predict_MA30*1.03
        elif i==14:
            value = choose_price
    
        return value

    def show_code_avg_price(self,code, count, mycsv):
        mycsv.save('代码,股票名,序号,日期,收盘价,平均价,当日主力,0,-3,-5,-7,MA5+5,MA5+3,MA10+5,MA10+3,MA20+5,MA20+3,MA30+5,MA30+3')
        all_price_list = self.code_to_all_price_list
        single_all_price_list = all_price_list[code]
        
        total = 0
        name = self.code_to_info[code][0]
        #close_price = single_all_price_list[0][4]
        #close_5 = close_price*0.95
        #print(f'close price = {close_price:.3f}, -5={close_5:.3f}')
        
        out_str = ',,,,,,'
        for j in [14] + list(range(3,14)):
            value = self.get_code_value(code,0,j)
            out_str = out_str + f',{value:.2f}'
        mycsv.save(out_str)
        
        for i in range(0,count):
            if i >= len(single_all_price_list):
                break
            avg_price = self.get_code_value(code,i,2)
            close_price = self.get_code_value(code,i,1)
            cur_date = self.get_code_value(code,i,0)
            
            cur_mf = self.get_sing_day_mf(code,i)/10000
            out_str = f'{code},{name},{i},{cur_date},{close_price:.2f},{avg_price:.2f},{cur_mf:.2f}'
            total = self.get_money_flow_value(code,i+1)/10000
            for j in [14] + list(range(3,14)):
                value = self.get_code_value(code,0,j)
                if value <= avg_price:
                    out_str = out_str + f',{total:.2f}'
                else:
                    out_str = out_str + ','
            mycsv.save(out_str)
        mycsv.save('')
        return
    
    def show_code_list_avg_price(self,code_list, count, filename):
        mycsv = c_csv('code_avg_price_'+filename)
        for code in code_list:
            self.show_code_avg_price(code, count,mycsv )
        mycsv.close()
        
    #查找连续 N中有M 天主力资金净流入 MF
    def find_money_flow_increase_N_M(self,N,M, MF):
        result = []
        for code in self.x_to_info['stock']:
            if code not in self.code_to_price_list:
                continue
            name = self.code_to_info[code][0]
            if name.find('ST')>=0 or name.find('st')>=0:
                continue
            
            price_list = self.code_to_price_list[code]
            if len(price_list)<N:
                continue
    
            count = 0
            for x in range(0,N):
                mf = self.get_sing_day_mf(code,x)
                if mf/10000 >= MF:
                    count += 1
    
            if count >= M:
                result.append(code)
        
        return result
    
    #在N天内，找到最大的资金流入量
    def find_money_good_flow_increase_N(self,N, min_MF):
        result = []
        for code in self.x_to_info['stock']:
            if code not in self.code_to_price_list:
                continue
            name = self.code_to_info[code][0]
            if name.find('ST')>=0 or name.find('st')>=0:
                continue
            
            price_list = self.code_to_price_list[code]
            if len(price_list)<N:
                continue
    
            total_MF = 0
            max_total_MF = -99999999999999
            for x in range(0,N):
                mf = self.get_sing_day_mf(code,x)
                total_MF += mf
                if total_MF >= max_total_MF:
                    max_total_MF =  total_MF
    
            max_total_MF /= 10000
            if max_total_MF >= min_MF:
                result.append((code, max_total_MF))
        
        return result
    
    def find_code_bwtween_fmv(self,FMV1, FMV2):
        result = []
        for code in self.x_to_info['stock']:
            if code not in self.code_to_price_list:
                continue
            name = self.code_to_info[code][0]
            if name.find('ST')>=0 or name.find('st')>=0:
                continue
            
            free_market_value = self.get_free_mv(code, 0)
            if free_market_value > FMV2*100000000 or free_market_value*10000 < FMV1*100000000:
                continue
    
            result.append(code)
        
        return result
    
    def get_free_mv(self, code, day_index):
        if code not in self.code_to_daily_basic_info:
            return 0
        code_daily_basic = self.code_to_daily_basic_info[code]
        turnover_f = code_daily_basic[day_index][2]
        tradeamount = self.code_to_trade_amount_list[code][day_index]
        free_mv = tradeamount*1000/(turnover_f/100)
        return free_mv
    
    def get_total_mv(self, code, day_index):
        if code not in self.code_to_daily_basic_info:
            return 0
        code_daily_basic = self.code_to_daily_basic_info[code]
        # 万元为单位
        #total_mv = code_daily_basic[day_index][8]
        free_mv = self.get_free_mv(code,day_index)
        total_mv = free_mv*code_daily_basic[day_index][6] / code_daily_basic[day_index][8]
        return total_mv/10000
    
    def filt_ths_code_by_name(self, ths_code, filter_list):
        name = self.code_to_info[ths_code][0]
        for x in filter_list:
            if name.find(x) >=0:
                return True
        return False

    def filt_ths_code_list_by_name(self, ths_list, filter_list):
        result = []
        for ths_code in ths_list:
            if not self.filt_ths_code_by_name(ths_code,filter_list):
                result.append(ths_code)
        return result
    
    #回测框架的统计信息
    def init_statistics_info(self,statistics_info):
        statistics_info['total_buy_count'] = 0
        statistics_info['total_sell_count'] = 0
        statistics_info['succ_count'] = 0
        statistics_info['fail_count'] = 0
        statistics_info['hold_max_day_count'] = 0
        statistics_info['exit_count'] = 0
        statistics_info['reach_max_and_down_count'] = 0
        statistics_info['total_rate'] = 0
        statistics_info['rate_distribute'] = {}
        statistics_info['candidate_count'] = {}
        statistics_info['buy_count'] = {}
        statistics_info['sell_count'] = {}
        statistics_info['active_count'] = {}
        statistics_info['sold_stock_info'] = []
        return
    
    #显示回测统计信息结果
    def show_statistics_info(self,piece_id,statistics_info):    
        total_sell_count = statistics_info['total_sell_count']
        #succ_count = statistics_info['succ_count']
        #fail_count = statistics_info['fail_count']
        #hold_max_day_count = statistics_info['hold_max_day_count']
        #exit_count = statistics_info['exit_count']
        total_rate = statistics_info['total_rate']
        rate_distribute = statistics_info['rate_distribute']
        
        print(f"ID={piece_id} total_buy_count = {statistics_info['total_buy_count']}, total_sell_count = {total_sell_count}")
        #print(f'succ_count = {succ_count}, rate={succ_count*100/total_sell_count:.1f}%')
        #print(f'fail_count = {fail_count}, rate={fail_count*100/total_sell_count:.1f}%')
        #print(f'hold_max_day_count = {hold_max_day_count}, rate={hold_max_day_count*100/total_sell_count:.1f}%')
        #print(f'exit_count = {exit_count}, rate={exit_count*100/total_sell_count:.1f}%')
        print(f'ID={piece_id} avg_margin = {total_rate*100/total_sell_count:.1f}%')
        for field in ['succ_count','fail_count','hold_max_day_count','exit_count','reach_max_and_down_count']:
            value = statistics_info[field]
            print(f'ID={piece_id} {field} = {value}, rate={value*100/total_sell_count:.1f}%')
        
        def get_max_min_mean(field):
            max_count = max(statistics_info[field].values())
            min_count = min(statistics_info[field].values())
            ave_count = np.mean(list(statistics_info[field].values()))
            return max_count,min_count,ave_count
        
        for field in ['candidate_count','buy_count','sell_count','active_count']:
            max_cand, min_cand, ave_cand = get_max_min_mean(field)
            print(f'ID={piece_id} {field}: max={max_cand}, min={min_cand}, mean={ave_cand}')
        
  
        for i in range(-100,100):
            if i in rate_distribute:
                if i < 0:
                    title = f'[{i*5:.1f}% to {(i+1)*5:.1f}%]'
                elif i > 0:
                    title = f'[{(i-1)*5:.1f}% to {i*5:.1f}%]'
                else:
                    title = '[0]'
                print(f'ID={piece_id} {title}: count={rate_distribute[i]}, rate={rate_distribute[i]*100/total_sell_count:.1f}%')
        
        return

    #回测系统，确定购买某个票
    def decide_buy(self,code,day_index,buy_price, active_codes,statistics_info ):
        active_code_info = {'buy_day_index':day_index, 'buy_price':buy_price,'context':{}}
        active_codes[code] = active_code_info
        
        statistics_info['total_buy_count'] += 1
        
        if day_index not in statistics_info['buy_count']:
            statistics_info['buy_count'][day_index] = 0
        else:
            statistics_info['buy_count'][day_index] += 1
        return

    #回测系统，确定卖出某个票
    def decide_sell(self,code,day_index,sell_price,sell_reason,active_codes,statistics_info):
        statistics_info['total_sell_count'] += 1
        buy_price = active_codes[code]['buy_price']
        statistics_info[sell_reason] += 1
        rate = sell_price/buy_price - 1
        statistics_info['total_rate'] += rate
        
        if day_index not in statistics_info['sell_count']:
            statistics_info['sell_count'][day_index] = 0
        else:
            statistics_info['sell_count'][day_index] += 1
        
        if rate == 0:
            distribute_index = 0
        elif rate > 0:
            distribute_index = int(rate/0.05)+1
        else:
            distribute_index = int(rate/0.05)-1
            
        if distribute_index not in statistics_info['rate_distribute']:
            statistics_info['rate_distribute'][distribute_index] = 0
        statistics_info['rate_distribute'][distribute_index] += 1
        
        buy_day_index = active_codes[code]['buy_day_index']
        
        if rate >=0.1 or rate <=-0.1:
        #    buy_day_index = active_codes[code]['buy_day_index']
            statistics_info['sold_stock_info'].append(code)
            price_list = self.code_to_all_price_list[code]
            print(f'code={code}, name={self.code_to_info[code][0]}, {sell_reason}',\
                  f' buy_date={price_list[buy_day_index][0]}, price={buy_price:.3f}',\
                f' sell_date={price_list[day_index][0]}, price={sell_price:.3f}, margin={rate:.3f}')
                
        active_codes[code]['buy_day_index'] = -1
        
        #statistics_info['sold_stock_info'].append(\
        #    (code,buy_day_index,buy_price,day_index,sell_price))
        return

    #日期移动，
    #框架包括，按某种策略选股，进入备选池，然后观察，然后按某种条件触发购买，然后按某种条件卖出
    #选股策略参数字典：candidate_policy_args
    #    'days1': 5，短期
    #    'days2': 20, 长期
    #    'amount_rate': 2, 成交量倍数，days1是days2的倍数
    #    'price_move_rate': 0.05, 价格波动幅度
    #    'mv0': 市值0
    #    'mv1': 市值1
    #    'desc': 描述选股策略
    #触发购买参数字典：buy_policy_args
    #卖出参数字典：sell_policy_args
    #总体参数字典：general_args: 
    #    'start_day'：从某天开始
    #    'end_day': 到某天结束，如果为0，则表示是最近的一个收盘日
    #    'hold_days': 最长持有天数
    #    'candidate_policy_func': 备选股票策略函数
    #    'buy_policy_func': 购买策略函数
    #    'sell_policy_func': 卖出策略函数
    #    'desc': 描述总体参数信息
    #statistics_info: 统计信息
    #    'total_buy_count': 总体购买数量
    #    'total_sell_count': 总体卖出数量
    #    'succ_count': 达到盈利条件退出数量
    #    'fail_count': 达到失败条件退出数量
    #    'hold_max_day_count': 达到持有最大时间退出数量
    #    'exit_count': 达到卖出条件数量
    #    'total_rate': 总体盈利比例
    #    'rate_distribute': 盈利比例分布
    def run_test(self,general_args, candidate_policy_args,buy_policy_args, sell_policy_args ):
        start_day = general_args['start_day']
        end_day = general_args['end_day']
        hold_days = general_args['hold_days']
        piece_id = general_args['piece_id']
        
        candidate_policy_func = general_args['candidate_policy_func']
        buy_policy_func = general_args['buy_policy_func']
        sell_policy_func = general_args['sell_policy_func']
        
        active_codes = {}
        statistics_info = {}
        self.init_statistics_info(statistics_info)
        
        step = 0
        total_step = start_day - end_day + 1
        last_pct = 10
        for i in range(start_day,end_day-1,-1 ):
            if i < 0:
                break
            tmp_candidate_codes_list = candidate_policy_func(i,general_args,candidate_policy_args)
            statistics_info['candidate_count'][i] = len(tmp_candidate_codes_list)
            buy_policy_func(i,tmp_candidate_codes_list,active_codes,statistics_info,buy_policy_args)
            sell_policy_func(i,hold_days,active_codes,statistics_info,sell_policy_args)
            
            step += 1
            cur_pct = step / total_step * 100
            if  cur_pct >= last_pct:
                print(f'ID={piece_id} Run test, passed {cur_pct:.1f}%')
                last_pct += 10
            
            statistics_info['active_count'][i] = 0
            for code in active_codes:
                if active_codes[code]['buy_day_index'] > 0:
                    statistics_info['active_count'][i] += 1
            
        
        print(f'ID={piece_id} 总体参数描述：{general_args["desc"]}')
        print(f'ID={piece_id} 选股策略描述：{candidate_policy_args["desc"]}')
        print(f'ID={piece_id} 买入策略描述：{buy_policy_args["desc"]}')
        print(f'ID={piece_id} 卖出策略描述：{sell_policy_args["desc"]}')
        self.show_statistics_info(piece_id,statistics_info)
        return statistics_info['sold_stock_info']
