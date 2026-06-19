# 03 — Deployments

> **Goal:** Understand why bare pods are not enough for production, how Deployments keep your app alive automatically, and how to update and roll back without downtime.

---

## The Problem: Pods Are Mortal

In topic 02 you learned that pods are ephemeral — when a node dies, any pods on it are **gone forever** unless something recreates them.

Imagine you `kubectl apply` three separate pod YAML files for your web app:

```
pod-web-1   → running on node-A
pod-web-2   → running on node-B
pod-web-3   → running on node-B
```

Node-B goes down overnight. You wake up to one pod instead of three — and nobody told you.

Even if the node comes back, Kubernetes does **not** reschedule those pods. They're just dead.

You also need to:
- Update your app to a new version without taking all pods offline at once
- Roll back instantly if the new version has a bug
- Scale from 3 copies to 10 with a single command

**A Deployment solves all of this.**

---

## The Analogy: A Restaurant Franchise Manager

Think of a fast-food chain that must always have exactly 5 restaurants open in a city:

| Franchise concept | Kubernetes equivalent |
|-------------------|-----------------------|
| The franchise contract | The **Deployment** (desired state: "always 5 open") |
| Currently open restaurants | **Pods** (running instances of your app) |
| The manager tracking locations | **ReplicaSet** (ensures the right count is running) |
| Renovating one restaurant at a time | **Rolling update** (update without closing everything) |
| Reverting to last week's menu | **Rollback** |

When a restaurant closes unexpectedly (pod crashes / node dies), the manager notices and immediately opens a replacement at another location. You never have to phone the manager — they're watching 24/7.

When you want to introduce a new menu (new app version), the manager renovates restaurants one by one. Customers always have somewhere to eat.

---

## Core Vocabulary

| Term | Meaning |
|------|---------|
| **Deployment** | A controller that manages a set of identical pods and keeps them in your desired state |
| **ReplicaSet** | Created by the Deployment; its only job is to ensure exactly N pod replicas exist |
| **Replica** | One running instance (pod) of your app |
| **Rolling update** | Replacing old pods with new ones gradually — zero downtime |
| **Rollback** | Reverting to a previous version of the Deployment |
| **Revision** | A snapshot of a Deployment's configuration, stored so you can roll back to it |
| **maxSurge** | How many extra pods above the desired count are allowed during an update |
| **maxUnavailable** | How many pods below the desired count are allowed during an update |
| **Recreate** | An update strategy that kills all old pods first, then starts new ones (has downtime) |

---

## How It Works

A Deployment manages a **ReplicaSet**, which manages **Pods**.

```
You
 │
 │  kubectl apply -f deployment.yaml
 ▼
Deployment (desired: 3 replicas of nginx:1.25)
 │
 │  creates and manages
 ▼
ReplicaSet (nginx:1.25 — owns 3 pods)
 ├── Pod 1  (nginx:1.25)   running on node-A
 ├── Pod 2  (nginx:1.25)   running on node-B
 └── Pod 3  (nginx:1.25)   running on node-C
```

The ReplicaSet watches its pods constantly. The moment a pod dies:

```
Pod 3 crashes
      │
      ▼
ReplicaSet sees: actual=2, desired=3
      │
      ▼
ReplicaSet creates Pod 4 on any healthy node
      │
      ▼
actual=3 again — alert not needed, nobody paged
```

### What Happens During a Rolling Update

When you change the image from `nginx:1.25` to `nginx:1.26`:

```
Before update:
ReplicaSet-A (nginx:1.25): Pod1, Pod2, Pod3

Step 1 — Deployment creates a new ReplicaSet:
ReplicaSet-A (nginx:1.25): Pod1, Pod2, Pod3
ReplicaSet-B (nginx:1.26): Pod4           ← new pod started

Step 2 — Old pod terminated, new one added:
ReplicaSet-A (nginx:1.25): Pod1, Pod2
ReplicaSet-B (nginx:1.26): Pod4, Pod5

Step 3 — Repeat until done:
ReplicaSet-A (nginx:1.25): Pod1
ReplicaSet-B (nginx:1.26): Pod4, Pod5, Pod6

Step 4 — Complete:
ReplicaSet-A (nginx:1.25): (0 pods, kept for rollback)
ReplicaSet-B (nginx:1.26): Pod4, Pod5, Pod6
```

