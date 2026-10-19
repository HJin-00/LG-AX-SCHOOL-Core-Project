"""이전 import 호환용. 실제 MySQL 코드는 database/mysql.py에 있습니다."""
from .database.mysql import connection, transaction, Transaction
