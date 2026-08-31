# Security Coding Standards

## SQL Injection Prevention
- Always use parameterized queries or prepared statements
- Never concatenate user input directly into SQL strings
- Use ORM query builders when available
- Validate and sanitize all input parameters

## XSS Prevention
- Escape all user-generated content before rendering in HTML
- Use templating engines with auto-escaping enabled
- Implement Content-Security-Policy (CSP) headers
- Sanitize rich text input using approved libraries

## Authentication & Authorization
- Never store passwords in plaintext; use bcrypt/argon2 hashing
- Implement proper session management with secure cookies
- Use short-lived JWT tokens with refresh token rotation
- Apply principle of least privilege for API endpoints
- Implement rate limiting on authentication endpoints

## Sensitive Data Handling
- Never log sensitive data (passwords, tokens, credit card numbers)
- Mask sensitive fields in API responses (show last 4 digits only)
- Use HTTPS for all data in transit
- Encrypt sensitive data at rest using AES-256 or equivalent
- Rotate encryption keys periodically

## Secret Management
- Never hardcode API keys, passwords, or tokens in source code
- Use environment variables or secret management services
- Add .env files to .gitignore
- Scan commits for accidentally committed secrets

## Input Validation
- Validate all input on the server side (never trust client validation)
- Use allowlists over blocklists for input validation
- Validate file uploads: check type, size, and content
- Implement request size limits to prevent DoS

## CSRF Protection
- Use anti-CSRF tokens for state-changing operations
- Implement SameSite cookie attribute
- Verify Origin and Referer headers for sensitive requests

## Dependency Security
- Regularly update dependencies to patch known vulnerabilities
- Use dependency scanning tools (e.g., safety, snyk)
- Pin dependency versions in requirements files
- Review changelogs before upgrading major versions
