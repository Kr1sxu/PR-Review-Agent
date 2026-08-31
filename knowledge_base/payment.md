# Payment Business Standards

## Transaction Safety
- All payment operations must be idempotent
- Use database transactions with proper isolation levels
- Implement distributed transaction handling for microservices
- Always verify payment amount matches the order amount

## Double Payment Prevention
- Implement idempotency keys for all payment requests
- Use optimistic locking on order status fields
- Check payment status before processing refunds
- Implement request deduplication at the API gateway level

## Amount Handling
- Use integer cents (or smallest currency unit) to avoid floating point errors
- Never use float/double for monetary calculations
- Validate amount ranges before processing
- Support multi-currency with proper decimal precision

## Payment Flow Integrity
- Verify webhook signatures before processing callbacks
- Implement retry mechanisms with exponential backoff for failed payments
- Log all payment state transitions with timestamps
- Implement reconciliation checks between internal records and payment provider

## Refund Safety
- Validate refund amount does not exceed original payment
- Check refund eligibility before initiating
- Implement partial refund tracking
- Prevent duplicate refunds using idempotency keys

## Error Handling
- Never expose internal payment details in error messages
- Implement proper timeout handling for payment gateway calls
- Use circuit breaker pattern for external payment services
- Provide clear user-facing error messages without technical details

## Audit Trail
- Log all payment operations with full context
- Include request ID, user ID, amount, currency, and status
- Ensure logs are immutable and tamper-proof
- Retain payment logs for regulatory compliance period (typically 7 years)

## PCI DSS Compliance
- Never store full credit card numbers in application logs
- Use tokenization for card-on-file scenarios
- Implement proper access controls on payment data
- Conduct regular security assessments of payment systems
