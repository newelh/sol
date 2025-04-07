# Rate Limiting

The Sol PyPI Index Server implements rate limiting to protect the API from abuse and ensure fair usage. This document explains how rate limiting works and how to configure it.

## Overview

Rate limiting is implemented using a token bucket algorithm, which allows for:
- Different limits for authenticated and unauthenticated users
- Different costs for different endpoints
- Bursting capability for temporary spikes in traffic

## Default Configuration

By default, the rate limiting is configured as follows:

- **Anonymous Users**:
  - 30 requests per second
  - Maximum burst capacity of 50 tokens

- **Authenticated Users**:
  - 60 requests per second
  - Maximum burst capacity of 100 tokens

- **Endpoint Costs**:
  - File downloads: 2 tokens per request
  - Upload operations: 5 tokens per request
  - Standard endpoints: 1 token per request

- **Exempt Paths**:
  - `/health`
  - `/docs`
  - `/redoc`
  - `/openapi.json`

## Response Headers

The rate limiter adds the following headers to responses:

- `X-RateLimit-Limit`: The maximum number of tokens available
- `X-RateLimit-Remaining`: The number of tokens remaining
- `X-RateLimit-Reset`: The estimated time (in seconds since epoch) when the rate limit will reset

## Configuration Options

Rate limiting can be configured using environment variables:

```bash
# Anonymous user limits
SERVER_RATE_LIMIT_ANON=30.0
SERVER_RATE_LIMIT_ANON_CAPACITY=50

# Authenticated user limits
SERVER_RATE_LIMIT_AUTH=60.0
SERVER_RATE_LIMIT_AUTH_CAPACITY=100
```

## Handling Rate Limit Exceeded

When rate limits are exceeded, the server returns a `429 Too Many Requests` response with a JSON body:

```json
{
  "detail": "Too many requests. Please try again later."
}
```

Clients should implement appropriate backoff strategies when receiving a 429 response.

## Client Best Practices

To make the most efficient use of rate limits:

1. **Authenticate** when possible to get higher rate limits
2. **Cache responses** when appropriate
3. **Implement exponential backoff** when rate limits are exceeded
4. **Batch operations** when possible instead of making many small requests

## Monitoring

Rate limiting events are logged at the WARNING level with details about the client identifier. Administrators can monitor these logs to identify potential abuse patterns.
