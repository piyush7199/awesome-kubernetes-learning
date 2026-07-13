# 09 — Health Checks (Probes)

> **Goal:** Understand why a running process is not the same as a working application, the three probe types and what each one does when it fails, the four probe mechanisms, how to tune probe timing parameters, and the critical design rule about what liveness probes should and should not check.

---

## The Problem: Running ≠ Healthy

Kubernetes knows when a container process exits — it sees the exit code and restarts it. But what about these situations?

```
Situation 1: App is in a deadlock
  → Process is running (no exit)
  → Every request hangs forever
  → Kubernetes sees: "process alive" ✓
  → Reality: app is completely broken

Situation 2: App just started, still loading a 2GB ML model
  → Process is running
  → Not ready to serve traffic yet
  → Kubernetes sees: "process alive" → routes traffic to it
  → Reality: every request gets an error

Situation 3: App has a memory leak, connection pool is exhausted
  → Process is running
  → Returns 503 on every request
  → Kubernetes sees: "process alive" ✓
  → Reality: app needs to be restarted

Situation 4: App is temporarily overwhelmed under a traffic spike
  → Process is running
  → Slow but still processing
  → Kubernetes sees: "process alive" → keeps sending traffic
  → Reality: app needs to temporarily stop receiving traffic, not restart
```

Kubernetes can't distinguish any of these from a truly healthy app by watching the process alone.

**Probes give Kubernetes a window into whether your app is actually doing its job.**

---

## The Analogy: Three Kinds of Doctor Checks

Think of a hospital patient:

```
Startup Probe  = "Is surgery done? Can we move you out of the OR?"
               → While in the OR, no visitors allowed (no traffic)
               → Once out, we start normal monitoring

Readiness Probe = "Are you ready to see visitors?"
               → No: stay rested, no visitors (remove from traffic)
               → Yes: visitors welcome (add to Service Endpoints)
               → Patient stays in the hospital either way — no intervention

Liveness Probe = "Are you still alive?"
               → No: call the crash team (restart the container)
               → Yes: continue monitoring
               → This is the drastic action — used only when recovery is impossible without restart
```

The key insight: **readiness is a door**, liveness is a **defibrillator**.  
Use readiness first. Only use liveness when you know restarting is the right cure.

---

## Core Vocabulary

| Term | Meaning |
|------|---------|
| **Liveness probe** | Checks if the container should be restarted — detects deadlocks, corruption, unrecoverable states |
| **Readiness probe** | Checks if the container should receive traffic — gates Service Endpoint inclusion |
| **Startup probe** | Protects slow-starting containers — disables liveness/readiness until the app is up |
| **HTTP GET probe** | Sends an HTTP request to a path; success = 2xx or 3xx response code |
| **TCP Socket probe** | Opens a TCP connection; success = connection accepted |
| **Exec probe** | Runs a command inside the container; success = exit code 0 |
| **gRPC probe** | Calls the gRPC Health Checking Protocol; success = SERVING status |
| **initialDelaySeconds** | Seconds to wait after container starts before running any probe |
| **periodSeconds** | How often to run the probe |
| **failureThreshold** | Consecutive failures before action is taken |
| **successThreshold** | Consecutive successes to consider the container healthy again |
| **timeoutSeconds** | Seconds to wait for a probe response before counting it as failed |

---

## The Three Probe Types

### Liveness Probe — "Should I restart this container?"

When a liveness probe fails `failureThreshold` times in a row, Kubernetes sends `SIGTERM` to the container and then force-kills it. The container restarts based on `restartPolicy`.

```
Liveness probe fails 3 times in a row
          │
          ▼
Kubernetes sends SIGTERM to container
          │
          ▼
Container restarts (RESTARTS counter +1)
          │
          ▼
If it keeps failing → CrashLoopBackOff
```

**Use liveness when:** your app can enter an unrecoverable state that a restart would fix — deadlock, memory corruption, infinite loop, hung goroutine.

**Do NOT use liveness when:** the issue is temporary or external — a dependency is down, the app is just slow. Restarting doesn't fix those, and you'll CrashLoop needlessly.

---

### Readiness Probe — "Should this container receive traffic?"

When a readiness probe fails, Kubernetes removes the pod's IP from the Service Endpoints. No new traffic reaches it. **The container is not restarted.** When the probe passes again, the pod is re-added to Endpoints and traffic resumes.

