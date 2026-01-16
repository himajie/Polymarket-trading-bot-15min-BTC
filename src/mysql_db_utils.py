import pymysql
from pymysql.cursors import DictCursor
import logging
import struct

# 连接到数据库（如果不存在会自动创建） 

class MySQLHelper: 
    # 配置 PyMySQL 的日志输出
    # logging.basicConfig(level=logging.DEBUG)
    # logger = logging.getLogger('pymysql')
    # logger.setLevel(logging.DEBUG)
    def __init__(self):
        self.connection = pymysql.connect(
            host="france-in.mysql.cnhk.rds.aliyuncs.com",      # MySQL 服务器地址
            user="france",          # 用户名
            password="Himajie123",    # 密码
            database="database_name",    # 数据库名（可选）
            charset='utf8mb4',
            cursorclass=DictCursor
        )
    
    def execute_query(self, query, params=None):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())
                if query.strip().upper().startswith('SELECT'):
                    return cursor.fetchall()
                self.connection.commit()
                return cursor.rowcount
        except Exception as e:
            self.connection.rollback()
            logging.error(f"Query failed: {query}\nError: {str(e)}")
            raise
    def select_one(self, query, params=None):
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())
                return cursor.fetchone()
        except Exception as e:
            self.connection.rollback()
            logging.error(f"Query failed: {query}\nError: {str(e)}")
            raise
    def insert_one(self, table, data):
        """
        单行插入数据
        :param table: 表名
        :param data: 字典格式数据，如 {"name": "Alice", "email": "alice@example.com"}
        :return: 插入的行数（通常为1）

        Partizan Belgrade
        """
        if not data:
            return 0
            
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['%s'] * len(data))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        params=tuple(data.values())
        try:
            # with self.connection.cursor() as cursor:
                cursor = self.connection.cursor()
                cursor.execute(query, params or ())
                lastrowid=cursor.lastrowid
                self.connection.commit()
                return lastrowid
        except Exception as e:
            self.connection.rollback()
            logging.error(f"Query failed: {query}\nError: {str(e)}")
            print(params)
            raise
    def betch_insert(self, table, data_list, max_batch_size=1000):
        if not data_list:
            return 0
        
        # 动态计算批次大小
        if len(data_list[0]) > 10:  # 如果字段很多，减小批次大小
            batch_size = min(500, max_batch_size)
        else:
            batch_size = max_batch_size
        
        columns = ', '.join(data_list[0].keys())
        placeholders = ', '.join(['%s'] * len(data_list[0]))
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        total_inserted = 0
        try:
            with self.connection.cursor() as cursor:
                for i in range(0, len(data_list), batch_size):
                    batch = data_list[i:i + batch_size]
                    params = [tuple(d.values()) for d in batch]
                    
                    cursor.executemany(query, params)
                    total_inserted += len(batch)
                    
                    # 进度显示（可选）
                    if len(data_list) > 10000:
                        progress = min(i + batch_size, len(data_list))
                        print(f"已插入 {progress}/{len(data_list)} 行")
                
                self.connection.commit()
                return total_inserted
                
        except Exception as e:
            self.connection.rollback()
            logging.error(f"批量插入失败，已处理 {total_inserted} 行\nError: {str(e)}")
            raise
    
    def __del__(self):
          if hasattr(self, 'connection') and self.connection.open:
            try:
                self.connection.close()
            except (AttributeError, struct.error):
                pass  # 忽略已关闭连接或无效状态



if __name__ == "__main__":
    dbHelper=MySQLHelper()
    table_team_sql="""
        CREATE TABLE IF NOT EXISTS team (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            vector_json TEXT
        )
    """
    table_team_sql="""
        CREATE TABLE IF NOT EXISTS france_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            main_id Integer,
            main_name TEXT,
            guest_id Integer,
            guest_name TEXT,
            main_name_source TEXT,
            guest_name_source TEXT,
            main_odds REAL,
            guest_odds REAL,
            draw_odds REAL,
            france_group TEXT,
            create_time TEXT,
            source TEXT
        )
    """
    dbHelper.execute_query(table_team_sql,())
    # dbHelper.insert_one("team", {"name": "Alice", "vector_json": "asdasd"})
    # results = dbHelper.execute_query("SELECT * FROM team",())
    results = dbHelper.execute_query("SELECT * FROM france_odds limit 10",())    
    print(results)