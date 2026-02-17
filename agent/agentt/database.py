import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to database: {e}")
        return None

def init_db():
    """Initializes the database with the required tables."""
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to DB, cannot initialize.")
        return

    try:
        cur = conn.cursor()

        # 1. Incidents Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id SERIAL PRIMARY KEY,
                incident_id VARCHAR(50) UNIQUE NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
                risk_score INTEGER,
                recovery_plan TEXT,
                agent_notes TEXT, -- Internal monologue/summary
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

        # 4. Agent Actions Table (Audit)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_actions (
                id SERIAL PRIMARY KEY,
                incident_id VARCHAR(50) REFERENCES incidents(incident_id) ON DELETE SET NULL,
                action_type VARCHAR(50) NOT NULL,
                input_params JSONB,
                output_result JSONB,
                agent_reasoning TEXT,
                observation TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        conn.commit()
        print("Database initialized successfully with Phase 1 tables.")

    except psycopg2.Error as e:
        print(f"Error initializing database: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    init_db()
