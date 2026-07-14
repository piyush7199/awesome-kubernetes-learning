# 13 — StatefulSets

> **Goal:** Understand why databases and other stateful workloads need StatefulSets instead of Deployments, and know how stable identity, stable storage, and ordered operations work together.

---

## The Problem

You know from [topic 03](../03-deployments/README.md) that Deployments manage multiple identical Pods. They're great for stateless apps — web servers, APIs — where any Pod is interchangeable with any other.

Now imagine running a PostgreSQL database with Deployments:

**Problem 1 — Storage conflict**
If you have 3 replicas all mounting the same PVC, they all try to write to the same files. Databases don't work that way. Each database node needs its own dedicated storage.

**Problem 2 — Identity matters**
In a PostgreSQL cluster, one node is the primary (accepts writes) and others are replicas (read-only). The replicas need to connect to the primary by a stable hostname. If the primary Pod gets restarted and comes back with a new random name (`postgres-abc123` → `postgres-xyz789`), all the replicas lose their connection.

**Problem 3 — Order matters**
A Kafka cluster needs its ZooKeeper nodes to be running before Kafka brokers start. A MySQL replica must finish initializing before it's allowed to receive traffic. Deployments start all Pods in parallel, with no ordering guarantees.

**StatefulSets** solve all three:
1. Each Pod gets its **own PVC** — private storage that follows it
2. Each Pod gets a **stable name** — `mysql-0`, `mysql-1`, `mysql-2` — that never changes
3. Pods start in **order** — 0 is ready before 1 starts; 1 is ready before 2 starts

---

## The Analogy

Think about a **sports team with jersey numbers**.

A Deployment is like hiring "5 generic workers." If worker #3 quits, you hire a new worker #3 — but they get a random badge number. You can't refer to them by number in a memo because it might be someone different tomorrow.

A StatefulSet is like a sports team. Player **#7** has jersey #7. If they get injured and come back, they wear **#7 again** — not a new random number. Their locker (#7) is always theirs. The team also has rules: the captain (#1) must be on the field before anyone else plays. If #3 gets a red card, #3 leaves first (reverse order).

In Kubernetes:
- **Jersey number** = Pod ordinal (0, 1, 2...)
- **Player name + number** = stable Pod name (`redis-0`, `redis-1`)
- **Locker** = dedicated PVC that stays with the ordinal
- **Captain first** = ordered startup (Pod 0 ready before Pod 1 starts)
- **Last one off the field** = Pod N-1 terminated before Pod N-2

---

## Core Vocabulary

| Term | In one sentence |
|------|-----------------|
| **StatefulSet** | A controller for Pods that need stable identity, stable storage, and ordered operations |
| **Headless Service** | A Service with `clusterIP: None` — gives each Pod its own DNS record instead of load-balancing |
| **Ordinal** | The number suffix on each Pod name: `myapp-0`, `myapp-1`, `myapp-2` |
| **Stable network identity** | Each Pod gets a permanent DNS name: `pod-0.service.namespace.svc.cluster.local` |
| **VolumeClaimTemplate** | A PVC template inside a StatefulSet — creates one PVC per Pod automatically |
| **Ordered deployment** | Pod 0 must be Running+Ready before Pod 1 starts; Pod 1 before Pod 2 |
| **Ordered termination** | Pods shut down in reverse ordinal order: 2 → 1 → 0 |
| **podManagementPolicy** | `OrderedReady` (default, sequential) or `Parallel` (all at once, like a Deployment) |
| **updateStrategy** | `RollingUpdate` (default, updates one pod at a time, highest ordinal first) or `OnDelete` (only updates when you manually delete a pod) |

---

## StatefulSet vs Deployment

| Feature | Deployment | StatefulSet |
|---------|-----------|-------------|
| Pod names | Random hash: `app-7d9f8-xk2lp` | Stable ordinal: `app-0`, `app-1` |
| Storage | Shared PVC or no PVC | Dedicated PVC per Pod |
| Startup order | Parallel (no order) | Sequential: 0 → 1 → 2 |
| Shutdown order | Random | Reverse: 2 → 1 → 0 |
| DNS per Pod | No (only Service DNS) | Yes: `pod-N.service.namespace.svc` |
| Pod restart | New Pod, new name | Same name, same PVC |
| Use for | Stateless apps, APIs | Databases, queues, distributed systems |

---

## How It Works (Architecture)

