# Testing Standards

## Test Coverage Requirements
- Minimum 80% line coverage for business logic modules
- 100% coverage for critical paths (payment, authentication)
- All public APIs must have integration tests
- All bug fixes must include regression tests

## Test Isolation
- Each test must be independent and not rely on execution order
- Use fresh test data for each test (no shared mutable state)
- Mock external dependencies (databases, APIs, file systems)
- Clean up test resources in teardown/finally blocks

## Test Naming Conventions
- Use descriptive names: test_{method}_{scenario}_{expected_result}
- Group related tests in classes or describe blocks
- Use consistent naming across the test suite

## Assertion Quality
- Each test should verify one specific behavior
- Use specific assertions (assertEqual, assertIn) over generic assertTrue
- Include meaningful assertion messages for debugging
- Test both positive and negative scenarios

## Edge Case Testing
- Test with empty inputs, null values, and boundary conditions
- Test with maximum and minimum valid values
- Test with invalid/malformed inputs
- Test concurrent access scenarios where applicable

## Test Performance
- Unit tests should complete in under 100ms each
- Integration tests should complete in under 5 seconds each
- Use test parallelization where supported
- Avoid unnecessary waits (use mocks instead of sleep)

## Test Data Management
- Use factories or fixtures for test data generation
- Never use production data in tests
- Anonymize any data derived from production
- Use deterministic test data (avoid random values without seeds)

## Mocking Guidelines
- Mock at the boundary (external services, databases)
- Do not mock the code under test
- Verify mock interactions when testing integration points
- Use dependency injection to make code testable
