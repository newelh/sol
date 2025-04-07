# Sol - PEP-compliant PyPI Index Server

Sol is a Python Package Index server that implements the PyPI API specifications as defined in various PEPs, including:
- PEP 503 (Simple Repository API)
- PEP 592 (Yanked Release Support)
- PEP 629 (API Version)
- PEP 658 (Serve Package Metadata in the Simple Repository API)
- PEP 691 (JSON-based Simple API for Python Package Indexes)
- PEP 700 (Additional Project Metadata in the Simple Repository API)
- PEP 714 (Rename Distribution Metadata)
- PEP 740 (Provenance Metadata)

## Features

- Simple Repository API (HTML and JSON formats)
- Package file serving with metadata
- Content negotiation (HTML or JSON)
- Caching for improved performance
- Package upload support
- Authentication and authorization
- Package search functionality

## Architecture

The application is built using:
- FastAPI - Web framework
- PostgreSQL - Database for package metadata
- S3-compatible storage (MinIO) - Package file storage
- Valkey (Redis) - Caching

## Development

### Prerequisites

- Docker and Docker Compose
- Python 3.13
- uv (Python package manager)

### Setting up the development environment

1. Clone the repository:
   ```
   git clone <repository-url>
   cd sol
   ```

2. Start the backing services (PostgreSQL, MinIO, Valkey):
   ```
   cd infra
   docker-compose up -d postgres minio valkey
   ```

3. Set up the initial database and S3 bucket:
   ```
   cd ../backend
   ./scripts/setup.sh
   ```

4. Install dependencies:
   ```
   uv pip install -e .
   ```

5. Run the development server:
   ```
   ./scripts/dev.sh
   ```

The API will be available at `http://localhost:8000`.

### Running with Docker Compose

To run the entire application stack with Docker Compose:

```
cd infra
docker-compose up -d
```

## API Endpoints

### Simple Repository API

- `GET /simple/` - Lists all available packages
- `GET /simple/{package_name}/` - Shows all versions of a package

### Package Files

- `GET /files/{file_path}` - Download a package file
- `GET /files/{file_path}.metadata` - Get package metadata
- `GET /files/{file_path}.asc` - Get package signature
- `GET /files/{file_path}/info` - Get file information

### PyPI-compatible JSON API

- `GET /pypi/{package_name}/json` - Get package information in JSON format

### Search API

- `GET /search?q={query}` - Search for packages by name or description
- `GET /search/advanced?name={name}&description={desc}...` - Advanced search with multiple criteria

### Legacy Upload API

- `POST /legacy/` - Upload packages (compatible with twine and other tools)

### Health and Metrics

- `GET /health` - Server health check
- `GET /metrics` - Server metrics (Prometheus format)

## Using Sol with pip

### Configure pip to use Sol

Create or edit `~/.pip/pip.conf` (Linux/macOS) or `%APPDATA%\pip\pip.ini` (Windows):

```ini
[global]
index-url = http://localhost:8000/simple/
trusted-host = localhost
```

### With credentials

For authenticated access:

```ini
[global]
index-url = http://testuser:testpassword@localhost:8000/simple/
trusted-host = localhost
```

### Using with pip

```bash
pip install some-package
```

## Uploading Packages

### Using twine

```bash
twine upload --repository-url http://localhost:8000/legacy/ dist/*
```

With credentials:

```bash
twine upload -u testuser -p testpassword --repository-url http://localhost:8000/legacy/ dist/*
```

## Testing

### Running Integration Tests

```bash
./test_integration.sh
```

### Configuration Check

```bash
./check_config.py
```

## Configuration

The application can be configured using environment variables. See `app/core/config.py` for all available options.
