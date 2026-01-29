# Cortex Platform Architecture

This document provides detailed technical architecture for the Cortex Platform's K3s-based infrastructure.

## System Overview

Cortex Platform is an AI-native infrastructure orchestration system built on K3s. It demonstrates how to build self-managing, serverless AI workloads on lightweight Kubernetes.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CORTEX PLATFORM STACK                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ APPLICATION LAYER                                                     │ │
│  │                                                                       │ │
│  │  UniFi Layer Fabric    │  Cortex Live TUI  │  Blog Writer  │  etc.   │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                     │                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ ORCHESTRATION LAYER                                                   │ │
│  │                                                                       │ │
│  │  MCP Servers: k3s-mcp │ talos-mcp │ proxmox-mcp │ unifi-mcp          │ │
│  │  Coordination: Redis Streams │ Agent Registry │ Task Queue           │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                     │                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ PLATFORM LAYER                                                        │ │
│  │                                                                       │ │
│  │  K3s Cluster (7 nodes) │ KEDA │ ArgoCD │ Prometheus │ Qdrant         │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                     │                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ INFRASTRUCTURE LAYER                                                  │ │
│  │                                                                       │ │
│  │  Talos Linux │ Proxmox VE │ etcd HA │ Longhorn Storage               │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## K3s Cluster Architecture

### Node Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           K3s CLUSTER                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   CONTROL PLANE (3 nodes, HA)                                               │
│   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐              │
│   │ k3s-master01    │ │ k3s-master02    │ │ k3s-master03    │              │
│   │                 │ │                 │ │                 │              │
│   │ • etcd member   │ │ • etcd member   │ │ • etcd member   │              │
│   │ • API server    │ │ • API server    │ │ • API server    │              │
│   │ • Controller    │ │ • Controller    │ │ • Controller    │              │
│   │ • Scheduler     │ │ • Scheduler     │ │ • Scheduler     │              │
│   └─────────────────┘ └─────────────────┘ └─────────────────┘              │
│                                                                             │
│   WORKER NODES (4+ nodes)                                                   │
│   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────┐ │
│   │ k3s-worker01    │ │ k3s-worker02    │ │ k3s-worker03    │ │ worker04│ │
│   │                 │ │                 │ │                 │ │         │ │
│   │ • kubelet       │ │ • kubelet       │ │ • kubelet       │ │ • ...   │ │
│   │ • containerd    │ │ • containerd    │ │ • containerd    │ │         │ │
│   │ • kube-proxy    │ │ • kube-proxy    │ │ • kube-proxy    │ │         │ │
│   └─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Namespace Organization

| Namespace | Purpose | Key Workloads |
|-----------|---------|---------------|
| `cortex-system` | Core infrastructure | cortex-live, resource-manager, health-monitor |
| `cortex-mcp` | MCP server deployments | kubernetes-mcp, talos-mcp, proxmox-mcp |
| `cortex-unifi` | UniFi Layer Fabric | activator, qdrant, reasoning, execution layers |
| `cortex-monitoring` | Observability | Prometheus, kube-state-metrics |
| `keda` | KEDA controller | keda-operator, keda-metrics-apiserver |
| `argocd` | GitOps | argocd-server, application-controller |

## UniFi Layer Fabric

The UniFi Layer Fabric is a serverless AI system for network operations. It demonstrates advanced K3s patterns including KEDA scaling, vector databases, and multi-tier routing.

### Layer Architecture