At no point were all pods unavailable. Traffic kept flowing.

---

## YAML Walkthrough

See [`examples/01-basic-deployment.yaml`](./examples/01-basic-deployment.yaml):

```yaml
apiVersion: apps/v1       # Deployment lives in the 'apps' API group, not core 'v1'
kind: Deployment
metadata:
  name: web-app
  labels:
    app: web-app
spec:
  replicas: 3             # desired number of pods running at all times

  selector:               # how the Deployment finds the pods it owns
    matchLabels:
      app: web-app        # must match the labels in the pod template below

  template:               # the pod blueprint — everything below is a pod spec
    metadata:
      labels:
        app: web-app      # must match selector.matchLabels above
    spec:
      containers:
        - name: nginx
          image: nginx:1.25
          ports:
            - containerPort: 80
```

The `selector` is critical. It's how the Deployment (and its ReplicaSet) knows which pods belong to it. If a pod has the label `app: web-app`, the ReplicaSet counts it. If it doesn't, the ReplicaSet ignores it.

---

## Controlling the Rolling Update

By default, K8s updates one pod at a time. You can tune this:

```yaml
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1         # allow 1 extra pod above desired (so up to 4 pods during update)
      maxUnavailable: 0   # never let the count drop below desired (always 3 available)
```

See [`examples/02-rolling-update-deployment.yaml`](./examples/02-rolling-update-deployment.yaml) for the full config.

### maxSurge and maxUnavailable

With `replicas: 3`, `maxSurge: 1`, `maxUnavailable: 0`:

```
Desired: 3 pods
Max allowed during update: 3 + 1 = 4  (maxSurge)
Min allowed during update: 3 - 0 = 3  (maxUnavailable)

→ Always at least 3 pods running, sometimes 4
→ Zero downtime guaranteed
```

With `maxUnavailable: 1` (faster but brief dip):

```
Min allowed: 3 - 1 = 2 pods
→ Slightly faster update, brief period of 2/3 pods serving traffic
```

### The Other Strategy: Recreate

```yaml
  strategy:
    type: Recreate    # kill ALL old pods, then start new ones
```

Use `Recreate` only when your app **cannot run two versions at the same time** (e.g. a database migration that is not backwards compatible). It causes downtime — all pods are offline between the delete and the start of new ones.

---

## Essential Deployment Commands

```bash
# Deploy
kubectl apply -f examples/01-basic-deployment.yaml

# Check the deployment
kubectl get deployments
kubectl get deploy          # shorthand

# See the pods it created
kubectl get pods

# See the ReplicaSet it created
kubectl get replicasets
kubectl get rs              # shorthand

# Full details
kubectl describe deployment web-app

# Scale up to 5 replicas (imperative — prefer editing the YAML in practice)
kubectl scale deployment web-app --replicas=5

# Update the image (imperative — triggers a rolling update)
kubectl set image deployment/web-app nginx=nginx:1.26

# Watch the rollout progress
kubectl rollout status deployment/web-app

# See the history of changes (revisions)
kubectl rollout history deployment/web-app

# Roll back to the previous version
kubectl rollout undo deployment/web-app

# Roll back to a specific revision
kubectl rollout undo deployment/web-app --to-revision=2

# Pause a rollout mid-way (useful for canary checks)
kubectl rollout pause deployment/web-app

# Resume a paused rollout
kubectl rollout resume deployment/web-app
```

---

## Revision History and Rollback in Detail

Every time you change a Deployment's pod template (image, env vars, resources), Kubernetes saves a **revision**:

```bash
kubectl rollout history deployment/web-app
# REVISION  CHANGE-CAUSE
# 1         <none>
# 2         <none>
# 3         <none>
```

The `CHANGE-CAUSE` is blank unless you annotate it. Good habit:

```bash
kubectl annotate deployment/web-app \
  kubernetes.io/change-cause="Updated nginx to 1.26 — security patch"
```

Or put it in the YAML:

