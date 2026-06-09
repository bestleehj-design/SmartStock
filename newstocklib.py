# -*- coding: utf-8 -*-
"""
Created on Sat Dec 11 16:39:38 2021

@author: hao
"""

#from EmQuantAPI import *
import tushare as ts
import datetime
import os
from datetime import timedelta, datetime,date
import time as _time
import traceback
import mysql.connector
import csv

# 导入配置文件
try:
    from config import DB_CONFIG
except ImportError:
    # 如果配置文件不存在，使用默认配置
    DB_CONFIG = {
        'host': '10.10.65.16',
        'port': 3306,
        'user': 'root',
        'password': '123456',
        'database': 'gp2',
        'charset': 'utf8mb4',
        'collation': 'utf8mb4_unicode_ci',
        'autocommit': True
    }

def mainCallback(quantdata):
    """
    mainCallback 是主回调函数，可捕捉如下错误
    在start函数第三个参数位传入，该函数只有一个为c.EmQuantData类型的参数quantdata
    :param quantdata:c.EmQuantData
    :return:
    """
    print ("mainCallback",str(quantdata))
    #登录掉线或者 登陆数达到上线（即登录被踢下线） 这时所有的服务都会停止
    if str(quantdata.ErrorCode) == "10001011" or str(quantdata.ErrorCode) == "10001009":
        print ("Your account is disconnect. You can force login automatically here if you need.")
    #行情登录验证失败（每次连接行情服务器时需要登录验证）或者行情流量验证失败时，会取消所有订阅，用户需根据具体情况处理
    elif str(quantdata.ErrorCode) == "10001021" or str(quantdata.ErrorCode) == "10001022":
        print ("Your all csq subscribe have stopped.")
    #行情服务器断线自动重连连续6次失败（1分钟左右）不过重连尝试还会继续进行直到成功为止，遇到这种情况需要确认两边的网络状况
    elif str(quantdata.ErrorCode) == "10002009":
        print ("Your all csq subscribe have stopped, reconnect 6 times fail.")
    # 行情订阅遇到一些错误(这些错误会导致重连，错误原因通过日志输出，统一转换成EQERR_QUOTE_RECONNECT在这里通知)，正自动重连并重新订阅,可以做个监控
    elif str(quantdata.ErrorCode) == "10002012":
        print ("csq subscribe break on some error, reconnect and request automatically.")
    # 资讯服务器断线自动重连连续6次失败（1分钟左右）不过重连尝试还会继续进行直到成功为止，遇到这种情况需要确认两边的网络状况
    elif str(quantdata.ErrorCode) == "10002014":
        print ("Your all cnq subscribe have stopped, reconnect 6 times fail.")
    # 资讯订阅遇到一些错误(这些错误会导致重连，错误原因通过日志输出，统一转换成EQERR_INFO_RECONNECT在这里通知)，正自动重连并重新订阅,可以做个监控
    elif str(quantdata.ErrorCode) == "10002013":
        print ("cnq subscribe break on some error, reconnect and request automatically.")
    # 资讯登录验证失败（每次连接资讯服务器时需要登录验证）或者资讯流量验证失败时，会取消所有订阅，用户需根据具体情况处理
    elif str(quantdata.ErrorCode) == "10001024" or str(quantdata.ErrorCode) == "10001025":
        print("Your all cnq subscribe have stopped.")
    else:
        pass

def startCallback(message):
    print("[EmQuantAPI Python]", message)
    return 1
def csqCallback(quantdata):
    """
    csqCallback 是csq订阅时提供的回调函数模板。该函数只有一个为c.EmQuantData类型的参数quantdata
    :param quantdata:c.EmQuantData
    :return:
    """
    print ("csqCallback,", str(quantdata))

def cstCallBack(quantdata):
    '''
    cstCallBack 是日内跳价服务提供的回调函数模板
    '''
    for i in range(0, len(quantdata.Codes)):
        length = len(quantdata.Dates)
        for it in quantdata.Data.keys():
            print(it)
            for k in range(0, length):
                for j in range(0, len(quantdata.Indicators)):
                    print(quantdata.Data[it][j * length + k], " ",end = "")
                print()
