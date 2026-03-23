// =============================================================================
// ITSM Agent — Neo4j Knowledge Graph Seed Script
// =============================================================================
// Run this in Neo4j Browser or via cypher-shell.
// All nodes are MERGE'd individually before relationships are created.
// This prevents duplicate nodes on re-seeding.
// =============================================================================

// ── CLEANUP (optional, uncomment to wipe and re-seed from scratch) ────────────
// MATCH (n) DETACH DELETE n;


// =============================================================================
// 1. APPLICATIONS
// =============================================================================

MERGE (app_ecom:Application {id: "ecommerce-prod"})
SET app_ecom.name       = "E-Commerce Platform",
    app_ecom.tier       = "Tier-1",
    app_ecom.owner_team = "platform-eng",
    app_ecom.region     = "eu-west-1";

MERGE (app_admin:Application {id: "admin-portal"})
SET app_admin.name       = "Internal Admin Portal",
    app_admin.tier       = "Tier-3",
    app_admin.owner_team = "internal-tools",
    app_admin.region     = "eu-west-1";

MERGE (app_notify:Application {id: "notification-svc"})
SET app_notify.name       = "Notification Service",
    app_notify.tier       = "Tier-2",
    app_notify.owner_team = "comms-eng",
    app_notify.region     = "eu-west-1";


// =============================================================================
// 2. SERVICES
// =============================================================================

// ── ecommerce-prod services ───────────────────────────────────────────────────

MERGE (s_frontend:Service {id: "web-frontend"})
SET s_frontend.name               = "Web Frontend",
    s_frontend.lang               = "React/Next.js",
    s_frontend.port               = 3000,
    s_frontend.host               = "k8s-prod-cluster",
    s_frontend.replica_count      = 4,
    s_frontend.criticality        = "P1",
    s_frontend.owner_team         = "frontend-eng",
    s_frontend.slo_latency_ms     = 500,
    s_frontend.slo_error_rate_pct = 2.0;

MERGE (s_pay:Service {id: "payment-api"})
SET s_pay.name               = "Payment API",
    s_pay.lang               = "Python/FastAPI",
    s_pay.port               = 8000,
    s_pay.host               = "k8s-prod-cluster",
    s_pay.replica_count      = 3,
    s_pay.criticality        = "P0",
    s_pay.owner_team         = "payments-team",
    s_pay.slo_latency_ms     = 300,
    s_pay.slo_error_rate_pct = 1.0;

MERGE (s_catalog:Service {id: "catalog-api"})
SET s_catalog.name               = "Product Catalog API",
    s_catalog.lang               = "Node.js/Express",
    s_catalog.port               = 4000,
    s_catalog.host               = "k8s-prod-cluster",
    s_catalog.replica_count      = 2,
    s_catalog.criticality        = "P1",
    s_catalog.owner_team         = "catalog-team",
    s_catalog.slo_latency_ms     = 200,
    s_catalog.slo_error_rate_pct = 2.0;

// ── admin-portal services ─────────────────────────────────────────────────────

MERGE (s_admin:Service {id: "admin-service"})
SET s_admin.name               = "Admin Backend",
    s_admin.lang               = "Python/Django",
    s_admin.port               = 8080,
    s_admin.host               = "k8s-internal-cluster",
    s_admin.replica_count      = 1,
    s_admin.criticality        = "P2",
    s_admin.owner_team         = "internal-tools",
    s_admin.slo_latency_ms     = 1000,
    s_admin.slo_error_rate_pct = 5.0;

MERGE (s_report:Service {id: "reporting-api"})
SET s_report.name               = "Reporting API",
    s_report.lang               = "Python/FastAPI",
    s_report.port               = 8001,
    s_report.host               = "k8s-internal-cluster",
    s_report.replica_count      = 1,
    s_report.criticality        = "P2",
    s_report.owner_team         = "internal-tools",
    s_report.slo_latency_ms     = 2000,
    s_report.slo_error_rate_pct = 10.0;

// ── notification-svc services ─────────────────────────────────────────────────

MERGE (s_mailer:Service {id: "mailer-service"})
SET s_mailer.name               = "Email Mailer",
    s_mailer.lang               = "Go",
    s_mailer.port               = 5000,
    s_mailer.host               = "k8s-prod-cluster",
    s_mailer.replica_count      = 2,
    s_mailer.criticality        = "P1",
    s_mailer.owner_team         = "comms-eng",
    s_mailer.slo_latency_ms     = 800,
    s_mailer.slo_error_rate_pct = 3.0;

MERGE (s_sms:Service {id: "sms-gateway"})
SET s_sms.name               = "SMS Gateway",
    s_sms.lang               = "Go",
    s_sms.port               = 5001,
    s_sms.host               = "k8s-prod-cluster",
    s_sms.replica_count      = 2,
    s_sms.criticality        = "P1",
    s_sms.owner_team         = "comms-eng",
    s_sms.slo_latency_ms     = 1000,
    s_sms.slo_error_rate_pct = 3.0;