```
StatefulSet: mydb (replicas: 3)
                │
                │ creates (in order)
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
 mydb-0       mydb-1      mydb-2      ← stable Pod names
    │           │           │
    ▼           ▼           ▼
data-mydb-0  data-mydb-1  data-mydb-2 ← dedicated PVCs (one per pod)


DNS (via Headless Service named "mydb"):
  mydb-0.mydb.default.svc.cluster.local → Pod 0's IP
  mydb-1.mydb.default.svc.cluster.local → Pod 1's IP
  mydb-2.mydb.default.svc.cluster.local → Pod 2's IP

Startup order:
  mydb-0 starts → waits for Running+Ready
         → mydb-1 starts → waits for Running+Ready
                   → mydb-2 starts

Shutdown order (scale down or delete):
  mydb-2 terminated → waits for completion
         → mydb-1 terminated → waits for completion
                    → mydb-0 terminated
```

---

## The Headless Service

A StatefulSet always needs a **Headless Service** — a Service with `clusterIP: None`.

A normal Service picks a random Pod and load-balances:
```
clients → Service (ClusterIP) → random Pod
```

A headless Service returns the actual Pod IPs directly from DNS:
```
client → DNS lookup for mydb-0.mydb.default.svc.cluster.local → mydb-0's IP
client → DNS lookup for mydb-1.mydb.default.svc.cluster.local → mydb-1's IP
```

This is what gives each Pod a stable, addressable hostname. Without the headless Service, there's no per-Pod DNS.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: mydb          # same name used in StatefulSet's serviceName field
spec:
  clusterIP: None     # this is what makes it headless
  selector:
    app: mydb
  ports:
    - port: 5432
```

---

## YAML Walkthrough

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mydb
spec:
  serviceName: mydb        # MUST match the headless Service name
  replicas: 3
  selector:
    matchLabels:
      app: mydb
  template:
    metadata:
      labels:
        app: mydb
    spec:
      containers:
        - name: postgres
          image: postgres:15
          env:
            - name: POSTGRES_PASSWORD
              value: "mypassword"
          ports:
            - containerPort: 5432
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data

  # VolumeClaimTemplates: one PVC is created per Pod automatically
  # PVC names: data-mydb-0, data-mydb-1, data-mydb-2
  volumeClaimTemplates:
    - metadata:
        name: data         # matches volumeMounts.name above
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 1Gi
```

**Key fields:**
- `serviceName` — must match your headless Service; drives the DNS naming
- `volumeClaimTemplates` — PVC blueprint; Kubernetes creates one PVC per Pod
- No `volumes:` block needed — the template handles it

---

## What Happens When a Pod Restarts

This is the core guarantee that makes StatefulSets useful for databases:

```
mydb-1 pod crashes
         │
         ▼
Kubernetes creates a NEW pod
         │
         ▼
New pod is named: mydb-1          ← same name as before
New pod gets:     data-mydb-1     ← same PVC as before (same data)
New pod gets DNS: mydb-1.mydb.default.svc.cluster.local  ← same hostname
         │
         ▼
Other pods reconnect to mydb-1 at the same hostname
Data is exactly where it was before
```

A Deployment would create a pod with a new random name, new PVC (or no PVC), and a new IP — losing data and breaking any hardcoded references.

---

## Update Strategy

When you update a StatefulSet (e.g., new image), it updates Pods one at a time, **highest ordinal first**:

```
replicas: 3, update triggered
  → mydb-2 updated first (waits for Ready)
  → mydb-1 updated next (waits for Ready)
  → mydb-0 updated last
```

This is the reverse of startup order. For databases, this means replicas are updated before the primary — safer than updating the primary first.

**`OnDelete` strategy** — Kubernetes only updates a Pod when you manually delete it. Useful when you need full manual control over the update sequence (e.g., for complex database failover procedures).

```yaml
spec:
  updateStrategy:
    type: OnDelete   # pods only update when you kubectl delete them manually
```

---

## Scaling

Scaling up: adds Pods in order (waits for each to be ready before creating the next).

Scaling down: removes Pods in reverse order (highest ordinal first).

```bash
# Scale up from 1 to 3
kubectl scale statefulset mydb --replicas=3
# Creates mydb-1 (waits for ready), then mydb-2

# Scale down from 3 to 1
kubectl scale statefulset mydb --replicas=1
# Deletes mydb-2 (waits for termination), then mydb-1
```

**PVCs are NOT deleted when scaling down.** If you scale from 3 to 1, `data-mydb-1` and `data-mydb-2` still exist. If you scale back up, `mydb-1` and `mydb-2` will reattach to their old PVCs with the existing data.

---