```
                                 USER QUERY
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LAYER 1: CORTEX ACTIVATOR                            │
│                           (Always On, 2 replicas)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     4-TIER ROUTING CASCADE                          │   │
│  │                                                                     │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────┐ │   │
│  │  │   TIER 1    │   │   TIER 2    │   │   TIER 3    │   │ TIER 4  │ │   │
│  │  │   Keyword   │──▶│  Similarity │──▶│ Classifier  │──▶│   SLM   │ │   │
│  │  │   Match     │   │   Search    │   │  (Qwen2)    │   │ (Phi-3) │ │   │
│  │  │   <10ms     │   │   <50ms     │   │   ~5s cold  │   │ ~12s    │ │   │
│  │  └─────────────┘   └─────────────┘   └─────────────┘   └─────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  Resources: 128MB memory, 200m CPU limit                                    │
│  Health: /health (liveness), /ready (readiness)                             │
│  Metrics: cortex_activator_queries_total, cortex_activator_cold_starts      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  LAYER 2: QDRANT    │  │ LAYERS 3-4: REASON  │  │ LAYERS 5-6: EXECUTE │
│  (Always On)        │  │ (Scale 0→1)         │  │ (Scale 0→1)         │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│                     │  │                     │  │                     │
│ Vector Memory       │  │ reasoning-classifier│  │ execution-unifi-api │
│ • routing_queries   │  │ • Qwen2-0.5B        │  │ • UniFi API calls   │
│ • routing_outcomes  │  │ • 400MB warm        │  │ • 200MB warm        │
│ • operations        │  │ • Intent classify   │  │ • Primary execution │
│ • troubleshooting   │  │                     │  │                     │
│                     │  │ reasoning-slm       │  │ execution-unifi-ssh │
│ 512MB, 5Gi PVC      │  │ • Phi-3 3.8B        │  │ • SSH failover      │
│ Embedding: 384 dim  │  │ • 2.5GB warm        │  │ • 100MB warm        │
│                     │  │ • Tool calling      │  │ • Diagnostics       │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
                                     │
                                     ▼
                      ┌─────────────────────────┐
                      │  LAYER 7: TELEMETRY     │
                      │  (Scale 0→1)            │
                      ├─────────────────────────┤
                      │                         │
                      │ • Prometheus metrics    │
                      │ • Audit logging         │
                      │ • Learning pipeline     │
                      │ • Training data export  │
                      │                         │
                      │ 128MB warm              │
                      └─────────────────────────┘
```

### KEDA Configuration

Each serverless layer uses KEDA for scale-to-zero:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: reasoning-slm
  namespace: cortex-unifi
spec:
  scaleTargetRef:
    name: reasoning-slm
  minReplicaCount: 0
  maxReplicaCount: 1
  cooldownPeriod: 300
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus.cortex-monitoring:9090
        metricName: cortex_activator_pending_requests
        query: sum(cortex_activator_pending_requests{layer="reasoning-slm"})
        threshold: "1"
```

### Memory Profile

| State | Memory Usage | Active Layers |
|-------|--------------|---------------|
| **Idle** | 640MB | Activator + Qdrant |
| **Simple Query** | ~1GB | + Execution API |
| **Classification** | ~1.4GB | + Classifier |
| **Complex Query** | ~4GB | + SLM Reasoning |
| **Full Stack** | ~4.5GB | All layers |

**Savings: 85%+ vs always-on architecture**

## Cortex Activator Deep Dive

### Query Processing Flow

```python
async def process_query(query: str, context: dict) -> Response:
    """
    Main query processing with 4-tier cascade
    """

    # Phase 4: Score query complexity (0-100)
    complexity = score_complexity(query)

    # Tier 1: Keyword pattern matching (<10ms)
    if pattern_match := match_keywords(query):
        return await execute_direct(pattern_match.layer, query)

    # Tier 2: Similarity search in Qdrant (<50ms)
    if similar := await qdrant_search(query, threshold=0.92):
        if similar.success_rate >= 0.8:
            return await execute_learned(similar.routing, query)

    # Tier 3: Lightweight classifier (~5s cold)
    if complexity < 50:
        await wake_layer("reasoning-classifier")
        classification = await classify(query)
        return await execute_classified(classification, query)

    # Tier 4: Full SLM reasoning (~12s cold)
    await wake_layer("reasoning-slm")
    reasoning = await reason(query, context)
    return await execute_reasoned(reasoning, query)
```

### Routing Rules

```yaml
routing:
  keywords:
    # Client operations
    - pattern: "(block|unblock).*client"
      layer: execution-unifi-api
      tool: block_client
      confidence: 0.95

    - pattern: "(list|show|get).*client"
      layer: execution-unifi-api
      tool: get_clients
      confidence: 0.90

    # Device operations
    - pattern: "(restart|reboot).*device"
      layer: execution-unifi-api
      tool: restart_device
      requiresConfirmation: true
      confidence: 0.95

    # Diagnostics (SSH layer)
    - pattern: "(diagnose|troubleshoot|investigate)"
      layer: reasoning-slm  # Needs reasoning first
      confidence: 0.70

    - pattern: "(show|get).*(log|logs)"
      layer: execution-unifi-ssh
      tool: get_logs
      confidence: 0.85