```
Readiness probe fails 3 times in a row
          │
          ▼
Pod IP removed from Service Endpoints
          │
          ▼
No new traffic → pod can recover, process queued work, warm up
          │
          ▼
Readiness probe passes again
          │
          ▼
Pod IP re-added to Endpoints → traffic resumes
```

**Use readiness when:** your app needs time to warm up (fill caches, load config), is temporarily overloaded and needs to shed traffic, or depends on a service that's temporarily unavailable.

---

### Startup Probe — "Has the app finished starting?"

Some applications take a long time to start — Spring Boot apps, Python with heavy imports, Java apps with large classpaths, apps that run database migrations on startup.

If you set a liveness probe without a startup probe, Kubernetes might kill the app before it even finishes starting (because liveness fails during the startup window).

**The startup probe disables liveness and readiness probes until it succeeds.** Once the startup probe passes, it is disabled and liveness/readiness take over.

```
Container starts
      │
      ▼
Startup probe runs (liveness + readiness disabled during this time)
      │
      ├─ Succeeds → Startup probe disabled → Liveness + Readiness probes begin
      │
      └─ Fails failureThreshold times → Container killed and restarted
```

**Startup probe timing math:**

```yaml
startupProbe:
  failureThreshold: 30
  periodSeconds: 10
# → 30 * 10 = 300 seconds (5 minutes) maximum startup time
# After 5 minutes without success, container is killed
```

This gives a slow app 5 minutes to start. Once started, the liveness probe checks it every 10 seconds (or whatever you configured). You're not stuck with a 5-minute liveness timeout.

---

## The Four Probe Mechanisms

### 1. HTTP GET

Most common for web services. Kubernetes sends an HTTP GET request. Any `2xx` or `3xx` response code is success. `4xx`, `5xx`, or no response is failure.

```yaml
livenessProbe:
  httpGet:
    path: /healthz      # the endpoint to call
    port: 8080          # the container port
    scheme: HTTP        # or HTTPS
    httpHeaders:        # optional custom headers
      - name: Authorization
        value: "Bearer probe-token"
```

**What your `/healthz` endpoint should do:**

```python
# Liveness endpoint — should be very cheap
# Just check: "am I fundamentally alive?"
@app.route('/healthz')
def liveness():
    return {'status': 'ok'}, 200

# Readiness endpoint — can check dependencies
@app.route('/ready')
def readiness():
    try:
        db.ping()           # check DB connection
        cache.ping()        # check cache
        return {'status': 'ready'}, 200
    except Exception as e:
        return {'status': 'not ready', 'error': str(e)}, 503
```

---

### 2. TCP Socket

Kubernetes tries to open a TCP connection to the specified port. If the connection succeeds (is accepted), the probe passes. Used for non-HTTP services: databases, message brokers, gRPC services without the gRPC health protocol.

```yaml
livenessProbe:
  tcpSocket:
    port: 5432    # postgres port — if TCP connection accepted, probe passes
```

**Limitation:** TCP socket probe only checks if the port accepts connections, not if the app is actually working correctly. A listening port doesn't mean your database is healthy. Use an exec probe with a real query for stronger checks.

---

### 3. Exec (Command)

Kubernetes runs a command inside the container. Exit code `0` = success. Any other exit code = failure.

```yaml
livenessProbe:
  exec:
    command:
      - /bin/sh
      - -c
      - "redis-cli ping | grep -q PONG"
      # exit 0 if redis responds with PONG, non-zero otherwise
```

More examples:
```yaml
# Check if a file exists (e.g. written by the app when it's ready)
readinessProbe:
  exec:
    command: ["test", "-f", "/tmp/app-ready"]

# Run a database health query
livenessProbe:
  exec:
    command:
      - psql
      - -U postgres
      - -c
      - "SELECT 1"
```

**Caution:** Exec probes spin up a new process inside the container on every check. For a 10-second period, that's 6 process spawns per minute. Keep the command lightweight.

---

### 4. gRPC

For services implementing the [gRPC Health Checking Protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md). Kubernetes calls the `Check` RPC and expects a `SERVING` status.