```yaml
metadata:
  annotations:
    kubernetes.io/change-cause: "Updated nginx to 1.26 — security patch"
```

To roll back:

```bash
kubectl rollout undo deployment/web-app
# Deployment immediately starts replacing new pods with the previous version
```

This works because Kubernetes kept the old ReplicaSet around with 0 replicas after the update — it just scales it back up.

---

## Common Mistakes & Gotchas

### 1. `selector` and `template.labels` must match exactly
If they don't, Kubernetes rejects the Deployment with a validation error. The Deployment uses the selector to find its pods — a mismatch means it can't manage them.

### 2. Never use `latest` as the image tag
```yaml
image: nginx:latest   # BAD — which version is this? Rollback means nothing.
image: nginx:1.25     # GOOD — explicit, reproducible, rollback has meaning
```
With `latest`, every node might pull a different actual version depending on when it last pulled the image. Deployments become non-deterministic.

### 3. Deleting a pod owned by a Deployment does nothing permanent
```bash
kubectl delete pod web-app-7d9f6b-xk2p4
```
The ReplicaSet sees: actual=2, desired=3 → immediately creates a replacement. This is a feature, not a bug — but it surprises beginners who think they're scaling down.

### 4. `kubectl rollout history` only stores 10 revisions by default
Controlled by `spec.revisionHistoryLimit`. Set it explicitly if you need more rollback headroom:

```yaml
spec:
  revisionHistoryLimit: 20
```

### 5. A Deployment update is triggered by the pod template, not the Deployment metadata
Changing `metadata.labels` on the Deployment itself does NOT trigger a rollout. Only changes inside `spec.template` do (image, env, resources, etc.).

---

## Common Questions & Doubts

### "What is the difference between a Deployment and a ReplicaSet? Do I need to create both?"

You only ever create a **Deployment**. The Deployment automatically creates and manages the ReplicaSet for you. You rarely interact with ReplicaSets directly. Think of the Deployment as the manager, the ReplicaSet as the worker it delegates to. The ReplicaSet's only job is counting pods; the Deployment's job is orchestrating updates and rollbacks across ReplicaSets.

---

### "If a Deployment recreates dead pods automatically, why do I need multiple replicas?"

Auto-recreation takes time — typically 10–30 seconds between a pod dying and a replacement being ready. With a single replica, your app is down during that window. With 3 replicas, the other two keep serving traffic while the third is being replaced. Replicas are about **availability**, auto-recreation is about **recovery**.

---

### "Can I edit a Deployment's YAML and apply it again, or do I need to delete and recreate?"

Just `kubectl apply -f` again. Kubernetes computes the diff and applies only what changed. If the pod template changed, a rolling update starts automatically. If only metadata changed, no rollout happens.

---

### "How many old ReplicaSets does Kubernetes keep after updates?"

By default, 10 (`spec.revisionHistoryLimit: 10`). This is what enables rollbacks — each old ReplicaSet is a saved revision. You can lower this to save etcd space or raise it for more rollback history.

---

### "What's the difference between `kubectl apply` and `kubectl replace`?"

- `kubectl apply` is **declarative** — merges changes, creates if not exists, triggers rolling updates properly. Always prefer this.
- `kubectl replace` is **imperative** — deletes and recreates the resource. It does not trigger a proper rolling update and loses any server-side changes made since the last apply.

---

## Interview Questions

**Q1. What is a Deployment and why would you use it instead of a bare pod?**

<details>
<summary>Show answer</summary>

A Deployment is a Kubernetes controller that maintains a desired number of identical pod replicas. Unlike bare pods, Deployments automatically recreate pods when they crash or when their node dies. They also provide rolling updates (zero-downtime upgrades) and rollbacks. In production, you should always use a Deployment (or similar controller) instead of bare pods.

</details>

---

**Q2. What is a ReplicaSet? How does it relate to a Deployment?**

<details>
<summary>Show answer</summary>

A ReplicaSet is a controller whose sole responsibility is ensuring a specific number of pod replicas are running at any time. A Deployment manages one or more ReplicaSets — when you do a rolling update, the Deployment creates a new ReplicaSet with the new pod template and scales it up while scaling the old one down. You almost never create a ReplicaSet directly; you let the Deployment manage it.

