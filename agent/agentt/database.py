import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except psycopg2.Error as e:
        print(f"❌ Connection Error: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        # 1. Incidents Table (Added app_id)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id SERIAL PRIMARY KEY,
                app_id VARCHAR(50), 
                incident_id VARCHAR(50) UNIQUE NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
                risk_score INTEGER,
                recovery_plan TEXT,
                agent_notes TEXT,
                generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        # 2. Evidence Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS evidence (
                id SERIAL PRIMARY KEY,
                incident_id VARCHAR(50) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
                log_line TEXT NOT NULL,
                source VARCHAR(20),
                timestamp TIMESTAMP WITH TIME ZONE,
                reasoning TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
        # 3. Recovery Steps Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS recovery_steps (
                id SERIAL PRIMARY KEY,
                incident_id VARCHAR(50) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
                step_order INTEGER NOT NULL,
                step_description TEXT NOT NULL,
                risk_level VARCHAR(20),
                status VARCHAR(20) DEFAULT 'PENDING',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)
       
        conn.commit()
        print("✅ Database initialized successfully with app_id support.")
    except Exception as e:
        print(f"❌ Init Error: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    init_db()