```yaml
livenessProbe:
  grpc:
    port: 50051         # the gRPC server port
    service: ""         # optional: specific service to check (empty = overall health)
```

Requires Kubernetes 1.24+ and the app must implement the gRPC health protocol.

---

## Probe Timing Parameters

Every probe shares these parameters. Understanding them prevents the most common probe misconfiguration bugs.

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 10   # wait 10s after container starts before first probe
  periodSeconds: 10          # check every 10 seconds
  timeoutSeconds: 5          # probe must respond within 5s or it's a failure
  failureThreshold: 3        # 3 consecutive failures → action taken
  successThreshold: 1        # 1 success → back to healthy (must be 1 for liveness)
```

### Visualising the Timeline

```
Container starts
    │
    ├── [0s - 10s]: initialDelaySeconds — no probes run
    │
    ├── [10s]: first probe runs
    │   ├── Success → healthy
    │   └── Failure (1/3)
    │
    ├── [20s]: second probe runs
    │   └── Failure (2/3)
    │
    ├── [30s]: third probe runs
    │   └── Failure (3/3) → failureThreshold reached → container restarted
    │
    ├── [10s after restart]: probes begin again with initialDelaySeconds
    └── ...
```

### Parameter Guidelines

| Parameter | Default | Guidance |
|-----------|---------|---------|
| `initialDelaySeconds` | 0 | Set to slightly longer than your app's typical startup time. Too low → false failures during startup. Use startup probe instead for slow apps. |
| `periodSeconds` | 10 | 10s is fine for most apps. 5s for latency-sensitive, 30s for cheap batch workloads. |
| `timeoutSeconds` | 1 | Must be less than `periodSeconds`. Set to how long a healthy response should take + buffer. |
| `failureThreshold` | 3 | 3 is usually right. Higher = more tolerance for transient failures. Lower = faster reaction. |
| `successThreshold` | 1 | For liveness: must be 1 (Kubernetes enforces this). For readiness: can be higher to require sustained recovery. |

---

## The Critical Design Rule

> **Liveness probes must only check the application itself — never external dependencies.**

This is the single most important rule in this topic. Here's why:

```
BAD: Liveness probe calls the database
─────────────────────────────────────
Database goes down (network blip, maintenance, outage)
  │
  ▼
Liveness probe fails 3 times
  │
  ▼
Kubernetes restarts your app
  │
  ▼
App starts, tries liveness probe again → DB still down → fails → restart
  │
  ▼
CrashLoopBackOff — your app is trapped restarting endlessly
  │
  ▼
When the DB comes back, your app is still in backoff delay
  │
  ▼
You've made a database outage worse by also taking your app offline
```

```
GOOD: Liveness checks only the app itself
──────────────────────────────────────────
Database goes down
  │
  ▼
Liveness probe: "Is the app process alive and not deadlocked?" → YES → passes
  │
  ▼
Readiness probe: "Is the app ready to serve? DB is down" → FAILS
  │
  ▼
Pod removed from Endpoints — no traffic sent
  │
  ▼
Database comes back
  │
  ▼
Readiness probe passes → pod re-added to Endpoints → traffic resumes
  │
  ▼
App was never restarted — state preserved, no backoff
```

**The rule, stated clearly:**
- **Liveness:** check app-internal health only (is the goroutine alive? is the event loop running?)
- **Readiness:** check anything that must be true for the pod to serve traffic (DB, cache, config loaded)

---

## Complete Real-World Example

See [`examples/03-full-probe-config.yaml`](./examples/03-full-probe-config.yaml) — a web app with all three probes properly configured.

The pattern for a typical web service:

```yaml
spec:
  containers:
    - name: api
      image: my-api:1.0

      # --- Startup: give the app time to finish initialising ---
      startupProbe:
        httpGet:
          path: /healthz
          port: 8080
        failureThreshold: 30     # 30 * 10s = 5 minutes max startup time
        periodSeconds: 10

      # --- Liveness: restart if app is fundamentally broken ---
      livenessProbe:
        httpGet:
          path: /healthz          # lightweight — just checks app is alive
          port: 8080
        initialDelaySeconds: 0   # startup probe handles the delay
        periodSeconds: 15
        timeoutSeconds: 5
        failureThreshold: 3

      # --- Readiness: gate traffic based on app + dependency health ---
      readinessProbe:
        httpGet:
          path: /readyz           # heavier — checks DB, cache, etc.
          port: 8080
        initialDelaySeconds: 0
        periodSeconds: 10
        timeoutSeconds: 3
        failureThreshold: 3
        successThreshold: 1