</details>

---

**Q3. Explain how a rolling update works in Kubernetes.**

<details>
<summary>Show answer</summary>

When you update a Deployment's pod template (e.g. change the container image), the Deployment creates a new ReplicaSet with the new template. It then incrementally scales up the new ReplicaSet and scales down the old one, controlled by `maxSurge` (how many extra pods above desired are allowed) and `maxUnavailable` (how many pods below desired are allowed). The process continues until all pods are running the new version. The old ReplicaSet is kept at 0 replicas to allow rollback.

</details>

---

**Q4. What are `maxSurge` and `maxUnavailable`? Give an example.**

<details>
<summary>Show answer</summary>

`maxSurge` controls how many pods above the desired count can exist during an update. `maxUnavailable` controls how many pods below the desired count are tolerated.

Example: `replicas: 4`, `maxSurge: 1`, `maxUnavailable: 1`
- Maximum pods during update: 4 + 1 = 5
- Minimum pods during update: 4 - 1 = 3
- 2 pods are replaced per step (1 old terminated + 1 new created), balancing speed and availability.

Setting `maxUnavailable: 0` guarantees zero downtime (new pods must be ready before old ones are removed).

</details>

---

**Q5. How do you roll back a Deployment and how does it work internally?**

<details>
<summary>Show answer</summary>

```bash
kubectl rollout undo deployment/<name>
# Or to a specific revision:
kubectl rollout undo deployment/<name> --to-revision=2
```

Internally, Kubernetes kept the old ReplicaSet around with 0 replicas after the update. Rolling back simply scales that old ReplicaSet back up and scales the current one down — the same rolling update process, just in reverse. No new pods are built from scratch; the old ones are just reactivated.

</details>

---

**Q6. What happens if you delete a pod that belongs to a Deployment?**

<details>
<summary>Show answer</summary>

The ReplicaSet immediately detects that the actual pod count dropped below the desired count and creates a replacement pod. The deleted pod is not gone for good — it's just replaced within seconds. This is by design: a Deployment's contract is to maintain the desired replica count at all times. To actually reduce the count, you must scale the Deployment itself.

</details>

---

**Q7. What is the difference between `RollingUpdate` and `Recreate` deployment strategies?**

<details>
<summary>Show answer</summary>

- **RollingUpdate** (default): replaces pods incrementally. Some old and some new pods run simultaneously during the update. Zero downtime if configured correctly.
- **Recreate**: terminates all existing pods first, then starts new ones. Causes downtime between the deletion and the new pods becoming ready. Use only when two versions of your app cannot coexist (e.g. incompatible database schema changes).

</details>

---

**Q8. What triggers a new rollout in a Deployment?**

<details>
<summary>Show answer</summary>

Only changes to `spec.template` trigger a rollout — specifically the pod spec (container image, environment variables, resource limits, volume mounts, etc.). Changes to the Deployment's own `metadata` (labels, annotations) or `spec.replicas` do NOT trigger a rollout. Scaling just adjusts the ReplicaSet's count without replacing pods.

</details>

---

## Summary

| Concept | In one sentence |
|---------|----------------|
| Deployment | A controller that maintains a desired pod count and manages updates/rollbacks |
| ReplicaSet | Created by the Deployment; ensures exactly N pods are running at all times |
| Rolling update | Gradual pod replacement — new version introduced incrementally, zero downtime |
| Recreate | Kill all pods first, then start new ones — has downtime, use only when necessary |
| maxSurge | Extra pods allowed above desired count during a rolling update |
| maxUnavailable | Pods allowed below desired count during a rolling update |
| Rollback | Reverting to a previous Deployment revision by scaling the old ReplicaSet back up |
| Revision | A saved snapshot of the pod template, kept for rollback |
| revisionHistoryLimit | How many old ReplicaSets (revisions) to keep (default: 10) |

---

## Exercises

See [exercises/README.md](./exercises/README.md) for hands-on practice.

---

## Navigation

**[← 02: Pods](../02-pods/README.md)** | **[04: Services →](../04-services/README.md)**