```

### Complexity Scoring

```python
def score_complexity(query: str) -> int:
    """
    Score query complexity from 0-100

    Factors:
    - Keywords: investigate (+20), analyze (+18), troubleshoot (+22)
    - Length: >500 chars (+15)
    - Questions: multiple questions (+8 each)
    - Entities: MACs, IPs, VLANs (+3 each)
    - Context: large context (+10)
    """
    score = 0

    # High complexity indicators
    if "investigate" in query.lower(): score += 20
    if "analyze" in query.lower(): score += 18
    if "troubleshoot" in query.lower(): score += 22

    # Low complexity indicators
    if query.lower().startswith(("list", "show", "get")): score -= 5

    # Length factor
    if len(query) > 500: score += 15

    # Question count
    score += query.count("?") * 8

    # Entity count (simplified)
    score += len(re.findall(r'[0-9a-f]{2}:[0-9a-f]{2}:', query, re.I)) * 3

    return min(100, max(0, score))
```

## Learning System

### Qdrant Collections

```yaml
collections:
  routing_queries:
    description: Query embeddings with routing decisions
    vector_size: 384  # all-MiniLM-L6-v2
    distance: Cosine
    indexes:
      - route_type: keyword  # cache, keyword, similarity, classifier, slm
      - tool: keyword
      - execution_layer: keyword
      - success: bool
      - latency_ms: integer
      - timestamp: datetime

  routing_outcomes:
    description: Links queries to execution results
    vector_size: 384
    indexes:
      - query_id: keyword
      - success: bool
      - error_type: keyword
      - user_feedback: keyword
      - timestamp: datetime
```

### Learning Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LEARNING PIPELINE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. QUERY ARRIVES                                                           │
│     │                                                                       │
│     ▼                                                                       │
│  2. EMBED QUERY                                                             │
│     │  Model: all-MiniLM-L6-v2 (384 dimensions)                            │
│     │                                                                       │
│     ▼                                                                       │
│  3. SEARCH SIMILAR (Tier 2)                                                 │
│     │  Threshold: 0.92 cosine similarity                                   │
│     │  Min samples: 3 successful executions                                │
│     │                                                                       │
│     ├─── MATCH FOUND ──▶ Reuse routing (skip classification)               │
│     │                                                                       │
│     └─── NO MATCH ──▶ Continue to Tier 3/4                                 │
│                                                                             │
│  4. EXECUTE QUERY                                                           │
│     │                                                                       │
│     ▼                                                                       │
│  5. STORE OUTCOME                                                           │
│     │  • Query ID + embedding                                              │
│     │  • Tool selected                                                      │
│     │  • Layer used                                                         │
│     │  • Success/failure                                                    │
│     │  • Latency                                                            │
│     │                                                                       │
│     ▼                                                                       │
│  6. UPDATE SUCCESS RATE                                                     │
│     │  • Per-tool success rate                                             │
│     │  • Per-routing success rate                                           │
│     │  • Overall confidence adjustment                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Deployment with ArgoCD

### ApplicationSet Structure

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: unifi-layer-fabric
  namespace: argocd
spec:
  generators:
    - list:
        elements:
          # Wave 0: Namespace
          - name: cortex-unifi-namespace
            wave: "0"

          # Wave 1: Always-on storage
          - name: cortex-qdrant
            wave: "1"

          # Wave 2: Always-on routing
          - name: cortex-activator
            wave: "2"

          # Wave 3: Reasoning layers
          - name: reasoning-classifier
            wave: "3"
          - name: reasoning-slm
            wave: "3"

          # Wave 4: Execution layers
          - name: execution-unifi-api
            wave: "4"
          - name: execution-unifi-ssh
            wave: "4"

          # Wave 5: Telemetry
          - name: cortex-telemetry
            wave: "5"

  template:
    metadata:
      name: '{{name}}'
      annotations:
        argocd.argoproj.io/sync-wave: '{{wave}}'
    spec:
      project: cortex
      source:
        repoURL: https://github.com/org/cortex-gitops
        targetRevision: HEAD
        path: 'charts/{{name}}'
      destination:
        server: https://kubernetes.default.svc
        namespace: cortex-unifi
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
```

## Monitoring & Observability

### Prometheus Metrics

