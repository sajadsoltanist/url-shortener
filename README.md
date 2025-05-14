# SCALABILITY.md

## Current Architecture

The URL shortener service follows a layered architecture with a clean separation of concerns:

```
                 ┌─────────┐
                 │  Redis  │
                 │  Cache  │◄────┐
                 └────┬────┘     │
                      │          │
                      ▼          │
┌────────┐      ┌───────────┐    │     ┌───────────┐
│        │      │   Read    │    │     │           │
│ Client ├─────►│  Service  ├────┴────►│ Database  │
│        │      │ Instances │          │           │
└────┬───┘      └───────────┘          └─────┬─────┘
     │                                       │
     │          ┌───────────┐                │
     │          │  Write    │                │
     └─────────►│  Service  ├────────────────┘
                │ Instances │    
                └─────┬─────┘    
                      │          ┌────────────┐
                      └─────────►│   Global   │
                                 │  Counter   │
                                 │  (Redis)   │
                                 └────────────┘
```

The system is built as an async-first application using FastAPI and SQLModel, with these key components:

1. **API Gateway**: Routes requests to appropriate service instances
2. **Read Service**: Handles URL redirection and statistics
   - Reads from Redis cache first
   - Falls back to database if cache misses
   - Updates cache with retrieved values (LRU cache strategy)
3. **Write Service**: Manages URL creation and updates
   - Communicates with the global counter service using atomic Redis operations (`INCR`/`INCRBY`)
   - Writes directly to the database
4. **Redis**: Serves dual purposes:
   - LRU cache for frequently accessed URLs
   - Global counter for short code generation using atomic operations
   - Redis Sentinel/Cluster for high availability and split-brain prevention
5. **Database**: PostgreSQL for persistent storage
   - Optimized schema with appropriate indexes
   - Connection pooling for efficient access (configured to 2*CPU cores for optimal performance)

## Addressing Scaling Challenges

### 1. Heavy Logging Without Performance Impact

When logging becomes a heavy operation, we implement a multi-layered approach to ensure it doesn't affect request latency:

#### Asynchronous Logging Pipeline

```
Request → FastAPI → [Non-blocking log collection] → [Buffer] → Background processor → External storage
```

#### Implementation Details

1. **OpenTelemetry Collection Layer**
   - Deploy OpenTelemetry collector as a sidecar or separate deployment in Kubernetes
   - Configure batch exporting with appropriate buffer sizes and flush intervals
   - Implement exemplar linking for high-cardinality metrics

2. **Structured Logging & Dynamic Sampling**
   - JSON-formatted logs for efficient indexing in ELK/Loki systems
   - Dynamic sampling rates: 100% for errors, configurable percentage for successful requests
   - Log level adjustment based on system load (DEBUG → INFO → WARN)

3. **Buffer-based Logging Architecture**
   - In-memory ring buffer with configurable size
   - Circuit breaker pattern to prevent application crash during logging system failure
   - Background flushing on time or size thresholds

4. **Distributed Task Processing**
   - Celery 5.x with Redis Streams or RabbitMQ as broker
   - Configured with `acks_late=True` and `max_retries=3` for resilience
   - Idempotent task design to handle potential duplicates during worker timeouts

5. **High-Volume Log Transport (for extreme scale)**
   - Kafka/Pulsar log bus when exceeding 100K+ events/second
   - Decouple log producers from consumers completely

### 2. Multi-Instance Deployment Across Different Servers

To scale horizontally across multiple instances and servers, we implement:

#### Service Decoupling & Externalization

1. **Kubernetes Orchestration**
   - Service discovery for internal communication
   - Health probes (readiness/liveness) to ensure traffic routes only to healthy instances
   - Proper termination grace periods to handle in-flight requests

2. **Python Concurrency Optimization**
   - Overcome GIL limitations using uvicorn with gunicorn (workers=cpu*2)
   - Asynchronous I/O operations throughout the codebase
   - Offload CPU-intensive tasks to separate processes

3. **State Management**
   - All application instances remain stateless
   - Redis for distributed caching and atomic counter operations
   - Distributed locking for critical sections when necessary