// =============================================================================
// 3. DATABASES
// =============================================================================

MERGE (db_payments:Database {id: "payment-db"})
SET db_payments.name        = "Payments PostgreSQL",
    db_payments.type        = "PostgreSQL",
    db_payments.version     = "15.2",
    db_payments.host        = "postgres-cluster-prod",
    db_payments.port        = 5432,
    db_payments.max_conn    = 150,
    db_payments.criticality = "P0",
    db_payments.owner_team  = "data-eng";

MERGE (db_catalog:Database {id: "catalog-db"})
SET db_catalog.name        = "Catalog MongoDB",
    db_catalog.type        = "MongoDB",
    db_catalog.version     = "6.0",
    db_catalog.host        = "mongo-cluster-prod",
    db_catalog.port        = 27017,
    db_catalog.max_conn    = 200,
    db_catalog.criticality = "P1",
    db_catalog.owner_team  = "data-eng";

// Shared DB — used by both admin-portal AND ecommerce-prod (cross-app blast radius)
MERGE (db_shared:Database {id: "shared-analytics-db"})
SET db_shared.name        = "Shared Analytics PostgreSQL",
    db_shared.type        = "PostgreSQL",
    db_shared.version     = "15.2",
    db_shared.host        = "postgres-cluster-prod",
    db_shared.port        = 5433,
    db_shared.max_conn    = 100,
    db_shared.criticality = "P1",
    db_shared.owner_team  = "data-eng";


// =============================================================================
// 4. INFRASTRUCTURE
// =============================================================================

MERGE (gw_prod:Infrastructure {id: "api-gateway-prod"})
SET gw_prod.name        = "Production API Gateway",
    gw_prod.type        = "Gateway",
    gw_prod.host        = "nginx-prod-01",
    gw_prod.timeout_ms  = 30000,
    gw_prod.criticality = "P0",
    gw_prod.owner_team  = "platform-eng";

MERGE (gw_internal:Infrastructure {id: "api-gateway-internal"})
SET gw_internal.name        = "Internal API Gateway",
    gw_internal.type        = "Gateway",
    gw_internal.host        = "nginx-internal-01",
    gw_internal.timeout_ms  = 60000,
    gw_internal.criticality = "P2",
    gw_internal.owner_team  = "platform-eng";

MERGE (cache_redis:Infrastructure {id: "redis-cache"})
SET cache_redis.name        = "Shared Redis Cache",
    cache_redis.type        = "Cache",
    cache_redis.host        = "redis-cluster-prod",
    cache_redis.port        = 6379,
    cache_redis.criticality = "P1",
    cache_redis.owner_team  = "platform-eng";

MERGE (queue_rabbit:Infrastructure {id: "rabbitmq-prod"})
SET queue_rabbit.name        = "RabbitMQ Message Broker",
    queue_rabbit.type        = "MessageQueue",
    queue_rabbit.host        = "rabbitmq-prod-01",
    queue_rabbit.port        = 5672,
    queue_rabbit.criticality = "P1",
    queue_rabbit.owner_team  = "platform-eng";


// =============================================================================
// 5. APP → SERVICE MEMBERSHIP
// =============================================================================

MATCH (a:Application {id: "ecommerce-prod"}), (s:Service {id: "web-frontend"})
MERGE (a)-[:CONTAINS]->(s);

MATCH (a:Application {id: "ecommerce-prod"}), (s:Service {id: "payment-api"})
MERGE (a)-[:CONTAINS]->(s);

MATCH (a:Application {id: "ecommerce-prod"}), (s:Service {id: "catalog-api"})
MERGE (a)-[:CONTAINS]->(s);

MATCH (a:Application {id: "admin-portal"}), (s:Service {id: "admin-service"})
MERGE (a)-[:CONTAINS]->(s);

MATCH (a:Application {id: "admin-portal"}), (s:Service {id: "reporting-api"})
MERGE (a)-[:CONTAINS]->(s);

MATCH (a:Application {id: "notification-svc"}), (s:Service {id: "mailer-service"})
MERGE (a)-[:CONTAINS]->(s);

MATCH (a:Application {id: "notification-svc"}), (s:Service {id: "sms-gateway"})
MERGE (a)-[:CONTAINS]->(s);


// =============================================================================
// 6. SERVICE DEPENDENCY RELATIONSHIPS (with edge properties)
// =============================================================================

// web-frontend calls payment-api and catalog-api
MATCH (s:Service {id: "web-frontend"}), (t:Service {id: "payment-api"})
MERGE (s)-[r:CALLS]->(t)
SET r.protocol = "HTTP/REST", r.latency_slo_ms = 300, r.timeout_ms = 5000;