```

---

## What Probe Failure Looks Like in kubectl

```bash
kubectl get pods
# NAME         READY   STATUS    RESTARTS   AGE
# my-app-xyz   0/1     Running   0          2m    ← READY 0/1 = readiness failing
# my-app-abc   1/1     Running   4          10m   ← RESTARTS = liveness was failing

# READY 0/1 means:
# - Container is running (not crashed)
# - But readiness probe is failing
# - Pod is excluded from Service Endpoints (no traffic)

kubectl describe pod my-app-xyz | grep -A20 "Conditions\|Events"
# Conditions:
#   Type              Status
#   Initialized       True
#   Ready             False      ← pod not ready
#   ContainersReady   False
#   PodScheduled      True
#
# Events:
#   Warning  Unhealthy  readiness probe failed: HTTP probe failed with statuscode: 503
```

---

## Probes and Rolling Updates

Readiness probes make rolling updates safe. During a Deployment rolling update:

```
New pod starts
    │
    ▼
Startup probe runs (if configured)
    │
    ▼
Readiness probe runs
    │
    ├── Fails: pod stays READY=0/1, NOT added to Endpoints
    │         Old pods keep serving traffic — rollout pauses
    │         (configured by minReadySeconds and maxUnavailable)
    │
    └── Passes: pod added to Endpoints, starts serving traffic
              Old pod removed, next pod updated
```

Without readiness probes, Kubernetes would add new pods to the load balancer as soon as they start — even before they're ready. Users would get errors during every rolling update.

---

## Essential Commands

```bash
# See probe status — look at Conditions and Events
kubectl describe pod <name>

# Watch readiness in real time
kubectl get pod <name> -w
# READY column: 0/1 = not ready, 1/1 = ready

# Force a readiness failure (patch the readiness endpoint to return 503)
# then watch the pod drop out of Endpoints
kubectl get endpoints <service-name> -w

# Check probe config on a running pod
kubectl get pod <name> -o jsonpath='{.spec.containers[0].livenessProbe}'
kubectl get pod <name> -o jsonpath='{.spec.containers[0].readinessProbe}'
```

---

## Common Mistakes & Gotchas

### 1. No `initialDelaySeconds` + slow startup = false liveness failures

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  # initialDelaySeconds not set — defaults to 0
  # Probe fires immediately on container start
  # App takes 20s to start → probe fails 2-3 times → container restarted
  # App never gets a chance to start → CrashLoopBackOff
```

Fix: use a startup probe for slow apps, or set `initialDelaySeconds` to cover startup time.

### 2. Using the same endpoint for liveness and readiness

```yaml
livenessProbe:
  httpGet:
    path: /healthz    # checks DB connection
    port: 8080
readinessProbe:
  httpGet:
    path: /healthz    # same endpoint!
    port: 8080
```

If the DB goes down: both probes fail → container restarts → liveness loop. Use separate endpoints with different logic: `/healthz` for liveness (app-only), `/readyz` for readiness (full check).

### 3. Liveness probe timeout shorter than probe period

```yaml
livenessProbe:
  periodSeconds: 10
  timeoutSeconds: 15   # timeout > period — impossible to succeed before next probe fires
```

`timeoutSeconds` must be less than `periodSeconds`. A slow response is counted as a failure if it exceeds `timeoutSeconds`.

### 4. `successThreshold > 1` on liveness probe

Kubernetes enforces `successThreshold: 1` for liveness probes — you cannot require multiple consecutive successes before restarting back to healthy. This only applies to readiness.

### 5. Heavy operations in the health endpoint

```python
@app.route('/healthz')
def liveness():
    # DON'T DO THIS
    run_full_database_integrity_check()   # takes 5 seconds every probe
    scan_all_files()                      # expensive
    return 'ok', 200
```

Health endpoints should return in milliseconds. They're called every few seconds. Expensive health checks add significant overhead to every pod and create false failures when the check itself times out.

---

## Common Questions & Doubts

### "If a readiness probe fails, will the pod eventually be restarted?"