```yaml
# Activator metrics
- cortex_activator_queries_total{route_type, layer, status}
- cortex_activator_cold_starts_total{layer}
- cortex_activator_cold_start_seconds{layer}  # histogram
- cortex_activator_pending_requests{layer}     # KEDA trigger
- cortex_activator_layer_up{layer}             # 0 or 1

# Learning metrics
- cortex_activator_similarity_lookups_total{result}  # hit, miss, error
- cortex_activator_similarity_latency_seconds        # histogram
- cortex_activator_routing_stored_total{route_type}
- cortex_activator_outcomes_stored_total{success}

# Mode switching metrics
- cortex_activator_mode_decisions_total{mode, complexity}
- cortex_activator_complexity_score        # histogram 0-100
- cortex_activator_escalations_total{reason}
```

### Alerting Rules

```yaml
groups:
  - name: cortex-fabric
    rules:
      - alert: ActivatorDown
        expr: up{job="cortex-activator"} == 0
        for: 1m
        labels:
          severity: critical

      - alert: HighColdStartLatency
        expr: histogram_quantile(0.95, cortex_activator_cold_start_seconds) > 30
        for: 5m
        labels:
          severity: warning

      - alert: LowRoutingSuccessRate
        expr: |
          sum(rate(cortex_activator_queries_total{status="success"}[5m])) /
          sum(rate(cortex_activator_queries_total[5m])) < 0.9
        for: 10m
        labels:
          severity: warning
```

## Dynamic Worker Pool Management

The Resource Manager AI agent manages dynamic worker pools:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DYNAMIC WORKER POOLS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  PERMANENT POOL (3-10 nodes)                                                │
│  ├── Always running                                                         │
│  ├── Core workloads                                                         │
│  └── No TTL                                                                 │
│                                                                             │
│  BURST POOL (0-20 nodes)                                                    │
│  ├── Scale up on demand                                                     │
│  ├── TTL-based cleanup (default: 1 hour)                                    │
│  └── Triggers: CPU ≥80%, Memory ≥85%, Pending pods                         │
│                                                                             │
│  SPOT POOL (0-15 nodes)                                                     │
│  ├── 70% cost savings                                                       │
│  ├── Preemptible workloads                                                  │
│  └── Tolerations for spot-instance taint                                    │
│                                                                             │
│  GPU POOL (0-5 nodes)                                                       │
│  ├── Special hardware                                                       │
│  ├── nvidia.com/gpu taint                                                   │
│  └── ML/AI workloads                                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

                           PROVISIONING FLOW

   Scale Trigger        Proxmox MCP            Talos MCP            K3s
        │                   │                      │                  │
        │  Clone VM         │                      │                  │
        ├──────────────────▶│                      │                  │
        │                   │  Generate config     │                  │
        │                   ├─────────────────────▶│                  │
        │                   │                      │  Join cluster    │
        │                   │                      ├─────────────────▶│
        │                   │                      │                  │
        │◀─────────────────────────────────────────────────────────────
        │                    Node ready
```

## Security Model

### RBAC Configuration

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cortex-activator
rules:
  # Scale serverless layers
  - apiGroups: ["apps"]
    resources: ["deployments", "deployments/scale"]
    verbs: ["get", "list", "watch", "patch"]

  # KEDA integration
  - apiGroups: ["keda.sh"]
    resources: ["scaledobjects"]
    verbs: ["get", "list", "watch", "patch"]

  # Pod status for health checks
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]
```

### Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: activator-egress
  namespace: cortex-unifi
spec:
  podSelector:
    matchLabels:
      app: cortex-activator
  policyTypes:
    - Egress
  egress:
    # Allow to other fabric layers
    - to:
        - namespaceSelector:
            matchLabels:
              name: cortex-unifi
    # Allow to Prometheus
    - to:
        - namespaceSelector:
            matchLabels:
              name: cortex-monitoring
    # Allow to Redis (Cortex master)
    - to:
        - namespaceSelector:
            matchLabels:
              name: cortex-system
```

## Conclusion

The Cortex Platform demonstrates how to build sophisticated, self-managing AI infrastructure on K3s:

1. **Serverless AI** - KEDA scales reasoning/execution layers 0→1
2. **Intelligent Routing** - 4-tier cascade minimizes cold starts
3. **Learning System** - Qdrant stores patterns for continuous improvement
4. **Dynamic Scaling** - AI manages worker pool lifecycle
5. **GitOps** - ArgoCD ensures declarative, version-controlled deployments

This architecture achieves 85%+ memory savings compared to always-on approaches while maintaining sub-second response times for common queries.