def cnqCallback(quantdata):
    """
    cnqCallback 是cnq订阅时提供的回调函数模板。该函数只有一个为c.EmQuantData类型的参数quantdata
    :param quantdata:c.EmQuantData
    :return:
    """
    # print ("cnqCallback,", str(quantdata))
    print("cnqCallback,")
    for code in quantdata.Data:
        total = len(quantdata.Data[code])
        for k in range(0, len(quantdata.Data[code])):
            print(quantdata.Data[code][k])

#----------------------------------------------------------------------
def initMySQL(dbname=None):
    """
    初始化MySQL数据库连接
    
    Args:
        dbname: 数据库名，如果为None则使用配置文件中的database
    """
    # 使用配置文件中的数据库配置
    config = DB_CONFIG.copy()
    
    # 如果指定了数据库名，则覆盖配置文件中的database
    if dbname is not None:
        config['database'] = dbname
    elif 'database' not in config:
        config['database'] = 'gp2'  # 默认数据库名
    
    mydb = mysql.connector.connect(
        host=config['host'],
        port=config['port'],
        user=config['user'],
        passwd=config['password'],
        database=config['database'],
        charset=config.get('charset', 'utf8mb4'),
        collation=config.get('collation', 'utf8mb4_unicode_ci'),
        use_unicode=True,
        autocommit=config.get('autocommit', True)
    )
    
    # 显式设置会话字符集变量，确保中文正确存储
    cursor = mydb.cursor()
    try:
        cursor.execute("SET NAMES 'utf8mb4'")
        cursor.execute("SET CHARACTER SET utf8mb4")
        cursor.execute("SET character_set_connection=utf8mb4")
        cursor.close()
    except:
        pass
    
    return mydb

def closeMySQL(db, dbcursor):
    dbcursor.close()
    db.close()
    return

def check_if_X_record_exist(dbcursor,code,reportdate, tablename, fieldname ):
    sql = f'select code from {tablename} where code="{code}" and {fieldname}="{reportdate}"'
    dbcursor.execute(sql)
    result = dbcursor.fetchone()
    
    if result == None or len(result) == 0:
        return False
    return True

def insert_into_tbl_all_values(dbcursor, code,tablename,values):
    sql = f'insert into {tablename} values ("{code}", {values})'
    #print(sql)
    dbcursor.execute(sql)
    #print(sql)
    return

def insert_into_tbl_all_values_ignore(dbcursor, code,tablename,values):
    """使用 INSERT IGNORE 插入数据，如果主键冲突则忽略（不会报错）"""
    sql = f'insert ignore into {tablename} values ("{code}", {values})'
    #print(sql)
    dbcursor.execute(sql)
    #print(sql)
    return

def isNaN(num):
    return num != num

def convert_list_into_str(alist):
    if alist[0] == None or isNaN(alist[0]):
        result = '-1'
    else:
        result = str(alist[0])
        
    for x in alist[1:len(alist)]:
        if x == None or isNaN(x):
            x = -1
        result += f',{x}'
    return result

def convert_str_list_into_str(alist):
    result = f"'{alist[0]}'"
    for x in alist[1:len(alist)]:
        result += f",'{x}'"
    return result

def datestr_to_date(datestr):
    #print(datestr)
    year = int(datestr[0:4])
    month = int(datestr[4:6])
    day = int(datestr[6:8])
    return date(year,month,day)

def date_to_datestr(onedate):
    return f'{onedate.year:04}{onedate.month:02}{onedate.day:02}'

def get_cur_year_report_date():
    curday = datetime.today().date()
    cur_year = curday.year
    date_list = (date(cur_year-1,12,31), date(cur_year,3,31), date(cur_year,6,30), date(cur_year,9,30), date(cur_year,12,31))
    return date_list

