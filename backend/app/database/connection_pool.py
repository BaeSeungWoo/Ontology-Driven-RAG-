# -*- coding: utf-8 -*-
"""
데이터베이스 연결 풀 관리 클래스 (pyodbc 전용)
Thread-safe한 pyodbc 연결 풀
"""

import threading
import time
import os
from queue import Queue, Empty
from contextlib import contextmanager
import pyodbc
from datetime import datetime

class DatabaseConnectionPool:
    """스레드 안전한 pyodbc 데이터베이스 연결 풀"""
    
    def __init__(self, pool_name="default",host=None ,port=None, username=None, password=None, database=None, min_connections=5, max_connections=10):
        self.pool_name = pool_name
        self.min_connections = min_connections
        self.max_connections = max_connections
        
        # 연결 풀과 상태 관리
        self.connection_pool = Queue(maxsize=max_connections)
        self.active_connections = set()
        
        # 스레드 안전성을 위한 락
        self.pool_lock = threading.Lock()
        
        # 연결 정보
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        
        # 최적의 ODBC 드라이버 선택
        self.driver = self._get_best_driver()
        self.connection_string = self._build_connection_string()
        
        # 통계 정보
        self.stats = {
            'connections_created': 0,
            'connections_active': 0,
            'connections_errors': 0,
            'last_cleanup': datetime.now()
        }
        
        # 초기 연결 생성
        self._initialize_pool()
        
        # 정리 스레드 시작
        self._start_cleanup_thread()
        
        # print(f"pyodbc 연결 풀 '{pool_name}' 초기화 완료")
        # print(f"   - 드라이버: {self.driver}")
        # print(f"   - 연결 풀 크기: {min_connections}~{max_connections}")
    
    def _get_best_driver(self):
        """사용 가능한 최적의 ODBC 드라이버 반환"""
        drivers = pyodbc.drivers()
        
        # 우선순위별로 드라이버 선택
        preferred_drivers = [
            "ODBC Driver 19 for SQL Server",
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server", 
            "ODBC Driver 16 for SQL Server", 
            "SQL Server Native Client 11.0",
            "SQL Server"
        ]
        
        for driver in preferred_drivers:
            if driver in drivers:
                # print(f"사용할 ODBC 드라이버: {driver}")
                return driver
        
        raise Exception(f"사용 가능한 SQL Server ODBC 드라이버가 없습니다. 설치된 드라이버: {drivers}")
    
    def _build_connection_string(self):
        """연결 문자열 생성"""
        return (
            f'DRIVER={{{self.driver}}};'
            f'SERVER={self.host},{self.port};'
            f'DATABASE={self.database};'
            f'UID={self.username};'
            f'PWD={self.password};'
            f'TrustServerCertificate=yes;'  # SSL 인증서 문제 회피
            f'Connection Timeout=60;'
            f'Command Timeout=60;'
        )
    
    def _initialize_pool(self):
        """초기 연결 생성"""
        # print(f"초기 pyodbc 연결 생성 중... (최소 {self.min_connections}개)")
        
        for i in range(self.min_connections):
            try:
                conn = self._create_connection()
                if conn:
                    self.connection_pool.put(conn)
                    self.active_connections.add(conn)
                    # print(f"✅ pyodbc 연결 {i+1} 생성 성공")
            except Exception as e:
                print(f"pyodbc 초기 연결 {i+1} 생성 실패: {e}")
    
    def _create_connection(self):
        """새로운 pyodbc 연결 생성"""
        try:
            conn = pyodbc.connect(
                self.connection_string,
                timeout=30
            )
            
            # 기본 설정
            conn.autocommit = True
            
            # 연결 테스트
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            
            self.stats['connections_created'] += 1
            return conn
            
        except Exception as e:
            self.stats['connections_errors'] += 1
            print(f"pyodbc 연결 생성 실패: {e}")
            return None
    
    def _is_connection_alive(self, conn):
        """연결 상태 확인"""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            cursor.close()
            return result is not None
        except:
            return False
    
    def get_connection(self, timeout=10):
        """연결 가져오기"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # 기존 연결 시도
                conn = self.connection_pool.get(timeout=1)
                
                # 연결 상태 확인
                if self._is_connection_alive(conn):
                    self.stats['connections_active'] += 1
                    return conn
                else:
                    # 죽은 연결 제거
                    self.active_connections.discard(conn)
                    # print("죽은 pyodbc 연결 발견, 새 연결 생성")
            
            except Empty:
                pass
            
            # 새 연결 생성 시도
            with self.pool_lock:
                if len(self.active_connections) < self.max_connections:
                    conn = self._create_connection()
                    if conn:
                        self.active_connections.add(conn)
                        self.stats['connections_active'] += 1
                        return conn
            
            # 잠깐 대기
            time.sleep(0.1)
        
        raise Exception(f"pyodbc 연결 풀에서 {timeout}초 내에 연결을 가져올 수 없습니다")
    
    def return_connection(self, conn):
        """연결 반환"""
        if conn and conn in self.active_connections:
            try:
                # 반환 시점 health check는 수행하지 않는다.
                # (프로시저 result set 상태/드라이버 내부 상태로 false negative 가능)
                # 실제 생존 검사는 get_connection() 대여 시점에 수행한다.
                try:
                    conn.autocommit = True
                except:
                    pass

                try:
                    self.connection_pool.put(conn, timeout=1)
                except Exception:
                    # 풀에 못 넣으면 안전하게 닫고 정리
                    try:
                        conn.close()
                    except Exception:
                        pass
                    self.active_connections.discard(conn)
                finally:
                    self.stats['connections_active'] -= 1
            except Exception as e:
                print(f"pyodbc 연결 반환 중 오류: {e}")
                self.active_connections.discard(conn)
                self.stats['connections_active'] -= 1
    
    @contextmanager
    def get_db_connection(self):
        """데이터베이스 연결 컨텍스트 매니저"""
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            raise
        finally:
            if conn:
                self.return_connection(conn)
    
    def _start_cleanup_thread(self):
        """정리 스레드 시작"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(300)  # 5분마다 정리
                    self._cleanup_dead_connections()
                except Exception as e:
                    print(f"정리 스레드 오류: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        print("🧹 연결 정리 스레드 시작됨 (5분 간격)")
    
    def _cleanup_dead_connections(self):
        """죽은 연결들 정리"""
        print("연결 풀 정리 시작...")
        
        dead_connections = []
        with self.pool_lock:
            temp_connections = []
            while not self.connection_pool.empty():
                try:
                    conn = self.connection_pool.get_nowait()
                    if self._is_connection_alive(conn):
                        temp_connections.append(conn)
                    else:
                        dead_connections.append(conn)
                        self.active_connections.discard(conn)
                except Empty:
                    break
            
            # 살아있는 연결만 다시 풀에 넣기
            for conn in temp_connections:
                try:
                    self.connection_pool.put_nowait(conn)
                except:
                    pass
        
        if dead_connections:
            print(f"정리 완료: {len(dead_connections)}개 연결 제거")
            
        self.stats['last_cleanup'] = datetime.now()
    
    def get_pool_status(self):
        """연결 풀 상태 반환"""
        return {
            'pool_name': self.pool_name,
            'driver': self.driver,
            'total_connections': len(self.active_connections),
            'available_connections': self.connection_pool.qsize(),
            'active_connections': self.stats['connections_active'],
            'created_total': self.stats['connections_created'],
            'errors_total': self.stats['connections_errors'],
            'last_cleanup': self.stats['last_cleanup'].strftime('%Y-%m-%d %H:%M:%S'),
            'config': {
                'min_connections': self.min_connections,
                'max_connections': self.max_connections,
                'connection_string': self.connection_string.replace(self.password, '***')
            }
        }
    
    def close_all_connections(self):
        """모든 연결 닫기 (종료 시 호출)"""
        print("모든 데이터베이스 연결을 닫는 중...")
        
        while not self.connection_pool.empty():
            try:
                conn = self.connection_pool.get_nowait()
                conn.close()
            except:
                pass
        
        print("✅ 모든 연결이 닫혔습니다")

# 전역 연결 풀 인스턴스
db_pools = {}

def initialize_connection_pool(pool_name="default"):
    """연결 풀 초기화"""
    global db_pools
    host = os.getenv("MSSQL_HOST", "127.0.0.1")
    port = os.getenv("MSSQL_PORT", "1433")
    username = os.getenv("MSSQL_USERNAME")
    password = os.getenv("MSSQL_PASSWORD")
    database = os.getenv("MSSQL_DATABASE")
    if pool_name == "secondary":
        database = os.getenv("MSSQL_SECONDARY_DATABASE")
    try:
        db_pools[pool_name] = DatabaseConnectionPool(
            pool_name=pool_name,
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            min_connections=10,
            max_connections=30
        )
        return True
    except Exception as e:
        print(f"연결 풀 초기화 실패: {e}")
        return False

def get_pool(pool_name="default"):
    """연결 풀 인스턴스 반환"""
    global db_pools
    if pool_name not in db_pools:
        initialize_connection_pool(pool_name)
    return db_pools[pool_name]

# 편의 함수들 (database.py 호환성)
@contextmanager
def get_db_connection(pool_name="default", charset=None):
    """데이터베이스 연결 컨텍스트 매니저 (기본)"""
    pool = get_pool(pool_name)
    if pool:
        with pool.get_db_connection() as conn:
            if charset:
                try:
                    if charset == 'EUC-KR' or charset == 'euckr':
                        conn.execute("SET NAMES 'Korean'")
                    elif charset == 'UTF-8' or charset == 'utf8':
                        conn.execute("SET NAMES 'UTF8'")
                    conn.commit()
                except:
                    # 실패해도 계속 진행
                    pass
            yield conn
    else:
        raise Exception("연결 풀이 초기화되지 않았습니다")

# 기존 pymssql 함수명과의 호환성을 위한 별명
@contextmanager  
def get_pymssql_connection():
    """pymssql 호환성을 위한 별명 (실제로는 pyodbc)"""
    with get_db_connection() as conn:
        yield conn
