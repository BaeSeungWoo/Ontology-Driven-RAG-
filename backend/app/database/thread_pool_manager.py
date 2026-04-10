# -*- coding: utf-8 -*-
"""
스레드 풀 관리 모듈
데이터베이스 작업을 병렬로 처리하기 위한 스레드 풀
"""

import concurrent.futures
import threading
from functools import wraps
from typing import List, Tuple, Any, Callable
import time

class ThreadPoolManager:
    """스레드 풀 관리 클래스"""
    
    def __init__(self, max_workers=10, pool_name="default"):
        self.max_workers = max_workers
        self.pool_name = pool_name
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"{pool_name}_worker"
        )
        self.active_tasks = set()
        self.completed_tasks = 0
        self.failed_tasks = 0
        
        print(f"스레드 풀 '{pool_name}' 초기화 완료 (최대 {max_workers}개 워커)")
    
    def submit_task(self, func: Callable, *args, **kwargs) -> concurrent.futures.Future:
        """작업을 스레드 풀에 제출"""
        future = self.thread_pool.submit(func, *args, **kwargs)
        self.active_tasks.add(future)
        
        # 완료 콜백 등록
        future.add_done_callback(self._task_completed_callback)
        
        return future
    
    def _task_completed_callback(self, future: concurrent.futures.Future):
        """작업 완료 시 호출되는 콜백"""
        self.active_tasks.discard(future)
        # print(f"스레드 풀 작업 완료: {future}")
        
        try:
            future.result()  # 예외가 있다면 여기서 발생
            self.completed_tasks += 1
        except Exception as e:
            self.failed_tasks += 1
            # print(f"❌ 스레드 풀 작업 실패: {e}")
    
    def execute_parallel(self, operations: List[Tuple[Callable, tuple, dict]]) -> List[Any]:
        """
        여러 작업을 병렬로 실행
        
        Args:
            operations: [(function, args, kwargs), ...] 형태의 작업 리스트
        
        Returns:
            결과 리스트 (순서 보장)
        """
        futures = []
        
        # 모든 작업 제출
        for func, args, kwargs in operations:
            future = self.submit_task(func, *args, **kwargs)
            futures.append(future)
        
        # 결과 수집 (순서 보장)
        results = []
        for future in futures:
            try:
                result = future.result(timeout=60)  # 60초 타임아웃
                results.append(result)
            except concurrent.futures.TimeoutError:
                # print("작업 타임아웃 발생")
                results.append(None)
            except Exception as e:
                # print(f"작업 실행 실패: {e}")
                results.append(None)
        
        return results
    
    def execute_parallel_with_callback(self, operations: List[Tuple[Callable, tuple, dict]], 
                                     callback: Callable[[int, Any], None] = None) -> List[Any]:
        """
        콜백과 함께 병렬 실행 (진행 상황 모니터링 가능)
        """
        futures = []
        
        # 작업 제출
        for i, (func, args, kwargs) in enumerate(operations):
            future = self.submit_task(func, *args, **kwargs)
            futures.append((i, future))
        
        # 결과 수집 (완료되는 순서대로)
        results = [None] * len(operations)
        
        for i, future in futures:
            try:
                result = future.result(timeout=60)
                results[i] = result
                
                # 콜백 호출
                if callback:
                    callback(i, result)
                    
            except Exception as e:
                # print(f"작업 {i} 실행 실패: {e}")
                results[i] = None
        
        return results
    
    def get_status(self) -> dict:
        """스레드 풀 상태 반환"""
        return {
            'pool_name': self.pool_name,
            'max_workers': self.max_workers,
            'active_tasks': len(self.active_tasks),
            'completed_tasks': self.completed_tasks,
            'failed_tasks': self.failed_tasks,
            'total_tasks': self.completed_tasks + self.failed_tasks + len(self.active_tasks)
        }
    
    def shutdown(self, wait=True):
        """스레드 풀 종료"""
        # print(f"스레드 풀 '{self.pool_name}' 종료 중...")
        self.thread_pool.shutdown(wait=wait)
        # print(f"스레드 풀 '{self.pool_name}' 종료 완료")

# 전역 스레드 풀 인스턴스들
db_thread_pool = None
api_thread_pool = None

def initialize_thread_pools():
    """스레드 풀들 초기화"""
    global db_thread_pool, api_thread_pool
    
    # 데이터베이스 작업용 스레드 풀
    db_thread_pool = ThreadPoolManager(
        max_workers=15,  # 데이터베이스 연결 풀 크기에 맞춤
        pool_name="database_operations"
    )
    
    # API 작업용 스레드 풀
    api_thread_pool = ThreadPoolManager(
        max_workers=20,  # API 요청 처리용
        pool_name="api_operations"
    )
    
    return True

def get_db_thread_pool() -> ThreadPoolManager:
    """데이터베이스 작업용 스레드 풀 반환"""
    global db_thread_pool
    if db_thread_pool is None:
        initialize_thread_pools()
    return db_thread_pool

def get_api_thread_pool() -> ThreadPoolManager:
    """API 작업용 스레드 풀 반환"""
    global api_thread_pool
    if api_thread_pool is None:
        initialize_thread_pools()
    return api_thread_pool

# 편의 함수들
def execute_db_operations_parallel(operations: List[Tuple[Callable, tuple, dict]]) -> List[Any]:
    """데이터베이스 작업을 병렬로 실행"""
    pool = get_db_thread_pool()
    return pool.execute_parallel(operations)

def execute_api_operations_parallel(operations: List[Tuple[Callable, tuple, dict]]) -> List[Any]:
    """API 작업을 병렬로 실행"""
    pool = get_api_thread_pool()
    return pool.execute_parallel(operations)

# 스레드 풀 데코레이터
def with_thread_pool(pool_type="db"):
    """함수를 스레드 풀에서 실행하는 데코레이터"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if pool_type == "db":
                pool = get_db_thread_pool()
            else:
                pool = get_api_thread_pool()
            
            future = pool.submit_task(func, *args, **kwargs)
            return future.result()
        return wrapper
    return decorator
