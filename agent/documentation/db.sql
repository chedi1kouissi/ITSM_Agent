-- =====================================================
-- 1. INCIDENTS TABLE (Core Entity)
-- =====================================================
CREATE TABLE incidents (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) UNIQUE NOT NULL,
    app_id VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    -- Status: OPEN, ANALYZING, PENDING_APPROVAL, APPROVED, REJECTED, RESOLVED, CLOSED
    
    -- Root Cause Analysis
    root_cause TEXT,
    severity VARCHAR(20), -- CRITICAL, HIGH, MEDIUM, LOW
    
    -- Risk Assessment
    risk_score INTEGER CHECK (risk_score >= 0 AND risk_score <= 100),
    requires_human_approval BOOLEAN DEFAULT FALSE,
    
    -- Recovery Plan
    recovery_plan TEXT,
    rollback_plan TEXT,
    estimated_fix_duration_minutes INTEGER,
    
    -- Agent Metadata
    agent_notes TEXT,
    confidence_score FLOAT, -- How confident the agent is in its analysis (0.0-1.0)
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    detected_at TIMESTAMP WITH TIME ZONE, -- When the incident actually occurred
    resolved_at TIMESTAMP WITH TIME ZONE,
    
    -- Human Interaction
    approved_by VARCHAR(100),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    
    -- Indexes
    INDEX idx_incident_status (status),
    INDEX idx_incident_app_id (app_id),
    INDEX idx_incident_created_at (created_at),
    INDEX idx_incident_severity (severity)
);

-- =====================================================
-- 2. EVIDENCE TABLE (Structured Log Lines)
-- =====================================================
CREATE TABLE evidence (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    
    -- Log Details
    log_line TEXT NOT NULL,
    source VARCHAR(20) NOT NULL, -- app, db, infra, monitoring
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    
    -- Agent Reasoning
    reasoning TEXT NOT NULL, -- Why this log is relevant
    relevance_score FLOAT, -- 0.0-1.0, how critical this evidence is
    
    -- Categorization
    log_level VARCHAR(10), -- INFO, WARN, ERROR, CRITICAL
    category VARCHAR(50), -- connection_pool, memory, latency, timeout, etc.
    
    -- Ordering
    sequence_order INTEGER, -- Order in the causal chain
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    INDEX idx_evidence_incident (incident_id),
    INDEX idx_evidence_timestamp (timestamp),
    INDEX idx_evidence_source (source)
);

-- =====================================================
-- 3. RECOVERY_STEPS TABLE (Actionable Remediation)
-- =====================================================
CREATE TABLE recovery_steps (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    
    step_order INTEGER NOT NULL,
    step_description TEXT NOT NULL,
    step_type VARCHAR(30), -- restart, scale, optimize_query, clear_cache, rollback
    
    -- Execution Tracking
    status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED
    executed_at TIMESTAMP WITH TIME ZONE,
    execution_result TEXT,
    
    -- Risk per step
    risk_level VARCHAR(20), -- HIGH, MEDIUM, LOW
    requires_approval BOOLEAN DEFAULT FALSE,
    
    -- Automation
    is_automated BOOLEAN DEFAULT FALSE,
    automation_script TEXT, -- Shell script or API call
    
    INDEX idx_recovery_incident (incident_id),
    INDEX idx_recovery_order (incident_id, step_order)
);

-- =====================================================
-- 4. RAW_LOGS TABLE (Archive Original Data)
-- =====================================================
CREATE TABLE raw_logs (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    
    app_logs TEXT,
    database_logs TEXT,
    infrastructure_logs TEXT,
    monitoring_logs TEXT,
    
    -- Additional log sources
    security_logs TEXT,
    network_logs TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    INDEX idx_rawlogs_incident (incident_id)
);

