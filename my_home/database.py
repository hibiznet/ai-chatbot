import os
import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

# 환경변수 무시하고 가장 확실한 정보로 고정
DB_HOST = "127.0.0.1"
DB_PORT = "5433" # 포트 충돌 방지를 위해 5433 사용
DB_NAME = "hibiz"
DB_USER = "hibiznet"
DB_PASSWORD = "hibiz1234!"

# URL 생성 (드라이버 명시)
db_url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 윈도우 인코딩 문제를 완전히 피하기 위한 커스텀 연결 함수
def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        client_encoding='utf8'
    )

engine = create_engine(db_url, creator=get_conn)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()