## Common Mistakes / Gotchas

**1. Forgetting the Headless Service**
The StatefulSet itself doesn't create the Service. You must create a separate Service with `clusterIP: None`. Without it, per-Pod DNS doesn't work.

**2. PVCs are never deleted automatically**
Deleting a StatefulSet does NOT delete its PVCs. You must delete them manually. This is a safety feature — you don't want to lose database data on an accidental `kubectl delete`. But it means storage costs accumulate if you don't clean up.

**3. `serviceName` must match the headless Service name**
If they don't match, per-Pod DNS records aren't created. This silently breaks peer discovery in clustered databases.

**4. `accessModes: ReadWriteOnce` limits you**
Most cloud block storage (EBS, GCE PD) only supports RWO — one node at a time. This means you can't run two Pods of the same StatefulSet on the same node if they share a storage class that only supports RWO. (They don't share storage — each has their own PVC — so this is usually fine, but be aware.)

**5. StatefulSets don't manage database replication for you**
A StatefulSet gives you stable identity and ordered startup — it does NOT configure primary/replica replication. You still need to configure that inside the application (e.g., PostgreSQL streaming replication, Kafka broker config). StatefulSet is the scaffolding; the database logic is yours.

**6. Deleting a pod doesn't delete its PVC**
Pod and PVC have independent lifecycles. `kubectl delete pod mydb-1` — Pod is recreated and reattaches to `data-mydb-1`. The data is safe.

---

## Common Questions & Doubts

**Can I use a regular (non-headless) Service with a StatefulSet?**

Yes — and it's actually common to have both. The headless Service provides per-Pod DNS (required for peer discovery). A regular ClusterIP Service provides a stable load-balanced endpoint for clients who don't care which Pod they hit (e.g., read queries routed to any replica). You'd typically have: one headless Service for internal Pod-to-Pod communication, and one regular Service for external client access.

**Why does the ordinal start at 0 instead of 1?**

Convention inherited from computer science (arrays, indices). In practice: Pod 0 is treated as the "first" and is often the primary. If you're configuring a database cluster, `mydb-0` is conventionally set up as the primary node.

**What happens if I need to run a database with more than 3 replicas — do I need a special image?**

No, the StatefulSet size is independent of the image. You can set `replicas: 5` on a PostgreSQL StatefulSet. However, you must configure the database software itself to accept and replicate to all those peers. The StatefulSet just gives you the stable identity and storage; replication configuration is inside the app.

**Are StatefulSets the right choice for every database?**

For managed databases (RDS, Cloud SQL, Atlas), use those — not StatefulSets. Running a database in Kubernetes adds operational complexity. StatefulSets are the right tool when you genuinely need a self-managed database in-cluster: development environments, databases that don't have a good managed offering, or specific compliance requirements. Many teams use managed databases for production and StatefulSets for dev/test.

**What if Pod 0 crashes while Pod 1 and 2 are running?**

Kubernetes restarts Pod 0 with the same name and PVC. Pod 1 and 2 keep running. But if your application assumes Pod 0 is the primary (primary/replica architecture), you need your application to handle the brief primary outage — Kubernetes does not trigger a failover for you. Tools like Patroni (for PostgreSQL) handle automatic failover and re-election inside the cluster.

---

## Interview Questions

<details>
<summary>Q: What is the difference between a Deployment and a StatefulSet?</summary>

