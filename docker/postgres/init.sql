-- ============================================
-- FrigoCore - PostgreSQL Initialization
-- Executed on first container start
-- ============================================

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Set default configuration
ALTER DATABASE frigocore SET timezone TO 'UTC';

-- ------------------------------------------
-- Schema placeholder
-- Tables will be created by Alembic migrations
-- ------------------------------------------