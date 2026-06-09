# -*- coding: utf-8 -*-
"""
Created on Sat Dec 11 19:13:11 2021

@author: hao
"""

from newstocklib import *
import time as _time
import csv
import sys

# 导入配置文件
try:
    from config import TUSHARE_TOKEN
except ImportError:
    # 如果配置文件不存在，使用默认token（不推荐，建议创建配置文件）
    TUSHARE_TOKEN = 'a054107022932e4f13f532718167561fd11765012b25472b351a81d7'
    print("⚠️ 警告: 未找到config.py配置文件，使用默认tushare token")

# 港股数据获取的全局时间戳，用于控制API调用频率
_last_hk_api_call_time = 0
_HK_API_MIN_INTERVAL = 30  # 每分钟最多2次，即每30秒最多1次

# 使用配置文件中的tushare token
pro = ts.pro_api(TUSHARE_TOKEN)
ts.set_token(TUSHARE_TOKEN) 
#--------------------------------------------------------------------------

# 从网络中获取交易日，插入到db中
def get_exchange_day_and_insert_to_db():
    sql = 'select trade_date from trade_date_info_tbl order by trade_date desc limit 1'
    dbcursor.execute(sql)
    result = dbcursor.fetchone()
    
    if result == None or len(result) == 0:
        start_date = date(2020,1,1)
    else:
        start_date = result[0] + timedelta(days=1)

    print("get exchange day from ",start_date)
    
    df = get_exchange_day_from_net(pro,start_date)
    print(f'...Get {len(df)} records')
    
    for date_str in df['cal_date'].values:
        sql = f'insert into trade_date_info_tbl values ("{date_str}")'
        dbcursor.execute(sql)
    
    mydb.commit()
    return

#--------------------------------------------------------------------------
def insert_or_modify_code_sw_info(code, sw1,sw2,sw3):
    sql = f'select code from stock_basic_info_tbl where code="{code}"'
    dbcursor.execute(sql)
    result = dbcursor.fetchone()
        
    if result == None or len(result)==0:
        return

    sql = f'update stock_basic_info_tbl set sw1="{sw1}", sw2="{sw2}", sw3="{sw3}" where code="{code}"'
    dbcursor.execute(sql)
    return

def fetch_sw3_code_list_from_tushare(sw1,sw2,sw3, index_code, pc):
    pc.invoke_once()
    df = pro.index_member(index_code=index_code, fields='con_code, out_date')

    for x in df.values:
        code = x[0]
        out_date = x[1]
        if out_date != None:
            continue
        insert_or_modify_code_sw_info(code,sw1,sw2,sw3)
    
    return

def fetch_sw2_code_list_from_tushare(sw1, sw2,industry_code2, pc ):
    pc.invoke_once()
    df = pro.index_classify(parent_code=industry_code2, src='SW2021')
    for x in df.values:
        index_code = x[0]
        sw3 = x[1]
        is_pub = x[4]
        if is_pub == '0':
            continue    
        fetch_sw3_code_list_from_tushare(sw1,sw2,sw3, index_code, pc)
    
    return


def fetch_sw1_code_list_from_tushare(sw1,industry_code1, pc ):
    pc.invoke_once()
    df = pro.index_classify(parent_code=industry_code1, src='SW2021')
    for x in df.values:
        sw2 = x[1]
        industry_code2 = x[3]
        is_pub = x[4]
        if is_pub == '0':
            continue    
        fetch_sw2_code_list_from_tushare(sw1, sw2, industry_code2, pc)
    
    return

#从tushare获取sw2021数据        
def get_sw_code_list_from_tushare():
    print("Now, begin to get sw code list info......")
    
    df = pro.index_classify(level='L1', src='SW2021')
    
    pc = progress_counter(len(df.values), 1, 50, 'SW code list')
    pc.invoke_once()
    
    for x in df.values:
        sw1 = x[1]
        industry_code1 = x[3]
        is_pub = x[4]
        
        if is_pub == '0':
            continue
        fetch_sw1_code_list_from_tushare(sw1, industry_code1, pc)
        pc.increase_counter(1)
        mydb.commit()
        #_time.sleep(10)
    
    mydb.commit() 
    return
        
#--------------------------------------------------------------------------
#内部函数
def insert_or_modify_code_info(data, x_to_info, code_type, force_update = False):
    import pandas as pd
    
    for stock_data in data.values:
        code = str(stock_data[0])
        
        # 处理名称：确保是 Unicode 字符串
        name_raw = stock_data[1]
        if pd.isna(name_raw) or name_raw is None:
            name = ""
        else:
            name = str(name_raw)
            # 如果是 pandas 的 object 类型，直接转换为字符串
            if isinstance(name, bytes):
                name = name.decode('utf-8', errors='ignore')
            # 确保是 Unicode 字符串
            if not isinstance(name, str):
                try:
                    name = name.decode('utf-8', errors='ignore')
                except:
                    name = str(name)
        
        # 处理市场：确保是 Unicode 字符串
        market_raw = stock_data[2] if len(stock_data) > 2 else ""
        if pd.isna(market_raw) or market_raw is None:
            market = ""
        else:
            market = str(market_raw)
            if isinstance(market, bytes):
                market = market.decode('utf-8', errors='ignore')
            if not isinstance(market, str):
                try:
                    market = market.decode('utf-8', errors='ignore')
                except:
                    market = str(market)
        
        if force_update:
            sql = 'delete from stock_basic_info_tbl where code=%s'
            dbcursor.execute(sql, (code,))
            # 使用参数化查询确保中文正确插入
            sql = 'insert into stock_basic_info_tbl values (%s, %s, %s, %s, "", "", "", "", "", %s)'
            dbcursor.execute(sql, (code, name, 1, code_type, market))
            continue
        
        if code in x_to_info:
            if name != x_to_info[code][0]:
                # 使用参数化查询更新名称
                sql = 'update stock_basic_info_tbl set name=%s where code=%s'
                dbcursor.execute(sql, (name, code))
        else:
            sql = 'select code from stock_basic_info_tbl where code=%s'
            dbcursor.execute(sql, (code,))
            result = dbcursor.fetchone()
            if result != None:
                continue
            
            # 使用参数化查询插入新记录
            sql = 'insert into stock_basic_info_tbl values (%s, %s, %s, %s, "", "", "", "", "", %s)'
            dbcursor.execute(sql, (code, name, 1, code_type, market))
            
    mydb.commit()        
    return