No — readiness failure alone never causes a restart. The pod stays running but gets removed from the Service Endpoints (traffic stops). Only liveness probe failure (or the container itself crashing) causes a restart. A pod can sit at `READY: 0/1` indefinitely without being restarted, as long as the liveness probe passes.

---

### "What's the difference between `READY: 0/1` and `STATUS: Running`?"

- `STATUS: Running` means the container process is running (not crashed, not pending)
- `READY: 0/1` means the readiness probe is failing — the container is alive but not serving traffic

A pod can be `Running` and `0/1 READY` at the same time. This is the normal state during startup (before readiness probe passes) or when a dependency is down. It is not an error state — it means Kubernetes is correctly holding traffic until the pod is truly ready.

---

### "Should I implement health check endpoints in every app?"

Yes, for any app that runs as a long-lived service. The health endpoint is a first-class concern, not an afterthought. Without it, you're relying on TCP socket probes (connection accepted ≠ app healthy) or exec probes (more overhead). HTTP health endpoints are cheap to implement and give you precise control over what "healthy" and "ready" mean for your app.

---

### "Can I have a readiness probe without a liveness probe?"

Yes, and it's often the right choice. If your app can't self-recover from any bad state (most apps can't), adding a liveness probe that restarts it might just mask a deeper problem. Many teams start with only a readiness probe and add a liveness probe only for specific known failure modes (e.g. a known deadlock bug that's hard to fix). Start simple.

---

### "What happens during a node failure? Do probes detect it?"

No — probes run on the node where the pod lives. If the node goes down entirely, the probes stop running. The control plane detects the node as `NotReady` through a different mechanism (node heartbeats/leases, topic 06). After the grace period (~5 minutes), it evicts pods from the dead node and reschedules them. Probes are for in-process app health, not node-level failure detection.

---

## Interview Questions

**Q1. What is the difference between a liveness probe and a readiness probe?**

<details>
<summary>Show answer</summary>

- **Liveness probe**: checks whether the container should be restarted. If it fails `failureThreshold` times, Kubernetes kills and restarts the container. Use it for unrecoverable states — deadlocks, hung goroutines, fatal corruption.
- **Readiness probe**: checks whether the container should receive traffic. If it fails, the pod's IP is removed from Service Endpoints — no new requests are routed to it. The container is NOT restarted. Use it for temporary unavailability — warming up, dependency down, temporarily overloaded.

The key difference: readiness is a traffic gate (reversible), liveness is a restart trigger (disruptive).

</details>

---

**Q2. What is a startup probe and why would you use it?**

<details>
<summary>Show answer</summary>

A startup probe protects slow-starting containers. While the startup probe is running, liveness and readiness probes are disabled — giving the app time to initialise without being killed. Once the startup probe succeeds, it is disabled and liveness/readiness take over.

Use case: a Spring Boot app that takes 90 seconds to start. Without a startup probe, you'd need `initialDelaySeconds: 90` on the liveness probe — meaning a genuine deadlock after startup would take 90+ seconds to detect. With a startup probe, you give the app up to `failureThreshold × periodSeconds` to start, then liveness detects real issues within its own fast cycle.

</details>

---

**Q3. A pod shows `READY: 0/1` but `STATUS: Running`. What does that mean and how do you debug it?**

<details>
<summary>Show answer</summary>

The container process is running but the readiness probe is failing. The pod is excluded from Service Endpoints — it's receiving no traffic. The pod has not restarted.

To debug:
```bash
kubectl describe pod <name>
```
Look at:
1. `Conditions` section — `ContainersReady: False` and `Ready: False`
2. `Events` section — "Unhealthy" events showing why the readiness probe failed (HTTP status code, connection refused, command exit code, etc.)
3. `kubectl logs <name>` — app logs may explain why it's not ready (DB connection failure, config error, etc.)

</details>

---

**Q4. Why should a liveness probe never check external dependencies like a database?**

<details>
<summary>Show answer</summary>

If the liveness probe checks the database and the database goes down:
1. Liveness probe fails → container restarts
2. Restarted container tries the liveness probe → database still down → fails again
3. Cycle repeats → CrashLoopBackOff

The app itself is healthy — restarting it doesn't fix the database. You've compounded a database outage by also taking your app offline and trapping it in a restart loop. When the database recovers, the app is still in exponential backoff, delaying recovery further.