MATCH (s:Service {id: "web-frontend"}), (t:Service {id: "catalog-api"})
MERGE (s)-[r:CALLS]->(t)
SET r.protocol = "HTTP/REST", r.latency_slo_ms = 200, r.timeout_ms = 3000;

// payment-api → payment-db
MATCH (s:Service {id: "payment-api"}), (d:Database {id: "payment-db"})
MERGE (s)-[r:WRITES_TO]->(d)
SET r.pool_size = 20, r.latency_slo_ms = 50, r.orm = "SQLAlchemy";

MATCH (s:Service {id: "payment-api"}), (d:Database {id: "payment-db"})
MERGE (s)-[r:READS_FROM]->(d)
SET r.pool_size = 20, r.latency_slo_ms = 50;

// payment-api → redis cache (session/idempotency keys)
MATCH (s:Service {id: "payment-api"}), (i:Infrastructure {id: "redis-cache"})
MERGE (s)-[r:READS_FROM]->(i)
SET r.use_case = "idempotency-keys", r.latency_slo_ms = 5;

// catalog-api → catalog-db
MATCH (s:Service {id: "catalog-api"}), (d:Database {id: "catalog-db"})
MERGE (s)-[r:READS_FROM]->(d)
SET r.pool_size = 30, r.latency_slo_ms = 30;

MATCH (s:Service {id: "catalog-api"}), (d:Database {id: "catalog-db"})
MERGE (s)-[r:WRITES_TO]->(d)
SET r.pool_size = 30, r.latency_slo_ms = 50;

// catalog-api → redis cache (product cache)
MATCH (s:Service {id: "catalog-api"}), (i:Infrastructure {id: "redis-cache"})
MERGE (s)-[r:READS_FROM]->(i)
SET r.use_case = "product-cache", r.ttl_seconds = 300;

// payment-api → analytics (cross-app shared db write)
MATCH (s:Service {id: "payment-api"}), (d:Database {id: "shared-analytics-db"})
MERGE (s)-[r:WRITES_TO]->(d)
SET r.pool_size = 5, r.latency_slo_ms = 200, r.use_case = "transaction-events";

// admin-service → shared analytics (blast radius: cross-app link)
MATCH (s:Service {id: "admin-service"}), (d:Database {id: "shared-analytics-db"})
MERGE (s)-[r:READS_FROM]->(d)
SET r.pool_size = 3, r.latency_slo_ms = 500, r.use_case = "report-queries";

// reporting-api → shared analytics
MATCH (s:Service {id: "reporting-api"}), (d:Database {id: "shared-analytics-db"})
MERGE (s)-[r:READS_FROM]->(d)
SET r.pool_size = 2, r.latency_slo_ms = 2000, r.use_case = "heavy-reports";

// mailer-service → rabbitmq
MATCH (s:Service {id: "mailer-service"}), (i:Infrastructure {id: "rabbitmq-prod"})
MERGE (s)-[r:READS_FROM]->(i)
SET r.use_case = "email-queue", r.prefetch_count = 10;

// sms-gateway → rabbitmq
MATCH (s:Service {id: "sms-gateway"}), (i:Infrastructure {id: "rabbitmq-prod"})
MERGE (s)-[r:READS_FROM]->(i)
SET r.use_case = "sms-queue", r.prefetch_count = 5;

// payment-api triggers notifications (publishes to queue)
MATCH (s:Service {id: "payment-api"}), (i:Infrastructure {id: "rabbitmq-prod"})
MERGE (s)-[r:WRITES_TO]->(i)
SET r.use_case = "payment-events", r.routing_key = "payment.completed";


// =============================================================================
// 7. INFRASTRUCTURE → SERVICE ROUTING
// =============================================================================

MATCH (gw:Infrastructure {id: "api-gateway-prod"}), (s:Service {id: "web-frontend"})
MERGE (gw)-[r:ROUTES_TO]->(s)
SET r.protocol = "HTTPS", r.timeout_ms = 30000;

MATCH (gw:Infrastructure {id: "api-gateway-prod"}), (s:Service {id: "payment-api"})
MERGE (gw)-[r:ROUTES_TO]->(s)
SET r.protocol = "HTTPS", r.timeout_ms = 30000, r.path_prefix = "/api/payments";

MATCH (gw:Infrastructure {id: "api-gateway-internal"}), (s:Service {id: "admin-service"})
MERGE (gw)-[r:ROUTES_TO]->(s)
SET r.protocol = "HTTP", r.timeout_ms = 60000;

MATCH (gw:Infrastructure {id: "api-gateway-internal"}), (s:Service {id: "reporting-api"})
MERGE (gw)-[r:ROUTES_TO]->(s)
SET r.protocol = "HTTP", r.timeout_ms = 120000, r.path_prefix = "/reports";
