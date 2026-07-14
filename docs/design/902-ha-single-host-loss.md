# Design Note: HA Single Host Loss Tolerance (#902)

## 1. Celery Beat/Worker Split
To ensure that rolling updates or host failures do not result in multiple Celery schedulers running simultaneously (which could duplicate tasks), we will split the worker and beat processes:
- **`docuelevate-beat`**: A dedicated deployment with `replicas: 1` and `strategy: Recreate`. This ensures that a rolling deploy will terminate the old pod before spinning up a new one. 
- **Locked Scheduler**: To provide a strict guarantee against scheduler overlap, we will adopt **RedBeat** (Redis-backed scheduler with distributed locking). If a network partition or other race condition causes a split brain, the Redis lock will prevent the second beat instance from triggering duplicate schedules.
- **`docuelevate-worker`**: Will have `-B` removed from its startup command. It can now be scaled horizontally (`replicas: 2+`) safely.
- **Availability Trade-off**: The beat scheduler is a singleton. During a node failure, it will briefly be unavailable while Kubernetes reschedules it. This is acceptable as missed schedule ticks will resume once it's back, and preventing overlap is more critical than 100% scheduler uptime.

## 2. Search HA Decision
The core choice for Meilisearch is between treating it as a singleton with degraded search (Option A), an ephemeral cache with automatic rebuilds (Option B), or migrating to an HA-capable external service (Option C).

**Decision: (A) + (B) Rebuildable Index on Reattachable Storage**
- **Architecture**: We will keep Meilisearch as a singleton stateful service (`replicas: 1`, `Recreate` strategy) using a `ReadWriteOnce` (RWO) PVC. On standard cloud Kubernetes, this PVC uses network block storage that can detach from a dead node and reattach to the new node where the pod is rescheduled.
- **Graceful Degradation**: The application will be updated to handle connection errors to Meilisearch gracefully. Uploads and document processing will continue to succeed even if the search indexing step fails. The search endpoints will explicitly indicate that search is temporarily unavailable instead of returning a 500.
- **Rebuildability**: If the PVC data is lost or corrupted, we will ensure that `sync_search_index` (the existing reindex task) can be invoked to rebuild the Meilisearch index from PostgreSQL, which remains the single source of truth.

## 3. Pod Disruption Budgets (PDB) and Topology Spread
Given a 3-node Kubernetes cluster (`lisa`, `smithers`, `flanders`):
- **Topology Spread**: We will apply `topologySpreadConstraints` with `maxSkew: 1`, `topologyKey: kubernetes.io/hostname`, and `whenUnsatisfiable: ScheduleAnyway` (soft spread). A soft spread is crucial for a 3-node cluster, as a hard spread (`DoNotSchedule`) would prevent pods from rescheduling if one node is permanently lost.
- **Pod Anti-Affinity**: We will add a `preferredDuringSchedulingIgnoredDuringExecution` anti-affinity rule to further discourage co-location on the same host.
- **PDBs**: We will add `PodDisruptionBudget` resources for multi-replica stateless services (API, Worker, Gotenberg, Redis HAProxy) with `maxUnavailable: 1` (or `minAvailable: 1`). 
- **Beat Exclusion**: We will *not* add a PDB for `docuelevate-beat` or `meilisearch`. Since they are singletons, a PDB with `minAvailable: 1` would completely block voluntary node drains (like cluster upgrades), requiring manual intervention.