#### Database Strategy

1. **Hash-based Sharding on `short_code`**
   - Implement consistent hashing algorithm to minimize data movement during resharding
   - Apply a well-distributed hash function (MurmurHash or xxHash) to the `short_code`
   - Determine shard using modulo: `shard_id = hash(short_code) % num_shards`

2. **ID Generation**
   - **Block Allocator Pattern**: Allocate blocks of 10K/100K IDs to each writer service
   - **Snowflake-inspired IDs** (for future implementation):
     ```
     5 bits shard_id | 41 bits timestamp(ms) | 18 bits sequence
     ```

#### Potential Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Redis Split-Brain | Redis Sentinel/Cluster with proper quorum settings; application-level consistency validation |
| Database replication lag | Monitor lag metrics; implement stale read detection; consider read-your-writes consistency |
| Service version compatibility | Semantic versioning; backward compatibility; blue/green deployments |
| Network partition | Retries with exponential backoff; circuit breakers; fallback strategies |
| Uneven load distribution | Load balancing algorithms review; health metrics monitoring; auto-scaling based on CPU/memory |

### 3. High-Traffic Marketing Campaign Management

To handle thousands of requests per second during high-traffic periods:

#### Multi-level Caching Strategy 

1. **Three-Level Cache Architecture**
   - L1: In-process cache (Python dict with TTL) for zero-latency hits
   - L2: Redis cache with appropriate eviction policies
   - L3: Database

2. **CDN Integration**
   - Edge caching for popular redirects
   - CDN edge functions (Cloudflare Workers) to serve redirects without hitting backend
   - Cache warming for anticipated high-volume URLs

#### Traffic Management

1. **Rate Limiting Implementation**
   - Token bucket algorithm with Redis using `CL.THROTTLE` (Redis Bloom module) or Lua scripts
   - Proper 429 responses with Retry-After headers
   - Client-specific rate limits with configurable tiers

2. **Circuit Breakers**
   - Protect downstream dependencies from cascading failures
   - Configurable failure thresholds and recovery periods
   - Fallback mechanisms for degraded operation

3. **Graceful Degradation**
   - Feature toggles for non-critical functionality
   - Statistics recording could be temporarily disabled
   - Tiered service levels based on load

#### Database Optimizations

1. **Connection Pooling**
   - Properly sized connection pools
   - Statement timeout configuration
   - pgBouncer for connection pooling at scale

2. **Query Optimization**
   - Targeted indexes on `short_code`
   - Prepared statements
   - Read replicas for scaling read operations

3. **Hot Partition Prevention**
   - Link bucketing with random prefix for high-volume campaigns
   - Traffic distribution analysis to detect and mitigate hotspots

#### Auto-Scaling & Monitoring

1. **Kubernetes HPA (Horizontal Pod Autoscaler)**
   - Scale based on CPU/memory metrics
   - Custom metrics from Prometheus for targeted scaling
   - Predictive scaling based on time-of-day patterns

2. **Real-time Monitoring**
   - Prometheus + Grafana dashboards
   - Critical alerts with proper escalation policies
   - Business metrics (redirect volume, latency, error rates)

## Implementation Roadmap

| Phase | Focus | Key Components | Timeline |
|-------|-------|----------------|----------|
| Now | Core Scalability | Service separation, Redis caching, Basic observability | Current |
| Next | Resilience | Circuit breakers, Rate limiting, Improved monitoring | 1-2 months |
| Later | Advanced Scale | Sharding implementation, CDN integration, Edge functions | 3-6 months |

## Success Metrics & SLOs

- **Redirect Latency**: p99 < 50ms at 1K RPS
- **Availability**: 99.95% uptime
- **Cache Hit Ratio**: > 95%
- **Error Rate**: < 0.1% of total requests

## Security Considerations

While not explicitly mentioned in the original requirements, a production-grade system must address:

- **HTTPS Only** with HSTS headers
- **Secret Management** via Vault/AWS Parameter Store
- **Data Governance** with proper retention policies
- **GDPR Compliance** for IP address handling in logs