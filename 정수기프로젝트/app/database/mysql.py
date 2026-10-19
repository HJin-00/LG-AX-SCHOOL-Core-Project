"""동의 저장소의 SQL 실행·트랜잭션 경계. 값은 항상 바인딩합니다."""
import os
from contextlib import contextmanager
import pymysql


def connection():
    database = os.environ.get('MYSQL_DATABASE', '')
    if not database:
        raise RuntimeError('MYSQL_DATABASE 설정이 필요합니다.')
    return pymysql.connect(host=os.environ.get('MYSQL_HOST', '127.0.0.1'),
                           port=int(os.environ.get('MYSQL_PORT', '3306')),
                           user=os.environ.get('MYSQL_USER', 'root'),
                           password=os.environ.get('MYSQL_PASSWORD', ''),
                           database=database, charset='utf8mb4', autocommit=False,
                           connect_timeout=5, read_timeout=10, write_timeout=10)


class Transaction:
    def __init__(self, db):
        self.db = db

    def execute(self, sql, values=()):
        cursor = self.db.cursor()
        cursor.execute(sql.replace('?', '%s'), values)
        return cursor


@contextmanager
def transaction():
    db = connection()
    try:
        yield Transaction(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