# 检查和修复表字符集
def check_and_fix_table_charset(auto_fix=False):
    """检查并修复 stock_basic_info_tbl 表的字符集"""
    try:
        # 检查表字符集（使用简单的 SHOW CREATE TABLE，更安全）
        sql = "SHOW CREATE TABLE stock_basic_info_tbl"
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
        if result:
            create_sql = result[1]
            # 检查是否包含 utf8mb4
            if 'utf8mb4' not in create_sql.lower():
                print("⚠️ Warning: Table charset is not utf8mb4.")
                if auto_fix:
                    print("🔧 Attempting to fix table charset...")
                    try:
                        # 修复整个表的字符集
                        fix_sql = "ALTER TABLE stock_basic_info_tbl CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                        dbcursor.execute(fix_sql)
                        mydb.commit()
                        print("✅ Table charset fixed successfully!")
                    except Exception as fix_err:
                        print(f"❌ Failed to fix table charset: {fix_err}")
                        print("Please run manually: ALTER TABLE stock_basic_info_tbl CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                else:
                    print("To fix: ALTER TABLE stock_basic_info_tbl CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            else:
                print("✅ Table charset is already utf8mb4")
                
            # 尝试检查 name 列的字符集（使用 INFORMATION_SCHEMA，避免临时文件问题）
            try:
                sql_columns = """
                    SELECT COLUMN_TYPE, COLLATION_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = DATABASE() 
                    AND TABLE_NAME = 'stock_basic_info_tbl' 
                    AND COLUMN_NAME = 'name'
                """
                dbcursor.execute(sql_columns)
                col_result = dbcursor.fetchone()
                if col_result:
                    col_type = col_result[0]  # COLUMN_TYPE
                    col_collation = col_result[1]  # COLLATION_NAME
                    
                    if col_collation and 'utf8mb4' not in str(col_collation).lower():
                        print(f"⚠️ Warning: name column charset is {col_collation}, not utf8mb4")
                        if auto_fix:
                            print("🔧 Attempting to fix name column charset...")
                            try:
                                # 从 COLUMN_TYPE 中提取类型（如 VARCHAR(255)）
                                # 修复 name 列的字符集
                                fix_col_sql = f"ALTER TABLE stock_basic_info_tbl MODIFY name {col_type} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                                dbcursor.execute(fix_col_sql)
                                mydb.commit()
                                print("✅ name column charset fixed successfully!")
                            except Exception as fix_err:
                                print(f"❌ Failed to fix name column charset: {fix_err}")
                                print(f"Please run manually: ALTER TABLE stock_basic_info_tbl MODIFY name {col_type} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                    else:
                        print(f"✅ name column charset is already utf8mb4 ({col_collation})")
            except Exception as col_err:
                # 如果检查列字符集失败，只修复表字符集
                print(f"⚠️ Could not check name column charset: {col_err}")
                print("Will only fix table-level charset.")
                if auto_fix:
                    # 如果检查失败，直接尝试修复 name 列（使用默认类型）
                    try:
                        print("🔧 Attempting to fix name column charset with default type...")
                        fix_col_sql = "ALTER TABLE stock_basic_info_tbl MODIFY name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                        dbcursor.execute(fix_col_sql)
                        mydb.commit()
                        print("✅ name column charset fixed successfully!")
                    except Exception as fix_err:
                        print(f"❌ Failed to fix name column charset: {fix_err}")
                        print("Please run manually: ALTER TABLE stock_basic_info_tbl MODIFY name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
        else:
            print("Warning: Could not check table charset.")
    except Exception as e:
        print(f"Warning: Could not check table charset: {e}")
        # 如果检查失败但需要修复，直接尝试修复
        if auto_fix:
            print("🔧 Attempting to fix table charset directly...")
            try:
                fix_sql = "ALTER TABLE stock_basic_info_tbl CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                dbcursor.execute(fix_sql)
                mydb.commit()
                print("✅ Table charset fixed successfully!")
                
                # 同时尝试修复 name 列
                try:
                    fix_col_sql = "ALTER TABLE stock_basic_info_tbl MODIFY name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    dbcursor.execute(fix_col_sql)
                    mydb.commit()
                    print("✅ name column charset fixed successfully!")
                except Exception as fix_err2:
                    print(f"⚠️ Could not fix name column: {fix_err2}")
            except Exception as fix_err:
                print(f"❌ Failed to fix table charset: {fix_err}")
                print("Please run manually:")
                print("  ALTER TABLE stock_basic_info_tbl CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                print("  ALTER TABLE stock_basic_info_tbl MODIFY name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")

# 从网络中获取股票基本信息，插入到db中
def get_stock_basic_info_and_insert_to_db(force_update=False, clear_table=False):
    print("Now, begin to get stock basic info......")
    
    # 如果需要清空表，先删除所有数据，然后修复字符集
    if clear_table:
        print("Clearing stock_basic_info_tbl table...")
        delete_all_data_by_tablename(dbcursor, "stock_basic_info_tbl")
        mydb.commit()
        print("Table cleared successfully.")
        # 清空表后，自动修复表字符集
        print("Checking and fixing table charset after clearing...")
        check_and_fix_table_charset(auto_fix=True)
    else:
        # 检查表字符集（仅检查，不自动修复）
        check_and_fix_table_charset(auto_fix=False)
    
    # TuShare often limits single-call results (~1000). Fetch per exchange with pagination.
    exchanges = ['SSE', 'SZSE', 'BSE']
    limit = 1000
    
    # Load existing info once (DB checks inside insert function will handle races for new codes)
    _, stock_to_info, _, _, _ = get_all_stock_basic_info_from_db(dbcursor)
    
    total_inserted = 0
    sample_count = 0
    for exch in exchanges:
        offset = 0
        while True:
            try:
                df = pro.stock_basic(
                    exchange=exch,
                    list_status='L',
                    fields='ts_code,name,market',
                    limit=limit,
                    offset=offset
                )
            except Exception as ee:
                print("get_stock_basic_info_and_insert_to_db error >>>", ee)
                _time.sleep(2)
                continue
            
            if df is None or len(df.values) == 0:
                break
            
            # 打印样本数据以验证编码
            if sample_count < 3 and len(df.values) > 0:
                sample = df.values[0]
                import pandas as pd
                name_raw = sample[1]
                name_str = str(name_raw) if not pd.isna(name_raw) else ""
                print(f"Sample data before insert:")
                print(f"  code={sample[0]}")
                print(f"  name_raw={repr(name_raw)}, type={type(name_raw)}")
                print(f"  name_str={repr(name_str)}")
                print(f"  name_unicode={repr(name_str.encode('utf-8') if isinstance(name_str, str) else name_str)}")
                sample_count += 1
            
            insert_or_modify_code_info(df, stock_to_info, 0, force_update)
            total_inserted += len(df.values)
            print(f"...Inserted/updated {len(df.values)} rows from exchange={exch}, offset={offset}")
            
            # Advance pagination
            offset += limit
            # Be gentle with API
            _time.sleep(0.5)
    
    print(f"Done stock basic info. Total processed ~{total_inserted} rows across exchanges")
    
    # 验证插入的数据（尝试多种方式，兼容不同的表结构）
    try:
        # 尝试使用 stock_type 列
        sql = 'select code, name from stock_basic_info_tbl where stock_type=0 limit 5'
        dbcursor.execute(sql)
        verify_results = dbcursor.fetchall()
    except Exception:
        try:
            # 如果没有 stock_type 列，尝试根据代码筛选股票（.SH 和 .SZ 结尾）
            sql = 'select code, name from stock_basic_info_tbl where (code like "%.SH" or code like "%.SZ") limit 5'
            dbcursor.execute(sql)
            verify_results = dbcursor.fetchall()
        except Exception:
            # 最后尝试直接查询前几条
            sql = 'select code, name from stock_basic_info_tbl limit 5'
            dbcursor.execute(sql)
            verify_results = dbcursor.fetchall()
    
    print("Sample inserted records from database:")
    for row in verify_results:
        code = row[0]
        name = row[1]
        # 检查名称是否正确
        if name and name != "???":
            print(f"  ✅ code={code}, name={name}, name_repr={repr(name)}")
        else:
            print(f"  ❌ code={code}, name={name}, name_repr={repr(name)} - WARNING: Name encoding issue!")
            
    # 尝试直接查询一条记录验证字符集
    if len(verify_results) > 0:
        test_code = verify_results[0][0]
        sql = 'SELECT HEX(name) as name_hex, name, CHAR_LENGTH(name) as name_len, LENGTH(name) as name_bytes FROM stock_basic_info_tbl WHERE code=%s LIMIT 1'
        dbcursor.execute(sql, (test_code,))
        hex_result = dbcursor.fetchone()
        if hex_result:
            print(f"Debug info for code {test_code}:")
            print(f"  HEX(name)={hex_result[0]}")
            print(f"  name={hex_result[1]}")
            print(f"  CHAR_LENGTH={hex_result[2]}")
            print(f"  BYTE_LENGTH={hex_result[3]}")
    
    return

#从网络中获取etf基本信息，插入db中
def get_etf_basic_info_and_insert_to_db():
    print("Now, begin to get ETF basic info......")
    
    data = pro.fund_basic(market='E', status = 'L', fields='ts_code,name,market')
    if len(data.values) == 0:
        return
    
    _,_,etf_to_info,_,_ = get_all_stock_basic_info_from_db(dbcursor)
    
    insert_or_modify_code_info(data,etf_to_info,1 )
    
    return

#从网络中获取港股基本信息，插入db中
def get_hk_stock_basic_info_and_insert_to_db(force_update=False):
    print("Now, begin to get HK stock basic info......")
    
    try:
        # tushare的hk_basic接口获取港股基本信息
        # 注意：如果API不支持hk_basic，可能需要使用其他接口或方法
        data = pro.hk_basic(exchange='HKEX', list_status='L', fields='ts_code,name,market')
        if len(data.values) == 0:
            print("Warning: No HK stock data returned from tushare")
            return
        
        _,stock_to_info,_,_,_ = get_all_stock_basic_info_from_db(dbcursor)
        
        # 使用stock_type=3表示港股
        # 注意：需要确保insert_or_modify_code_info函数能正确处理stock_type=3的情况
        insert_or_modify_code_info(data, stock_to_info, 3, force_update)
        
        print(f"Done HK stock basic info. Total processed {len(data.values)} rows")
    except Exception as e:
        print(f"Error getting HK stock basic info: {e}")
        print("Note: You may need to check if your tushare token has access to HK data, or if the API interface has changed.")
        # 如果hk_basic不存在，尝试其他方法
        try:
            # 尝试使用stock_basic接口，指定exchange参数
            # 注意：tushare可能不支持在stock_basic中直接获取港股
            print("Trying alternative method...")
            data = pro.stock_basic(exchange='HKEX', list_status='L', fields='ts_code,name,market')
            if len(data.values) > 0:
                _,stock_to_info,_,_,_ = get_all_stock_basic_info_from_db(dbcursor)
                insert_or_modify_code_info(data, stock_to_info, 3, force_update)
                print(f"Done HK stock basic info (alternative method). Total processed {len(data.values)} rows")
        except Exception as e2:
            print(f"Alternative method also failed: {e2}")
    
    return

#从网络中获取ths concept基本信息，插入db中
def get_ths_concept_basic_info_and_insert_to_db():
    print("Now, begin to get THS concept basic info......")
    
    data = pro.ths_index(exchange='A',fields='ts_code,name,type')
    if len(data.values) == 0:
        return
    
    _,_,_,ths_concept_to_info,_ = get_all_stock_basic_info_from_db(dbcursor)
    
    insert_or_modify_code_info(data,ths_concept_to_info,2 )
    
    return
#--------------------------------------------------------------------------
#获取东财概念
def fetch_choice_concept(to_fetch_code_list, stock_to_info):
    curday = datetime.today().date()
    data = c.css(to_fetch_code_list, "BLCONCEPTSORNOT", f"Enddate={curday}, Ispandas=0")
    if not isinstance(data, c.EmQuantData):
        print(data)
    elif (data.ErrorCode != 0):
        print("request css Error, ", data.ErrorMsg)
    else:
        for code in data.Codes:
            if data.Data[code][0] != None:
                choice_concept = stock_to_info[code][5]
                if data.Data[code][0] != choice_concept:
                    sql = f'update stock_basic_info_tbl set choice_concept_list="{data.Data[code][0]}" where code="{code}"'
                    dbcursor.execute(sql)
    
    return
    
#从网络中获取东财概念信息
def get_choice_concept_info_and_insert_to_db():
    print("Now, begin to get choice concept code info......")
    
    _,stock_to_info,_,_,_ = get_all_stock_basic_info_from_db(dbcursor)
    
    pc = progress_counter(len(stock_to_info), 30, 200, 'Choice concept')
    
    tmp_code_list = ''
    count = 0
    for code in stock_to_info:
        if count == 0:
            tmp_code_list = code
        else:
            tmp_code_list += ',' + code
        count += 1
        
        if count == 30:
            pc.invoke_once()
            fetch_choice_concept(tmp_code_list, stock_to_info)
            pc.increase_counter(30)
            
            mydb.commit()
            tmp_code_list = ''
            count = 0
            #pc.increase(30)
            #_time.sleep(1)
    
    if count > 0:
        fetch_choice_concept(tmp_code_list, stock_to_info)
    
    mydb.commit()
    return

#--------------------------------------------------------------------------
# 从ths 概念或者指数 中获取member code
def fetch_single_ths_concept_member(ths_concept, ths_concept_to_info):
    df = pro.ths_member(ts_code=ths_concept)
    
    codes_list = ''
    for x in df.values:
        code = x[1]
        codes_list += code + ';'
        if len(codes_list) > 4000:
            break
    
    codes_list = codes_list.replace('"','’')
    codes_list = codes_list.replace("'",'’')
    
    exist_codes_list = ths_concept_to_info[ths_concept][6]
    if exist_codes_list != codes_list:
        sql = f'update stock_basic_info_tbl set code_list="{codes_list}" where code="{ths_concept}"'
        dbcursor.execute(sql)
    
    return

    
def get_ths_concept_code_info_and_insert_to_db():
    print("Now, begin to get THS concept code info......")
    
    _,_,_,ths_concept_to_info,_ = get_all_stock_basic_info_from_db(dbcursor)

    pc = progress_counter(len(ths_concept_to_info), 10, 50, 'THS concept')    
    
    for ths_concept in ths_concept_to_info:
        pc.invoke_once()
        fetch_single_ths_concept_member(ths_concept, ths_concept_to_info)
        if pc.increase_counter(1):
            mydb.commit()
            #_time.sleep(5)
    
    mydb.commit()
    return

# 从 ETF 中获取member code
def fetch_single_ETF_member(etf_code, etf_to_info):
    reportdate_list = (date(1111,3,31),date(1111,6,30),date(1111,9,30),date(1111,12,31))
    curday = datetime.today().date()
    
    codes_list = ''
    for i in range(3,-1,-1):
        reportdate = date(curday.year,reportdate_list[i].month,reportdate_list[i].day )
        df = pro.fund_portfolio(ts_code=etf_code,end_date=date_to_datestr(reportdate),fields='symbol' )

        if len(df) == 0:
            continue
        for x in df.values:
            codes_list += x[0] + ';'
            if len(codes_list) > 4000:
                break
        exist_codes_list = etf_to_info[etf_code][6]
        if exist_codes_list != codes_list:
            sql = f'update stock_basic_info_tbl set code_list="{codes_list}" where code="{etf_code}"'
            dbcursor.execute(sql)
        
        break
    
    return

def get_etf_code_info_and_insert_to_db():
    print("Now, begin to get ETF code info......")
    
    _,_,etf_to_info,_,_ = get_all_stock_basic_info_from_db(dbcursor)

    pc = progress_counter(len(etf_to_info), 10, 50, 'ETF member')    
    
    for etf_code in etf_to_info:
        pc.invoke_once()
        fetch_single_ETF_member(etf_code, etf_to_info)
        if pc.increase_counter(1):
            mydb.commit()
            #_time.sleep(5)
    
    mydb.commit()
    return
#--------------------------------------------------------------------------
# 获取10大流通股东信息
def get_single_10_stk_holder_info(code, start_date, end_date):
    df = pro.top10_floatholders(ts_code=code, \
                                start_date=date_to_datestr(start_date), \
                                end_date=date_to_datestr(end_date))
    if len(df) ==0:
        return
    
    for x in df.values:
        name = x[3].replace('"','‘')
        name = name.replace("'",'’')
        values = f'"{x[2]}", "{name}",{x[4]}'
        try:
            insert_into_tbl_all_values(dbcursor,code,"holder_info_tbl", values)
        except:
            pass
    
    return

def get_10_stk_holder_info():
    #reportdate_list = (date(1111,3,31),date(1111,6,30),date(1111,9,30),date(1111,12,31))
    print("Now, begin to get 10 stk holder info......")
    
    curday = datetime.today().date()
    cur_year = curday.year
    
    _,stock_to_info,_,_,_ = get_all_stock_basic_info_from_db(dbcursor)
    
    pc = progress_counter(len(stock_to_info),50,300,"Get 10 STK")
    
    for code in stock_to_info:
        sql = f'select reportdate from holder_info_tbl where code="{code}" order by reportdate desc limit 1'
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
        
        if result == None or len(result) == 0:
            start_date = date(2014,1,1)
        else:
            start_date = result[0] + timedelta(days=1)
        
        end_date = date(cur_year,12,31)
        pc.invoke_once()
        get_single_10_stk_holder_info(code, start_date, end_date)
        if pc.increase_counter(1):
            mydb.commit()
    
    mydb.commit()
    return
        
#--------------------------------------------------------------------------
# 获取利润，收入等信息
def get_last_reportdate_of_fina_info():
    sql = 'select reportdate from fina_info_tbl where code="000001.SZ" order by reportdate desc limit 1'
    dbcursor.execute(sql)
    result = dbcursor.fetchone()
    
    if result == None or len(result) == 0:
        return date(2013,1,1)
    
    return result[0] + timedelta(days=1)

def get_single_fina_info_from_net(reportdate):
    df = []
    for _ in range(5):
        try:
            df = pro.fina_indicator_vip(ts_code='',\
                                period=date_to_datestr(reportdate), \
                                fields='ts_code, profit_dedt,q_dtprofit,q_profit_yoy,q_netprofit_yoy,netprofit_yoy ,q_gr_yoy,tr_yoy' )
        except:
            _time.sleep(3)
        else:
            return df
    return []

def check_if_fina_record_exist(code,reportdate ):
    return check_if_X_record_exist(dbcursor,code, reportdate, 'fina_info_tbl','reportdate')

def get_single_fina_info(reportdate):
    print("Get date:",reportdate)
    df = get_single_fina_info_from_net(reportdate)
    if len(df) == 0:
        return
    
    for x in df.values:
        code = x[0]
        '''
        profit_dedt = x[1]
        q_dtprofit = x[2]
        netprofit_yoy = x[3]
        tr_yoy = x[4]
        q_gr_yoy = x[5]
        q_profit_yoy = x[6]
        q_netprofit_yoy = x[7]
        '''
        if not check_if_fina_record_exist(code,reportdate):
            value1 = convert_list_into_str(x[1:8])
            values = f'"{reportdate}", {value1}'
            insert_into_tbl_all_values(dbcursor,code,"fina_info_tbl", values)
    
    mydb.commit()
    
    return

def get_fina_info():
    print("Now, begin to get fina info......")
    
    reportdate_list = (date(1111,3,31),date(1111,6,30),date(1111,9,30),date(1111,12,31))
    
    start_date = get_last_reportdate_of_fina_info()
    curday = datetime.today().date()
    print(f'......start_date={start_date}, current_day={curday}')
    
    while start_date <= curday:
        for reportdate in reportdate_list:
            if start_date.month == reportdate.month and start_date.day == reportdate.day:
                get_single_fina_info(start_date)
                break
        
        start_date += timedelta(days=1)
    
    return

#--------------------------------------------------------------------------
# 详细财务数据采集（为基本面分析提供扩展指标）
def get_last_reportdate_of_detailed_fina_info():
    sql = 'select reportdate from fina_info_detailed_tbl where code="000001.SZ" order by reportdate desc limit 1'
    try:
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
    except Exception:
        # 表可能还不存在
        return date(2013, 1, 1)

    if result is None or len(result) == 0:
        return date(2013, 1, 1)

    return result[0] + timedelta(days=1)


def get_single_detailed_fina_info_from_net(reportdate):
    """调用 fina_indicator_vip 获取扩展财务指标"""
    df = []
    for _ in range(5):
        try:
            df = pro.fina_indicator_vip(
                ts_code='',
                period=date_to_datestr(reportdate),
                fields='ts_code,roe,roe_yoy,roa,'
                       'grossprofit_margin,netprofit_margin,'
                       'profit_dedt,q_dtprofit,q_profit_yoy,q_netprofit_yoy,'
                       'netprofit_yoy,q_gr_yoy,tr_yoy,'
                       'debt_to_assets,current_ratio,assets_turn,'
                       'ocf_yoy,ocf_to_or'
            )
        except Exception:
            _time.sleep(3)
        else:
            return df
    return []


def check_if_detailed_fina_record_exist(code, reportdate):
    return check_if_X_record_exist(dbcursor, code, reportdate, 'fina_info_detailed_tbl', 'reportdate')


def insert_detailed_fina_info(reportdate, df):
    """将DataFrame转为JSON存入fina_info_detailed_tbl"""
    import json
    import math

    # (API列名, JSON存储键) — ocf_to_or 存为 cf_sales 供基本面分析使用
    field_pairs = [
        ('roe', 'roe'), ('roe_yoy', 'roe_yoy'), ('roa', 'roa'),
        ('grossprofit_margin', 'grossprofit_margin'),
        ('netprofit_margin', 'netprofit_margin'),
        ('profit_dedt', 'profit_dedt'), ('q_dtprofit', 'q_dtprofit'),
        ('q_profit_yoy', 'q_profit_yoy'), ('q_netprofit_yoy', 'q_netprofit_yoy'),
        ('netprofit_yoy', 'netprofit_yoy'), ('q_gr_yoy', 'q_gr_yoy'), ('tr_yoy', 'tr_yoy'),
        ('debt_to_assets', 'debt_to_assets'), ('current_ratio', 'current_ratio'),
        ('assets_turn', 'assets_turn'),
        ('ocf_yoy', 'ocf_yoy'), ('ocf_to_or', 'cf_sales'),
    ]
    col_set = set(df.columns)

    for _, row in df.iterrows():
        code = row['ts_code']
        if check_if_detailed_fina_record_exist(code, str(reportdate)):
            continue

        data_dict = {}
        for api_col, json_key in field_pairs:
            val = row[api_col] if api_col in col_set else None
            if val is not None:
                try:
                    fv = float(val)
                    if math.isnan(fv):
                        val = None
                    else:
                        val = fv
                except (ValueError, TypeError):
                    pass
            data_dict[json_key] = val

        json_str = json.dumps(data_dict, ensure_ascii=False)
        sql = (
            f'INSERT IGNORE INTO fina_info_detailed_tbl (code, reportdate, data) '
            f'VALUES ("{code}", "{reportdate}", \'{json_str}\')'
        )
        try:
            dbcursor.execute(sql)
        except Exception as e:
            print(f"  ⚠️ 插入详细财务数据失败 {code}: {e}")

    mydb.commit()


def get_single_detailed_fina_info(reportdate):
    print("Get detailed fina date:", reportdate)
    df = get_single_detailed_fina_info_from_net(reportdate)
    if len(df) == 0:
        return

    insert_detailed_fina_info(reportdate, df)
    return


def get_detailed_fina_info():
    print("Now, begin to get detailed fina info......")

    # 确保表存在
    try:
        dbcursor.execute('''
            CREATE TABLE IF NOT EXISTS fina_info_detailed_tbl (
                code VARCHAR(10) NOT NULL COMMENT '股票代码',
                reportdate DATE NOT NULL COMMENT '报告期',
                data JSON NOT NULL COMMENT '完整财务指标JSON',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                PRIMARY KEY (code, reportdate),
                INDEX idx_code (code),
                INDEX idx_reportdate (reportdate)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        mydb.commit()
        print("  ✅ fina_info_detailed_tbl 表已就绪")
    except Exception as e:
        print(f"  ⚠️ 创建 fina_info_detailed_tbl 失败: {e}")

    reportdate_list = (date(1111, 3, 31), date(1111, 6, 30), date(1111, 9, 30), date(1111, 12, 31))

    start_date = get_last_reportdate_of_detailed_fina_info()
    curday = datetime.today().date()
    print(f'......start_date={start_date}, current_day={curday}')

    while start_date <= curday:
        for reportdate in reportdate_list:
            if start_date.month == reportdate.month and start_date.day == reportdate.day:
                get_single_detailed_fina_info(start_date)
                break

        start_date += timedelta(days=1)

    return

#--------------------------------------------------------------------------
def get_last_update_date():
    sql = 'select update_date from data_update_date_info_tbl limit 1'
    dbcursor.execute(sql)
    result = dbcursor.fetchone()
    
    if result == None or len(result) == 0:
        return None
    
    return result[0]

def update_date():
    curday = datetime.today().date()
    if get_last_update_date() != None:
        sql = f'update data_update_date_info_tbl set update_date = "{curday}"'
    else:
        sql = f'insert into data_update_date_info_tbl values ("{curday}")'
    dbcursor.execute(sql)
    mydb.commit()
    return

def update_all_basic_info(force_update=False, clear_stock_table=False):
    last_update_date = get_last_update_date()
    curday = datetime.today().date()
    
    print("last_update_date:",last_update_date,"curday:",curday)
    
    # 如果需要清空整个表，在开始前清空（包括股票、ETF、THS概念等所有数据）
    if clear_stock_table:
        print("Clearing entire stock_basic_info_tbl table (all stock types)...")
        delete_all_data_by_tablename(dbcursor, "stock_basic_info_tbl")
        mydb.commit()
        print("Entire table cleared successfully.")
        # 清空表后，自动修复表字符集
        print("Checking and fixing table charset after clearing...")
        check_and_fix_table_charset(auto_fix=True)
        # 清空表后强制更新数据
        force_update = True
        print("Force update enabled after clearing table.")
    
    if last_update_date == None or last_update_date + timedelta(days=30) < curday or force_update:
        # to update basic info
        print("Begin to update basic info...")
        # 获取基本股票信息
        # 注意：如果已经在上一步清空了整个表，这里不需要再次清空
        get_stock_basic_info_and_insert_to_db(force_update, clear_table=False)
        # 获取etf信息
        get_etf_basic_info_and_insert_to_db()
        
        # 获取东财概念信息
        #get_choice_concept_info_and_insert_to_db()
        # 获取申万信息
        get_sw_code_list_from_tushare()
        
        # 获取ETF对应的code信息
        get_etf_code_info_and_insert_to_db()

        # 获取股票前10流通股东信息
        get_10_stk_holder_info()
        
        # 获取ths概念和指数信息
        get_ths_concept_basic_info_and_insert_to_db()
        # 获取ths概念对应的code信息
        get_ths_concept_code_info_and_insert_to_db()
        
        # 获取港股基本信息
        get_hk_stock_basic_info_and_insert_to_db(force_update)
        
        update_date()
    else:
        print("Not to update basic info today")
        
    return
#--------------------------------------------------------------------------
# 获取普通股票日行情
#获取某个交易日期的所有股票的 日线 信息
def get_stock_daily(trade_date):
    df = []
    for _ in range(5):
        try:
            df = pro.daily(trade_date=trade_date, fields='ts_code,open,high,low,close,vol,amount')
        except:
            _time.sleep(3)
        else:
            return df
    return []

#获取某一天的所有股票的复权因子
def get_stock_daily_adj_factor(trade_date):
    ret_result = {}
    for _ in range(5):
        try:
            df = pro.adj_factor(ts_code='',trade_date=trade_date,fields='ts_code,adj_factor')
        except:
            _time.sleep(3)
        else:
            for value in df.values:
               ret_result[value[0]] = value[1]
            return ret_result
    return {}

#获得本次开始获取记录的时间
def get_stock_start_date():
    return get_X_start_date(dbcursor,"daily_info_tbl","000001.SZ" )

#获取某个股票，某个日期列表中的股价信息
def get_single_stock_daily_by_datelist(code, datelist):
    print(f'begin to fetch single stock daily info: {code}')
    for date_str in datelist:
        df = get_stock_daily(date_str)
        print(f'...Get {len(df)} records')
        adj_factor = get_stock_daily_adj_factor(date_str)
        for daily_info in df.values:
            if code == daily_info[0]:
                print(f'get stock daily info success: {code} {date_str}')
                if code in adj_factor:
                    cur_adj_factor = adj_factor[daily_info[0]]
                    insert_daily_data_into_table(dbcursor,daily_info[0],date_str,daily_info,cur_adj_factor  )
                    print("get adj_factor info success: ",date_str, " code: ",code)
                else:
                    print("get adj_factor info fail: ",date_str, " code: ",code)
                break
    
    mydb.commit()
    return


#从csv文件中读取daily basic信息
def get_all_stock_daily_from_csv(csv_filename_stock, csv_filename_adj):
    try:
        code_to_adj_dict={}
        with open(csv_filename_adj, mode='r', encoding='utf-8') as file:
            csv_reader = csv.reader(file)   
            headers = next(csv_reader)
            count = 0
            for row in csv_reader:
                code_to_adj_dict[row[0]] = row[2]
                count += 1
            print(f"read adj factor count={count}")
        
        with open(csv_filename_stock, mode='r', encoding='utf-8') as file1:
            # 创建 CSV 读取器
            csv_reader1 = csv.reader(file1)            
            # 获取表头
            headers1 = next(csv_reader1)
            #print("表头:", headers)            
            # 读取并打印每行数据
            #print("\n内容:")
            count = 0
            for row in csv_reader1:
                #''ts_code,open,high,low,close,vol,amount'
                #ts_code	trade_date	close	open	high	low	pre_close	change	pct_change	vol	amount
                #print(row)
                new_row=row
                for i in range(len(row)):
                    if row[i]=="":
                        new_row[i] = "-1"
                row = new_row
                if row[0] in code_to_adj_dict:
                    adj_factor = code_to_adj_dict[row[0]]
                    if adj_factor=="":
                        adj_factor = '-1'
                else:
                    adj_factor = '-1'
                
                values = f'"{row[1]}",{row[3]},{row[4]},{row[5]},{row[2]},{row[9]},{row[10]},{adj_factor}'
                #print(values)
                insert_into_tbl_all_values(dbcursor,row[0],"daily_info_tbl",values)
                count += 1
            print(f'read stock daily total rows={count}')
            mydb.commit()
            
    except FileNotFoundError:
        print(f"错误: 文件 '{file_path}' 未找到")
    except Exception as e:
        print(f"发生错误: {str(e)}")
    
    return

#从tushare 获得所有日线数据
def get_all_stock_daily():
    print('Now, to get all stock daily info from tushare')
    exchange_day = get_exchange_day_from_db(dbcursor)
    start_date = get_stock_start_date()
    
    for date_tuple in exchange_day:
        cur_date = date_tuple[0]
        if cur_date < start_date:
            continue
        
        print("Get date: ", cur_date)
        date_str = date_to_datestr(cur_date)
        df = get_stock_daily(date_str)
        print(f'...Get {len(df)} records')
        adj_factor = get_stock_daily_adj_factor(date_str)
        
        for daily_info in df.values:
            if daily_info[0] in adj_factor:
                cur_adj_factor = adj_factor[daily_info[0]]
                insert_daily_data_into_table(dbcursor,daily_info[0],cur_date,daily_info,cur_adj_factor  )
            else:
                print("get adj factor failed: ",date_str, " code: ",daily_info[0]," not use today data")
            
        mydb.commit()
        _time.sleep(1)
    
    mydb.commit()
    
    return
#--------------------------------------------------------------------------
# 获取ETF行情信息
#获得本次开始获取记录的时间
def get_ETF_start_date():
    return get_X_start_date(dbcursor,"daily_info_tbl","512880.SH" )

#获取某个交易日期的所有ETF的 日线 信息
def get_ETF_daily(trade_date):
    df = []
    for _ in range(5):
        try:
            df = pro.fund_daily(trade_date=trade_date, fields='ts_code,open,high,low,close,vol,amount')
        except:
            _time.sleep(3)
        else:
            return df
    return []

#获取某一天的所有ETF的复权因子
def get_ETF_daily_adj_factor(trade_date):
    ret_result = {}
    for _ in range(5):
        try:
            df = pro.fund_adj(trade_date=trade_date,fields='ts_code,adj_factor')
        except:
            _time.sleep(3)
        else:
            for value in df.values:
               ret_result[value[0]] = value[1]
            return ret_result
    return {}

#从tushare 获得所有日线数据
def get_all_ETF_daily():
    print('Now, to get all ETF daily info from tushare')
    exchange_day = get_exchange_day_from_db(dbcursor)
    start_date = get_ETF_start_date()
    
    for date_tuple in exchange_day:
        cur_date = date_tuple[0]
        if cur_date < start_date:
            continue
        
        print("Get date: ", cur_date)
        date_str = date_to_datestr(cur_date)
        df = get_ETF_daily(date_str)
        print(f'...Get {len(df)} records')
        adj_factor = get_ETF_daily_adj_factor(date_str)
        
        for daily_info in df.values:
            if daily_info[0] in adj_factor:
                cur_adj_factor = adj_factor[daily_info[0]]
                insert_daily_data_into_table(dbcursor,daily_info[0],cur_date,daily_info,cur_adj_factor  )
            else:
                print("get adj factor failed: ",date_str, " code: ",daily_info[0]," not use today data")
            
        mydb.commit()
        _time.sleep(1)
    
    mydb.commit()
    
    return

#--------------------------------------------------------------------------
# 获取港股行情信息
#获得本次开始获取记录的时间
def get_HK_start_date():
    # 使用一个港股代码作为示例，例如腾讯控股 00700.HK
    return get_X_start_date(dbcursor,"daily_info_tbl","00700.HK" )

#获取某个交易日期的所有港股的 日线 信息
def get_HK_daily(trade_date):
    global _last_hk_api_call_time
    
    # 只对异常进行重试，空数据不重试
    for retry in range(5):
        try:
            # 控制API调用频率，确保不超过每分钟2次的限制
            current_time = _time.time()
            time_since_last_call = current_time - _last_hk_api_call_time
            if time_since_last_call < _HK_API_MIN_INTERVAL:
                wait_time = _HK_API_MIN_INTERVAL - time_since_last_call
                print(f"Waiting {wait_time:.1f}s to avoid API rate limit...")
                _time.sleep(wait_time)
            
            # tushare的hk_daily接口获取港股日线数据
            # 注意：hk_daily接口可能需要使用start_date和end_date参数，而不是单独的trade_date
            # 如果trade_date参数不工作，尝试使用start_date和end_date都设置为trade_date
            _last_hk_api_call_time = _time.time()
            df = pro.hk_daily(trade_date=trade_date, fields='ts_code,open,high,low,close,vol,amount')
            if df is not None and len(df) > 0:
                return df
            # 如果返回空数据，尝试使用start_date和end_date方式（只尝试一次）
            if retry == 0:
                print(f"Warning: hk_daily with trade_date={trade_date} returned empty, trying start_date/end_date...")
                try:
                    # 再次检查频率限制
                    current_time = _time.time()
                    time_since_last_call = current_time - _last_hk_api_call_time
                    if time_since_last_call < _HK_API_MIN_INTERVAL:
                        wait_time = _HK_API_MIN_INTERVAL - time_since_last_call
                        print(f"Waiting {wait_time:.1f}s before retry to avoid API rate limit...")
                        _time.sleep(wait_time)
                    
                    _last_hk_api_call_time = _time.time()
                    df = pro.hk_daily(start_date=trade_date, end_date=trade_date, fields='ts_code,open,high,low,close,vol,amount')
                    if df is not None and len(df) > 0:
                        return df
                except Exception as e2:
                    print(f"Warning: hk_daily with start_date/end_date also failed: {e2}")
            
            # 如果没有异常但返回空数据，直接返回空，不重试
            print(f"Empty data for date {trade_date}, returning empty (no retry for empty data)")
            return []
        except Exception as e:
            error_msg = str(e)
            # 检测是否是频率限制错误
            is_rate_limit = "每分钟最多访问" in error_msg or "rate limit" in error_msg.lower()
            
            # 只有出现异常时才重试
            print(f"Error getting HK daily data for date {trade_date} (retry {retry+1}/5): {e}")
            
            if retry < 4:
                # 如果是频率限制错误，等待更长时间（至少30秒）
                if is_rate_limit:
                    wait_time = _HK_API_MIN_INTERVAL
                    print(f"Rate limit detected, waiting {wait_time}s before retry...")
                    _time.sleep(wait_time)
                else:
                    _time.sleep(3)
            else:
                print(f"Failed to get HK daily data for date {trade_date} after 5 retries")
                return []
    
    return []

#从tushare 获得所有港股日线数据
def get_all_HK_daily():
    print('Now, to get all HK stock daily info from tushare')
    exchange_day = get_exchange_day_from_db(dbcursor)
    start_date = get_HK_start_date()
    print(f'Start date from DB: {start_date}')
    print(f'Total exchange days to process: {len(exchange_day)}')
    
    success_count = 0
    empty_count = 0
    skip_count = 0
    
    for date_tuple in exchange_day:
        cur_date = date_tuple[0]
        if cur_date < start_date:
            skip_count += 1
            continue
        
        print("Get HK date: ", cur_date)
        date_str = date_to_datestr(cur_date)
        df = get_HK_daily(date_str)
        if df is None or len(df)==0:
            empty_count += 1
            print(f"Get empty HK info for date {cur_date} (date_str: {date_str})")
            print(f"  Empty count so far: {empty_count}, Success count: {success_count}")
            continue
        
        success_count += 1
        print(f'...Get {len(df)} HK records for date {cur_date}')
        
        # 港股可能没有复权因子，或者使用不同的接口
        # 暂时使用1作为复权因子
        for daily_info in df.values:
            insert_daily_data_into_table(dbcursor,daily_info[0],cur_date,daily_info,1  )
            
        mydb.commit()
        _time.sleep(1)
    
    mydb.commit()
    print(f'HK daily data fetch completed. Success: {success_count}, Empty: {empty_count}, Skipped: {skip_count}')
    
    return

#--------------------------------------------------------------------------
# 获取ths指数信息
#获得本次开始获取记录的时间
def get_THS_start_date():
    return get_X_start_date(dbcursor,"daily_info_tbl","885472.TI" )

#获取某个交易日期的所有ths指数的 日线 信息
def get_THS_daily(trade_date):
    df = []
    for _ in range(5):
        try:
            df = pro.ths_daily(trade_date=trade_date, fields='ts_code,open,high,low,close,vol,float_mv')
        except:
            _time.sleep(3)
        else:
            return df
    return []

#从tushare 获得所有日线数据
def get_all_THS_daily():
    print('Now, to get all THS daily info from tushare')
    exchange_day = get_exchange_day_from_db(dbcursor)
    start_date = get_THS_start_date()
    
    for date_tuple in exchange_day:
        cur_date = date_tuple[0]
        if cur_date < start_date:
            continue
        
        print("Get date: ", cur_date)
        date_str = date_to_datestr(cur_date)
        df = get_THS_daily(date_str)
        if len(df)==0:
            print("Get empty info")
            continue
        print(f'...Get {len(df)} records')
        
        for daily_info in df.values:
            insert_daily_data_into_table(dbcursor,daily_info[0],cur_date,daily_info,1  )
            
        mydb.commit()
        _time.sleep(1)
    
    mydb.commit()
    
    return
#--------------------------------------------------------------------------
# 获取普通股票 daily_basic

#从csv文件中读取daily basic信息
def get_daily_basic_daily_from_csv(csv_filename):
    try:
        with open(csv_filename, mode='r', encoding='utf-8') as file:
            # 创建 CSV 读取器
            csv_reader = csv.reader(file)            
            # 获取表头
            headers = next(csv_reader)
            #print("表头:", headers)            
            # 读取并打印每行数据
            #print("\n内容:")
            count = 0
            for row in csv_reader:
                #'ts_code,turnover_rate_f,pe,pe_ttm,pb,total_share,float_share,total_mv,circ_mv,free_share'
                #print(row)
                new_row=row
                for i in range(len(row)):
                    if row[i]=="":
                        new_row[i] = "-1"
                row = new_row
                values = f'"{row[1]}",{row[4]},{row[5]},{row[6]},{row[7]},{row[10]},{row[11]},{row[13]},{row[14]},{row[12]}'
                #print(values)
                insert_into_tbl_all_values(dbcursor,row[0],"daily_basic_tbl",values)
                count += 1
            print(f'total rows={count}')
            mydb.commit()
            
    except FileNotFoundError:
        print(f"错误: 文件 '{file_path}' 未找到")
    except Exception as e:
        print(f"发生错误: {str(e)}")
    
    return


def check_if_daily_basic_record_exist(code,tradedate ):
    return check_if_X_record_exist(dbcursor,code, tradedate, 'daily_basic_tbl','tradedate')

def get_daily_basic_start_date():
    return get_X_start_date(dbcursor,"daily_basic_tbl","000001.SZ" )

#获取某个交易日期的所有ths指数的 日线 信息
def get_daily_basic_daily(trade_date):
    df = []
    for _ in range(5):
        try:
            df = pro.daily_basic(ts_code='',trade_date=trade_date, fields='ts_code,turnover_rate_f,pe,pe_ttm,pb,total_share,float_share,total_mv,circ_mv,free_share')
        except:
            _time.sleep(3)
        else:
            return df
    return []

#从tushare 获得所有日线数据
def get_all_daily_basic_daily():
    print('Now, to get all daily basic info from tushare')
    exchange_day = get_exchange_day_from_db(dbcursor)
    start_date = get_daily_basic_start_date()
    
    is_break = False
    for date_tuple in exchange_day:
        cur_date = date_tuple[0]
        if cur_date < start_date:
            continue
        
        print("Get date: ", cur_date)
        date_str = date_to_datestr(cur_date)
        df = get_daily_basic_daily(date_str)
        print(f'...Get {len(df)} records')
        
        for daily_info in df.values:
            code = daily_info[0]
            value1 = convert_list_into_str(daily_info[1:10])
            values = f'"{cur_date}", {value1}'
            try:
                # 使用 INSERT IGNORE 避免主键冲突，直接在 SQL 层面处理
                insert_into_tbl_all_values_ignore(dbcursor,code,"daily_basic_tbl",values)
            except Exception as ee:
                print("error >>>",ee)
                print(values)
                is_break = True
                break
        if is_break:
            break
            
        mydb.commit()
        _time.sleep(1)
    
    mydb.commit()
    
    return
#--------------------------------------------------------------------------
# 获取资金流向信息
def check_if_money_flow_record_exist(code,tradedate ):
    return check_if_X_record_exist(dbcursor,code, tradedate, 'daily_moneyflow_tbl','tradedate')

# 获取普通股票 daily_basic
def get_daily_money_flow_start_date():
    return get_X_start_date(dbcursor,"daily_moneyflow_tbl","000001.SZ" )

#获取某个交易日期的所有ths指数的 日线 信息
def get_daily_money_flow(trade_date):
    df = []
    for _ in range(5):
        try:
            df = pro.moneyflow(trade_date=trade_date, \
                               fields='ts_code,buy_lg_vol,buy_lg_amount,sell_lg_vol,sell_lg_amount,buy_elg_vol,buy_elg_amount,sell_elg_vol,sell_elg_amount ')
        except:
            _time.sleep(3)
        else:
            return df
    return []

#从tushare 获得所有日线数据
def get_all_money_flow_daily():
    print('Now, to get all money flow info from tushare')
    exchange_day = get_exchange_day_from_db(dbcursor)
    start_date = get_daily_money_flow_start_date()
    
    for date_tuple in exchange_day:
        cur_date = date_tuple[0]
        if cur_date < start_date:
            continue
        
        print("Get date: ", cur_date)
        date_str = date_to_datestr(cur_date)
        df = get_daily_money_flow(date_str)
        print(f'...Get {len(df)} records')
        
        for x in df.values:
            code = x[0]
            net_lg_vol = x[1] - x[3]
            net_lg_amount = x[2] - x[4]
            net_elg_vol = x[5] - x[7]
            net_elg_amount = x[6] - x[8]
            
            values = f'"{cur_date}", {net_lg_vol},{net_lg_amount},{net_elg_vol},{net_elg_amount}'
            if not check_if_money_flow_record_exist(code,cur_date):
                insert_into_tbl_all_values(dbcursor,code,"daily_moneyflow_tbl",values)
            
        mydb.commit()
        _time.sleep(1)
    
    mydb.commit()
    
    return

#--------------------------------------------------------------------------
# 从 daily_moneyflow_tbl_2
# 获取资金流向信息
def check_if_money_flow_record_exist_v2(code,tradedate ):
    return check_if_X_record_exist(dbcursor,code, tradedate, 'daily_moneyflow_tbl_2','tradedate')

# 获取普通股票 daily_basic
def get_daily_money_flow_start_date_v2():
    return get_X_start_date(dbcursor,"daily_moneyflow_tbl_2","000001.SZ" )

#获取某个交易日期的所有ths指数的 日线 信息
def get_daily_money_flow_v2(trade_date):
    df = []
    for _ in range(5):
        try:
            df = pro.moneyflow(trade_date=trade_date)
        except:
            _time.sleep(3)
        else:
            return df
    return []

def get_all_money_flow_single_day_v2(date_str):
    df = get_daily_money_flow_v2(date_str)
    for x in df.values:
            code = x[0]
            values = f'"{date_str}",' + convert_list_into_str(x[2:len(x)])
            
            #values = f'"{cur_date}", {net_lg_vol},{net_lg_amount},{net_elg_vol},{net_elg_amount}'
            if not check_if_money_flow_record_exist_v2(code,date_str):
                insert_into_tbl_all_values(dbcursor,code,"daily_moneyflow_tbl_2",values)
            
    mydb.commit()
    return

#从csv文件中读取daily basic信息
def get_all_money_flow_daily_v2_from_csv(csv_filename):
    try:
        with open(csv_filename, mode='r', encoding='utf-8') as file:
            # 创建 CSV 读取器
            csv_reader = csv.reader(file)            
            # 获取表头
            headers = next(csv_reader)
            #print("表头:", headers)            
            # 读取并打印每行数据
            #print("\n内容:")
            count = 0
            for row in csv_reader:
                #'ts_code,turnover_rate_f,pe,pe_ttm,pb,total_share,float_share,total_mv,circ_mv,free_share'
                #print(row)
                new_row=row
                for i in range(len(row)):
                    if row[i]=="":
                        new_row[i] = "-1"
                row = new_row
                values = f'"{row[1]}",{row[16]},{row[15]},{row[18]},{row[17]}'
                values += f',{row[12]},{row[11]},{row[14]},{row[13]}'
                values += f',{row[8]},{row[7]},{row[10]},{row[9]}'
                values += f',{row[4]},{row[3]},{row[6]},{row[5]}'
                values += f',{row[20]},{row[19]}'
                #print(values)
                insert_into_tbl_all_values(dbcursor,row[0],"daily_moneyflow_tbl_2",values)
                count += 1
            print(f'get money flow total rows={count}')
            mydb.commit()
            
    except FileNotFoundError:
        print(f"错误: 文件 '{file_path}' 未找到")
    except Exception as e:
        print(f"发生错误: {str(e)}")
    
    return

#从tushare 获得所有日线数据
def get_all_money_flow_daily_v2():
    print('Now, to get all money flow info v2 from tushare')
    exchange_day = get_exchange_day_from_db(dbcursor)
    start_date = get_daily_money_flow_start_date_v2()
    
    for date_tuple in exchange_day:
        cur_date = date_tuple[0]
        if cur_date < start_date:
            continue
        
        print("Get date: ", cur_date)
        date_str = date_to_datestr(cur_date)
        df = get_daily_money_flow_v2(date_str)
        print(f'...Get {len(df)} records')
        
        for x in df.values:
            code = x[0]
            values = f'"{cur_date}",' + convert_list_into_str(x[2:len(x)])
            
            #values = f'"{cur_date}", {net_lg_vol},{net_lg_amount},{net_elg_vol},{net_elg_amount}'
            if not check_if_money_flow_record_exist_v2(code,cur_date):
                insert_into_tbl_all_values(dbcursor,code,"daily_moneyflow_tbl_2",values)
            
        mydb.commit()
        _time.sleep(1)
    
    mydb.commit()
    
    return

#--------------------------------------------------------------------------
# 从tushare获取筹码分布信息
def check_if_cyq_perf_record_exist(code,tradedate ):
    return check_if_X_record_exist(dbcursor,code, tradedate, 'cyq_perf_tbl','tradedate')

def get_daily_cyq_perf_start_date():
    return get_X_start_date(dbcursor,"cyq_perf_tbl","000001.SZ" )

def get_daily_cyq_perf(trade_date):
    df = []
    for _ in range(5):
        try:
            df = pro.cyq_perf(trade_date=trade_date)
        except:
            _time.sleep(3)
        else:
            return df
    return []

def get_single_cyq_perf_info(code,datelist):
    for date_str in datelist:
        df = get_daily_cyq_perf(date_str)
        print(f'...Get {len(df)} records')
        for x in df.values:
            if code == x[0]:
                values = f'"{date_str}",' + convert_list_into_str(x[2:len(x)])
                if not check_if_cyq_perf_record_exist(code,date_str):
                    insert_into_tbl_all_values(dbcursor,code,"cyq_perf_tbl",values)
                    print(f'insert cyq info at {code}, {date_str}')
                break
    mydb.commit()
    return

def get_all_cyq_perf_info():
    print('Now, to get all cyq_perf_info from tushare')
    exchange_day = get_exchange_day_from_db(dbcursor)
    start_date = get_daily_cyq_perf_start_date()
    
    for date_tuple in exchange_day:
        cur_date = date_tuple[0]
        if cur_date < start_date:
            continue
        
        print("Get date: ", cur_date)
        date_str = date_to_datestr(cur_date)
        df = get_daily_cyq_perf(date_str)
        print(f'...Get {len(df)} records')
        
        for x in df.values:
            code = x[0]
            values = f'"{cur_date}",' + convert_list_into_str(x[2:len(x)])
            
            #values = f'"{cur_date}", {net_lg_vol},{net_lg_amount},{net_elg_vol},{net_elg_amount}'
            if not check_if_cyq_perf_record_exist(code,cur_date):
                insert_into_tbl_all_values(dbcursor,code,"cyq_perf_tbl",values)
            
        mydb.commit()
        _time.sleep(1)
    
    mydb.commit()
    
    return
#--------------------------------------------------------------------------
# 显示所有数据类型的最后更新日期
def show_data_update_status():
    """显示各类数据的最后更新日期"""
    print("\n" + "="*60)
    print("数据更新状态查询")
    print("="*60)
    
    # 查询A股数据最后更新日期
    try:
        sql = 'select max(tradedate) from daily_info_tbl where code like "%.SZ" or code like "%.SH"'
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
        if result and result[0]:
            print(f"A股数据最后更新日期: {result[0]}")
        else:
            print("A股数据: 无数据")
    except Exception as e:
        print(f"A股数据查询错误: {e}")
    
    # 查询ETF数据最后更新日期（使用ETF示例代码512880.SH）
    try:
        sql = 'select max(tradedate) from daily_info_tbl where code = "512880.SH"'
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
        if result and result[0]:
            print(f"ETF数据最后更新日期: {result[0]}")
        else:
            print("ETF数据: 无数据")
    except Exception as e:
        print(f"ETF数据查询错误: {e}")
    
    # 查询港股数据最后更新日期
    try:
        sql = 'select max(tradedate) from daily_info_tbl where code like "%.HK"'
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
        if result and result[0]:
            print(f"港股数据最后更新日期: {result[0]}")
        else:
            print("港股数据: 无数据")
    except Exception as e:
        print(f"港股数据查询错误: {e}")
    
    # 查询THS指数数据最后更新日期
    try:
        sql = 'select max(tradedate) from daily_info_tbl where code like "%.TI"'
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
        if result and result[0]:
            print(f"THS指数数据最后更新日期: {result[0]}")
        else:
            print("THS指数数据: 无数据")
    except Exception as e:
        print(f"THS指数数据查询错误: {e}")
    
    # 查询daily_basic数据最后更新日期
    try:
        sql = 'select max(tradedate) from daily_basic_tbl'
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
        if result and result[0]:
            print(f"Daily Basic数据最后更新日期: {result[0]}")
        else:
            print("Daily Basic数据: 无数据")
    except Exception as e:
        print(f"Daily Basic数据查询错误: {e}")
    
    # 查询资金流向数据最后更新日期
    try:
        sql = 'select max(tradedate) from daily_moneyflow_tbl_2'
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
        if result and result[0]:
            print(f"资金流向数据最后更新日期: {result[0]}")
        else:
            print("资金流向数据: 无数据")
    except Exception as e:
        print(f"资金流向数据查询错误: {e}")
    
    # 查询cyq_perf数据最后更新日期
    try:
        sql = 'select max(tradedate) from cyq_perf_tbl'
        dbcursor.execute(sql)
        result = dbcursor.fetchone()
        if result and result[0]:
            print(f"CYQ绩效数据最后更新日期: {result[0]}")
        else:
            print("CYQ绩效数据: 无数据")
    except Exception as e:
        print(f"CYQ绩效数据查询错误: {e}")
    
    # 显示下次将开始获取的日期
    print("\n" + "-"*60)
    print("下次将开始获取的日期:")
    print("-"*60)
    try:
        stock_start = get_stock_start_date()
        print(f"A股下次开始日期: {stock_start}")
    except:
        print("A股下次开始日期: 无法获取")
    
    try:
        etf_start = get_ETF_start_date()
        print(f"ETF下次开始日期: {etf_start}")
    except:
        print("ETF下次开始日期: 无法获取")
    
    try:
        hk_start = get_HK_start_date()
        print(f"港股下次开始日期: {hk_start}")
    except:
        print("港股下次开始日期: 无法获取")
    
    print("="*60 + "\n")

#--------------------------------------------------------------------------
def main_entrance(get_hk_data=True):
    #'''
    total_start = _time.time()
    print("[TIMING] Begin main_entrance")
    
    # 显示数据更新状态
    show_data_update_status()
    # 根据是否获取港股数据调整总步数
    total_steps = 12 if get_hk_data else 11
    step_idx = 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_exchange_day_and_insert_to_db: start")
    get_exchange_day_and_insert_to_db()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_exchange_day_and_insert_to_db: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_all_stock_daily: start")
    get_all_stock_daily()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_all_stock_daily: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_all_ETF_daily: start")
    get_all_ETF_daily()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_all_ETF_daily: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_all_THS_daily: start")
    get_all_THS_daily()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_all_THS_daily: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    # 根据参数决定是否获取港股数据
    if get_hk_data:
        step_start = _time.time()
        print(f"[TIMING] ({step_idx}/{total_steps}) -> get_all_HK_daily: start")
        get_all_HK_daily()
        print(f"[TIMING] ({step_idx}/{total_steps}) <- get_all_HK_daily: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
        step_idx += 1
    else:
        print(f"[TIMING] ({step_idx}/{total_steps}) -> get_all_HK_daily: SKIPPED (get_hk_data=False)")
        step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_all_daily_basic_daily: start")
    get_all_daily_basic_daily()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_all_daily_basic_daily: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_fina_info: start")
    get_fina_info()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_fina_info: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_detailed_fina_info: start")
    get_detailed_fina_info()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_detailed_fina_info: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_all_money_flow_daily: start")
    get_all_money_flow_daily()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_all_money_flow_daily: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_all_money_flow_daily_v2: start")
    get_all_money_flow_daily_v2()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_all_money_flow_daily_v2: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> get_all_cyq_perf_info: start")
    get_all_cyq_perf_info()
    print(f"[TIMING] ({step_idx}/{total_steps}) <- get_all_cyq_perf_info: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")
    step_idx += 1

    step_start = _time.time()
    print(f"[TIMING] ({step_idx}/{total_steps}) -> update_all_basic_info: start")
    update_all_basic_info(force_update=False, clear_stock_table=False)
    print(f"[TIMING] ({step_idx}/{total_steps}) <- update_all_basic_info: {(_time.time()-step_start):.2f}s, total {(_time.time()-total_start):.2f}s")

    print(f"[TIMING] End main_entrance. Total: {(_time.time()-total_start):.2f}s")
    #'''
    
    return

def read_all_from_csv():
    curdate = '20250820'
    get_daily_basic_daily_from_csv(f'C:\\zh\\stock_csv\\daily_basic_{curdate}.csv')
    get_all_stock_daily_from_csv(f'C:\\zh\\stock_csv\\daily_{curdate}.csv',f'C:\\zh\\stock_csv\\adj_factor_{curdate}.csv')
    get_all_money_flow_daily_v2_from_csv(f'C:\\zh\\stock_csv\\moneyflow_{curdate}.csv')
    return
#--------------------------------------------------------------------------
# 删除某天的所有记录
def remove_data_by_date_mf_v2(some_date):
    delete_data_by_date(dbcursor,"daily_moneyflow_tbl_2",some_date)
    mydb.commit()
    return

def remove_data_by_date(some_date):
    print('begin to remove data')
    delete_data_by_date(dbcursor,"daily_info_tbl",some_date)
    mydb.commit()
    delete_data_by_date(dbcursor,"cyq_perf_tbl",some_date)
    mydb.commit()
    delete_data_by_date(dbcursor,"daily_basic_tbl",some_date)
    mydb.commit()
    delete_data_by_date(dbcursor,"daily_moneyflow_tbl",some_date)
    mydb.commit()
    delete_data_by_date(dbcursor,"daily_moneyflow_tbl_2",some_date)
    mydb.commit()
    print('end removing')
    
#--------------------------------------------------------------------------

if __name__ == '__main__':
    dbname = 'gp2'
    
    # 解析命令行参数，控制是否获取港股数据
    # 使用方式: python new_get_all_stock.py --no-hk 或 python new_get_all_stock.py --skip-hk
    # 默认获取港股数据
    get_hk_data = True
    if len(sys.argv) > 1:
        if '--no-hk' in sys.argv or '--skip-hk' in sys.argv:
            get_hk_data = False
            print("港股数据获取已禁用 (通过命令行参数 --no-hk 或 --skip-hk)")
        elif '--status' in sys.argv or '--check' in sys.argv:
            # 只查询状态，不运行数据获取
            try:
                mydb = initMySQL(dbname)
                dbcursor = mydb.cursor(buffered=True)
                show_data_update_status()
                closeMySQL(mydb, dbcursor)
            except Exception as ee:
                print("error >>>",ee)
                import traceback
                traceback.print_exc()
            sys.exit(0)
        elif '--help' in sys.argv or '-h' in sys.argv:
            print("用法: python new_get_all_stock.py [选项]")
            print("选项:")
            print("  --no-hk, --skip-hk  跳过港股数据获取")
            print("  --status, --check   只查询数据更新状态，不运行数据获取")
            print("  --help, -h           显示此帮助信息")
            sys.exit(0)

    try:
        #调用登录函数（激活后使用，不需要用户名密码）
        #loginResult = c.start("ForceLogin=1", '', mainCallback)
        #if(loginResult.ErrorCode != 0):
        #    print("login in fail")
        #    exit()
        
        mydb = initMySQL(dbname)
        dbcursor = mydb.cursor(buffered=True)
        
        try:
            main_entrance(get_hk_data=get_hk_data)
            #read_all_from_csv()
            #remove_data_by_date('2024-09-30')
            #get_single_stock_daily_by_datelist('689009.SH',['20240108','20231016','20220525','20220524','20220523','20220520','20220519','20220518','20220517','20220516','20220512','20220511','20220510','20220509','20220506','20220505','20220429','20220428','20220427','20220426','20220425','20220422','20220421','20220420','20220419','20220418','20220415','20220414','20220413','20220412','20220411','20220408','20220407','20220406','20220401','20220321','20220307','20220224','20220223','20220222','20220221','20220207','20211227','20211217','20211216','20211215','20210222'])
            #get_single_cyq_perf_info('688584.SH',['20240208'])
            #get_single_stock_daily_by_datelist('689009.SH',['20240108'])
            #datestr = '20210924'
            #remove_data_by_date_mf_v2(datestr)
            #get_all_money_flow_single_day_v2(datestr)
            #delete_data_by_date(dbcursor,"cyq_perf_tbl",'20240429')
            #delete_data_by_date(dbcursor,"cyq_perf_tbl",'20241021')
            #mydb.commit()
            #delete_all_data_by_tablename(dbcursor,"cyq_perf_tbl")
            #mydb.commit()
        except Exception as ee:
            print("error >>>",ee)
            traceback.print_exc()
        finally:
            #退出
            closeMySQL(mydb, dbcursor)
            #data = logoutResult = c.stop()
            
    except Exception as ee:
        print("error >>>",ee)
        traceback.print_exc()
    finally:
        print("end")





