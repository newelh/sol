#!/bin/bash
set -e

# Create the S3 bucket
echo "Creating S3 bucket..."
mc config host add minio http://localhost:9000 minioadmin minioadmin
mc mb minio/pypi || echo "Bucket already exists"

# Set up the initial database
echo "Setting up PostgreSQL database..."
PGPASSWORD=postgres psql -h localhost -U postgres -c "CREATE DATABASE pypi;" || echo "Database already exists"

# Create necessary tables
echo "Creating database tables..."
PGPASSWORD=postgres psql -h localhost -U postgres -d pypi -c "
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    normalized_name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS releases (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    version TEXT NOT NULL,
    requires_python TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    release_id INTEGER NOT NULL REFERENCES releases(id),
    filename TEXT NOT NULL,
    size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    md5 TEXT,
    upload_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    uploaded_by TEXT,
    content_type TEXT,
    is_yanked BOOLEAN DEFAULT FALSE,
    yank_reason TEXT,
    has_signature BOOLEAN DEFAULT FALSE,
    has_metadata BOOLEAN DEFAULT FALSE,
    metadata_sha256 TEXT,
    UNIQUE(release_id, filename)
);

CREATE INDEX IF NOT EXISTS idx_projects_normalized_name ON projects(normalized_name);
CREATE INDEX IF NOT EXISTS idx_releases_project_id ON releases(project_id);
CREATE INDEX IF NOT EXISTS idx_files_release_id ON files(release_id);
"

echo "Setup complete!"
