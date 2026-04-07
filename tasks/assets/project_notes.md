# Project Phoenix - Development Notes

## Overview
Project Phoenix is a microservices migration of the legacy monolith billing system.
The primary goal is to decompose the existing Java application into independently deployable services.

## Timeline
- Phase 1 (API Gateway): Completed March 15
- Phase 2 (User Service): In progress, due June 1
- Phase 3 (Billing Core): Planned, due September 30
- Final release: December 15

## Architecture Decisions
- Service mesh: Istio on Kubernetes
- Message broker: Apache Kafka for async communication
- Database: PostgreSQL per service (database-per-service pattern)
- Auth: OAuth2 with Keycloak

## Open Issues
- Latency budget for cross-service calls needs investigation
- Data migration strategy for billing history not finalized
- Team capacity concern: only 3 backend engineers available for Phase 2