-- =====================================================
-- 5. SERVICES TABLE (Service Registry)
-- =====================================================
CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    service_name VARCHAR(100) UNIQUE NOT NULL,
    app_id VARCHAR(50) UNIQUE NOT NULL,
    
    -- Service Metadata
    service_type VARCHAR(50), -- api, database, cache, queue, etc.
    criticality VARCHAR(20), -- CRITICAL, HIGH, MEDIUM, LOW
    team_owner VARCHAR(100),
    
    -- SLO Thresholds
    max_latency_ms INTEGER,
    max_error_rate_percent FLOAT,
    max_cpu_percent INTEGER,
    max_memory_percent INTEGER,
    
    -- Connection Pool Settings
    db_max_connections INTEGER,
    db_connection_timeout_sec INTEGER,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- 6. INCIDENT_METRICS TABLE (Performance Data)
-- =====================================================
CREATE TABLE incident_metrics (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    
    -- Service Impact
    affected_users_count INTEGER,
    affected_requests_count INTEGER,
    revenue_impact_usd DECIMAL(10, 2),
    
    -- Performance Degradation
    avg_latency_ms INTEGER,
    peak_latency_ms INTEGER,
    error_rate_percent FLOAT,
    
    -- Resource Usage
    cpu_usage_percent FLOAT,
    memory_usage_percent FLOAT,
    db_connection_usage_percent FLOAT,
    
    -- Time Metrics
    detection_time_seconds INTEGER, -- Time to detect the issue
    resolution_time_seconds INTEGER, -- Time to resolve
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =====================================================
-- 7. SIMILAR_INCIDENTS TABLE (Pattern Matching)
-- =====================================================
CREATE TABLE similar_incidents (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    similar_incident_id VARCHAR(50) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    
    similarity_score FLOAT NOT NULL, -- 0.0-1.0
    matching_criteria JSONB, -- What made them similar (error types, services, etc.)
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    INDEX idx_similar_incident (incident_id),
    CONSTRAINT unique_similar_pair UNIQUE (incident_id, similar_incident_id)
);

-- =====================================================
-- 8. AGENT_ACTIONS TABLE (Audit Trail)
-- =====================================================
CREATE TABLE agent_actions (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) REFERENCES incidents(incident_id) ON DELETE SET NULL,
    
    action_type VARCHAR(50) NOT NULL, -- save_evidence, calculate_risk, create_ticket, query_similar
    tool_name VARCHAR(50) NOT NULL,
    input_params JSONB,
    output_result JSONB,
    
    execution_time_ms INTEGER,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    INDEX idx_action_incident (incident_id),
    INDEX idx_action_type (action_type),
    INDEX idx_action_created (created_at)
);

-- =====================================================
-- 9. KNOWLEDGE_BASE TABLE (Learned Solutions)
-- =====================================================
CREATE TABLE knowledge_base (
    id SERIAL PRIMARY KEY,
    
    -- Problem Pattern
    error_pattern VARCHAR(200) NOT NULL,
    symptom_keywords TEXT[], -- Array of keywords to match
    affected_services VARCHAR(100)[],
    
    -- Solution
    recommended_solution TEXT NOT NULL,
    success_rate FLOAT, -- 0.0-1.0
    avg_resolution_time_minutes INTEGER,
    
    -- Metadata
    created_from_incident_id VARCHAR(50),
    times_used INTEGER DEFAULT 0,
    last_used_at TIMESTAMP WITH TIME ZONE,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    INDEX idx_kb_error_pattern (error_pattern),
    INDEX idx_kb_keywords USING GIN (symptom_keywords)
);

-- =====================================================
-- 10. HUMAN_FEEDBACK TABLE (Learning Loop)
-- =====================================================
CREATE TABLE human_feedback (
    id SERIAL PRIMARY KEY,
    incident_id VARCHAR(50) NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    
    feedback_type VARCHAR(30) NOT NULL, -- APPROVE, REJECT, MODIFY, COMMENT
    feedback_text TEXT,
    
    -- What was modified
    original_recovery_plan TEXT,
    modified_recovery_plan TEXT,
    
    -- Rating
    agent_accuracy_rating INTEGER CHECK (agent_accuracy_rating >= 1 AND agent_accuracy_rating <= 5),
    
    provided_by VARCHAR(100) NOT NULL,
    provided_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    INDEX idx_feedback_incident (incident_id)
);

-- =====================================================
-- TRIGGERS
-- =====================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_incidents_updated_at BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_services_updated_at BEFORE UPDATE ON services
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();