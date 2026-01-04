# Tippr Production Deployment Guide

## About This Guide

This deployment guide is for **Tippr**, a modern fork of the Reddit codebase updated for Python 3 and current infrastructure. While the core architecture remains similar to the original Reddit design, this guide has been updated for modern cloud platforms and self-hosting scenarios.

**Attribution**: Based on Reddit's open-source architecture and deployment patterns. Original Reddit code © 2006-2015 Reddit, Inc.

For the original Reddit codebase and historical context, see: https://github.com/reddit-archive/reddit

---

This document provides guidance for deploying the Tippr codebase in a production environment. While `install-tippr.sh` sets up a development environment with all services running locally, production deployments require a distributed architecture with proper scaling, redundancy, and managed services.

## Table of Contents

**Getting Started**
1. [Architecture Overview](#architecture-overview)
2. [Choosing Your Deployment Strategy](#choosing-your-deployment-strategy)
3. [Development vs Production](#development-vs-production)

**Cloud Deployments**
4. [AWS Deployment Guide](#aws-managed-services-strategy)
5. [Google Cloud Platform Guide](#google-cloud-platform-strategy)
6. [Microsoft Azure Guide](#microsoft-azure-strategy)
7. [Cloud Provider Comparison](#cloud-provider-comparison)

**Self-Hosted Deployments**
8. [Self-Hosted Production Deployment](#self-hosted-production-deployment)
9. [Hybrid Deployment Strategy](#hybrid-deployment-strategy)

**Common Components** (all deployment types)
10. [Database Configuration](#database-configuration)
11. [Caching Layer](#caching-layer)
12. [Message Queue](#message-queue)
13. [Application Servers](#application-servers)
14. [Load Balancing & Reverse Proxy](#load-balancing--reverse-proxy)

**Operations**
15. [Configuration Changes for Production](#configuration-changes-for-production)
16. [Migration from Development to Production](#migration-from-development-to-production)
17. [Backup & Disaster Recovery](#backup--disaster-recovery)
18. [Monitoring & Observability](#monitoring--observability)
19. [Security Considerations](#security-considerations)
20. [Scaling Lessons from Reddit's History](#scaling-lessons-from-reddits-history)
21. [Deployment Checklists](#deployment-checklist)
22. [Additional Resources](#additional-resources)

---

## Architecture Overview

### Development vs Production

| Component | Development (`install-tippr.sh`) | Production |
|-----------|-----------------------------------|------------|
| PostgreSQL | Local single instance | AWS RDS / GCP Cloud SQL / Azure Database for PostgreSQL |
| Cassandra | Local single node | AWS Keyspaces / Azure Managed Cassandra / Astra DB |
| Memcached | Local single instance | AWS ElastiCache / GCP Memorystore / Azure Cache for Redis |
| RabbitMQ | Local single instance | AWS MQ / Azure Service Bus / Self-managed |
| Application | Single paster process | Multiple Gunicorn workers behind load balancer |
| Static Files | Local filesystem | S3 / GCS / Azure Blob Storage + CDN |
| Search | Local Solr (optional) | CloudSearch / OpenSearch / Azure Cognitive Search |

### High-Level Production Architecture

```
                                    [CloudFront CDN]
                                          |
                                    [Application Load Balancer]
                                          |
                    +---------------------+---------------------+
                    |                     |                     |
              [App Server 1]        [App Server 2]        [App Server N]
                    |                     |                     |
                    +---------------------+---------------------+
                                          |
              +---------------------------+---------------------------+
              |                           |                           |
     [RDS PostgreSQL]            [Amazon Keyspaces]          [ElastiCache]
        (Multi-AZ)               (Cassandra-compatible)        (Memcached)
              |
        [Read Replicas]
```

---

## Choosing Your Deployment Strategy

### Decision Tree

**Start here**: What's your primary goal?

```
├─ Fastest time-to-production → AWS (all managed services, minimal code changes)
│  └─ Expected cost: $1,325-1,910/month
│
├─ Cost optimization → GCP + Astra DB or Self-Hosted Hybrid
│  ├─ Cloud: $950-1,450/month (GCP + Astra DB)
│  └─ Hybrid: $100-260/month (local compute + cloud storage/DB)
│
├─ Enterprise/Microsoft ecosystem → Azure
│  └─ Expected cost: $1,220-2,450/month (depending on Cassandra choice)
│
├─ Learning/Development → Self-Hosted (all local)
│  └─ Expected cost: Hardware + ~$50-100/month (internet + power + backups)
│
└─ Maximum scale (Reddit-level) → GCP with Bigtable (requires code changes)
   └─ Expected cost: $2,200-2,750/month
```

### Quick Comparison

| Priority | Best Choice | Why |
|----------|-------------|-----|
| Speed to production | AWS | All managed services, S3 provider exists in codebase |
| Lowest operating cost | Self-hosted hybrid | Local compute, cloud storage/DB only |
| Easiest to manage | AWS or GCP + Astra DB | Fully managed, CQL-compatible |
| Enterprise features | Azure | Best Microsoft integration, compliance certifications |
| Learning the architecture | Self-hosted | Full control, understand all components |
| Maximum scalability | GCP + Bigtable | Petabyte-scale, but requires code refactoring |

### Cost Estimation by Traffic Tier

| Traffic Tier | DAU | AWS | GCP + Astra | Azure + Astra | Self-Hosted Hybrid |
|--------------|-----|-----|-------------|---------------|-------------------|
| Small | <10K | $500-800 | $400-600 | $450-700 | $50-150 |
| Medium | 10K-100K | $1,325-1,910 | $950-1,450 | $1,220-1,750 | $100-260 |
| Large | 100K-1M | $3,000-5,000 | $2,500-4,000 | $3,000-5,000 | $300-500 |
| X-Large | >1M | $8,000+ | $6,000+ | $7,000+ | Full cloud recommended |

> **Note on costs**: These estimates do not include data transfer/egress fees, which can add 10-30% depending on traffic patterns. Reserved instances and committed use discounts can reduce costs by 30-70% for predictable workloads.

---

## AWS Managed Services Strategy

### Why Use Managed Services?

Using AWS managed services like Amazon Keyspaces and RDS PostgreSQL provides several advantages for initial production deployments:

1. **Reduced operational overhead** - No need to manage patches, backups, or failover
2. **Built-in high availability** - Multi-AZ deployments with automatic failover
3. **Scalability** - Easy vertical and horizontal scaling
4. **Security** - Encryption at rest and in transit, IAM integration
5. **Cost optimization** - Pay for what you use, especially with on-demand capacity

### Amazon Keyspaces (for Apache Cassandra)

Amazon Keyspaces is a serverless, Cassandra-compatible database service ideal for Tippr's time-series data (votes, comments, activity tracking).

#### Setup Considerations

```ini
# production.update - Cassandra/Keyspaces configuration
[DEFAULT]
# Amazon Keyspaces endpoint (replace region)
cassandra_seeds = cassandra.us-east-1.amazonaws.com:9142

# Keyspaces requires SSL/TLS
cassandra_ssl = true
cassandra_ssl_certfile = /path/to/sf-class2-root.crt

# Adjust consistency levels for Keyspaces
# LOCAL_QUORUM is recommended for production
cassandra_rcl = LOCAL_QUORUM
cassandra_wcl = LOCAL_QUORUM

# Connection pooling - Keyspaces handles scaling
cassandra_pool_size = 10
```

#### Keyspaces-Specific Considerations

1. **Authentication**: Use AWS Signature Version 4 (SigV4) authentication plugin or service-specific credentials
2. **Keyspace creation**: Create keyspaces via AWS Console or CQL with `SingleRegionStrategy`
3. **Throughput**: Start with on-demand capacity mode; switch to provisioned once traffic patterns are understood
4. **Schema**: Same CQL schema works, but avoid unsupported features (see limitations below)

#### Keyspaces Limitations (Important)

> **Warning**: Amazon Keyspaces is CQL-compatible but not feature-complete. Review these limitations before migrating:

| Feature | Self-Hosted Cassandra | Amazon Keyspaces | Impact |
|---------|----------------------|------------------|--------|
| `ALLOW FILTERING` | Supported | **Not supported** | Must redesign queries |
| Lightweight Transactions (LWT) | Full support | Limited support | `IF NOT EXISTS` works, but behavior differs |
| Counters | Native counters | **Emulated, eventual** | May see stale counts briefly |
| User-Defined Functions (UDF) | Supported | **Not supported** | Move logic to application layer |
| User-Defined Aggregates | Supported | **Not supported** | Aggregate in application |
| Materialized Views | Supported | **Not supported** | Create separate tables manually |
| Secondary Indexes | Supported | **Not supported** | Design with partition keys |
| Batch Statements | Unlimited | **Max 30 statements** | Split large batches |
| Request Size | Configurable | **Max 1MB** | Paginate large results |
| TTL | Any value | **Max 630,720,000 sec (~20 years)** | Usually not an issue |

**Throughput Considerations:**
- On-demand mode: Good for variable/unknown traffic, but can throttle on spikes
- Provisioned mode: Predictable cost, but must size correctly
- **Burst capacity**: Keyspaces provides burst capacity but throttles sustained high traffic

**Recommended Testing:**
```bash
# Before migrating, test your queries against Keyspaces
# Use the NoSQL Workbench for Amazon Keyspaces to validate schema
```

```python
# Example: Connecting to Keyspaces with SigV4
# Add to r2/r2/lib/db/cassandra_compat.py or connection setup
from ssl import SSLContext, PROTOCOL_TLS_CLIENT, CERT_REQUIRED
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from cassandra_sigv4.auth import SigV4AuthProvider

ssl_context = SSLContext(PROTOCOL_TLS_CLIENT)
ssl_context.load_verify_locations('/path/to/sf-class2-root.crt')
ssl_context.check_hostname = False
ssl_context.verify_mode = CERT_REQUIRED

auth_provider = SigV4AuthProvider(boto3.Session())
cluster = Cluster(
    ['cassandra.us-east-1.amazonaws.com'],
    ssl_context=ssl_context,
    auth_provider=auth_provider,
    port=9142
)
```

#### Data Migration to Keyspaces

Use AWS Database Migration Service (DMS) or the existing migration tools:

```bash
# Export from local Cassandra
cqlsh localhost 9042 -e "COPY tippr.votes TO 'votes.csv';"

# Import to Keyspaces (use smaller batches due to throughput limits)
cqlsh cassandra.us-east-1.amazonaws.com 9142 --ssl \
  -e "COPY tippr.votes FROM 'votes.csv' WITH MAXBATCHSIZE=10;"
```

### Amazon RDS for PostgreSQL

RDS PostgreSQL handles Tippr's relational data: links, accounts, vaults, and anything requiring ACID transactions.

#### Setup Considerations

```ini
# production.update - PostgreSQL/RDS configuration
[DEFAULT]
db_user = tippr
db_pass = YOUR_SECURE_PASSWORD
db_port = 5432

# Connection pooling - important for RDS
db_pool_size = 10
db_pool_overflow_size = 20

# List all database logical names
databases = main, comment, email, authorize, award, hc, traffic

# Primary (writer) endpoint
main_db = tippr, your-db.cluster-xxxxx.us-east-1.rds.amazonaws.com, *, *, *, *, *

# Read replicas for read-heavy tables
# Use reader endpoint for slave connections
comment_db = tippr, your-db.cluster-ro-xxxxx.us-east-1.rds.amazonaws.com, *, *, *, *, *
```

#### RDS Instance Recommendations

| Traffic Level | Instance Type | Storage | Multi-AZ |
|---------------|---------------|---------|----------|
| Low (<100K daily users) | db.t3.medium | 100GB gp3 | Optional |
| Medium (<1M daily users) | db.r6g.large | 500GB gp3 | Yes |
| High (>1M daily users) | db.r6g.xlarge+ | 1TB+ io1 | Yes |

#### RDS Best Practices

1. **Use read replicas**: Route read queries to replicas to reduce primary load
2. **Connection pooling**: Use PgBouncer or RDS Proxy to manage connections
3. **Parameter tuning**: Adjust `shared_buffers`, `work_mem`, `effective_cache_size`
4. **Storage**: Use gp3 for balanced workloads, io1/io2 for high IOPS requirements
5. **Backup**: Enable automated backups with appropriate retention period

```ini
# Database server configuration with read replicas
# Primary for writes
db_servers_link = main, main
db_servers_account = main

# Use replica for heavy read tables - add !avoid_master flag
db_servers_comment = comment, comment, !avoid_master
db_servers_subreddit = comment, comment, !avoid_master
```

#### SSD Performance Note

From Tippr's scaling experience: **SSDs provide 16x performance improvement at only 4x the cost**. RDS with gp3 or io1 storage uses SSDs by default. If self-managing PostgreSQL:

- Use NVMe or SSD-backed EBS volumes
- Consider i3 or i3en instance types for local NVMe storage
- Monitor IOPS and latency to right-size storage

---

## Google Cloud Platform Strategy

Google Cloud Platform (GCP) offers a compelling alternative to AWS with competitive pricing, strong networking, and excellent managed services. This section covers the equivalent GCP services for running Tippr in production.

### GCP Architecture Overview

```
                                    [Cloud CDN]
                                          |
                                    [Cloud Load Balancer]
                                          |
                    +---------------------+---------------------+
                    |                     |                     |
              [GCE Instance 1]      [GCE Instance 2]      [GCE Instance N]
              (or GKE Pod)          (or GKE Pod)          (or GKE Pod)
                    |                     |                     |
                    +---------------------+---------------------+
                                          |
              +---------------------------+---------------------------+
              |                           |                           |
     [Cloud SQL PostgreSQL]        [Cloud Bigtable]           [Memorystore]
        (Regional HA)              (Cassandra alternative)      (Memcached)
              |
        [Read Replicas]
```

### GCP Service Mapping

| Tippr Component | AWS Service | GCP Equivalent |
|------------------|-------------|----------------|
| PostgreSQL | RDS for PostgreSQL | Cloud SQL for PostgreSQL |
| Cassandra | Amazon Keyspaces | DataStax Astra DB / Cloud Bigtable / Self-managed |
| Memcached | ElastiCache | Memorystore for Memcached |
| RabbitMQ | Amazon MQ | Cloud Pub/Sub (or self-managed on GKE) |
| Application Hosting | EC2 + ASG | Compute Engine + MIG (or GKE) |
| Load Balancer | ALB | Cloud Load Balancing |
| CDN | CloudFront | Cloud CDN |
| Object Storage | S3 | Cloud Storage (GCS) |
| Secrets | Secrets Manager | Secret Manager |
| Search | CloudSearch/OpenSearch | Elasticsearch on GKE |
| Monitoring | CloudWatch | Cloud Monitoring + Cloud Logging |

### Cloud SQL for PostgreSQL

Cloud SQL is Google's fully managed PostgreSQL service with automatic failover, backups, and read replicas.

#### Configuration

```ini
# production-gcp.update - Cloud SQL configuration
[DEFAULT]
db_user = tippr
db_pass = YOUR_SECURE_PASSWORD
db_port = 5432

# Connection pooling
db_pool_size = 10
db_pool_overflow_size = 20

databases = main, comment, email, authorize, award, hc, traffic

# Cloud SQL connection (private IP recommended)
# Format: project:region:instance or private IP
main_db = tippr, 10.0.0.5, *, *, *, *, *

# Read replica for heavy read tables
comment_db = tippr, 10.0.0.6, *, *, *, *, *
```

#### Cloud SQL Instance Recommendations

| Traffic Level | Machine Type | Storage | High Availability |
|---------------|--------------|---------|-------------------|
| Low (<100K daily) | db-custom-2-4096 | 100GB SSD | Optional |
| Medium (<1M daily) | db-custom-4-16384 | 500GB SSD | Yes (Regional) |
| High (>1M daily) | db-custom-8-32768+ | 1TB+ SSD | Yes (Regional) |

#### Cloud SQL Proxy (Recommended)

Use Cloud SQL Proxy for secure connections without exposing the database:

```bash
# Download and run Cloud SQL Proxy
./cloud-sql-proxy --private-ip \
  your-project:us-central1:tippr-db &

# Application connects to localhost
# production-gcp.update
main_db = tippr, 127.0.0.1, *, *, *, *, *
```

#### Cloud SQL Best Practices

1. **Use Private IP**: Keep database off public internet
2. **Enable automatic storage increases**: Prevents running out of disk
3. **Use regional HA**: Automatic failover across zones
4. **Connection pooling**: Use PgBouncer sidecar or built-in connection limits
5. **Query Insights**: Enable for slow query analysis

### Cassandra Options on GCP

GCP offers three approaches for Cassandra workloads, each with different trade-offs:

| Option | CQL Compatible | Managed | Code Changes | Best For |
|--------|----------------|---------|--------------|----------|
| DataStax Astra DB | Yes | Fully | None | Fastest migration |
| Cloud Bigtable | No | Fully | Significant | Maximum scale |
| Self-managed on GKE | Yes | No | None | Cost optimization |

#### Option A: DataStax Astra DB (Recommended for Migration)

DataStax Astra DB is a fully managed Cassandra-as-a-Service available on Google Cloud through a partnership with DataStax. It provides **full CQL compatibility**, making it equivalent to AWS Keyspaces for migration purposes.

**Key Advantages:**
- **Zero code changes**: Full CQL compatibility with existing Cassandra code
- **Serverless**: Pay-per-use pricing, no node management
- **Multi-cloud**: Can run on GCP, AWS, or Azure
- **Integrations**: Native integration with BigQuery, Dataflow, and Google Cloud AI services
- **Vector Search**: Built-in vector search for AI/ML workloads

```ini
# production-gcp.update - DataStax Astra DB configuration
[DEFAULT]
# Astra DB Secure Connect Bundle approach
cassandra_seeds = YOUR_ASTRA_DB_ID-YOUR_REGION.apps.astra.datastax.com:29042

# Astra requires SSL/TLS
cassandra_ssl = true
cassandra_ssl_certfile = /path/to/secure-connect-bundle/ca.crt

# Consistency levels
cassandra_rcl = LOCAL_QUORUM
cassandra_wcl = LOCAL_QUORUM

# Connection pooling
cassandra_pool_size = 10
```

**Python Connection Example:**

```python
# Connecting to Astra DB from Tippr codebase
# Minimal changes to r2/r2/lib/db/cassandra_compat.py
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

# Using Secure Connect Bundle (recommended)
cloud_config = {
    'secure_connect_bundle': '/path/to/secure-connect-tippr.zip'
}
auth_provider = PlainTextAuthProvider(
    username='token',
    secret='AstraCS:YOUR_APPLICATION_TOKEN'
)
cluster = Cluster(cloud=cloud_config, auth_provider=auth_provider)
session = cluster.connect('tippr')

# All existing CQL queries work unchanged
session.execute("SELECT * FROM votes WHERE user_id = %s", [user_id])
```

**Astra DB Pricing (Serverless):**

| Usage Level | Reads/Writes | Est. Monthly Cost |
|-------------|--------------|-------------------|
| Low | 10M ops/month | $25-50 |
| Medium | 100M ops/month | $150-300 |
| High | 1B ops/month | $500-1,000 |

**Note**: Astra DB serverless pricing is based on read/write units consumed, making it cost-effective for variable workloads. For predictable high-volume workloads, consider Astra DB Dedicated.

#### Option B: Cloud Bigtable (Maximum Scale)

Cloud Bigtable is Google's NoSQL wide-column database. While not CQL-compatible, it's highly performant for Tippr's use cases (votes, activity tracking, time-series data) at massive scale.

##### Key Differences from Cassandra

| Feature | Cassandra/Astra DB | Cloud Bigtable |
|---------|---------------------|----------------|
| Query Language | CQL | HBase API / Client Libraries |
| Data Model | Wide-column with CQL | Wide-column with row keys |
| Consistency | Tunable | Strong (single-row) |
| Schema | Defined tables | Schema-less (column families) |
| Pricing | Per read/write or provisioned | Node-hours + storage |

Bigtable excels at high-throughput, low-latency workloads but requires code changes to use Google's client libraries instead of CQL.

```python
# Example: Bigtable client for vote storage
# Would require adapting r2/r2/lib/db/tdb_cassandra.py
from google.cloud import bigtable
from google.cloud.bigtable import column_family

client = bigtable.Client(project='your-project', admin=True)
instance = client.instance('tippr-instance')
table = instance.table('votes')

# Write vote
row_key = f"user:{user_id}#link:{link_id}".encode()
row = table.direct_row(row_key)
row.set_cell('vote', 'direction', str(direction).encode())
row.set_cell('vote', 'timestamp', str(timestamp).encode())
row.commit()

# Read votes for user
rows = table.read_rows(row_key_prefix=f"user:{user_id}#".encode())
```

#### Bigtable Instance Sizing

| Traffic Level | Node Type | Nodes | Storage |
|---------------|-----------|-------|---------|
| Low | Development (1 node) | 1 | 100GB SSD |
| Medium | Production | 3 | 500GB SSD |
| High | Production | 5-10+ | 1TB+ SSD |

**Note**: Bigtable minimum for production is 3 nodes. Development instances (1 node) have performance limitations.

#### Option B: Self-Managed Cassandra on GKE

For CQL compatibility without code changes, run Cassandra on Google Kubernetes Engine:

```yaml
# cassandra-statefulset.yaml (simplified)
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra
spec:
  serviceName: cassandra
  replicas: 3
  selector:
    matchLabels:
      app: cassandra
  template:
    metadata:
      labels:
        app: cassandra
    spec:
      containers:
      - name: cassandra
        image: cassandra:4.1
        ports:
        - containerPort: 9042
        env:
        - name: CASSANDRA_SEEDS
          value: "cassandra-0.cassandra.default.svc.cluster.local"
        volumeMounts:
        - name: cassandra-data
          mountPath: /var/lib/cassandra
  volumeClaimTemplates:
  - metadata:
      name: cassandra-data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: premium-rwo
      resources:
        requests:
          storage: 100Gi
```

```ini
# production-gcp.update - Self-managed Cassandra on GKE
cassandra_seeds = cassandra-0.cassandra.default.svc.cluster.local:9042,cassandra-1.cassandra.default.svc.cluster.local:9042
cassandra_pool_size = 10
cassandra_rcl = LOCAL_QUORUM
cassandra_wcl = LOCAL_QUORUM
```

### Memorystore for Memcached

Memorystore provides managed Memcached compatible with Tippr's caching layer.

#### Configuration

```ini
# production-gcp.update - Memorystore configuration
[DEFAULT]
# Memorystore discovery endpoint
lockcaches = 10.0.0.10:11211
permacache_memcaches = 10.0.0.10:11211
hardcache_memcaches = 10.0.0.10:11211

# Connection pool
num_mc_clients = 20
```

#### Memorystore Sizing

| Traffic Level | Memory | Nodes |
|---------------|--------|-------|
| Low | 1GB | 1 |
| Medium | 5-10GB | 2-3 |
| High | 20GB+ | 3-5 |

### Message Queue Options on GCP

#### Option A: Cloud Pub/Sub (GCP Native)

Cloud Pub/Sub is a fully managed messaging service. It uses a different paradigm (topics/subscriptions) than RabbitMQ (exchanges/queues) and would require adapter code.

```python
# Example: Pub/Sub adapter for Tippr's queue system
# Would wrap r2/r2/lib/amqp.py
from google.cloud import pubsub_v1

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path('your-project', 'vote-queue')

def add_item(queue_name, item):
    data = json.dumps(item).encode('utf-8')
    future = publisher.publish(topic_path, data)
    return future.result()

# Subscriber (consumer)
subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path('your-project', 'vote-processor')

def callback(message):
    item = json.loads(message.data.decode('utf-8'))
    process_vote(item)
    message.ack()

subscriber.subscribe(subscription_path, callback=callback)
```

#### Option B: Self-Managed RabbitMQ on GKE (Recommended)

For drop-in compatibility, run RabbitMQ on GKE:

```yaml
# rabbitmq-deployment.yaml (using RabbitMQ Cluster Operator)
apiVersion: rabbitmq.com/v1beta1
kind: RabbitmqCluster
metadata:
  name: tippr-rabbitmq
spec:
  replicas: 3
  persistence:
    storageClassName: premium-rwo
    storage: 50Gi
  resources:
    requests:
      cpu: 1
      memory: 2Gi
    limits:
      cpu: 2
      memory: 4Gi
```

```ini
# production-gcp.update - RabbitMQ on GKE
amqp_host = tippr-rabbitmq.default.svc.cluster.local:5672
amqp_user = tippr
amqp_pass = YOUR_SECURE_PASSWORD
amqp_virtual_host = /
```

### Compute Options

#### Option A: Compute Engine with Managed Instance Groups

Traditional VM-based deployment similar to EC2:

```bash
# Create instance template
gcloud compute instance-templates create tippr-template \
  --machine-type=n2-standard-4 \
  --image-family=ubuntu-2404-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-ssd \
  --metadata-from-file=startup-script=startup.sh

# Create managed instance group with autoscaling
gcloud compute instance-groups managed create tippr-mig \
  --template=tippr-template \
  --size=3 \
  --zone=us-central1-a

gcloud compute instance-groups managed set-autoscaling tippr-mig \
  --min-num-replicas=2 \
  --max-num-replicas=10 \
  --target-cpu-utilization=0.7 \
  --zone=us-central1-a
```

#### Option B: Google Kubernetes Engine (GKE)

Container-based deployment for better resource utilization:

```yaml
# tippr-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tippr-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: tippr
  template:
    metadata:
      labels:
        app: tippr
    spec:
      containers:
      - name: tippr
        image: gcr.io/your-project/tippr:latest
        ports:
        - containerPort: 8001
        env:
        - name: PYTHONPATH
          value: "/app/tippr:/app"
        resources:
          requests:
            cpu: "1"
            memory: "2Gi"
          limits:
            cpu: "2"
            memory: "4Gi"
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: tippr-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: tippr-app
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### Load Balancing & CDN on GCP

#### Cloud Load Balancing

```bash
# Create health check
gcloud compute health-checks create http tippr-health \
  --port=8001 \
  --request-path=/health

# Create backend service
gcloud compute backend-services create tippr-backend \
  --protocol=HTTP \
  --health-checks=tippr-health \
  --global

# Add instance group to backend
gcloud compute backend-services add-backend tippr-backend \
  --instance-group=tippr-mig \
  --instance-group-zone=us-central1-a \
  --global

# Create URL map
gcloud compute url-maps create tippr-lb \
  --default-service=tippr-backend

# Create HTTPS proxy with SSL cert
gcloud compute target-https-proxies create tippr-https-proxy \
  --url-map=tippr-lb \
  --ssl-certificates=tippr-ssl-cert

# Create forwarding rule
gcloud compute forwarding-rules create tippr-https-rule \
  --target-https-proxy=tippr-https-proxy \
  --ports=443 \
  --global
```

#### Cloud CDN

Enable Cloud CDN on the backend service for caching:

```bash
gcloud compute backend-services update tippr-backend \
  --enable-cdn \
  --cache-mode=CACHE_ALL_STATIC \
  --default-ttl=3600 \
  --global
```

### Cloud Storage for Media

```ini
# production-gcp.update - GCS for media storage
[DEFAULT]
media_provider = gcs  # Requires implementing GCS provider

# GCS bucket configuration
gcs_media_bucket = your-tippr-media
gcs_image_bucket = your-tippr-images
gcs_project = your-project-id
```

**Note**: The codebase has an S3 provider (`r2/r2/lib/providers/media/s3.py`). You would need to implement a GCS provider or use the S3-compatible GCS XML API.

```python
# GCS with S3-compatible API (alternative)
# production-gcp.update
media_provider = s3
S3KEY_ID = YOUR_GCS_HMAC_ACCESS_ID
S3SECRET_KEY = YOUR_GCS_HMAC_SECRET
s3_media_domain = storage.googleapis.com
s3_media_buckets = your-tippr-media
```

### GCP Production Configuration

```ini
# production-gcp.update
[DEFAULT]
# CRITICAL: Disable debug mode
debug = false
template_debug = false
reload_templates = false
uncompressedJS = false
sqlprinting = false

# Production domain
domain = yourdomain.com
media_domain = media.yourdomain.com
https_endpoint = https://yourdomain.com

# Cloud SQL
db_user = tippr
db_pass = YOUR_SECURE_PASSWORD
db_port = 5432
databases = main, comment, email, authorize, award, hc, traffic
main_db = tippr, /cloudsql/project:region:instance, *, *, *, *, *

# Bigtable or self-managed Cassandra
cassandra_seeds = cassandra.default.svc.cluster.local:9042
cassandra_pool_size = 10

# Memorystore
lockcaches = 10.0.0.10:11211
permacache_memcaches = 10.0.0.10:11211
hardcache_memcaches = 10.0.0.10:11211

# RabbitMQ on GKE
amqp_host = tippr-rabbitmq.default.svc.cluster.local:5672
amqp_user = tippr
amqp_pass = YOUR_SECURE_PASSWORD

# GCS media storage (S3-compatible)
media_provider = s3
s3_media_domain = storage.googleapis.com
s3_media_buckets = your-media-bucket

# Security
trust_local_proxies = true
ENFORCE_RATELIMIT = true

# Monitoring (Cloud Monitoring via OpenTelemetry)
statsd_addr = localhost:8125  # Use statsd-exporter sidecar
```

### GCP Monitoring & Observability

#### Cloud Monitoring

```yaml
# Deploy Prometheus/Grafana on GKE or use Cloud Monitoring
# statsd-exporter sidecar for StatsD -> Prometheus
apiVersion: v1
kind: ConfigMap
metadata:
  name: statsd-mapping
data:
  mapping.yml: |
    mappings:
    - match: "tippr.*"
      name: "tippr_${1}"
      labels:
        job: "tippr"
```

#### Cloud Logging

Application logs are automatically collected from GCE/GKE and available in Cloud Logging.

```ini
# production-gcp.update - Logging configuration
[logger_root]
level = INFO
handlers = console

# Logs go to stdout, captured by Cloud Logging agent
```

### GCP Cost Estimation

For a medium-traffic deployment (~100K-500K daily active users):

| Service | Configuration | Est. Monthly Cost |
|---------|---------------|-------------------|
| Cloud SQL PostgreSQL | db-custom-4-16384, HA | $250-350 |
| **Cassandra Option A:** DataStax Astra DB | Serverless, ~100M ops/mo | $150-300 |
| **Cassandra Option B:** Cloud Bigtable | 3 nodes production | $1,400-1,600 |
| **Cassandra Option C:** Self-managed on GKE | 3x n2-standard-4 | $300-400 |
| Memorystore | 5GB | $150-200 |
| GKE Cluster | 3x n2-standard-4 | $300-400 |
| Cloud Load Balancing | Standard | $20-50 |
| Cloud CDN | 1TB transfer | $80-150 |
| Cloud Storage | 100GB | $2-5 |
| **Total (with Astra DB)** | | **$950-1,450/month** |
| **Total (with Bigtable)** | | **$2,200-2,750/month** |
| **Total (with self-managed Cassandra)** | | **$1,100-1,550/month** |

**Notes**:
- GCP offers sustained use discounts (up to 30% for VMs running full month)
- Committed use discounts provide 50-70% savings for 1-3 year commitments
- Astra DB serverless pricing scales with actual usage, ideal for variable traffic

### GCP Deployment Checklist

- [ ] Create GCP project and enable required APIs
- [ ] Set up VPC with private subnets
- [ ] Provision Cloud SQL PostgreSQL (Regional HA)
- [ ] Provision Memorystore for Memcached
- [ ] Set up Cassandra layer (choose one):
  - [ ] **Option A**: Create DataStax Astra DB database and download Secure Connect Bundle
  - [ ] **Option B**: Provision Cloud Bigtable instance (requires code changes)
  - [ ] **Option C**: Deploy self-managed Cassandra StatefulSet on GKE
- [ ] Deploy RabbitMQ on GKE (using RabbitMQ Cluster Operator)
- [ ] Create GCS buckets for media (enable S3-compatible HMAC keys)
- [ ] Configure Cloud Load Balancer with SSL
- [ ] Enable Cloud CDN
- [ ] Set up Cloud Monitoring dashboards
- [ ] Configure Secret Manager for credentials
- [ ] Deploy application to GKE or MIG
- [ ] Configure autoscaling policies
- [ ] Set up Cloud Armor for WAF (optional)
- [ ] (Optional) Configure BigQuery integration for analytics

---

## Microsoft Azure Strategy

Microsoft Azure provides a comprehensive set of managed services for running Tippr in production, with strong enterprise integration and hybrid cloud capabilities.

### Azure Architecture Overview

```
                                    [Azure CDN / Front Door]
                                          |
                                    [Application Gateway]
                                          |
                    +---------------------+---------------------+
                    |                     |                     |
              [VM Scale Set]        [VM Scale Set]        [AKS Pod]
              (or AKS Pod)          (or AKS Pod)
                    |                     |                     |
                    +---------------------+---------------------+
                                          |
              +---------------------------+---------------------------+
              |                           |                           |
     [Azure Database for          [Azure Managed           [Azure Cache
      PostgreSQL - Flexible]       Cassandra]               for Redis]
              |
        [Read Replicas]
```

### Azure Service Mapping

| Tippr Component | AWS Service | GCP Equivalent | Azure Equivalent |
|------------------|-------------|----------------|------------------|
| PostgreSQL | RDS for PostgreSQL | Cloud SQL | Azure Database for PostgreSQL |
| Cassandra | Amazon Keyspaces | Astra DB / Bigtable | Azure Managed Instance for Cassandra |
| Memcached | ElastiCache | Memorystore | Azure Cache for Redis (Memcached protocol) |
| RabbitMQ | Amazon MQ | Self-managed | Azure Service Bus / Self-managed on AKS |
| Application | EC2 + ASG | GCE + MIG / GKE | VM Scale Sets / Azure Kubernetes Service |
| Load Balancer | ALB | Cloud LB | Application Gateway / Azure Load Balancer |
| CDN | CloudFront | Cloud CDN | Azure CDN / Azure Front Door |
| Object Storage | S3 | Cloud Storage | Azure Blob Storage |
| Secrets | Secrets Manager | Secret Manager | Azure Key Vault |
| Search | CloudSearch | Elasticsearch | Azure Cognitive Search |
| Monitoring | CloudWatch | Cloud Monitoring | Azure Monitor + Log Analytics |

### Azure Database for PostgreSQL - Flexible Server

Azure Database for PostgreSQL Flexible Server is the recommended option for new deployments, offering more control over database configuration and better price-performance.

#### Configuration

```ini
# production-azure.update - Azure PostgreSQL configuration
[DEFAULT]
db_user = tippr
db_pass = YOUR_SECURE_PASSWORD
db_port = 5432

# Connection pooling
db_pool_size = 10
db_pool_overflow_size = 20

databases = main, comment, email, authorize, award, hc, traffic

# Azure PostgreSQL Flexible Server (private endpoint recommended)
main_db = tippr, tippr-db.postgres.database.azure.com, *, *, *, *, *

# Read replica for heavy read tables
comment_db = tippr, tippr-db-replica.postgres.database.azure.com, *, *, *, *, *
```

#### Azure PostgreSQL Instance Recommendations

| Traffic Level | Compute Tier | vCores | Storage | High Availability |
|---------------|--------------|--------|---------|-------------------|
| Low (<100K daily) | Burstable B2s | 2 | 128GB | Optional |
| Medium (<1M daily) | General Purpose D4s_v3 | 4 | 512GB | Zone-redundant |
| High (>1M daily) | Memory Optimized E8s_v3+ | 8+ | 1TB+ | Zone-redundant |

#### Azure PostgreSQL Best Practices

1. **Use Private Link**: Connect via private endpoint, not public internet
2. **Enable zone-redundant HA**: Automatic failover across availability zones
3. **Configure connection pooling**: Use PgBouncer (built-in option available)
4. **Enable Query Performance Insight**: Identify slow queries
5. **Use Azure AD authentication**: For enhanced security

```bash
# Create Azure PostgreSQL Flexible Server
az postgres flexible-server create \
  --resource-group tippr-rg \
  --name tippr-db \
  --location eastus \
  --admin-user tippr \
  --admin-password YOUR_SECURE_PASSWORD \
  --sku-name Standard_D4s_v3 \
  --tier GeneralPurpose \
  --storage-size 512 \
  --version 15 \
  --high-availability ZoneRedundant \
  --zone 1 \
  --standby-zone 2
```

### Azure Managed Instance for Apache Cassandra

Azure Managed Instance for Apache Cassandra provides a fully managed, CQL-compatible Cassandra service with automatic scaling and maintenance.

#### Key Advantages

- **Full CQL compatibility**: No code changes required from existing Cassandra code
- **Hybrid support**: Can connect to on-premises Cassandra clusters
- **Automatic scaling**: Add/remove nodes without downtime
- **Azure-native integration**: Works with Azure Monitor, Key Vault, and Private Link
- **Cost-effective**: Pay for what you use with flexible scaling

#### Configuration

```ini
# production-azure.update - Azure Managed Cassandra configuration
[DEFAULT]
# Azure Managed Cassandra data center endpoint
cassandra_seeds = tippr-cassandra-dc1.cassandra.cosmos.azure.com:10350

# Azure Managed Cassandra requires SSL/TLS
cassandra_ssl = true
cassandra_ssl_certfile = /path/to/azure-cassandra-ca.crt

# Consistency levels (LOCAL_QUORUM recommended)
cassandra_rcl = LOCAL_QUORUM
cassandra_wcl = LOCAL_QUORUM

# Connection pooling
cassandra_pool_size = 10
```

#### Python Connection Example

```python
# Connecting to Azure Managed Cassandra from Tippr codebase
# Minimal changes to r2/r2/lib/db/cassandra_compat.py
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from ssl import SSLContext, PROTOCOL_TLS_CLIENT, CERT_REQUIRED

# SSL configuration for Azure
ssl_context = SSLContext(PROTOCOL_TLS_CLIENT)
ssl_context.load_verify_locations('/path/to/azure-cassandra-ca.crt')
ssl_context.check_hostname = True
ssl_context.verify_mode = CERT_REQUIRED

# Authentication
auth_provider = PlainTextAuthProvider(
    username='tippr-cassandra',
    password='YOUR_CASSANDRA_PASSWORD'
)

cluster = Cluster(
    contact_points=['tippr-cassandra-dc1.cassandra.cosmos.azure.com'],
    port=10350,
    auth_provider=auth_provider,
    ssl_context=ssl_context
)
session = cluster.connect('tippr')

# All existing CQL queries work unchanged
session.execute("SELECT * FROM votes WHERE user_id = %s", [user_id])
```

#### Azure Managed Cassandra Sizing

| Traffic Level | SKU | Nodes | Disk per Node |
|---------------|-----|-------|---------------|
| Low | Standard_D8s_v4 | 3 | 1TB P30 |
| Medium | Standard_D16s_v4 | 3-5 | 2TB P40 |
| High | Standard_D32s_v4 | 5-10+ | 4TB P50 |

```bash
# Create Azure Managed Cassandra Cluster
az managed-cassandra cluster create \
  --resource-group tippr-rg \
  --cluster-name tippr-cassandra \
  --location eastus \
  --delegated-management-subnet-id /subscriptions/.../subnets/cassandra-subnet \
  --initial-cassandra-admin-password YOUR_CASSANDRA_PASSWORD

# Create data center
az managed-cassandra datacenter create \
  --resource-group tippr-rg \
  --cluster-name tippr-cassandra \
  --data-center-name dc1 \
  --data-center-location eastus \
  --delegated-subnet-id /subscriptions/.../subnets/cassandra-subnet \
  --node-count 3 \
  --sku Standard_D8s_v4 \
  --disk-sku P30
```

#### Alternative: DataStax Astra DB on Azure

Astra DB is also available on Azure, providing the same serverless experience as on GCP:

```ini
# production-azure.update - Astra DB on Azure
[DEFAULT]
cassandra_seeds = YOUR_ASTRA_DB_ID-YOUR_REGION.apps.astra.datastax.com:29042
cassandra_ssl = true
cassandra_pool_size = 10
```

### Azure Cache for Redis

Azure doesn't offer managed Memcached, but Azure Cache for Redis can work as a high-performance caching layer. For Memcached protocol compatibility, you can self-host Memcached on AKS.

#### Option A: Azure Cache for Redis (Recommended)

Redis is more feature-rich than Memcached and works well for Tippr's caching needs. However, it requires changes to the caching code to use Redis instead of Memcached.

```ini
# production-azure.update - Azure Cache for Redis
# Note: Requires implementing Redis cache provider in r2/r2/lib/cache.py
[DEFAULT]
redis_host = tippr-cache.redis.cache.windows.net
redis_port = 6380
redis_password = YOUR_ACCESS_KEY
redis_ssl = true
```

#### Option B: Self-Managed Memcached on AKS

For drop-in Memcached compatibility:

```yaml
# memcached-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: memcached
spec:
  replicas: 3
  selector:
    matchLabels:
      app: memcached
  template:
    metadata:
      labels:
        app: memcached
    spec:
      containers:
      - name: memcached
        image: memcached:1.6-alpine
        ports:
        - containerPort: 11211
        args: ["-m", "2048", "-c", "4096"]
        resources:
          requests:
            memory: "2Gi"
            cpu: "500m"
          limits:
            memory: "2.5Gi"
            cpu: "1"
---
apiVersion: v1
kind: Service
metadata:
  name: memcached
spec:
  ports:
  - port: 11211
  selector:
    app: memcached
```

```ini
# production-azure.update - Self-managed Memcached on AKS
lockcaches = memcached.default.svc.cluster.local:11211
permacache_memcaches = memcached.default.svc.cluster.local:11211
hardcache_memcaches = memcached.default.svc.cluster.local:11211
num_mc_clients = 20
```

### Message Queue Options on Azure

#### Option A: Azure Service Bus (Managed)

Azure Service Bus provides enterprise messaging with queues and topics. It uses a different API than RabbitMQ, requiring an adapter.

```python
# Example: Azure Service Bus adapter for Tippr's queue system
from azure.servicebus import ServiceBusClient, ServiceBusMessage

connection_str = "Endpoint=sb://tippr-bus.servicebus.windows.net/;..."
client = ServiceBusClient.from_connection_string(connection_str)

def add_item(queue_name, item):
    with client.get_queue_sender(queue_name) as sender:
        message = ServiceBusMessage(json.dumps(item))
        sender.send_messages(message)

def process_items(queue_name, callback):
    with client.get_queue_receiver(queue_name) as receiver:
        for message in receiver:
            item = json.loads(str(message))
            callback(item)
            receiver.complete_message(message)
```

#### Option B: Self-Managed RabbitMQ on AKS (Recommended)

For drop-in compatibility with existing code:

```yaml
# rabbitmq-deployment.yaml (using RabbitMQ Cluster Operator)
apiVersion: rabbitmq.com/v1beta1
kind: RabbitmqCluster
metadata:
  name: tippr-rabbitmq
spec:
  replicas: 3
  persistence:
    storageClassName: managed-premium
    storage: 50Gi
  resources:
    requests:
      cpu: 1
      memory: 2Gi
    limits:
      cpu: 2
      memory: 4Gi
```

```ini
# production-azure.update - RabbitMQ on AKS
amqp_host = tippr-rabbitmq.default.svc.cluster.local:5672
amqp_user = tippr
amqp_pass = YOUR_SECURE_PASSWORD
amqp_virtual_host = /
```

### Compute Options on Azure

#### Option A: Virtual Machine Scale Sets

Traditional VM-based deployment with auto-scaling:

```bash
# Create VM Scale Set
az vmss create \
  --resource-group tippr-rg \
  --name tippr-vmss \
  --image Ubuntu2204 \
  --vm-sku Standard_D4s_v3 \
  --instance-count 3 \
  --admin-username tippr \
  --generate-ssh-keys \
  --custom-data cloud-init.yaml \
  --load-balancer tippr-lb \
  --backend-pool-name tippr-backend

# Configure autoscaling
az monitor autoscale create \
  --resource-group tippr-rg \
  --resource tippr-vmss \
  --resource-type Microsoft.Compute/virtualMachineScaleSets \
  --min-count 2 \
  --max-count 10 \
  --count 3

az monitor autoscale rule create \
  --resource-group tippr-rg \
  --autoscale-name tippr-vmss-autoscale \
  --scale out 1 \
  --condition "Percentage CPU > 70 avg 5m"
```

#### Option B: Azure Kubernetes Service (AKS)

Container-based deployment with excellent Azure integration:

```yaml
# tippr-deployment.yaml for AKS
apiVersion: apps/v1
kind: Deployment
metadata:
  name: tippr-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: tippr
  template:
    metadata:
      labels:
        app: tippr
    spec:
      containers:
      - name: tippr
        image: tippracr.azurecr.io/tippr:latest
        ports:
        - containerPort: 8001
        env:
        - name: PYTHONPATH
          value: "/app/tippr:/app"
        resources:
          requests:
            cpu: "1"
            memory: "2Gi"
          limits:
            cpu: "2"
            memory: "4Gi"
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: tippr-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: tippr-app
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

```bash
# Create AKS cluster
az aks create \
  --resource-group tippr-rg \
  --name tippr-aks \
  --node-count 3 \
  --node-vm-size Standard_D4s_v3 \
  --enable-cluster-autoscaler \
  --min-count 2 \
  --max-count 10 \
  --network-plugin azure \
  --enable-managed-identity \
  --generate-ssh-keys
```

### Load Balancing & CDN on Azure

#### Application Gateway

Azure Application Gateway provides L7 load balancing with WAF capabilities:

```bash
# Create Application Gateway
az network application-gateway create \
  --resource-group tippr-rg \
  --name tippr-appgw \
  --location eastus \
  --sku Standard_v2 \
  --capacity 2 \
  --vnet-name tippr-vnet \
  --subnet appgw-subnet \
  --frontend-port 443 \
  --http-settings-port 8001 \
  --http-settings-protocol Http \
  --routing-rule-type Basic \
  --priority 100
```

#### Azure Front Door + CDN

For global distribution and caching:

```bash
# Create Azure Front Door
az afd profile create \
  --resource-group tippr-rg \
  --profile-name tippr-afd \
  --sku Premium_AzureFrontDoor

az afd endpoint create \
  --resource-group tippr-rg \
  --profile-name tippr-afd \
  --endpoint-name tippr-endpoint \
  --enabled-state Enabled

# Enable caching
az afd route create \
  --resource-group tippr-rg \
  --profile-name tippr-afd \
  --endpoint-name tippr-endpoint \
  --route-name default-route \
  --origin-group tippr-origin-group \
  --patterns "/*" \
  --enable-caching true \
  --query-string-caching-behavior IgnoreQueryString
```

### Azure Blob Storage for Media

```ini
# production-azure.update - Azure Blob Storage
[DEFAULT]
media_provider = azure  # Requires implementing Azure provider

# Azure Blob Storage configuration
azure_storage_account = tipprstorageaccount
azure_storage_container = media
azure_storage_connection_string = DefaultEndpointsProtocol=https;AccountName=...
```

**Note**: The codebase has an S3 provider. You can use Azure Blob Storage's S3-compatible API or implement a native Azure provider.

```python
# Azure Blob with S3-compatible API (via Azurite or Azure Blob S3 proxy)
# Alternatively, implement native Azure provider in r2/r2/lib/providers/media/
from azure.storage.blob import BlobServiceClient

blob_service = BlobServiceClient.from_connection_string(connection_string)
container = blob_service.get_container_client("media")

def upload_media(filename, data):
    blob = container.get_blob_client(filename)
    blob.upload_blob(data, overwrite=True)
    return f"https://{account}.blob.core.windows.net/media/{filename}"
```

### Azure Production Configuration

```ini
# production-azure.update
[DEFAULT]
# CRITICAL: Disable debug mode
debug = false
template_debug = false
reload_templates = false
uncompressedJS = false
sqlprinting = false

# Production domain
domain = yourdomain.com
media_domain = media.yourdomain.com
https_endpoint = https://yourdomain.com

# Azure Database for PostgreSQL
db_user = tippr
db_pass = YOUR_SECURE_PASSWORD
db_port = 5432
databases = main, comment, email, authorize, award, hc, traffic
main_db = tippr, tippr-db.postgres.database.azure.com, *, *, *, *, *

# Azure Managed Cassandra
cassandra_seeds = tippr-cassandra-dc1.cassandra.cosmos.azure.com:10350
cassandra_ssl = true
cassandra_pool_size = 10
cassandra_rcl = LOCAL_QUORUM
cassandra_wcl = LOCAL_QUORUM

# Self-managed Memcached on AKS
lockcaches = memcached.default.svc.cluster.local:11211
permacache_memcaches = memcached.default.svc.cluster.local:11211
hardcache_memcaches = memcached.default.svc.cluster.local:11211

# RabbitMQ on AKS
amqp_host = tippr-rabbitmq.default.svc.cluster.local:5672
amqp_user = tippr
amqp_pass = YOUR_SECURE_PASSWORD

# Azure Blob Storage
media_provider = azure
azure_storage_account = tipprstorageaccount
azure_storage_container = media

# Security
trust_local_proxies = true
ENFORCE_RATELIMIT = true

# Monitoring (Azure Monitor)
statsd_addr = localhost:8125  # Use statsd-exporter sidecar with Azure Monitor
```

### Azure Monitoring & Observability

#### Azure Monitor + Log Analytics

```bash
# Create Log Analytics workspace
az monitor log-analytics workspace create \
  --resource-group tippr-rg \
  --workspace-name tippr-logs

# Enable diagnostic settings for PostgreSQL
az monitor diagnostic-settings create \
  --resource /subscriptions/.../tippr-db \
  --name tippr-db-diagnostics \
  --workspace tippr-logs \
  --logs '[{"category": "PostgreSQLLogs", "enabled": true}]' \
  --metrics '[{"category": "AllMetrics", "enabled": true}]'
```

#### Application Insights

```bash
# Create Application Insights
az monitor app-insights component create \
  --resource-group tippr-rg \
  --app tippr-insights \
  --location eastus \
  --workspace tippr-logs
```

### Azure Cost Estimation

For a medium-traffic deployment (~100K-500K daily active users):

| Service | Configuration | Est. Monthly Cost |
|---------|---------------|-------------------|
| Azure Database for PostgreSQL | D4s_v3, Zone-redundant HA | $300-400 |
| Azure Managed Cassandra | 3x D8s_v4 nodes | $800-1,000 |
| *OR* Astra DB on Azure | Serverless, ~100M ops/mo | $150-300 |
| Azure Cache for Redis | C3 Standard | $150-200 |
| *OR* Memcached on AKS | 3x pods (included in AKS) | $0 (AKS cost) |
| AKS Cluster | 3x D4s_v3 nodes | $350-450 |
| Application Gateway | Standard_v2, 2 units | $150-200 |
| Azure Front Door | Premium tier | $100-150 |
| Blob Storage | 100GB + CDN | $20-50 |
| **Total (with Managed Cassandra)** | | **$1,870-2,450/month** |
| **Total (with Astra DB)** | | **$1,220-1,750/month** |

**Notes**:
- Azure Hybrid Benefit can reduce costs if you have existing Windows Server/SQL licenses
- Reserved instances provide up to 72% savings for 1-3 year commitments
- Dev/Test pricing available for non-production environments

### Azure Deployment Checklist

- [ ] Create Resource Group and configure Azure subscription
- [ ] Set up Virtual Network with subnets (app, db, cache, aks)
- [ ] Provision Azure Database for PostgreSQL Flexible Server
- [ ] Set up Cassandra layer (choose one):
  - [ ] **Option A**: Create Azure Managed Instance for Apache Cassandra
  - [ ] **Option B**: Deploy DataStax Astra DB on Azure
  - [ ] **Option C**: Deploy self-managed Cassandra on AKS
- [ ] Set up caching layer:
  - [ ] **Option A**: Create Azure Cache for Redis (requires code changes)
  - [ ] **Option B**: Deploy self-managed Memcached on AKS
- [ ] Deploy RabbitMQ on AKS (using RabbitMQ Cluster Operator)
- [ ] Create Azure Blob Storage account and containers
- [ ] Configure Application Gateway with WAF
- [ ] Set up Azure Front Door + CDN
- [ ] Configure Azure Key Vault for secrets
- [ ] Create AKS cluster or VM Scale Set
- [ ] Set up Azure Monitor and Log Analytics
- [ ] Configure autoscaling policies
- [ ] Set up Azure DDoS Protection (optional)
- [ ] Configure Private Link for all services

---

## Caching Layer

### Amazon ElastiCache for Memcached

Tippr heavily relies on memcached for performance. The caching layer handles:
- Page fragment caching
- Query result caching
- Session data
- Rate limiting counters
- Lock coordination

#### Configuration

```ini
# production.update - ElastiCache configuration
[DEFAULT]
# ElastiCache cluster nodes (configuration endpoint for cluster mode)
lockcaches = your-cache.xxxxx.cfg.use1.cache.amazonaws.com:11211
permacache_memcaches = your-cache.xxxxx.cfg.use1.cache.amazonaws.com:11211
hardcache_memcaches = your-cache.xxxxx.cfg.use1.cache.amazonaws.com:11211

# Increase client pool for production
num_mc_clients = 20

# Enable mcrouter for consistent hashing (optional but recommended)
mcrouter_addr = 127.0.0.1:5050
```

#### ElastiCache Cluster Sizing

| Traffic Level | Node Type | Nodes | Total Memory |
|---------------|-----------|-------|--------------|
| Low | cache.t3.medium | 2 | 6.4GB |
| Medium | cache.r6g.large | 3-5 | 39-65GB |
| High | cache.r6g.xlarge | 5-10 | 130-260GB |

#### Caching Strategy from Tippr's Experience

1. **Batch memcache calls**: Network latency on cloud is higher than datacenter. Batch multiple gets into single requests
2. **Use consistent hashing**: Prevents cache invalidation when scaling cluster
3. **Separate cache tiers**: Use different clusters for different purposes (locks, permacache, stalecache)
4. **Aggressive caching for logged-out users**: Serve fully cached pages to anonymous users via CDN

```ini
# Enable stale cache for non-critical data (improves resilience)
stalecaches = your-stale-cache.xxxxx.cfg.use1.cache.amazonaws.com:11211
```

---

## Message Queue

### Amazon MQ for RabbitMQ

Tippr uses RabbitMQ for async job processing: votes, comments, scraping, search indexing.

#### Configuration

```ini
# production.update - Amazon MQ configuration
[DEFAULT]
amqp_host = b-xxxxx.mq.us-east-1.amazonaws.com:5671
amqp_user = tippr
amqp_pass = YOUR_SECURE_PASSWORD
amqp_virtual_host = /tippr

# Enable SSL for Amazon MQ
amqp_ssl = true

# Enable AMQP logging for production monitoring
amqp_logging = true
```

#### Queue Consumer Scaling

Scale queue consumers based on queue depth. Production consumer counts:

```bash
# /home/tippr/consumer-count.d/
echo 5 > commentstree_q    # Parallelize comment tree processing
echo 3 > vote_link_q       # Handle vote processing
echo 3 > vote_comment_q
echo 2 > scraper_q         # Thumbnail/embed scraping
echo 2 > butler_q          # User mentions
echo 1 > del_account_q
echo 1 > markread_q
```

From Tippr's experience: **Put everything into a queue**. Queues:
- Buffer traffic spikes
- Allow monitoring via queue length
- Hide temporary failures from users
- Enable horizontal scaling of workers

---

## Application Servers

### Gunicorn Configuration

Replace development paster server with production Gunicorn:

```ini
# production.update
[server:main]
use = egg:gunicorn#main
host = 0.0.0.0
port = 8001
workers = 4
worker_class = sync
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 50
```

#### Worker Calculation

```
workers = (2 * CPU_cores) + 1
```

For c5.xlarge (4 vCPUs): `workers = 9`

### Systemd Service (Production)

```ini
# /etc/systemd/system/tippr-app.service
[Unit]
Description=Tippr Application Server
After=network.target

[Service]
Type=simple
User=tippr
Group=tippr
WorkingDirectory=/home/tippr/src/tippr/r2
Environment=PYTHONPATH=/home/tippr/src/tippr:/home/tippr/src
Environment=PATH=/home/tippr/venv/bin:/usr/bin
ExecStart=/home/tippr/venv/bin/gunicorn \
    --bind 0.0.0.0:8001 \
    --workers 4 \
    --timeout 30 \
    --access-logfile /var/log/tippr/access.log \
    --error-logfile /var/log/tippr/error.log \
    'r2.config.middleware:make_app()'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Auto Scaling Group

Use AWS Auto Scaling with:
- Launch template with pre-baked AMI
- Scaling policies based on CPU or request count
- Health checks via ALB
- Minimum 2 instances for availability

---

## Load Balancing & Reverse Proxy

### Application Load Balancer (ALB)

Replace local HAProxy with ALB for production:

```
Target Groups:
- tippr-app (port 8001) - Main application
- tippr-websockets (port 9001) - WebSocket connections
- tippr-media (port 9000) - Static/media files (or use S3/CloudFront)
```

#### Routing Rules

| Path Pattern | Target |
|--------------|--------|
| `/websocket/*` | tippr-websockets |
| `/media/*` | S3 via CloudFront |
| `/pixel/*` | tippr-pixel (or Lambda@Edge) |
| `/*` | tippr-app |

### CloudFront CDN

**Critical for performance**: Serve cached content to logged-out users via CDN.

From Tippr's experience: By serving logged-out users (80% of traffic) cached content from CDN:
- Reduces load on application servers dramatically
- Provides geographic edge caching
- Handles traffic spikes gracefully
- If Tippr goes down, logged-out users may never notice

```
CloudFront Configuration:
- Origin: ALB
- Cache behaviors:
  - /static/* -> Cache TTL 1 year (versioned assets)
  - /media/* -> Cache TTL 1 day
  - Default -> Cache for logged-out users, bypass for logged-in
```

---

## Configuration Changes for Production

Create `production.update` file to override development defaults:

```ini
# production.update
[DEFAULT]
# CRITICAL: Disable debug mode
debug = false
template_debug = false
reload_templates = false
uncompressedJS = false
sqlprinting = false

# Production domain
domain = yourdomain.com
media_domain = media.yourdomain.com
https_endpoint = https://yourdomain.com
payment_domain = https://pay.yourdomain.com

# Security
trust_local_proxies = true  # If behind ALB
cdn_provider = cloudflare   # or custom

# Media storage
media_provider = s3
S3KEY_ID = YOUR_AWS_KEY
S3SECRET_KEY = YOUR_AWS_SECRET
s3_media_buckets = your-media-bucket
s3_image_buckets = your-image-bucket
s3_media_domain = s3.amazonaws.com

# Disable dev-only features
disable_captcha = false
disable_ratelimit = false
disable_require_admin_otp = false

# Enable rate limiting
ENFORCE_RATELIMIT = true
RL_SITEWIDE_ENABLED = true

# Search (if using CloudSearch)
search_provider = cloudsearch
CLOUDSEARCH_SEARCH_API = https://search-xxx.us-east-1.cloudsearch.amazonaws.com
CLOUDSEARCH_DOC_API = https://doc-xxx.us-east-1.cloudsearch.amazonaws.com

# Monitoring
statsd_addr = your-statsd-host:8125
statsd_sample_rate = 0.1
amqp_logging = true

# Email
email_provider = mailgun
mailgun_api_base_url = https://api.mailgun.net/v3
```

Generate production.ini:
```bash
cd /home/tippr/src/tippr/r2
make ini  # Creates production.ini from example.ini + production.update
```

---

## Scaling Lessons from Reddit's History

> **Note**: These lessons come from Reddit's engineering team's experience scaling the original codebase from 1 million to 1 billion pageviews. While Tippr is a fork with modernizations, these architectural principles remain relevant.
>
> **Source**: [Reddit's scaling talk by Jeremy Edberg](https://www.youtube.com/watch?v=nUcO7n4hek4)

### 1. Plan for Scale, But Don't Over-Engineer Early

> "It's not necessary to build a scalable architecture from the start. You don't know what your feature set will be."

Start with managed services, identify bottlenecks as they appear, then optimize.

### 2. Use SSDs for Databases

> "Think of SSDs as cheap RAM, not expensive disk. Tippr reduced from 12 database servers to 1 with tons of headroom."

Always use SSD-backed storage (gp3, io1) for RDS and any self-managed databases.

### 3. Batch Network Calls

> "In the datacenter they had submillisecond memcache access. EC2 has 10x higher latency."

The codebase already batches memcache calls, but ensure:
- Use `get_multi()` instead of multiple `get()` calls
- Batch database queries where possible
- Use connection pooling

### 4. Separate Traffic by Speed

> "Use a proxy to route slow traffic one place and fast traffic another."

Monitor response times by endpoint. Route slow operations (search, heavy listings) to dedicated worker pools.

### 5. Put Limits on Everything

> "Everything that can happen repeatedly put a high limit on it."

```ini
# production.update - Limits
sr_banned_quota = 10000
sr_moderator_invite_quota = 10000
max_sr_images = 50
max_comments = 500
wiki_max_page_length_bytes = 262144
```

### 6. Expire Old Data

> "Lock out old threads and create a fully rendered page and cache it."

Tippr archives threads after 6 months. This:
- Prevents unbounded data growth
- Allows aggressive caching of old content
- Reduces database load

### 7. Treat Logged-Out Users as Second-Class Citizens

> "By always giving logged-out users cached content, Akamai bears the brunt of traffic."

- Serve fully cached pages to anonymous users via CDN
- Don't compute personalized content for logged-out users
- 80% of traffic can be served from cache

### 8. Cassandra for Fast Negative Lookups

> "Cassandra's bloom filters enabled really fast negative lookups for comments."

Use Cassandra/Keyspaces for:
- Vote data (fast to check "what haven't I voted on")
- Activity tracking
- Time-series data

### 9. Keep Postgres for Money

> "Everything that deals with money is kept in a relational database because of transactions and easier analytics."

Use RDS PostgreSQL for:
- User accounts
- Gold subscriptions
- Payment history
- Anything requiring ACID transactions

### 10. Let Users Do the Work

> "Thousands of volunteer moderators take care of most of the spam problem."

This is an architectural principle: design for user-generated moderation rather than costly automated systems.

---

## Monitoring & Observability

### Metrics (StatsD/CloudWatch)

```ini
# production.update
statsd_addr = your-statsd-host:8125
statsd_sample_rate = 0.1  # Sample 10% of requests
stats_sample_rate = 10    # 10% of events
```

Key metrics to monitor:
- Request latency (p50, p95, p99)
- Error rates by endpoint
- Queue depths (RabbitMQ)
- Cache hit rates
- Database connection pool usage
- Active user counts

### Logging

```ini
# production.update
[logger_root]
level = INFO
handlers = console, syslog

[handler_syslog]
class = handlers.SysLogHandler
args = ('/dev/log', handlers.SysLogHandler.LOG_USER)
formatter = tippr
```

Ship logs to CloudWatch Logs or ELK stack.

### Alerting

Set up alerts for:
- Queue depth > threshold (jobs backing up)
- Error rate > 1%
- Response time p95 > 2s
- Database connections near max
- Cache hit rate < 90%

---

## Security Considerations

### Secrets Management

```ini
# Use AWS Secrets Manager or Parameter Store
# Never commit secrets to code

# production.update
liveconfig_source = zookeeper  # or secrets manager
secrets_source = zookeeper
```

### Network Security

```
VPC Configuration:
- Public subnets: ALB only
- Private subnets: Application servers, databases
- Database security groups: Only allow app server access
- Use VPC endpoints for AWS services
```

### Authentication

```ini
# production.update
bcrypt_work_factor = 12  # Increase if hardware allows
ADMIN_COOKIE_TTL = 32400
ADMIN_COOKIE_MAX_IDLE = 900
disable_require_admin_otp = false  # Require OTP for admins
```

### HTTPS

```ini
# Force HTTPS in production
feature_force_https = on
feature_https_redirect = on
feature_upgrade_cookies = on
```

---

## Deployment Checklist

### Pre-Launch

- [ ] Provision RDS PostgreSQL Multi-AZ
- [ ] Provision Amazon Keyspaces or Cassandra cluster
- [ ] Provision ElastiCache Memcached cluster
- [ ] Provision Amazon MQ for RabbitMQ
- [ ] Configure S3 buckets for media storage
- [ ] Set up CloudFront distribution
- [ ] Configure ALB with target groups
- [ ] Create production.update with all settings
- [ ] Generate and test production.ini
- [ ] Set up VPC with proper security groups
- [ ] Configure secrets in Secrets Manager
- [ ] Set up monitoring and alerting
- [ ] Create AMI with application pre-installed
- [ ] Configure Auto Scaling group
- [ ] Set up CI/CD pipeline

### Launch

- [ ] Migrate database schema to RDS
- [ ] Create Keyspaces keyspace and tables
- [ ] Deploy application to ASG
- [ ] Verify health checks passing
- [ ] Test all major user flows
- [ ] Enable CloudFront caching
- [ ] Monitor error rates and latency

### Post-Launch

- [ ] Review and tune cache hit rates
- [ ] Analyze slow queries and optimize
- [ ] Right-size instance types based on actual usage
- [ ] Enable detailed monitoring
- [ ] Document runbooks for common issues
- [ ] Schedule regular backups verification

---

## Cost Estimation (Starting Point)

For a medium-traffic deployment (~100K-500K daily active users):

| Service | Configuration | Est. Monthly Cost |
|---------|---------------|-------------------|
| RDS PostgreSQL | db.r6g.large Multi-AZ | $300-400 |
| Amazon Keyspaces | On-demand, ~10M reads/writes/day | $50-150 |
| ElastiCache | 3x cache.r6g.large | $300-400 |
| Amazon MQ | mq.m5.large | $150-200 |
| EC2 (App Servers) | 3x c5.xlarge | $400-500 |
| ALB | Standard | $20-50 |
| CloudFront | 1TB transfer | $100-200 |
| S3 | 100GB storage | $5-10 |
| **Total** | | **$1,325-1,910/month** |

Costs scale with traffic. Start small and scale up based on actual usage.

---

## Cloud Provider Comparison

### Feature Comparison Matrix

| Feature | AWS | GCP | Azure | Notes |
|---------|-----|-----|-------|-------|
| **PostgreSQL** | RDS | Cloud SQL | Azure DB for PostgreSQL | All excellent, mature options |
| **Cassandra (CQL)** | Keyspaces | Astra DB | Managed Cassandra | All CQL-compatible, minimal code changes |
| **Memcached** | ElastiCache | Memorystore | Self-managed on AKS | Azure lacks managed Memcached |
| **RabbitMQ** | Amazon MQ | Self-managed | Self-managed | Only AWS offers managed RabbitMQ |
| **Kubernetes** | EKS | GKE | AKS | GKE > AKS > EKS for ease of use |
| **Load Balancing** | ALB/NLB | Cloud LB | App Gateway/Front Door | All capable; Azure Front Door excellent globally |
| **CDN** | CloudFront | Cloud CDN | Azure CDN/Front Door | All comparable |
| **Hybrid Cloud** | Outposts | Anthos | Azure Arc | Azure strongest for hybrid/on-prem |
| **Enterprise Integration** | Good | Good | Excellent | Azure best for Microsoft shops |
| **Pricing** | Pay-as-you-go | Sustained use discounts | Reserved + Hybrid Benefit | GCP/Azure offer more discount options |
| **AI/ML** | SageMaker, Bedrock | Vertex AI, BigQuery | Azure OpenAI, Cognitive Services | All strong; Azure has OpenAI partnership |

### When to Choose AWS

**Choose AWS if:**

1. **Minimal code changes**: Amazon Keyspaces provides CQL compatibility, meaning the existing Cassandra code works with configuration changes only
2. **Managed RabbitMQ**: Amazon MQ is a drop-in replacement for self-hosted RabbitMQ
3. **S3 integration**: The codebase already has an S3 media provider
4. **Existing AWS infrastructure**: Easier to integrate with existing AWS resources
5. **Enterprise support needs**: AWS has a larger partner ecosystem

**AWS Strengths for Tippr:**
- Keyspaces = no code changes for Cassandra layer
- Amazon MQ = no code changes for queue layer
- S3 provider already exists in codebase
- Broader managed service options

### When to Choose GCP

**Choose GCP if:**

1. **Kubernetes-native deployment**: GKE is generally considered superior to EKS
2. **Cost optimization priority**: Sustained use discounts and committed use pricing
3. **Network-intensive workloads**: GCP's network is often faster, especially globally
4. **AI/ML integration**: Need BigQuery, Vertex AI, or vector search capabilities
5. **Multi-cloud strategy**: Astra DB works across GCP, AWS, and Azure

**GCP Strengths for Tippr:**
- GKE is excellent for container orchestration
- Better sustained use pricing for always-on workloads
- Cloud SQL is very reliable
- Simpler IAM model
- Stronger global network backbone
- DataStax Astra DB provides CQL compatibility (no code changes needed)
- Native BigQuery integration for analytics on Cassandra data

### When to Choose Azure

**Choose Azure if:**

1. **Enterprise/Microsoft ecosystem**: Already using Azure AD, Office 365, or other Microsoft services
2. **Hybrid cloud requirements**: Need to connect to on-premises data centers with Azure Arc
3. **CQL compatibility needed**: Azure Managed Instance for Apache Cassandra is fully CQL-compatible
4. **Compliance requirements**: Azure has extensive compliance certifications (FedRAMP, HIPAA, etc.)
5. **Windows workloads**: Running any Windows-based components alongside Tippr

**Azure Strengths for Tippr:**
- Azure Managed Cassandra = no code changes for Cassandra layer
- Strong enterprise security and compliance features
- Azure Front Door provides excellent global load balancing
- AKS is a solid Kubernetes option with good Azure integration
- Hybrid Benefit can significantly reduce costs with existing licenses
- Azure OpenAI for AI-powered features

**Azure Considerations:**
- No managed Memcached (must self-host or switch to Redis)
- No managed RabbitMQ (must self-host on AKS)
- Requires implementing Azure Blob provider for media storage

### Cost Comparison Summary

| Deployment Size | AWS | GCP + Astra DB | GCP + Bigtable | Azure + Managed Cassandra | Azure + Astra DB |
|-----------------|-----|----------------|----------------|---------------------------|------------------|
| Low traffic | $800-1,200/mo | $700-1,000/mo | $1,200-1,500/mo | $900-1,300/mo | $700-1,000/mo |
| Medium traffic | $1,325-1,910/mo | $1,200-1,700/mo | $2,200-2,750/mo | $1,870-2,450/mo | $1,220-1,750/mo |
| High traffic | $3,000-5,000/mo | $2,500-4,000/mo | $4,500-6,000/mo | $4,000-6,000/mo | $2,800-4,500/mo |

**Notes**:
- **AWS**: Consistent pricing, all managed services, minimal code changes
- **GCP + Astra DB**: Best balance of ease and cost; serverless pricing scales with usage
- **GCP + Bigtable**: Most expensive but scales to petabyte-level workloads
- **Azure + Managed Cassandra**: Good for enterprise; higher base cost but Hybrid Benefit can reduce
- **Azure + Astra DB**: Best Azure option for cost; Astra DB is multi-cloud

### Migration Effort Comparison

| Component | AWS | GCP + Astra DB | Azure + Managed Cassandra | Azure + Astra DB |
|-----------|-----|----------------|---------------------------|------------------|
| PostgreSQL | Low (config) | Low (config) | Low (config) | Low (config) |
| Cassandra | Low (config + SSL) | Low (config + SSL) | Low (config + SSL) | Low (config + SSL) |
| Memcached | Low (config) | Low (config) | Medium (self-managed) | Medium (self-managed) |
| RabbitMQ | Low (config + SSL) | Medium (self-managed) | Medium (self-managed) | Medium (self-managed) |
| Media Storage | None (S3 exists) | Low (S3-compat API) | Medium (new provider) | Medium (new provider) |
| **Overall** | **Low** | **Low-Medium** | **Medium** | **Medium** |

### Recommendation

**For fastest time-to-production**: Choose **AWS**
- All managed services available (Keyspaces, Amazon MQ, ElastiCache)
- S3 provider already exists in codebase
- Minimal code changes required

**For cost optimization with managed services**: Choose **GCP + Astra DB** or **Azure + Astra DB**
- Astra DB serverless pricing scales with usage
- GCP sustained use discounts / Azure Hybrid Benefit reduce costs
- Astra DB works across all three clouds for multi-cloud flexibility

**For enterprise/hybrid deployments**: Choose **Azure**
- Best integration with Microsoft ecosystem (Azure AD, Office 365)
- Azure Arc for hybrid cloud scenarios
- Strong compliance certifications
- Azure Managed Cassandra is fully CQL-compatible

**For maximum scalability**: Choose **GCP with Bigtable**
- Bigtable scales to petabytes with consistent performance
- Requires significant code refactoring
- Best for Reddit-scale traffic (billions of requests)

**For AI/ML workloads**: Choose based on AI platform preference
- **Azure**: Azure OpenAI Service for GPT-4 integration
- **GCP**: Vertex AI + BigQuery + Astra Vector Search
- **AWS**: Amazon Bedrock + SageMaker

### Hybrid Considerations

You could also consider:
- **Multi-cloud with Astra DB**: Use Astra DB (available on all three clouds) for database portability
- **Gradual migration**: Start on AWS (easiest), migrate to GCP/Azure later for cost savings
- **Disaster recovery**: Use one cloud as primary, another as DR
- **Geographic distribution**: Use different clouds in different regions based on presence

---

## Additional Resources

### AWS Resources
- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [Amazon Keyspaces Documentation](https://docs.aws.amazon.com/keyspaces/)
- [Amazon RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)
- [Amazon MQ for RabbitMQ](https://docs.aws.amazon.com/amazon-mq/latest/developer-guide/welcome.html)

### GCP Resources
- [Google Cloud Architecture Framework](https://cloud.google.com/architecture/framework)
- [Cloud SQL for PostgreSQL](https://cloud.google.com/sql/docs/postgres)
- [Cloud Bigtable Documentation](https://cloud.google.com/bigtable/docs)
- [GKE Best Practices](https://cloud.google.com/kubernetes-engine/docs/best-practices)
- [Memorystore for Memcached](https://cloud.google.com/memorystore/docs/memcached)

### Azure Resources
- [Azure Well-Architected Framework](https://docs.microsoft.com/azure/architecture/framework/)
- [Azure Database for PostgreSQL](https://docs.microsoft.com/azure/postgresql/)
- [Azure Managed Instance for Apache Cassandra](https://docs.microsoft.com/azure/managed-instance-apache-cassandra/)
- [Azure Kubernetes Service (AKS)](https://docs.microsoft.com/azure/aks/)
- [Azure Cache for Redis](https://docs.microsoft.com/azure/azure-cache-for-redis/)
- [Azure Front Door](https://docs.microsoft.com/azure/frontdoor/)
- [Azure Blob Storage](https://docs.microsoft.com/azure/storage/blobs/)

### DataStax Astra DB Resources
- [Astra DB Documentation](https://docs.datastax.com/en/astra/docs/)
- [Astra DB on Google Cloud](https://www.datastax.com/products/datastax-astra/google-cloud)
- [Python Driver for Astra DB](https://docs.datastax.com/en/developer/python-driver/latest/cloud/)
- [Astra DB + BigQuery Integration](https://docs.datastax.com/en/astra/docs/integrations/google-bigquery.html)
- [Astra Vector Search](https://docs.datastax.com/en/astra/docs/vector-search-overview.html)

### Reddit Scaling Resources
- [Original Reddit Scaling Talk](https://www.youtube.com/watch?v=nUcO7n4hek4) - Jeremy Edberg at RAMP Conference
- [High Scalability - Reddit Lessons](http://highscalability.com/blog/2013/8/26/reddit-lessons-learned-from-mistakes-made-scaling-to-1-billi.html)
- [Reddit Engineering (RedditEng subreddit)](https://www.reddit.com/r/RedditEng/)

---

## Kubernetes-Native Deployment

For production-grade deployments across any cloud provider, Kubernetes provides consistent orchestration. This section provides a cloud-agnostic Kubernetes approach.

### Why Kubernetes?

| Advantage | Description |
|-----------|-------------|
| **Automatic failover** | Self-healing restarts failed containers |
| **Zero-downtime updates** | Rolling deployments with health checks |
| **Horizontal autoscaling** | Scale based on CPU, memory, or custom metrics |
| **Resource efficiency** | Better bin-packing than VM-per-service |
| **Service discovery** | Built-in DNS and load balancing |
| **Portability** | Same manifests work on EKS, GKE, AKS, or self-hosted |

### Helm Chart Structure

```yaml
# Chart.yaml
apiVersion: v2
name: tippr
version: 1.0.0
description: Tippr application deployment

dependencies:
  - name: postgresql
    version: "12.x.x"
    repository: "https://charts.bitnami.com/bitnami"
    condition: postgresql.enabled
  - name: rabbitmq
    version: "11.x.x"
    repository: "https://charts.bitnami.com/bitnami"
    condition: rabbitmq.enabled
  - name: memcached
    version: "6.x.x"
    repository: "https://charts.bitnami.com/bitnami"
    condition: memcached.enabled
```

```yaml
# values.yaml
replicaCount: 3

image:
  repository: your-registry/tippr
  tag: latest
  pullPolicy: IfNotPresent

# External managed database (recommended for production)
database:
  external: true
  host: tippr-db.xxx.rds.amazonaws.com
  port: 5432
  name: tippr
  ssl: true
  existingSecret: tippr-db-credentials

# External Cassandra/Keyspaces
cassandra:
  external: true
  seeds: cassandra.us-east-1.amazonaws.com:9142
  ssl: true
  existingSecret: tippr-cassandra-credentials

# Local memcached (low latency is important)
memcached:
  enabled: true
  replicaCount: 3
  resources:
    requests:
      memory: 1Gi
    limits:
      memory: 2Gi

# Local RabbitMQ (or external Amazon MQ)
rabbitmq:
  enabled: true
  replicaCount: 3
  auth:
    existingPasswordSecret: tippr-rabbitmq-credentials

# Autoscaling
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 20
  targetCPUUtilization: 70
  targetMemoryUtilization: 80

# Ingress
ingress:
  enabled: true
  className: nginx  # or alb, gce, azure
  hosts:
    - host: tippr.net
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: tippr-tls
      hosts:
        - tippr.net

# Resources
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "2"
    memory: "4Gi"
```

### Application Deployment Manifest

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "tippr.fullname" . }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      app: tippr
  template:
    metadata:
      labels:
        app: tippr
    spec:
      containers:
      - name: tippr
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        ports:
        - containerPort: 8001
        env:
        - name: PYTHONPATH
          value: "/app/tippr:/app"
        - name: DB_HOST
          valueFrom:
            secretKeyRef:
              name: tippr-db-credentials
              key: host
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: tippr-db-credentials
              key: password
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 10
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 30
          periodSeconds: 10
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "tippr.fullname" . }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "tippr.fullname" . }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: {{ .Values.autoscaling.targetCPUUtilization }}
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: {{ .Values.autoscaling.targetMemoryUtilization }}
```

### Deployment Commands

```bash
# Add Bitnami repo for dependencies
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Install with managed databases (production recommended)
helm install tippr ./tippr-chart \
  --namespace tippr \
  --create-namespace \
  --set database.external=true \
  --set cassandra.external=true \
  --set-file secrets.dbPassword=./secrets/db-password.txt

# Install with all local services (development/testing)
helm install tippr ./tippr-chart \
  --namespace tippr \
  --create-namespace \
  --set postgresql.enabled=true \
  --set database.external=false

# Upgrade with new image
helm upgrade tippr ./tippr-chart \
  --namespace tippr \
  --set image.tag=v1.2.3

# Rollback if needed
helm rollback tippr 1 --namespace tippr
```

---

## Migration from Development to Production

If you started with `install-tippr.sh` and need to move to production, follow this guide.

### Phase 1: Data Export (on development machine)

```bash
# 1. Stop the application to ensure consistent data
sudo systemctl stop tippr-app

# 2. Export PostgreSQL
pg_dump -U tippr -h localhost tippr > tippr_dev_backup.sql

# 3. Export Cassandra data (for each table)
cqlsh localhost 9042 -e "COPY tippr.votes TO 'votes.csv' WITH HEADER=TRUE;"
cqlsh localhost 9042 -e "COPY tippr.activity TO 'activity.csv' WITH HEADER=TRUE;"

# 4. Package media files (if stored locally)
tar -czvf media_backup.tar.gz /var/lib/tippr/media/

# 5. Backup configuration
cp /home/tippr/src/tippr/r2/production.ini production.ini.backup
```

### Phase 2: Cloud Setup

**For AWS:**
```bash
# Create RDS PostgreSQL
aws rds create-db-instance \
  --db-instance-identifier tippr-prod \
  --db-instance-class db.t3.medium \
  --engine postgres \
  --master-username tippr \
  --master-user-password YOUR_PASSWORD \
  --allocated-storage 100 \
  --multi-az

# Wait for RDS to be available
aws rds wait db-instance-available --db-instance-identifier tippr-prod

# Get endpoint
aws rds describe-db-instances --db-instance-identifier tippr-prod \
  --query 'DBInstances[0].Endpoint.Address' --output text
```

### Phase 3: Data Import

```bash
# Import PostgreSQL to RDS
psql -h tippr-prod.xxx.rds.amazonaws.com -U tippr -d tippr < tippr_dev_backup.sql

# Import Cassandra to Keyspaces (use smaller batches)
cqlsh cassandra.us-east-1.amazonaws.com 9142 --ssl \
  -e "COPY tippr.votes FROM 'votes.csv' WITH HEADER=TRUE AND MAXBATCHSIZE=10;"

# Upload media to S3
aws s3 sync /var/lib/tippr/media/ s3://your-tippr-media-bucket/
```

### Phase 4: Application Configuration

Create `production.update` with cloud endpoints:

```ini
[DEFAULT]
debug = false

# Cloud database
db_user = tippr
db_pass = YOUR_RDS_PASSWORD
main_db = tippr, tippr-prod.xxx.rds.amazonaws.com, *, *, *, *, *
db_ssl = true

# Cloud Cassandra
cassandra_seeds = cassandra.us-east-1.amazonaws.com:9142
cassandra_ssl = true

# Cloud media storage
media_provider = s3
s3_media_buckets = your-tippr-media-bucket
```

### Phase 5: Verification Checklist

- [ ] Database connection works: `psql -h <rds-endpoint> -U tippr -c "SELECT 1"`
- [ ] Cassandra connection works: `cqlsh <keyspaces-endpoint> 9142 --ssl -e "DESCRIBE KEYSPACES"`
- [ ] Application starts without errors
- [ ] Login/logout works
- [ ] Posting and voting works
- [ ] Media uploads work
- [ ] All background jobs are processing (check queue depths)

### Phase 6: DNS Cutover

```bash
# Update DNS to point to production load balancer
# Reduce TTL beforehand (e.g., to 300 seconds)
# Monitor closely for 24-48 hours after cutover
```

---

## Backup & Disaster Recovery

### Backup Strategy

| Component | Backup Method | Frequency | Retention |
|-----------|--------------|-----------|-----------|
| PostgreSQL | RDS automated snapshots | Daily | 30 days |
| PostgreSQL | Manual snapshots | Before major changes | 90 days |
| Cassandra/Keyspaces | Point-in-time recovery | Continuous | 35 days |
| Media (S3) | Cross-region replication | Real-time | Indefinite |
| Configuration | Git repository | Every change | Indefinite |

### PostgreSQL Backup (RDS)

```bash
# Enable automated backups (during RDS creation or modify)
aws rds modify-db-instance \
  --db-instance-identifier tippr-prod \
  --backup-retention-period 30 \
  --preferred-backup-window "03:00-04:00"

# Create manual snapshot before risky changes
aws rds create-db-snapshot \
  --db-instance-identifier tippr-prod \
  --db-snapshot-identifier tippr-pre-migration-$(date +%Y%m%d)

# Restore from snapshot (creates new instance)
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier tippr-restored \
  --db-snapshot-identifier tippr-pre-migration-20240115
```

### Cassandra/Keyspaces Backup

Amazon Keyspaces provides Point-in-Time Recovery (PITR):

```bash
# Enable PITR on a table
aws keyspaces update-table \
  --keyspace-name tippr \
  --table-name votes \
  --point-in-time-recovery status=ENABLED

# Restore to a point in time (creates new table)
aws keyspaces restore-table \
  --source-keyspace-name tippr \
  --source-table-name votes \
  --target-keyspace-name tippr \
  --target-table-name votes_restored \
  --restore-timestamp 2024-01-15T12:00:00Z
```

### Media Backup (S3)

```bash
# Enable versioning
aws s3api put-bucket-versioning \
  --bucket your-tippr-media \
  --versioning-configuration Status=Enabled

# Enable cross-region replication
aws s3api put-bucket-replication \
  --bucket your-tippr-media \
  --replication-configuration file://replication-config.json
```

### Disaster Recovery Runbook

**RTO (Recovery Time Objective)**: 4 hours
**RPO (Recovery Point Objective)**: 1 hour

| Scenario | Recovery Steps | Estimated Time |
|----------|----------------|----------------|
| Single AZ failure | Automatic RDS failover | 1-2 minutes |
| Application bug | Rollback deployment | 5-10 minutes |
| Database corruption | Restore from snapshot | 30-60 minutes |
| Region outage | Promote DR region | 2-4 hours |
| Accidental deletion | Restore from backup | 30-60 minutes |

### Recovery Testing

Schedule quarterly DR tests:

```markdown
## DR Test Checklist

1. [ ] Restore PostgreSQL from 24-hour-old snapshot to test instance
2. [ ] Verify data integrity with checksums
3. [ ] Restore Cassandra table from PITR
4. [ ] Test application against restored databases
5. [ ] Document recovery time and any issues
6. [ ] Update runbooks based on findings
```

---

## Self-Hosted Production Deployment

## Hybrid Deployment Strategy

This section describes a hybrid deployment approach that combines local (on-prem) compute and caching with cloud-managed storage and databases. The goal is to keep latency-sensitive services local while moving durable storage and backups to the cloud to reduce operational risk.

### Hybrid Architecture Diagram

```
                     ┌──────────────────────────────────┐
                     │            CLOUD                 │
                     │                                  │
                     │  ┌───────────┐  ┌───────────┐   │
                     │  │ Managed   │  │  Object   │   │
                     │  │ Database  │  │  Storage  │   │
                     │  │(Postgres) │  │ (S3/GCS)  │   │
                     │  └───────────┘  └───────────┘   │
                     │                                  │
                     │  ┌───────────┐                   │
                     │  │  Backups  │                   │
                     │  │(Optional) │                   │
                     │  └───────────┘                   │
                     └────────────┬─────────────────────┘
                                  │ VPN/Direct Connect
                                  │
┌─────────────────────────────────┼─────────────────────────────────┐
│                          LOCAL  │                                 │
│                                 │                                 │
│  ┌──────────┐    ┌──────────────┴──────────────┐                 │
│  │ pfSense  │───▶│       App Servers           │                 │
│  │ HAProxy  │    │    (192.168.1.101-103)      │                 │
│  └──────────┘    └──────────────┬──────────────┘                 │
│                                 │                                 │
│              ┌──────────────────┼──────────────────┐             │
│              ▼                  ▼                  ▼             │
│       ┌───────────┐      ┌───────────┐      ┌──────────┐        │
│       │ Memcached │      │ RabbitMQ  │      │  Redis   │        │
│       └───────────┘      └───────────┘      └──────────┘        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Priority Order: What to Cloud First

#### 1. Object Storage (S3/GCS/Azure Blob) - Do This First

**Why first:**
- Extremely cheap (~$0.02/GB/month)
- Zero maintenance
- Built-in CDN integration
- Offloads bandwidth from your home connection
- No migration pain - just configure and use

**Cost:** $5-20/month for typical usage

**Example `production.update` snippet for media storage:**

```ini
# production.update
media_provider = s3
S3KEY_ID = YOUR_KEY
S3SECRET_KEY = YOUR_SECRET
s3_media_buckets = your-tippr-media
s3_media_domain = s3.amazonaws.com
# Or use Cloudflare R2 (S3-compatible, no egress fees)
s3_media_domain = your-account.r2.cloudflarestorage.com
```

#### 2. PostgreSQL (RDS/Cloud SQL) - High Value, Moderate Cost

**Why second:**
- Hardest to manage yourself (backups, replication, failover)
- Data loss here is catastrophic
- Automatic backups, point-in-time recovery
- Easy read replicas when you need them
- Connection from local servers works fine over internet/VPN

**Cost:** $50-150/month (smallest production tier)

**Provider comparison (small production tiers):**

| Provider | Smallest Production Tier | Monthly Cost |
|----------|-------------------------|--------------|
| AWS RDS | db.t3.small (2GB RAM) | ~$50-70 |
| GCP Cloud SQL | db-custom-1-3840 | ~$40-60 |
| Azure PostgreSQL | Burstable B1ms | ~$35-50 |
| Neon (Serverless) | Free tier + usage | ~$0-25 |
| Supabase | Pro plan | ~$25 |

**Budget Option: Neon or Supabase**
- Serverless PostgreSQL with generous free tiers
- Pay only for what you use
- Great for lower traffic

**Example `production.update` for Neon:**

```ini
# production.update for Neon
main_db = tippr, ep-cool-darkness-123456.us-east-2.aws.neon.tech, *, *, *, *, *
db_port = 5432
# Neon requires SSL
db_ssl = true
```

#### 3. Backups to Cloud Storage - Essential, Cheap

Even if you keep databases local initially, back up to cloud.

**Cost:** $5-10/month

| Provider | Cost | Notes |
|----------|------|-------|
| Backblaze B2 | $0.005/GB | Cheapest, S3-compatible |
| Wasabi | $0.0059/GB | No egress fees |
| Cloudflare R2 | $0.015/GB | No egress fees |

### What to Keep Local (Cost Savings)

#### Keep Local: Memcached/Redis

**Why:**
- Latency-sensitive (cloud adds ~10-50ms)
- Easy to run, low maintenance
- Cheap hardware requirement
- Data is ephemeral anyway

#### Keep Local: RabbitMQ

**Why:**
- Works fine locally
- Amazon MQ is expensive (~$150/month minimum)
- Queue data is transient
- Easy to migrate later if needed

#### Keep Local: Cassandra (Initially)

**Why:**
- Managed Cassandra is expensive
- Can start with single node locally
- Migrate to Astra DB (serverless) later when traffic justifies

> **Exception**: If Cassandra management is painful, use Astra DB serverless - you only pay for operations, so low traffic = low cost (~$25/month at low usage).

#### Keep Local: Application Servers

**Why:**
- Your pfSense/HAProxy handles load balancing well
- Easy to scale by adding machines
- Compute is where self-hosting saves the most money

### Recommended Hybrid Setup

#### Phase 1: Minimal Cloud (Start Here)

| Component | Location | Monthly Cost |
|-----------|----------|--------------|
| App Servers | Local | $0 |
| Memcached | Local | $0 |
| Redis | Local | $0 |
| RabbitMQ | Local | $0 |
| PostgreSQL | Neon/Supabase | $0-25 |
| Cassandra | Local | $0 |
| Media Storage | Cloudflare R2 | $5-15 |
| Backups | Backblaze B2 | $5-10 |
| **Total Cloud** | | **$10-50/month** |

#### Phase 2: Production-Ready Hybrid

| Component | Location | Monthly Cost |
|-----------|----------|--------------|
| App Servers | Local | $0 |
| Memcached | Local | $0 |
| Redis | Local | $0 |
| RabbitMQ | Local | $0 |
| PostgreSQL | RDS/Cloud SQL | $50-100 |
| Cassandra | Astra DB Serverless | $25-100 |
| Media Storage | S3 + CloudFront | $20-50 |
| Backups | B2 | $5-10 |
| **Total Cloud** | | **$100-260/month** |

### Connection Configuration

#### Secure Connection to Cloud Database

**Option 1: Direct SSL Connection (Simplest)**

```ini
# production.update
db_ssl = true
main_db = tippr, your-db.xxx.us-east-1.rds.amazonaws.com, *, *, *, *, *
```

**Option 2: WireGuard VPN to Cloud VPC**

More secure, keeps database off public internet:

```bash
# On pfSense: Install WireGuard package
# Create tunnel to AWS/GCP VPC
# Route database subnet through tunnel
```

**Option 3: AWS Site-to-Site VPN**

For production-grade connectivity (~$35/month for AWS VPN).

### Example `production.update` for Hybrid

```ini
# production.update - Hybrid deployment
[DEFAULT]
debug = false
# Domain
domain = yourdomain.com
https_endpoint = https://yourdomain.com
# PostgreSQL in Cloud (Neon example)
db_user = tippr
db_pass = YOUR_NEON_PASSWORD
db_port = 5432
db_ssl = true
databases = main, comment, email, authorize, award, hc, traffic
main_db = tippr, ep-xxx.us-east-2.aws.neon.tech, *, *, *, *, *
# Cassandra - Local for now
cassandra_seeds = 192.168.1.111:9042
cassandra_pool_size = 10
# Cache - Local (latency sensitive)
lockcaches = 192.168.1.112:11211
permacache_memcaches = 192.168.1.112:11211
hardcache_memcaches = 192.168.1.112:11211
# Queue - Local
amqp_host = 192.168.1.112:5672
amqp_user = tippr
amqp_pass = YOUR_LOCAL_PASSWORD
# Media - Cloud (Cloudflare R2)
media_provider = s3
S3KEY_ID = YOUR_R2_ACCESS_KEY
S3SECRET_KEY = YOUR_R2_SECRET_KEY
s3_media_domain = your-account.r2.cloudflarestorage.com
s3_media_buckets = tippr-media
# Or if using AWS S3 + CloudFront
# s3_media_domain = d123xxx.cloudfront.net
# s3_media_buckets = tippr-media-bucket
```

### Migration Path Summary

```
Phase 1 (Now)           Phase 2 (Growth)         Phase 3 (Scale)
─────────────────       ─────────────────        ─────────────────
Local Everything   →    Hybrid                →   Full Cloud
                        + Cloud DB                + Cloud Compute
                        + Cloud Storage           + Managed Cache
                        + Cloud Backups           + CDN

Cost: ~$150/mo          Cost: ~$200-350/mo       Cost: $1,500+/mo
```

> **Key insight**: Cloud databases and storage are cheap and eliminate your biggest operational risks (data loss, complex backups). Keep compute local where you save the most money.

---

For smaller deployments or when you want to start locally before migrating to cloud, self-hosting is a viable option. This approach lets you validate your application and understand traffic patterns before committing to cloud infrastructure costs.

### When to Self-Host

**Good candidates for self-hosting:**
- Early-stage projects with limited traffic
- Development/staging environments
- Cost-sensitive deployments
- Learning and experimentation
- Geographic regions without nearby cloud availability zones

**Consider cloud when:**
- You need 99.9%+ uptime guarantees
- Traffic exceeds your internet bandwidth capacity
- Geographic distribution is required
- Power/internet reliability is a concern
- You need rapid scaling capabilities

### Self-Hosted Architecture Overview

```
                        Internet
                            │
                            ▼
                    ┌──────────────┐
                    │   pfSense    │
                    │   HAProxy    │
                    │  (Router)    │
                    └──────┬───────┘
                           │ SSL Termination
                           │ Load Balancing
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  App Srv 1 │  │  App Srv 2 │  │  App Srv 3 │
    │ 192.168.1.101│ │ 192.168.1.102│ │ 192.168.1.103│
    │   :3000    │  │   :3000    │  │   :3000    │
    └────────────┘  └────────────┘  └────────────┘
           │               │               │
           └───────────────┴───────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ PostgreSQL│ │ Cassandra│ │  Redis/  │
       │  :5432   │ │  :9042   │ │ Memcached│
       └──────────┘ └──────────┘ └──────────┘
```

### Hardware Requirements

#### Minimum Single-Server Setup

| Component | Specification |
|-----------|--------------|
| CPU | 4+ cores (8+ recommended) |
| RAM | 16GB minimum (32GB recommended) |
| Storage | 500GB SSD (NVMe preferred) |
| Network | 100 Mbps symmetric (1 Gbps recommended) |
| UPS | Required for power protection |

#### Recommended Multi-Server Setup

| Server Role | Count | Specs |
|-------------|-------|-------|
| Application Servers | 2-3 | 4 cores, 8GB RAM, 100GB SSD |
| Database Server | 1 | 8 cores, 32GB RAM, 500GB NVMe |
| Cache/Queue Server | 1 | 4 cores, 16GB RAM, 100GB SSD |

### Operating System Setup

**Recommended: Ubuntu Server 22.04 LTS or 24.04 LTS**

Ubuntu Server provides:
- Long-term support (5 years)
- Extensive documentation
- Easy migration path to AWS/GCP/Azure (same OS on cloud VMs)
- Good Docker and container support

```bash
# Initial server setup
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y \
    curl wget git htop \
    ufw fail2ban \
    docker.io docker-compose-v2

# Enable and start Docker
sudo systemctl enable docker
sudo systemctl start docker

# Add your user to docker group
sudo usermod -aG docker $USER
```

### Network Infrastructure with pfSense + HAProxy

If you're already running pfSense as your router/firewall, you can leverage its built-in HAProxy package for load balancing and SSL termination.

#### HAProxy Frontend Configuration

In **Services → HAProxy → Frontend**:

| Setting | Value |
|---------|-------|
| Name | `tippr_frontend` |
| Listen Address | WAN address |
| Port | 443 |
| SSL Offloading | Enabled |
| Certificate | Let's Encrypt (via ACME package) |
| Default Backend | `tippr_servers` |

**HTTP to HTTPS Redirect (Port 80):**

| Setting | Value |
|---------|-------|
| Name | `http_redirect` |
| Listen Address | WAN address |
| Port | 80 |
| Action | HTTP redirect to HTTPS |

#### HAProxy Backend Configuration

In **Services → HAProxy → Backend**:

| Setting | Value |
|---------|-------|
| Name | `tippr_servers` |
| Balance | `roundrobin` or `leastconn` |
| Health Check Method | HTTP |
| Health Check URI | `/health` |
| Health Check Interval | `5000` ms |

**Server Pool:**

| Server | Address | Port | Weight |
|--------|---------|------|--------|
| app1 | 192.168.1.101 | 8001 | 100 |
| app2 | 192.168.1.102 | 8001 | 100 |
| app3 | 192.168.1.103 | 8001 | 100 |

#### Load Balancing Algorithms

| Algorithm | Best For |
|-----------|----------|
| `roundrobin` | Equal servers, stateless requests |
| `leastconn` | Varying request durations, long-running connections |
| `source` | Session persistence (sticky sessions) |

#### SSL Certificate with ACME

Install the ACME package in pfSense for automatic Let's Encrypt certificates:

1. **System → Package Manager → Available Packages** → Install `acme`
2. **Services → ACME → Certificates** → Add new certificate
3. Configure DNS validation or HTTP-01 challenge
4. Enable auto-renewal

### Docker Compose Deployment

#### Single-Server All-in-One Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: ./tippr
    restart: always
    ports:
      - "8001:8001"
    environment:
      - PYTHONPATH=/app/tippr:/app
      - TIPPR_INI=/app/tippr/r2/production.ini
    volumes:
      - ./config/production.update:/app/tippr/r2/production.update:ro
    depends_on:
      - db
      - memcached
      - rabbitmq
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  db:
    image: postgres:15-alpine
    restart: always
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    environment:
      - POSTGRES_USER=tippr
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=tippr
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tippr"]
      interval: 10s
      timeout: 5s
      retries: 5

  cassandra:
    image: cassandra:4.1
    restart: always
    volumes:
      - cassandra_data:/var/lib/cassandra
    environment:
      - CASSANDRA_CLUSTER_NAME=tippr
      - MAX_HEAP_SIZE=2G
      - HEAP_NEWSIZE=400M
    healthcheck:
      test: ["CMD", "cqlsh", "-e", "describe keyspaces"]
      interval: 30s
      timeout: 10s
      retries: 5

  memcached:
    image: memcached:1.6-alpine
    restart: always
    command: ["-m", "1024", "-c", "4096"]
    healthcheck:
      test: ["CMD", "nc", "-z", "localhost", "11211"]
      interval: 10s
      timeout: 5s
      retries: 3

  rabbitmq:
    image: rabbitmq:3.12-management-alpine
    restart: always
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    environment:
      - RABBITMQ_DEFAULT_USER=tippr
      - RABBITMQ_DEFAULT_PASS=${RABBITMQ_PASSWORD}
    ports:
      - "15672:15672"  # Management UI (internal only)
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  postgres_data:
  cassandra_data:
  rabbitmq_data:
```

#### Multi-Server Setup

**Application Server (192.168.1.101-103):**

```yaml
# docker-compose.app.yml
version: '3.8'

services:
  app:
    build: ./tippr
    restart: always
    ports:
      - "8001:8001"
    environment:
      - PYTHONPATH=/app/tippr:/app
      - TIPPR_INI=/app/tippr/r2/production.ini
      - DATABASE_URL=postgres://tippr:${DB_PASSWORD}@192.168.1.110:5432/tippr
      - CASSANDRA_SEEDS=192.168.1.111:9042
      - MEMCACHED_SERVERS=192.168.1.112:11211
      - RABBITMQ_URL=amqp://tippr:${RABBITMQ_PASSWORD}@192.168.1.112:5672/
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

**Database Server (192.168.1.110):**

```yaml
# docker-compose.db.yml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    restart: always
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    environment:
      - POSTGRES_USER=tippr
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=tippr
    command:
      - "postgres"
      - "-c"
      - "shared_buffers=8GB"
      - "-c"
      - "effective_cache_size=24GB"
      - "-c"
      - "work_mem=256MB"
      - "-c"
      - "maintenance_work_mem=2GB"
      - "-c"
      - "max_connections=200"

  cassandra:
    image: cassandra:4.1
    restart: always
    ports:
      - "9042:9042"
    volumes:
      - cassandra_data:/var/lib/cassandra
    environment:
      - CASSANDRA_CLUSTER_NAME=tippr
      - MAX_HEAP_SIZE=8G
      - HEAP_NEWSIZE=1600M

volumes:
  postgres_data:
  cassandra_data:
```

**Cache/Queue Server (192.168.1.112):**

```yaml
# docker-compose.cache.yml
version: '3.8'

services:
  memcached:
    image: memcached:1.6-alpine
    restart: always
    ports:
      - "11211:11211"
    command: ["-m", "4096", "-c", "8192"]

  rabbitmq:
    image: rabbitmq:3.12-management-alpine
    restart: always
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    environment:
      - RABBITMQ_DEFAULT_USER=tippr
      - RABBITMQ_DEFAULT_PASS=${RABBITMQ_PASSWORD}

  redis:
    image: redis:7-alpine
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru

volumes:
  rabbitmq_data:
  redis_data:
```

### Session Management for Load Balancing

When running multiple application servers, you need a strategy for session handling:

#### Option 1: Sticky Sessions (Simplest)

Configure HAProxy backend with cookie-based persistence:

| Setting | Value |
|---------|-------|
| Persistence | Cookie |
| Cookie Name | `SERVERID` |
| Cookie Mode | Insert |

This pins users to the same server for the duration of their session.

#### Option 2: Shared Session Store (Recommended)

Use Redis for centralized session storage:

```ini
# production.update
[DEFAULT]
# Redis for session storage
session_store = redis
redis_session_host = 192.168.1.112
redis_session_port = 6379
redis_session_db = 0
```

This allows any application server to handle any request.

### Production Configuration for Self-Hosting

```ini
# production.update for self-hosted deployment
[DEFAULT]
# CRITICAL: Disable debug mode
debug = false
template_debug = false
reload_templates = false
uncompressedJS = false
sqlprinting = false

# Production domain
domain = yourdomain.com
media_domain = media.yourdomain.com
https_endpoint = https://yourdomain.com

# PostgreSQL (self-hosted)
db_user = tippr
db_pass = YOUR_SECURE_PASSWORD
db_port = 5432
databases = main, comment, email, authorize, award, hc, traffic
main_db = tippr, 192.168.1.110, *, *, *, *, *

# Cassandra (self-hosted)
cassandra_seeds = 192.168.1.111:9042
cassandra_pool_size = 10
cassandra_rcl = LOCAL_QUORUM
cassandra_wcl = LOCAL_QUORUM

# Memcached (self-hosted)
lockcaches = 192.168.1.112:11211
permacache_memcaches = 192.168.1.112:11211
hardcache_memcaches = 192.168.1.112:11211
num_mc_clients = 20

# RabbitMQ (self-hosted)
amqp_host = 192.168.1.112:5672
amqp_user = tippr
amqp_pass = YOUR_SECURE_PASSWORD
amqp_virtual_host = /

# Local media storage (or configure S3-compatible like MinIO)
media_provider = filesystem
media_fs_root = /var/tippr/media
media_fs_url = https://media.yourdomain.com

# Security
trust_local_proxies = true
ENFORCE_RATELIMIT = true

# Monitoring
statsd_addr = 192.168.1.112:8125
```

### Security Hardening

#### Firewall Configuration (UFW)

```bash
# On each application server
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (change port if using non-standard)
sudo ufw allow 22/tcp

# Allow HAProxy health checks from pfSense
sudo ufw allow from 192.168.1.1 to any port 8001

# Enable firewall
sudo ufw enable
```

```bash
# On database server
sudo ufw default deny incoming
sudo ufw default allow outgoing

sudo ufw allow 22/tcp
sudo ufw allow from 192.168.1.101 to any port 5432  # PostgreSQL
sudo ufw allow from 192.168.1.102 to any port 5432
sudo ufw allow from 192.168.1.103 to any port 5432
sudo ufw allow from 192.168.1.101 to any port 9042  # Cassandra
sudo ufw allow from 192.168.1.102 to any port 9042
sudo ufw allow from 192.168.1.103 to any port 9042

sudo ufw enable
```

#### SSH Hardening

```bash
# /etc/ssh/sshd_config
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2

# Restart SSH
sudo systemctl restart sshd
```

#### Fail2Ban Configuration

```bash
sudo apt install fail2ban

# /etc/fail2ban/jail.local
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
```

### Backup Strategy

#### Automated PostgreSQL Backups

```bash
#!/bin/bash
# /opt/scripts/backup-postgres.sh

BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

# Create backup
docker exec postgres pg_dump -U tippr tippr | gzip > "${BACKUP_DIR}/tippr_${DATE}.sql.gz"

# Upload to offsite storage (Backblaze B2, Wasabi, etc.)
rclone copy "${BACKUP_DIR}/tippr_${DATE}.sql.gz" b2:tippr-backups/postgres/

# Remove old local backups
find ${BACKUP_DIR} -type f -mtime +${RETENTION_DAYS} -delete
```

```bash
# Crontab entry (daily at 2 AM)
0 2 * * * /opt/scripts/backup-postgres.sh >> /var/log/backup.log 2>&1
```

#### Cassandra Backup with nodetool

```bash
#!/bin/bash
# /opt/scripts/backup-cassandra.sh

BACKUP_DIR="/backups/cassandra"
DATE=$(date +%Y%m%d_%H%M%S)

# Create snapshot
docker exec cassandra nodetool snapshot -t backup_${DATE} tippr

# Copy snapshot files
docker cp cassandra:/var/lib/cassandra/data/tippr/. "${BACKUP_DIR}/${DATE}/"

# Compress and upload
tar -czf "${BACKUP_DIR}/cassandra_${DATE}.tar.gz" "${BACKUP_DIR}/${DATE}"
rclone copy "${BACKUP_DIR}/cassandra_${DATE}.tar.gz" b2:tippr-backups/cassandra/

# Cleanup
rm -rf "${BACKUP_DIR}/${DATE}"
docker exec cassandra nodetool clearsnapshot -t backup_${DATE}
```

### Monitoring for Self-Hosted Deployment

#### Uptime Kuma (Self-Hosted Uptime Monitoring)

```yaml
# Add to docker-compose
uptime-kuma:
  image: louislam/uptime-kuma:1
  restart: always
  ports:
    - "3001:3001"
  volumes:
    - uptime-kuma:/app/data
```

Configure monitors for:
- HAProxy frontend (HTTPS endpoint)
- Each application server health endpoint
- PostgreSQL connectivity
- Cassandra connectivity
- RabbitMQ management interface

#### Netdata (Real-Time Server Metrics)

```bash
# Install on each server
bash <(curl -Ss https://get.netdata.cloud/kickstart.sh)
```

Access at `http://server-ip:19999` for real-time CPU, memory, disk, and network metrics.

#### Prometheus + Grafana Stack

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    restart: always
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    restart: always
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}

  node-exporter:
    image: prom/node-exporter:latest
    restart: always
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'

volumes:
  prometheus_data:
  grafana_data:
```

### Deployment Scripts

#### Rolling Deployment Script

```bash
#!/bin/bash
# /opt/scripts/deploy.sh

SERVERS=("192.168.1.101" "192.168.1.102" "192.168.1.103")
REPO_PATH="/opt/tippr"
BRANCH="${1:-main}"

for server in "${SERVERS[@]}"; do
    echo "=========================================="
    echo "Deploying to ${server}..."
    echo "=========================================="

    # Optionally: Drain from HAProxy via pfSense API
    # curl -X POST "https://pfsense/api/haproxy/drain/${server}"

    ssh ${server} << 'ENDSSH'
        cd ${REPO_PATH}
        git fetch origin
        git checkout ${BRANCH}
        git pull origin ${BRANCH}

        cd ${REPO_PATH}
        docker compose build app
        docker compose up -d app

        # Wait for health check
        sleep 10
        curl -f http://localhost:8001/health || exit 1
ENDSSH

    if [ $? -ne 0 ]; then
        echo "Deployment to ${server} failed!"
        exit 1
    fi

    echo "Successfully deployed to ${server}"

    # Wait between servers for graceful rollout
    sleep 30
done

echo "=========================================="
echo "Deployment complete!"
echo "=========================================="
```

### Domain & DNS Setup

#### Option 1: Static IP

If your ISP provides a static IP:
1. Register a domain (~$12/year from Namecheap, Cloudflare, etc.)
2. Set A record pointing to your static IP
3. Configure SSL via Let's Encrypt (ACME package in pfSense)

#### Option 2: Dynamic DNS

If your IP changes:
1. Use a Dynamic DNS service (Cloudflare, DuckDNS, No-IP)
2. Install ddclient on your server or configure in pfSense

```bash
# /etc/ddclient.conf for Cloudflare
protocol=cloudflare
use=web
web=checkip.dyndns.org
login=your-cloudflare-email
password=your-api-token
zone=yourdomain.com
yourdomain.com
```

#### Cloudflare (Recommended)

Use Cloudflare's free tier for:
- DNS management
- DDoS protection
- SSL termination (Full Strict mode)
- Caching of static assets
- Hide your origin IP

### Cost Comparison: Self-Hosted vs Cloud

| Item | Self-Hosted (One-Time) | Self-Hosted (Monthly) | Cloud (Monthly) |
|------|------------------------|----------------------|-----------------|
| Hardware (3 servers) | $2,000-5,000 | - | - |
| Electricity | - | $30-100 | - |
| Internet (Business) | - | $100-300 | - |
| Domain | - | $1 | $1 |
| Backups (B2/Wasabi) | - | $5-20 | - |
| **Total Monthly** | - | **$136-421** | **$1,325-1,910** |
| **Break-even** | | **6-12 months** | |

**Note**: Self-hosting requires more hands-on management and expertise. Factor in your time cost.

### Migration Path to Cloud

When traffic justifies cloud migration:

1. **Database First**: Migrate PostgreSQL to RDS/Cloud SQL
   - Use pg_dump/pg_restore or AWS DMS
   - Update connection strings in production.update

2. **Cache Layer**: Move to ElastiCache/Memorystore
   - Simply update memcached server addresses

3. **Application Servers**: Move to EC2/GCE/VM Scale Sets
   - Same Docker containers work on cloud VMs
   - Update HAProxy to point to cloud servers (or switch to ALB)

4. **Decommission HAProxy**: Switch to cloud load balancer
   - ALB/Cloud LB/Application Gateway

5. **Final Cutover**: Update DNS to point to cloud endpoints

This gradual migration minimizes risk and allows testing at each stage.

### Self-Hosted Deployment Checklist

#### Infrastructure Setup
- [ ] Hardware procured and rack-mounted (or VM hosts configured)
- [ ] Ubuntu Server LTS installed on all servers
- [ ] Static IPs assigned to all servers
- [ ] Network switches configured with proper VLANs
- [ ] UPS installed and configured
- [ ] pfSense configured with HAProxy package

#### Security
- [ ] SSH key authentication only (passwords disabled)
- [ ] Fail2ban installed and configured
- [ ] UFW firewall rules configured
- [ ] SSL certificates obtained (Let's Encrypt via ACME)
- [ ] All default passwords changed

#### Services
- [ ] Docker and Docker Compose installed
- [ ] PostgreSQL container running with persistent volume
- [ ] Cassandra container running with persistent volume
- [ ] Memcached container running
- [ ] RabbitMQ container running
- [ ] Redis container running (for sessions)
- [ ] Application containers deployed

#### HAProxy Configuration
- [ ] Frontend configured for ports 80/443
- [ ] SSL offloading enabled with valid certificate
- [ ] Backend pool configured with all app servers
- [ ] Health checks configured and passing
- [ ] HTTP to HTTPS redirect enabled

#### Backup & Recovery
- [ ] PostgreSQL backup script configured
- [ ] Cassandra backup script configured
- [ ] Offsite backup destination configured (B2, Wasabi, etc.)
- [ ] Backup cron jobs scheduled
- [ ] Restore procedure tested

#### Monitoring
- [ ] Uptime Kuma or similar monitoring deployed
- [ ] Health endpoints monitored for all services
- [ ] Disk space alerts configured
- [ ] Email/Slack notifications configured

#### DNS & Domain
- [ ] Domain registered and DNS configured
- [ ] A records pointing to your IP
- [ ] Dynamic DNS configured (if needed)
- [ ] Cloudflare or similar CDN/protection enabled (optional)

#### Documentation
- [ ] Server IP addresses documented
- [ ] Credentials stored securely (password manager)
- [ ] Runbook for common operations written
- [ ] Recovery procedures documented

---

*This document is a starting point. Production deployments should be reviewed by experienced DevOps/SRE engineers and adapted to your specific requirements and traffic patterns.*
