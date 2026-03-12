-- SQL script to create a benchmark test user
-- Password: BenchmarkPassword123!
-- This script can be run with:
-- docker compose -f docker-compose.dev.yml exec postgres psql -U postgres -d lia -f /path/to/create_benchmark_user.sql

-- First, delete the user if it already exists
DELETE FROM users WHERE email = 'benchmark@example.com';

-- Insert the benchmark user with a bcrypt-hashed password
-- Password: BenchmarkPassword123!
-- Hashed using bcrypt with salt rounds = 12
INSERT INTO users (
    id,
    email,
    hashed_password,
    full_name,
    is_active,
    is_verified,
    is_superuser,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'benchmark@example.com',
    '$2b$12$QJnJ1FxAIs0eF1UWIFdS3ub/RsOr.rPfsWcYzNHSuvI2K23CWUFc.',
    'Benchmark User',
    true,  -- is_active = true (IMPORTANT!)
    true,  -- is_verified = true
    false, -- is_superuser = false
    NOW(),
    NOW()
);

-- Verify the user was created
SELECT
    id,
    email,
    full_name,
    is_active,
    is_verified,
    is_superuser,
    created_at
FROM users
WHERE email = 'benchmark@example.com';