Liveness should only check app-internal state (event loop alive, goroutines not deadlocked). Readiness can check dependencies — if they're down, the app stops receiving traffic gracefully without restarting.

</details>

---

**Q5. What are the four probe mechanisms in Kubernetes?**

<details>
<summary>Show answer</summary>

1. **HTTP GET**: sends GET to `path:port`; 2xx or 3xx = success. Most common for web services. Best for detailed health logic in your app's health endpoint.
2. **TCP Socket**: opens a TCP connection to a port; accepted = success. Works for any TCP server (databases, brokers) but only verifies the port accepts connections — not app-level health.
3. **Exec**: runs a command inside the container; exit code 0 = success. Flexible but spawns a process on every check — keep commands cheap.
4. **gRPC**: calls the gRPC Health Checking Protocol's `Check` RPC; `SERVING` status = success. Requires K8s 1.24+ and app implementation of the gRPC health protocol.

</details>

---

**Q6. What do `initialDelaySeconds`, `failureThreshold`, and `successThreshold` do?**

<details>
<summary>Show answer</summary>

- `initialDelaySeconds`: how long after the container starts before the first probe fires. Protects against false failures during app startup. For slow-starting apps, use a startup probe instead.
- `failureThreshold`: how many consecutive probe failures trigger action (restart for liveness, traffic removal for readiness). Default is 3. Higher = more tolerant of transient failures; lower = faster reaction to real failures.
- `successThreshold`: how many consecutive successes are required to transition from unhealthy back to healthy. Must be 1 for liveness (Kubernetes enforces this). For readiness, setting it higher (e.g. 2) prevents flapping — the pod must prove it's stable before traffic resumes.

</details>

---

**Q7. How do readiness probes make rolling updates safer?**

<details>
<summary>Show answer</summary>

During a rolling update, new pods start and Kubernetes only routes traffic to them once their readiness probe passes. Old pods are only terminated after new pods are confirmed ready. Without readiness probes, Kubernetes would send traffic to a new pod the moment it starts — before it's actually ready to serve — causing errors during every update. With readiness probes, the rollout pauses at each step until the new pod proves it can handle traffic, ensuring zero-downtime updates as long as the new version's readiness endpoint works correctly.

</details>

---

**Q8. What happens if both a liveness and readiness probe are failing at the same time?**

<details>
<summary>Show answer</summary>

Both act independently:
- Readiness failure removes the pod from Service Endpoints immediately (within one `failureThreshold` cycle).
- Liveness failure (after its own `failureThreshold` cycles) restarts the container.

In practice: readiness failure happens first (often same cycle). The pod stops receiving traffic. Then liveness failure happens and restarts the container. After restart, the startup probe (if configured) runs, then readiness must pass before traffic resumes. The container cycling through this pattern is a sign that either the liveness probe logic is wrong (checking a dependency) or the app truly has an unrecoverable failure.

</details>

---

## Summary

| Concept | In one sentence |
|---------|----------------|
| Liveness probe | Checks if the container should be restarted — triggers restart on failure |
| Readiness probe | Checks if the container should receive traffic — removes from Endpoints on failure, no restart |
| Startup probe | Protects slow-starting apps — disables liveness/readiness until app is up |
| HTTP GET | Probe sends HTTP GET; 2xx/3xx = success — most common for web services |
| TCP Socket | Probe opens TCP connection; accepted = success — for non-HTTP services |
| Exec | Probe runs a command; exit 0 = success — flexible but spawns a process |
| gRPC | Probe calls gRPC health protocol — requires K8s 1.24+ and app support |
| `initialDelaySeconds` | Wait time before first probe — prevents false failures during startup |
| `failureThreshold` | Consecutive failures before action is taken (default: 3) |
| `successThreshold` | Consecutive successes to recover (must be 1 for liveness) |
| READY 0/1 | Container running but readiness probe failing — excluded from traffic |
| Design rule | Liveness checks app-internal health only; readiness can check dependencies |

---

## Exercises

See [exercises/README.md](./exercises/README.md) for hands-on practice.

---

## Navigation

**[← 08: Resource Limits](../08-resource-limits/README.md)** | **[10: Ingress →](../10-ingress/README.md)**
