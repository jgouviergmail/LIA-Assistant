-- Initialize PostgreSQL database for LIA
-- This script runs automatically when the container is first created

-- Create pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create uuid extension for UUID support
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create pg_trgm extension for text search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Set default encoding
SET client_encoding = 'UTF8';

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'LIA database initialized successfully';
    RAISE NOTICE 'Extensions installed: vector, uuid-ossp, pg_trgm';
END$$;