#-----------------------------------------------------------------------
class progress_counter:
    max_count = 0        #最大计数器
    cur_count = 0        #当前计数器
    disp_count = 0       #每隔多少显示一下进度
    invoke_per_min = 0   #每分钟最多调用次数
    start_time = 0
    counter_name = ''    #计数器名字    
    time_record = []     #记录每次调用的时间，0代表最远的，第一次
    
    def __init__(self, max_count, disp_count, invoke_per_min, counter_name):
        self.max_count = max_count
        self.cur_count = 0
        self.disp_count = disp_count
        self.counter_name = counter_name
        self.start_time = _time.time()
        self.invoke_per_min = invoke_per_min
    
    def invoke_once(self):
        while len(self.time_record) > 0:
            starttime = self.time_record[0]
            timegap = _time.time() - starttime
            if timegap < 60:
                if len(self.time_record) + 1 >= self.invoke_per_min:
                    #1分钟内超过调用次数，休眠时间等超过1分钟
                    print(self.counter_name, f'{timegap:0.3f}s', len(self.time_record) )
                    _time.sleep( 63 - timegap)
                    del self.time_record[0]
                break
            else:
                del self.time_record[0]
        
        self.time_record.append(_time.time())
        return
    
    def increase_counter(self, count):
        result = False
        cur_time = _time.time()
        elapse_time = cur_time - self.start_time
        
        self.cur_count += count
        time_per_count = elapse_time/(self.cur_count/count)
        
        if self.cur_count % self.disp_count == 0:
            print(f'{elapse_time:0.3f}s {time_per_count:0.3f}s',self.counter_name,f'{self.cur_count*100/self.max_count:0.2f}%')
            result = True
        
        return result

#-----------------------------------------------------------------------
# 从网络获取交易日信息
#获取从2021-01-01到今天的所有交易日期
def get_exchange_day_from_net(pro, start_date):
    curday = datetime.today().date()
    curday_str = date_to_datestr(curday)
    
    start_date_str = date_to_datestr(start_date)
    
    df = pro.trade_cal( exchange='SSE', is_open='1', start_date=start_date_str, end_date=curday_str, fields='cal_date')
    return df


# 获取所有基本股票信息
def get_all_stock_basic_info_from_db(dbcursor):
    sql = 'select * from stock_basic_info_tbl'
    dbcursor.execute(sql)
    result = dbcursor.fetchall()
    
    if result == None or len(result) == 0:
        return {},{},{},{},{}
    
    code_to_info = {}
    stock_to_info = {}
    etf_to_info = {}
    ths_concept_to_info = {}
    
    name_to_code = {}
    
    for x in result:
        code = x[0]
        name = x[1]
        stock_type = x[3]
        sw1 = x[4]
        sw2 = x[5]
        sw3 = x[6]
        choice_concept_list = x[7]
        member_code_list = x[8]
        market = x[9]
        
        data_info = (name, stock_type, sw1, sw2, sw3, choice_concept_list, member_code_list,market)
        code_to_info[code] = data_info
        name_to_code[name] = code
        if stock_type == 0:
            stock_to_info[code] = data_info
        elif stock_type == 1:
            etf_to_info[code] = data_info
        elif stock_type == 2:
            ths_concept_to_info[code] = data_info
        else:
            pass
    
    return code_to_info, stock_to_info, etf_to_info,ths_concept_to_info, name_to_code

#删除某个表格的符合某个日期条件的数据
def delete_data_by_date(dbcursor,tablename,delete_date):
    try:
        sql = f'delete from {tablename} where tradedate="{delete_date}"'
        dbcursor.execute(sql)
    except Exception as ee:
        print(sql)
        print("error >>>",ee)
        traceback.print_exc()
    finally:
        return

#删除某个表格的所有数据
def delete_all_data_by_tablename(dbcursor,tablename):
    try:
        sql = f'delete from {tablename}'
        dbcursor.execute(sql)
    except Exception as ee:
        print(sql)
        print("error >>>",ee)
        traceback.print_exc()
    finally:
        return