Deployments are for stateless workloads where all Pods are interchangeable. Pods get random names, share (or don't use) PVCs, start in parallel, and can be replaced with differently-named Pods.

StatefulSets are for stateful workloads that need: (1) stable Pod names (`app-0`, `app-1`) that survive restarts, (2) dedicated per-Pod PVCs via `volumeClaimTemplates`, (3) ordered startup (Pod 0 ready before Pod 1 starts), and (4) per-Pod DNS via a headless Service. Use StatefulSets for databases, message queues, and distributed systems where identity and storage continuity matter.
</details>

<details>
<summary>Q: What is a Headless Service and why do StatefulSets need one?</summary>

A Headless Service has `clusterIP: None`. Instead of load-balancing through a virtual IP, DNS returns the actual Pod IPs directly. For a StatefulSet, the headless Service creates a DNS A-record per Pod: `<pod-name>.<service-name>.<namespace>.svc.cluster.local`. This gives each Pod a stable, predictable hostname that survives restarts. Without the headless Service, there's no per-Pod DNS — distributed database nodes can't find each other by name, which breaks peer discovery and replication config.
</details>

<details>
<summary>Q: What happens to PVCs when you delete a StatefulSet?</summary>

They are NOT deleted. Deleting a StatefulSet deletes the Pods and the StatefulSet controller object, but leaves all PVCs intact. This is intentional — you don't want to lose database data on an accidental delete. You must manually delete PVCs: `kubectl delete pvc -l app=mydb`. Similarly, scaling down (e.g., 3→1) does not delete the PVCs for the removed Pods — if you scale back up, the Pods reattach to their existing PVCs with the old data still there.
</details>

<details>
<summary>Q: In what order does a StatefulSet start and stop Pods?</summary>

Startup: ordinals ascending — Pod 0 starts and must reach Running+Ready before Pod 1 starts; Pod 1 must be ready before Pod 2, and so on.

Shutdown (scale down or delete): ordinals descending — highest ordinal terminates first and must fully stop before the next one terminates. For 3 Pods: 2 → 1 → 0.

Updates (RollingUpdate): highest ordinal first — Pod 2 is updated and becomes Ready before Pod 1 is updated, then Pod 0 last. This means replicas are updated before the primary.
</details>

<details>
<summary>Q: What is `volumeClaimTemplates` and how is it different from `volumes`?</summary>

`volumes` in a Pod spec references an existing PVC by name — all Pods in a Deployment using the same volume spec would share one PVC.

`volumeClaimTemplates` in a StatefulSet is a PVC blueprint. Kubernetes creates one PVC per Pod from this template, naming them `<template-name>-<pod-name>`. For a StatefulSet `mydb` with 3 replicas and a template named `data`, it creates: `data-mydb-0`, `data-mydb-1`, `data-mydb-2`. Each Pod gets its own isolated storage, which persists independently of the Pod's lifecycle.
</details>

<details>
<summary>Q: What is `podManagementPolicy: Parallel` and when would you use it?</summary>

By default, StatefulSets use `OrderedReady` — each Pod must be ready before the next one starts. Setting `podManagementPolicy: Parallel` makes the StatefulSet start (or stop) all Pods simultaneously, like a Deployment.

Use it when: (a) your application doesn't require ordering (e.g., independent cache nodes that don't replicate), or (b) you're doing bulk operations and the startup time with ordering would be impractically long. Don't use it for databases with primary/replica relationships — if the replica starts before the primary is ready, replication setup will fail.
</details>

<details>
<summary>Q: Scenario — Your StatefulSet has 3 replicas. Pod mydb-1 is stuck in CrashLoopBackOff. What do you check and how does this affect mydb-0 and mydb-2?</summary>

First: `kubectl describe pod mydb-1` and `kubectl logs mydb-1` to find the crash reason — common causes are bad config, missing env vars, or a PVC issue.

Effect on other Pods: mydb-0 and mydb-2 are unaffected and keep running. A StatefulSet does not take down healthy Pods when one crashes — they're independently managed.

Effect on scaling: if you try to scale up (add a 4th replica), Kubernetes will wait for mydb-1 to become healthy first before creating mydb-3, because ordered deployment requires Pods to be ready in sequence.

Fix options: (1) fix the root cause (bad config → update ConfigMap/Secret, then delete the pod so it restarts cleanly), (2) if PVC corruption: delete the pod + PVC and let StatefulSet recreate both from scratch (data loss for that node), (3) if transient error: sometimes simply `kubectl delete pod mydb-1` to force a fresh start is enough.
</details>

---

## Summary

| Concept | What to remember |
|---------|-----------------|
| When to use | Databases, queues, distributed systems — anything with per-node state |
| Stable names | `app-0`, `app-1`, `app-2` — survive restarts, never change |
| volumeClaimTemplates | Creates one PVC per Pod: `data-app-0`, `data-app-1` |
| Headless Service | `clusterIP: None` — gives each Pod its own DNS entry |
| Startup order | 0 → 1 → 2, sequential, each must be Ready first |
| Shutdown order | 2 → 1 → 0, reverse, each must finish before next |
| Update order | 2 → 1 → 0 (highest first, replicas before primary) |
| PVC lifecycle | NOT deleted with StatefulSet — must be deleted manually |
| Replication | StatefulSet gives identity; YOU configure database replication |
| podManagementPolicy | `Parallel` for independent nodes; `OrderedReady` (default) for databases |

---

## Exercises

Work through the hands-on tasks in [exercises/README.md](./exercises/README.md).

---

**Previous topic:** [12 — Helm](../12-helm/README.md)
**Next topic:** [14 — DaemonSets](../14-daemonsets/README.md)
