# 08 — Resource Limits

> **Goal:** Understand why unconstrained containers are dangerous, the critical difference between requests and limits, why CPU and memory behave completely differently when limits are breached, what Quality of Service classes mean for your pod's eviction priority, and how to set sensible values in practice.

---

## Table of Contents

- [The Problem: The Noisy Neighbor](#the-problem-the-noisy-neighbor)
- [The Analogy: Hotel Room Reservation + Physical Size Limit](#the-analogy-hotel-room-reservation--physical-size-limit)
- [Core Vocabulary](#core-vocabulary)
- [Resource Units](#resource-units)
- [Requests vs Limits: The Full Picture](#requests-vs-limits-the-full-picture)
- [What Happens When Neither Is Set](#what-happens-when-neither-is-set)
- [Quality of Service (QoS) Classes](#quality-of-service-qos-classes)
- [How to Actually Set Sensible Values](#how-to-actually-set-sensible-values)
- [How to Detect OOMKill](#how-to-detect-oomkill)
- [CPU Throttling — How to Detect It](#cpu-throttling--how-to-detect-it)
- [The Relationship with LimitRange (from Topic 06)](#the-relationship-with-limitrange-from-topic-06)
- [Namespace-Wide Limits Overview](#namespace-wide-limits-overview)
- [Essential Commands](#essential-commands)
- [Common Mistakes & Gotchas](#common-mistakes--gotchas)
- [Common Questions & Doubts](#common-questions--doubts)
- [Interview Questions](#interview-questions)
- [Summary](#summary)
- [Exercises](#exercises)
- [Navigation](#navigation)

---

## The Problem: The Noisy Neighbor

Imagine four tenants in an apartment building sharing a fixed water supply:

- Tenant A (your app): uses 20 gallons/day normally
- Tenant B (a batch job): suddenly starts using 400 gallons/day — taking hot showers all day
- Tenants C and D (other services): get no hot water, their service degrades

This is the **noisy neighbor** problem. Without resource limits, one misbehaving pod can starve every other pod on the same node.

In Kubernetes:

```
Node with 8 CPU cores, 16GB RAM
├── Pod A: web app — needs 0.5 CPU, 256MB RAM normally
├── Pod B: rogue batch job — no limits set, takes 7 CPU cores and 14GB RAM
├── Pod C: API service — throttled to almost nothing, starts timing out
└── Pod D: monitoring — can't get CPU to send alerts about the problem
```

**Resource limits prevent one pod from consuming what belongs to others.**

They also enable Kubernetes to make smart scheduling decisions — but only if you tell it what your pod actually needs.

---

## The Analogy: Hotel Room Reservation + Physical Size Limit

Think about booking a hotel:

```
Requests = your reservation
  → The hotel holds a room for you
  → They won't give it to someone else
  → If you don't show up, the room sits empty (wasted)

Limits = the maximum room size the hotel will give you
  → Even if you want a bigger suite, you can't have it
  → You're physically capped
```

And the type of resource determines what happens when you exceed the limit:

```
CPU limit = speed limit on a road
  → You're slowed down (throttled) if you exceed it
  → You don't crash, you just go slower
  → No data loss

Memory limit = size of your fuel tank
  → If you try to put more fuel than the tank holds, it overflows
  → The engine stops (OOMKill) — the container is killed
  → Data loss is possible
```

This is the single most important distinction in this entire topic.

---

## Core Vocabulary

| Term | Meaning |
|------|---------|
| **Request** | The amount of CPU/memory Kubernetes **reserves** for your container on the node — used for scheduling |
| **Limit** | The **maximum** CPU/memory your container can use — enforced at runtime by the kernel |
| **Millicores (m)** | CPU unit: 1000m = 1 core. `100m` = 10% of one CPU core |
| **OOMKill** | Out Of Memory Kill — the kernel forcibly terminates a container that exceeds its memory limit |
| **Throttling** | CPU is slowed but not killed when it exceeds its limit |
| **QoS class** | Quality of Service — Guaranteed, Burstable, or BestEffort — determines eviction priority |
| **cgroups** | Linux kernel feature used to enforce CPU and memory limits on containers |
| **Eviction** | Kubernetes terminating a pod on a memory-pressured node to free resources |
| **Resource pressure** | A node condition where CPU or memory is running low |

---

## Resource Units

### CPU

```
1     = 1 vCPU / 1 core / 1 hyperthread
0.5   = half a core
500m  = 500 millicores = half a core (same as 0.5)
100m  = 100 millicores = one tenth of a core
10m   = the minimum meaningful CPU request (< 10m rounds to zero)
```

CPU is **time-based** — `100m` means your container gets 10% of a CPU core's time per second.

### Memory

```
Ki  = kibibyte  = 1,024 bytes         (binary, 2^10)
Mi  = mebibyte  = 1,048,576 bytes     (binary, 2^20)
Gi  = gibibyte  = 1,073,741,824 bytes (binary, 2^30)

K   = kilobyte  = 1,000 bytes         (decimal — less common in K8s)
M   = megabyte  = 1,000,000 bytes
G   = gigabyte  = 1,000,000,000 bytes
```

> **Always use `Mi` and `Gi`**, not `M` and `G`. The difference is small but can cause confusion — `500M` is ~477 MiB, which might round differently than you expect.

---

## Requests vs Limits: The Full Picture

This is the most important concept in this topic. Read it carefully.

```yaml
resources:
  requests:
    cpu: "100m"       # I need at least 0.1 cores to function
    memory: "128Mi"   # I need at least 128MB to function
  limits:
    cpu: "500m"       # I can burst up to 0.5 cores maximum
    memory: "256Mi"   # I must never exceed 256MB — or I get killed
```

### What Requests Do

Requests are used by the **scheduler** — not the runtime.

When a pod is created, the scheduler looks at every node and asks:
> "Does this node have enough **unallocated** resources to satisfy this pod's requests?"

```
Node: 4 CPU cores, 8GB RAM
Already allocated by requests:
  Pod A: cpu=500m, memory=1Gi
  Pod B: cpu=1000m, memory=2Gi
  Pod C: cpu=500m, memory=1Gi
  Total used: 2000m CPU, 4Gi RAM

Remaining allocatable: 2000m CPU, 4Gi RAM

New pod requests cpu=2500m, memory=3Gi → REJECTED by scheduler
New pod requests cpu=500m, memory=1Gi  → ACCEPTED (fits within remaining)
```

Requests do **not** stop a pod from using more at runtime. They are a scheduling hint and a reservation.

### What Limits Do

Limits are enforced at runtime by the Linux kernel via **cgroups** — completely independent of scheduling.

**CPU limit — throttling:**

```
Container CPU limit: 500m (half a core)
Container actual usage: 800m

→ Kernel throttles the container's CPU time
→ It can only run 50% of the time — the remaining 30% is suppressed
→ Container keeps running, just slower
→ Your requests take longer to process — latency increases
→ No restart, no crash
```

**Memory limit — OOMKill:**

```
Container memory limit: 256Mi
Container actual usage: 260Mi (tries to allocate a bit more)

→ Kernel's OOM killer activates
→ The container process is killed immediately (SIGKILL)
→ Kubernetes sees the container exited
→ Based on restartPolicy, it restarts the container
→ RESTARTS counter increments in kubectl get pods
→ If it keeps happening: CrashLoopBackOff
```

This asymmetry is why OOMKill is far more dangerous than CPU throttling: **a throttled app is slow but alive; an OOMKilled app loses in-flight state and may CrashLoop**.

---

## What Happens When Neither Is Set

```yaml
containers:
  - name: app
    image: my-app:1.0
    # No resources block at all
```

- **Scheduling**: the scheduler places this pod on any node with any available space. No reservation.
- **Runtime**: the container can use as much CPU and memory as the node has. No ceiling.
- **QoS class**: BestEffort — first to be evicted when the node is under memory pressure.

This is the noisy neighbor scenario. Avoid it in any shared cluster.

---

## Quality of Service (QoS) Classes

Kubernetes automatically assigns every pod one of three QoS classes based on its resource spec. You don't set this — it's derived.

```bash
kubectl get pod my-pod -o jsonpath='{.status.qosClass}'
# Guaranteed / Burstable / BestEffort
```

### Guaranteed (Highest Priority)

**Rule:** Every container in the pod has `requests == limits` for both CPU and memory.

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "500m"      # same as request
    memory: "256Mi"  # same as request
```

- Scheduler reserves exactly this — the node is never over-committed for these resources
- Last to be evicted when a node runs low on memory
- Best for production databases, stateful services, anything where interruption is costly

### Burstable (Medium Priority)

**Rule:** At least one container has requests or limits set, but they're not equal (or one is missing).

```yaml
resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"      # limit > request — can burst up to 500m
    memory: "256Mi"
```

- Can use more than requested if the node has spare capacity
- Evicted before Guaranteed pods when memory pressure occurs
- Best for most stateless applications with variable load

### BestEffort (Lowest Priority)

**Rule:** No requests or limits set anywhere in the pod.

- Can use anything available
- **First to be evicted** when a node is under memory pressure — Kubernetes kills these before touching any other class
- Practically: never use this in shared clusters or production

### The Eviction Order During Node Memory Pressure

```
Node running low on memory
        │
        ▼
  1. Evict BestEffort pods first (no reservations, lowest priority)
        │
        ▼
  2. Evict Burstable pods that are using MORE than their requests
        │
        ▼
  3. Evict Burstable pods using at/below their requests
        │
        ▼
  4. Evict Guaranteed pods only as absolute last resort
```

This is why setting requests and limits is not just about performance — **it directly determines whether your pod gets evicted when things go wrong.**

---

## How to Actually Set Sensible Values

Setting requests and limits is one of the hardest practical problems in Kubernetes. Here's a systematic approach:

### Step 1: Measure First

Don't guess. Run your app under realistic load and observe actual usage:

```bash
# Real-time resource usage (requires metrics-server)
kubectl top pods
kubectl top pods --containers   # per-container breakdown
kubectl top nodes

# Historical: use your observability stack
# Prometheus + Grafana: container_cpu_usage_seconds_total, container_memory_working_set_bytes
# Datadog: kubernetes.cpu.usage, kubernetes.memory.usage
```

### Step 2: Set Requests at P50 Usage

Your request should cover normal (median) load:

```
Observed CPU usage:
  P50 (median):  80m
  P95:           250m
  P99 (peak):    400m

Set requests.cpu = 100m   (slightly above P50 — gives headroom for normal variance)
Set limits.cpu   = 500m   (covers P99 + burst — you may throttle at peaks)
```

### Step 3: Set Memory Limits Generously (CPU Limits Conservatively)

- **Memory:** OOMKill is hard to debug and causes restarts. Set limits with 20-30% headroom above your P99 usage. Running out of memory is worse than running slow.
- **CPU:** Throttling is recoverable. Setting CPU limits lower is safer — the app just slows briefly at peaks.

```
Observed memory usage:
  P99: 180Mi
  Set limit: 256Mi   (42% headroom — account for GC spikes, caches, etc.)
```

### Step 4: Watch and Adjust

Deploy with your initial values and watch these signals:
- `kubectl top pods` — actual usage vs requests
- OOMKill events → limit is too low → increase memory limit
- High CPU throttle → check if it's causing latency issues → raise CPU limit or optimize app
- Pods pending → requests too high → not enough nodes → lower requests or scale cluster

---

## How to Detect OOMKill

```bash
# RESTARTS > 0 on a pod is a warning sign
kubectl get pods
# NAME         READY   STATUS    RESTARTS   AGE
# my-app-xyz   1/1     Running   3          10m   ← 3 restarts is suspicious

# Check the last termination reason
kubectl describe pod my-app-xyz | grep -A5 "Last State"
# Last State:  Terminated
#   Reason:    OOMKilled   ← confirmed OOMKill
#   Exit Code: 137         ← 137 = 128 + 9 (SIGKILL)

# See how much memory it was using when killed
kubectl describe pod my-app-xyz | grep -A10 "Limits\|Requests"

# Check container events
kubectl describe pod my-app-xyz | grep -i oom
```

Exit code 137 = `128 + SIGKILL(9)` = OOMKilled. This is the signature you look for.

---

## CPU Throttling — How to Detect It

CPU throttling doesn't crash pods, so it's harder to notice. Signs:
- Latency spikes that don't correlate with traffic spikes
- Requests taking longer than expected during load

To measure throttling, you need Prometheus:

```promql
# CPU throttled fraction for a container
rate(container_cpu_throttled_seconds_total[5m])
  /
rate(container_cpu_usage_seconds_total[5m])
```

A throttle ratio above 25% suggests your CPU limit is too low and causing real performance impact. Raise the limit or optimize the app.

---

## The Relationship with LimitRange (from Topic 06)

From topic 06, `LimitRange` can inject default requests and limits into pods that don't specify them. This interacts directly with resource limits:

```yaml
# LimitRange in a namespace:
default:
  cpu: "500m"
  memory: "256Mi"
defaultRequest:
  cpu: "100m"
  memory: "64Mi"
```

When you deploy a pod without a `resources` block in a namespace that has this LimitRange, Kubernetes injects those defaults automatically. The pod gets `Burstable` QoS class (since requests ≠ limits).

This is the safety net for teams that forget to set resources.

---

## Namespace-Wide Limits Overview

| Object | Scope | What it controls |
|--------|-------|-----------------|
| `resources.requests` | Container | Scheduling reservation + QoS class |
| `resources.limits` | Container | Runtime cap (throttle/OOMKill) |
| `LimitRange` | Namespace | Default + min/max per container |
| `ResourceQuota` | Namespace | Total consumption cap for the whole namespace |

All four work together. LimitRange fills in what the developer forgot. ResourceQuota catches teams that try to collectively exceed their fair share.

---

## Essential Commands

```bash
# See resource usage right now (requires metrics-server addon)
kubectl top pods
kubectl top pods -A                     # all namespaces
kubectl top pods --containers           # per-container breakdown
kubectl top nodes

# Enable metrics-server on Minikube
minikube addons enable metrics-server
kubectl top pods   # works after ~60 seconds

# Inspect resource spec of a running pod
kubectl get pod my-pod -o jsonpath='{.spec.containers[*].resources}'

# Check QoS class
kubectl get pod my-pod -o jsonpath='{.status.qosClass}'

# Look for OOMKill in pod history
kubectl describe pod my-pod | grep -A5 "Last State"
```

---

## Common Mistakes & Gotchas

### 1. Setting memory limit too close to working set

```yaml
limits:
  memory: "128Mi"   # app normally uses 110Mi — only 16% headroom
```

Java, Node.js, and Python applications have garbage collectors that can briefly spike memory usage 1.5-2x above the working set. A GC cycle at 110Mi usage can briefly hit 160Mi → OOMKill → restart → repeat → CrashLoopBackOff.

**Fix:** Set memory limits at least 20-30% above your P99, more for GC-heavy runtimes.

### 2. Setting no CPU limits at all in a shared cluster

```yaml
resources:
  requests:
    cpu: "100m"
  # No CPU limit
```

This is actually a valid pattern for some teams — it avoids CPU throttling entirely and lets the app burst freely. But in a shared cluster it creates noisy neighbors. The trade-off: throttling (with limits) vs starvation (without limits). If you choose no CPU limits, use ResourceQuota to cap the namespace total.

### 3. Confusing `Mi` with `MB`

```yaml
memory: "500M"    # 500 megabytes (decimal) = 476.8 MiB
memory: "500Mi"   # 500 mebibytes (binary)  = 524.3 MB
```

The difference is small (~5%) but can matter when doing capacity planning. Kubernetes internally uses binary units — use `Mi` and `Gi` to avoid ambiguity.

### 4. Requests higher than limits

```yaml
resources:
  requests:
    memory: "512Mi"
  limits:
    memory: "256Mi"   # limit < request — invalid!
```

Kubernetes rejects this. Limits must always be >= requests.

### 5. Setting `requests == limits` blindly for everything

Guaranteed QoS sounds great but it means zero bursting. If your app has variable load (it almost certainly does), setting `requests == limits` means you either over-provision (wasteful) or under-provision (OOMKills during peaks). Use Burstable for most workloads unless you need precise reservation guarantees.

---

## Common Questions & Doubts

### "If I don't set limits, can my container use the entire node's resources?"

Yes. A container without limits can use every CPU cycle and every byte of RAM on the node. This is why namespace ResourceQuotas require limits when active — to force developers to declare consumption. Without either limits or quotas, a single runaway container (memory leak, infinite loop) can take down an entire node.

---

### "Why does Kubernetes kill my pod when it has memory left on the node?"

Because it exceeded **its own limit** — not the node's total. A pod with a 256Mi limit is killed if it tries to use 257Mi, even if the node has 10GB free. The limit is enforced per-container, not per-node. The limit is the contract your pod agreed to when it was created.

---

### "Should I always set CPU limits?"

This is genuinely debated. Arguments against CPU limits:
- CPU is compressible — throttling doesn't crash apps, just slows them
- CPU limits can cause unnecessary latency spikes even when the node has spare capacity
- Some high-performance teams (databases, latency-sensitive services) deliberately omit CPU limits

Arguments for CPU limits:
- Prevents noisy neighbors in shared clusters
- Makes resource accounting predictable
- Required when ResourceQuota is active

**Rule of thumb:** Always set memory limits (OOMKill is dangerous). CPU limits are optional if you trust your team, but use ResourceQuota as a namespace-level safety net.

---

### "What is the `metrics-server` and why do I need it for `kubectl top`?"

`metrics-server` is an in-cluster component that collects CPU and memory usage from kubelets and exposes them via the Kubernetes Metrics API. `kubectl top` queries this API. It's not installed by default on all clusters — on Minikube you enable it with `minikube addons enable metrics-server`. On managed clusters (GKE, EKS, AKS) it's usually pre-installed. Without it, `kubectl top` returns `error: Metrics API not available`.

---

### "How is resource limit enforcement different from a VM?"

In a VM, you get exactly the vCPUs and RAM you configured — no more, no less, always. Kubernetes requests and limits are more nuanced: requests are a scheduling reservation (not enforced at runtime), limits are enforced by cgroups. Multiple pods can be scheduled with total requests exceeding node capacity if Kubernetes predicts they won't all peak simultaneously — this is called **overcommitment**. It's efficient but means QoS eviction order matters.

---

## Interview Questions

**Q1. What is the difference between resource requests and resource limits in Kubernetes?**

<details>
<summary>Show answer</summary>

**Requests** are used by the scheduler to decide which node can host the pod. The node must have at least this much unallocated capacity. Requests reserve space but don't cap runtime usage.

**Limits** are the maximum the container can use at runtime, enforced by the Linux kernel via cgroups. A container can use more than its request (if the node has spare capacity) but never more than its limit.

Example: `requests.cpu: 100m, limits.cpu: 500m` — the scheduler reserves 100m on the node, but the container can burst up to 500m if CPU is available.

</details>

---

**Q2. What happens when a container exceeds its CPU limit? What about its memory limit?**

<details>
<summary>Show answer</summary>

**CPU:** the container is **throttled** — its CPU time is artificially reduced so it cannot exceed the limit. The container keeps running but processes requests more slowly. There is no crash, no restart, no data loss. It's recoverable slowness.

**Memory:** the Linux kernel's OOM killer sends SIGKILL to the container process. The container is **killed immediately** — no graceful shutdown. Kubernetes detects the exit, increments the RESTARTS counter, and restarts the container (per restartPolicy). Repeated OOMKills cause CrashLoopBackOff. Exit code 137 (`128 + 9`) is the signature.

</details>

---

**Q3. What are the three Kubernetes QoS classes and how is each assigned?**

<details>
<summary>Show answer</summary>

QoS is automatically derived from the pod's resource spec — you don't set it directly.

- **Guaranteed**: every container has `requests == limits` for both CPU and memory. Highest eviction priority — last to be evicted. Best for stateful or latency-sensitive workloads.
- **Burstable**: at least one container has requests or limits, but they're not all equal. Can use spare capacity above requests. Evicted after BestEffort but before Guaranteed.
- **BestEffort**: no container has any requests or limits set. Can use anything available. **First evicted** when the node is under memory pressure.

</details>

---

**Q4. How does the Kubernetes scheduler use resource requests?**

<details>
<summary>Show answer</summary>

When a pod is created, the scheduler iterates over nodes and filters out those where the sum of existing pods' requests plus the new pod's requests would exceed the node's allocatable capacity. It then scores the remaining nodes (e.g. by which has the most remaining capacity or best fit) and picks the winner. Requests are the only signal the scheduler has about resource needs — if requests are not set or are too low, the scheduler may pack pods too tightly, leading to OOMKills and throttling at runtime.

</details>

---

**Q5. A pod keeps restarting. How do you determine if it's OOMKilled?**

<details>
<summary>Show answer</summary>

```bash
kubectl describe pod <name>
```

Look for the `Last State` section under the container:
```
Last State:  Terminated
  Reason:    OOMKilled
  Exit Code: 137
```

Exit code 137 = `128 + SIGKILL(9)` = OOMKill. Also check `kubectl get pod <name>` — `RESTARTS > 0` is the first signal. If confirmed, the memory limit is too low: check `kubectl top pods --containers` for recent usage and increase the limit with headroom above P99.

</details>

---

**Q6. What does it mean to "overcommit" resources on a node?**

<details>
<summary>Show answer</summary>

Overcommitment means the sum of all pods' requests on a node exceeds the node's physical capacity. This is intentional — Kubernetes assumes not all pods peak simultaneously. For CPU (compressible), overcommitment causes throttling at peak. For memory (incompressible), overcommitment is more dangerous — if multiple pods spike simultaneously, the node runs out of memory and the OOM killer starts evicting pods in BestEffort → Burstable → Guaranteed order. QoS classes determine which pods survive.

</details>

---

**Q7. Why is it important to set memory limits generously (with headroom), but CPU limits can be tighter?**

<details>
<summary>Show answer</summary>

Exceeding a CPU limit causes throttling — the app slows but recovers automatically once load drops. Exceeding a memory limit causes OOMKill — the container dies, loses in-flight state, and restarts from scratch. For GC-heavy runtimes (Java, Go, Node.js), memory usage can spike 1.5–2x during garbage collection. A limit set too close to the working set will trigger OOMKills during GC cycles, causing CrashLoopBackOff even though the app is behaving normally. Memory limits should have at least 20–30% headroom above P99 usage; more for GC-heavy apps.

</details>

---

**Q8. What is the relationship between LimitRange and resource limits in a pod spec?**

<details>
<summary>Show answer</summary>

A `LimitRange` (topic 06) in a namespace sets default, minimum, and maximum resource values for containers. When a pod is created without a `resources` block, LimitRange injects the `default` and `defaultRequest` values automatically. When a pod specifies resources, LimitRange validates them against the `min` and `max` bounds and rejects the pod if they're out of range. LimitRange is the namespace-level policy; the pod's `resources` block is the per-pod declaration. Together they ensure every container has declared resources (required when ResourceQuota is active) without forcing every developer to remember every time.

</details>

---

## Summary

| Concept | In one sentence |
|---------|----------------|
| Request | Scheduling reservation — the scheduler needs this much free on the node to place the pod |
| Limit | Runtime cap enforced by the kernel — container cannot exceed this |
| CPU throttling | Container exceeds CPU limit → slowed down, not killed — recoverable |
| OOMKill | Container exceeds memory limit → killed immediately by kernel, restarts → exit code 137 |
| Guaranteed QoS | requests == limits for all containers — highest eviction protection |
| Burstable QoS | requests < limits (or mixed) — can burst, medium eviction priority |
| BestEffort QoS | No requests or limits — uses anything available, evicted first |
| Millicores (m) | CPU unit: 1000m = 1 core, 100m = 10% of a core |
| Mi / Gi | Binary memory units (1 Mi = 1,048,576 bytes) — use these, not M/G |
| Overcommitment | Sum of pod requests > node capacity — intentional, relies on pods not all peaking at once |

---

## Exercises

See [exercises/README.md](./exercises/README.md) for hands-on practice.

---

## Navigation

**[← 07: Persistent Volumes](../07-persistent-volumes/README.md)** | **[09: Health Checks →](../09-health-checks/README.md)**