#插入从tushare获得的所有数据
def insert_daily_data_into_table(dbcursor, ts_code, cur_date, daily_info,cur_adj_factor ):
    try:
        sql1 = 'insert into daily_info_tbl values'
        sql2 = f'"{ts_code}","{cur_date}",{daily_info[1]},{daily_info[2]},{daily_info[3]},{daily_info[4]},{daily_info[5]},{daily_info[6]}'
        sql3 = f'{cur_adj_factor}'
    
        sql = f'{sql1} ( {sql2}, {sql3})'
        dbcursor.execute(sql)
    finally:
        return

#获取股票，etf，指数等的开始日期
def get_X_start_date(dbcursor, table_name, code):
    sql = f'select tradedate from {table_name} where code = "{code}" order by tradedate desc limit 1'
    dbcursor.execute(sql)
    result = dbcursor.fetchone()
    
    if result == None:
        #没有任何数据，则从2021-1-1开始
        return date(2022,1,1)
    
    lastdate = result[0]
    return lastdate + timedelta(days=1)

# 从db获取交易日信息
def get_exchange_day_from_db(dbcursor):
    sql = 'select trade_date from trade_date_info_tbl order by trade_date asc'
    dbcursor.execute(sql)
    return dbcursor.fetchall()

# 两个列表的交集
def list_jiaoji(a,b):
    c = []
    for x in a:
        if x in b:
            c.append(x)
    return c

# 多个列表的交集
def list_x(a,b,**c):
    d = list_jiaoji(a,b)
    for x in c:
        d = list_jiaoji(d,c[x])
    
    return d

# 多个列表的交集
def list_y(x):
    d = list_jiaoji(x[0],x[1])
    for i in range(2,len(x)):
        d = list_jiaoji(d,x[i])
    return d

def get_output_filename(fn_path, fn_prefix='', fn_suffix=''):
    curday = datetime.today().date()
    cur_min = datetime.today().minute;
    cur_hour = datetime.today().hour;
    cur_second = datetime.today().second
    
    fn = f'C:\\zh\\stock\\{fn_path}\\{fn_prefix}-{curday}-{cur_hour}-{cur_min}-{cur_second}-{fn_suffix}'
    filename = f'{fn}.txt'
    filename2 = f'{fn}-info.csv'
    return filename, filename2

def show_stock_info(codes_list, is_save_to_file, fn_path, fn_prefix='', fn_suffix=''):
    if is_save_to_file:
        fn, fn2 = get_output_filename(fn_path,fn_prefix,fn_suffix)
        file = open(fn,'a')
    for code in codes_list:
        if is_save_to_file:
            file.write(code+'\n')
        else:
            print(code)
    
    if is_save_to_file:
        file.close()
    
    return

def remove_duplicate_item(list1, list2):
    result = []
    for x in list1:
        if x not in list2:
            result.append(x)
    return result

def remove_duplicate_item_in_list(list1):
    result = []
    for x in list1:
        if x not in result:
            result.append(x)
    return result

def bigger_or_equal(v1, v2):
    return v1>=v2
    #if v1>=v2:
    #    return True
    #if int(v1*100) == int(v2*100):
    #    return True
    #if abs(v1-v2)/v1 <= 0.005:
    #    return True
    #return False

def bigger_or_equal_5(v1,v2,v3,v4,v5):
    return bigger_or_equal(v1,v2) and bigger_or_equal(v2,v3) and bigger_or_equal(v3,v4) and bigger_or_equal(v4,v5)

def bigger_or_equal_4(v1,v2,v3,v4):
    return bigger_or_equal(v1,v2) and bigger_or_equal(v2,v3) and bigger_or_equal(v3,v4)

def bigger_or_equal_3(v1,v2,v3):
    return bigger_or_equal(v1,v2) and bigger_or_equal(v2,v3)


def zt_rate(market):
    if market == '主板' or market=='中小板' :
        return 0.0988
    return 0.199

class c_csv:
    file = None
    def __init__(self, filename):
        _,fn2 = get_output_filename('up_MA',filename)
        self.file=open(fn2,'a')
    
    def save(self, out_str):
        self.file.write(out_str+'\n')
    
    def close(self):
        self.file.close()
        