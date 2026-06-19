# 06 — Namespaces

> **Goal:** Understand how namespaces divide one cluster into isolated virtual zones, what resources live inside them vs span the whole cluster, how to control resource consumption with ResourceQuota and LimitRange, and the important truth about what namespaces do and do not isolate.

---

## The Problem: One Cluster, Many Teams, Zero Order

Imagine your company runs a single Kubernetes cluster shared by three teams:

- **Team Frontend** deploys a service called `api`
- **Team Backend** also deploys a service called `api`

They collide — one overwrites the other. Chaos.

Now imagine all three environments share the same cluster:

- A developer accidentally runs `kubectl delete deployment api` thinking they're in `dev`  
  They were in `prod`. The production API is gone.

And one team's poorly-written batch job consumes 80% of cluster CPU, starving every other team's pods.

**Namespaces solve all three problems:**
1. **Name isolation** — two teams can both have a resource named `api` as long as they're in different namespaces
2. **Access control** — RBAC (topic 11) can restrict who can touch which namespace
3. **Resource quotas** — cap how much CPU, memory, or number of pods a namespace can consume

---

## The Analogy: Floors in an Office Building

Picture a large office building with multiple companies:

```
Office Building (Kubernetes Cluster)
│
├── Floor 1: Team Frontend  (namespace: frontend)
│   ├── Meeting Room "api"   (Service named "api")
│   ├── Meeting Room "cache" (Service named "cache")
│   └── Quota: max 20 rooms, max 50 employees
│
├── Floor 2: Team Backend   (namespace: backend)
│   ├── Meeting Room "api"   (Service named "api") ← same name, different floor = no conflict
│   ├── Meeting Room "db"    (Service named "db")
│   └── Quota: max 30 rooms, max 100 employees
│
└── Floor 3: kube-system    (Kubernetes internals)
    ├── The building's boiler room, power panel, elevators
    └── Do not touch
```

Each floor has its own key card access (RBAC). You can call someone on a different floor using the building directory (cross-namespace DNS). But you can't accidentally book a meeting room on the wrong floor — the room name only matters within your floor.

---

## The Four Default Namespaces

When you start a fresh cluster, four namespaces already exist:

```bash
kubectl get namespaces
# NAME              STATUS   AGE
# default           Active   5d
# kube-node-lease   Active   5d
# kube-public       Active   5d
# kube-system       Active   5d
```

| Namespace | Purpose | Touch it? |
|-----------|---------|-----------|
| `default` | Where your resources go when you don't specify a namespace | Yes — your workloads live here by default |
| `kube-system` | Kubernetes own components: API server, scheduler, CoreDNS, kube-proxy | No — don't deploy here or delete anything |
| `kube-public` | Readable by everyone, even unauthenticated users. Holds a ConfigMap with basic cluster info | Rarely — almost never touched |
| `kube-node-lease` | Node heartbeat Lease objects — lets the control plane detect dead nodes faster | Never — purely internal |

> **Rule of thumb:** Never deploy your own applications into `kube-system`. Create your own namespaces.

---

## Core Vocabulary

| Term | Meaning |
|------|---------|
| **Namespace** | A logical partition inside a cluster — isolates names, quotas, and access control |
| **Namespace-scoped resource** | A resource that lives inside a namespace (pods, services, deployments) |
| **Cluster-scoped resource** | A resource that spans the whole cluster with no namespace (nodes, PersistentVolumes) |
| **ResourceQuota** | An object that limits the total resources a namespace can consume |
| **LimitRange** | An object that sets default and max resource requests/limits for individual pods |
| **Context** | A named combination of cluster + user + namespace stored in kubeconfig |

---

## Namespace-Scoped vs Cluster-Scoped Resources

Not everything lives in a namespace. Resources fall into two categories:

**Namespace-scoped** (belong to exactly one namespace):
```
Pods            Deployments     ReplicaSets
Services        ConfigMaps      Secrets
PersistentVolumeClaims          ServiceAccounts
Ingresses       CronJobs        Jobs
```

**Cluster-scoped** (span the whole cluster, no namespace):
```
Nodes                   PersistentVolumes
Namespaces              StorageClasses
ClusterRoles            ClusterRoleBindings
IngressClasses          CustomResourceDefinitions
```

A quick way to check if a resource is namespace-scoped:

```bash
kubectl api-resources --namespaced=true   # namespace-scoped
kubectl api-resources --namespaced=false  # cluster-scoped
```

This distinction matters for RBAC (topic 11): you can give a user permission to manage pods only in the `dev` namespace, but you can't restrict access to Nodes to a namespace — they're always cluster-wide.

---

## How Namespaces Work: Name Isolation

The key rule: **resource names must be unique within a namespace, but can repeat across namespaces.**

```
Cluster
├── namespace: frontend
│   ├── deployment/api    ✓
│   └── service/api       ✓
│
└── namespace: backend
    ├── deployment/api    ✓  (same name — different namespace — no conflict)
    └── service/api       ✓
```

Kubernetes fully qualifies every namespaced resource internally as `<name>.<namespace>`. `api.frontend` and `api.backend` are completely separate objects.

---

## Creating and Using Namespaces

```bash
# Create a namespace
kubectl create namespace dev
kubectl create namespace staging
kubectl create namespace production

# Or from a YAML file (recommended — version-controllable)
kubectl apply -f examples/01-namespaces.yaml

# List namespaces
kubectl get namespaces
kubectl get ns    # shorthand
```

**Working with a specific namespace:**

```bash
# The -n flag specifies the namespace for any command
kubectl get pods -n dev
kubectl get deployments -n production
kubectl describe service api -n staging
kubectl delete pod my-pod -n dev

# See everything across ALL namespaces at once
kubectl get pods --all-namespaces
kubectl get pods -A              # shorthand
```

**Set a default namespace so you don't type `-n` every time:**

```bash
# Set the default namespace in your current kubectl context
kubectl config set-context --current --namespace=dev

# Verify
kubectl config view --minify | grep namespace

# Now all commands without -n go to 'dev'
kubectl get pods          # shows pods in 'dev'
kubectl get pods -n prod  # explicitly override to 'prod'
```

---

## Deploying to a Namespace

Option 1: Set `namespace` in the resource YAML:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: frontend    # hard-coded into the manifest
spec:
  ...
```

Option 2: Apply without namespace in YAML and use `-n` flag:

```bash
kubectl apply -f deployment.yaml -n frontend
```

Option 1 is better for GitOps — the intent is explicit in the file.

---

## ResourceQuota — Capping What a Namespace Can Consume

A `ResourceQuota` sets hard limits on the total resources a namespace is allowed to use. If a namespace hits its quota, new pods/services are rejected until something is deleted.

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: dev-quota
  namespace: dev
spec:
  hard:
    # Compute resources (across ALL pods in the namespace)
    requests.cpu: "4"          # total CPU requested: 4 cores
    requests.memory: 8Gi       # total memory requested: 8 GB
    limits.cpu: "8"            # total CPU limit: 8 cores
    limits.memory: 16Gi        # total memory limit: 16 GB

    # Object count limits
    pods: "20"                 # max 20 pods
    services: "10"             # max 10 services
    secrets: "30"              # max 30 secrets
    configmaps: "30"
    persistentvolumeclaims: "5"
```

When a quota is in place on CPU/memory, **every pod in that namespace must specify resource requests and limits** — otherwise the API server rejects it. This forces teams to declare their consumption explicitly.

```bash
kubectl describe resourcequota dev-quota -n dev
# Name:                   dev-quota
# Namespace:              dev
# Resource                Used    Hard
# --------                ----    ----
# limits.cpu              2       8
# limits.memory           4Gi     16Gi
# pods                    5       20
# requests.cpu            1       4
# requests.memory         2Gi     8Gi
```

See [`examples/02-resource-quota.yaml`](./examples/02-resource-quota.yaml).

---

## LimitRange — Defaults and Bounds for Individual Pods

ResourceQuota controls the namespace total. `LimitRange` controls **individual pods and containers** within the namespace.

Without a LimitRange, a developer can forget to set resource limits and deploy a container with unlimited CPU/memory, starving everything else.

With a LimitRange, you can:
- Set **default** requests and limits (applied automatically if the pod doesn't specify them)
- Set **minimum** values (pods can't request less than this)
- Set **maximum** values (pods can't request more than this)

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: dev-limits
  namespace: dev
spec:
  limits:
    - type: Container
      default:               # applied automatically if pod doesn't specify limits
        cpu: "500m"          # 0.5 CPU cores
        memory: "256Mi"
      defaultRequest:        # applied automatically if pod doesn't specify requests
        cpu: "100m"
        memory: "64Mi"
      max:                   # container cannot request MORE than this
        cpu: "2"
        memory: "1Gi"
      min:                   # container cannot request LESS than this
        cpu: "50m"
        memory: "32Mi"
```

See [`examples/03-limit-range.yaml`](./examples/03-limit-range.yaml).

### ResourceQuota vs LimitRange — What's the Difference?

```
ResourceQuota:  "This entire namespace can use at most 8 CPU cores total"
                → enforced at namespace level

LimitRange:     "Each individual container can use at most 2 CPU cores"
                → enforced at pod/container level
```

They work together. LimitRange ensures no single pod is a runaway consumer. ResourceQuota ensures the whole team doesn't exceed the cluster's fair share.

---

## Cross-Namespace Communication

Namespaces isolate names, not network traffic (unless you use Network Policies — topic 17).

A pod in `frontend` can talk to a service in `backend` using the full DNS name:

```
Short name (same namespace only):   backend-api
Namespace-qualified name:           backend-api.backend
Full FQDN:                          backend-api.backend.svc.cluster.local
```

```
┌────────────────────────────────────────────────────────┐
│  namespace: frontend                                    │
│                                                         │
│  ┌─────────────────┐                                   │
│  │  frontend-pod   │──── curl http://api.backend/ ────►│
│  └─────────────────┘                                   │
│                                                         │
└────────────────────────────────────────────────────────┘
                  │
                  ▼  (CoreDNS resolves api.backend → ClusterIP of api in backend namespace)
┌────────────────────────────────────────────────────────┐
│  namespace: backend                                     │
│                                                         │
│  ┌───────────────┐     ┌────────────┐                  │
│  │  Service: api  │────►│  backend   │                  │
│  └───────────────┘     │  pods      │                  │
│                         └────────────┘                  │
└────────────────────────────────────────────────────────┘
```

---

## The Truth About Namespace Isolation

This is a critical point that surprises many people:

**Namespaces do NOT provide network isolation by default.**

A pod in `dev` can send network packets to a pod in `prod` freely. There are no firewall rules between namespaces unless you explicitly create **NetworkPolicies** (topic 17).

Similarly, namespaces do not isolate:
- Node-level access (a container can still try to access the node filesystem)
- Kernel calls (no seccomp/AppArmor by default)

| What namespaces DO provide | What namespaces do NOT provide |
|---------------------------|-------------------------------|
| Name isolation (no name collisions) | Network isolation (pods can still talk cross-namespace) |
| Quota boundaries | Hard security boundary (not a VM-level isolation) |
| RBAC scope (access control) | Kernel-level isolation |
| Separate DNS short-name resolution | Node isolation |

For real security isolation between tenants, use:
- NetworkPolicies (topic 17) for network
- Pod Security Admission for pod-level restrictions
- Separate clusters for true hard isolation (e.g. prod always gets its own cluster)

---

## Naming Conventions Used in Practice

Teams typically adopt one of these namespace patterns:

**By environment:**
```
dev       staging       production
```
Simple. Risk: `prod` is on the same cluster as `dev` — a bad RBAC config is dangerous.

**By team:**
```
team-frontend     team-backend     team-data
```
Good for platform teams giving each app team their own space.

**By environment + team:**
```
frontend-dev     frontend-prod
backend-dev      backend-prod
```
Most isolation with the most namespaces to manage.

**By application:**
```
payments-app     inventory-app     notification-service
```
Common in microservice architectures where each service owns its own namespace.

---

## Essential Commands

```bash
# Create / delete
kubectl create namespace my-ns
kubectl delete namespace my-ns   # WARNING: deletes EVERYTHING inside it

# List and inspect
kubectl get namespaces
kubectl describe namespace dev

# Apply resources into a specific namespace
kubectl apply -f deployment.yaml -n dev

# Switch default namespace in your context
kubectl config set-context --current --namespace=dev

# View quota and limit range status
kubectl describe resourcequota -n dev
kubectl describe limitrange -n dev

# Get all resources in a namespace at once
kubectl get all -n dev

# Get all resources across all namespaces
kubectl get all -A
```

---

## Common Mistakes & Gotchas

### 1. Deleting a namespace deletes EVERYTHING inside it — instantly

```bash
kubectl delete namespace production   # ← no confirmation prompt, no undo
```

This cascade-deletes every pod, deployment, service, secret, and configmap in that namespace. There is no recycle bin. Always double-check which namespace you're in.

### 2. Forgetting `-n` and operating on the wrong namespace

The default namespace is `default`. If you forget `-n dev`, you might be looking at the wrong resources or worse, deleting from the wrong place.

```bash
# Dangerous pattern — which namespace are these pods in?
kubectl delete pods --all

# Safer — always be explicit
kubectl delete pods --all -n dev
```

Use `kubectl config set-context --current --namespace=<ns>` to make your working namespace explicit in your session.

### 3. Cross-namespace DNS requires the full name

This is the most common cross-namespace networking bug:

```bash
# From namespace 'frontend', calling a service in namespace 'backend'
curl http://api/data           # FAILS — 'api' resolves in 'frontend', not found
curl http://api.backend/data   # WORKS — namespace-qualified name
```

### 4. ResourceQuota requires all pods to have resource requests/limits

Once a ResourceQuota with CPU/memory limits is active in a namespace, every pod must declare `resources.requests` and `resources.limits`. Any pod without them is rejected:

```
Error from server (Forbidden): pods "my-pod" is forbidden:
[maximum cpu usage per Pod is 2, but no limit is set.
 maximum memory usage per Pod is 1Gi, but no limit is set.]
```

Use a LimitRange with `default` values to auto-inject limits for pods that don't specify them — this prevents the rejection without requiring every developer to remember.

### 5. Cluster-scoped resources ignore the `-n` flag

```bash
kubectl get nodes -n dev         # same result as kubectl get nodes — -n is ignored
kubectl get persistentvolumes -n dev  # same — PVs are cluster-scoped
```

---

## Common Questions & Doubts

### "Can I move a resource from one namespace to another?"

No. Namespace is baked into a resource's identity. You cannot `kubectl move` something. The only way is to delete it from the source namespace and recreate it in the destination namespace. For stateless resources (Deployments, Services, ConfigMaps) this is straightforward. For stateful resources (PVCs, Secrets) it requires more care — you need to copy the data too.

---

### "Should I run dev, staging, and prod in the same cluster?"

It depends on your risk tolerance. Sharing a cluster saves cost and operations overhead, but a single misconfigured RBAC rule could let a dev accidentally affect prod. Many teams use namespaces for dev/staging but a **completely separate cluster** for production. The rule of thumb: if a `kubectl delete` mistake in one environment can't be allowed to affect another, they should be separate clusters.

---

### "Do I need namespaces for a personal project or small team?"

For a personal project or a 2-person team: not really. The `default` namespace is fine. Namespaces pay off when you have multiple teams, multiple environments, or need to enforce resource quotas. Don't add complexity you don't need yet.

---

### "What happens to running pods when a LimitRange is applied to an existing namespace?"

LimitRange only affects **new** pods created after the LimitRange exists. Already-running pods are not evicted or changed. The new defaults and limits apply on the next pod creation (e.g. after a rolling update, when a pod crashes and restarts, or on scale-up).

---

### "Can a ResourceQuota prevent the cluster from scheduling system pods?"

No, if applied to a user namespace. ResourceQuota applies only within the namespace it's created in. `kube-system` pods are in `kube-system` and are never affected by a quota you set in `dev` or `production`. You can also set `kube-system` quotas but this is very rarely done and requires extreme care.

---

## Interview Questions

**Q1. What is a Kubernetes namespace and what problems does it solve?**

<details>
<summary>Show answer</summary>

A namespace is a logical partition inside a Kubernetes cluster. It solves three problems:
1. **Name isolation** — multiple teams can use the same resource names (like `api`) without collision, as long as they're in different namespaces
2. **Access control scope** — RBAC rules can be scoped to a namespace, so a team only has permission to touch their own namespace
3. **Resource quotas** — ResourceQuota objects limit total CPU, memory, or object count per namespace, preventing one team from starving others

</details>

---

**Q2. What are the four default Kubernetes namespaces and what is each used for?**

<details>
<summary>Show answer</summary>

- `default` — where user resources go when no namespace is specified; your workloads typically live here or in custom namespaces
- `kube-system` — Kubernetes' own components: API server, scheduler, controller manager, CoreDNS, kube-proxy; never deploy your own apps here
- `kube-public` — publicly readable without authentication; mainly holds a `cluster-info` ConfigMap; rarely used
- `kube-node-lease` — stores Lease objects for each node so the control plane can detect node failures faster through lighter-weight heartbeats; purely internal, never touched directly

</details>

---

**Q3. What is the difference between namespace-scoped and cluster-scoped resources? Give examples.**

<details>
<summary>Show answer</summary>

Namespace-scoped resources belong to exactly one namespace: Pods, Deployments, ReplicaSets, Services, ConfigMaps, Secrets, PVCs, Ingresses. They cannot be accessed across namespaces without the namespace qualifier.

Cluster-scoped resources have no namespace — they exist at the cluster level: Nodes, PersistentVolumes, StorageClasses, Namespaces themselves, ClusterRoles, ClusterRoleBindings, CustomResourceDefinitions.

The distinction matters for RBAC: you can restrict a user to read pods only in the `dev` namespace, but you cannot restrict which Nodes they can see — Nodes are cluster-scoped.

</details>

---

**Q4. What is a ResourceQuota and how does it work?**

<details>
<summary>Show answer</summary>

A ResourceQuota is an object created inside a namespace that sets hard limits on the total resources that namespace can consume. It can limit compute resources (total CPU and memory requests/limits across all pods) and object counts (max number of pods, services, secrets, etc.). When the namespace hits a quota limit, new objects that would exceed it are rejected by the API server. If CPU/memory quotas exist, every pod must declare resource requests and limits — otherwise the pod is rejected.

</details>

---

**Q5. What is a LimitRange and how is it different from ResourceQuota?**

<details>
<summary>Show answer</summary>

ResourceQuota caps the total consumption of the whole namespace. LimitRange sets defaults and boundaries for individual pods and containers.

LimitRange lets you set:
- `default` / `defaultRequest` — automatically injected into pods that don't specify resources
- `max` — a container cannot request more than this
- `min` — a container cannot request less than this

The two work together: LimitRange ensures no single container is a runaway consumer, ResourceQuota ensures the entire namespace doesn't exceed its fair share. The `default` in LimitRange also solves the "pods rejected because they have no limits" problem that ResourceQuota causes.

</details>

---

**Q6. Do namespaces provide network isolation?**

<details>
<summary>Show answer</summary>

No, not by default. A pod in namespace `dev` can freely send traffic to a pod in namespace `prod` — there are no firewall rules between namespaces unless you explicitly create NetworkPolicies (topic 17). Namespaces provide name isolation and access control scope, but the network is flat across the cluster by default. For real network isolation between namespaces, apply NetworkPolicies that restrict ingress/egress by namespace selector.

</details>

---

**Q7. How do pods in different namespaces communicate via DNS?**

<details>
<summary>Show answer</summary>

Each Service gets a DNS record in the format `<service>.<namespace>.svc.cluster.local`. From within the same namespace, the short name `<service>` works. From a different namespace, you need at minimum `<service>.<namespace>` (CoreDNS fills in `svc.cluster.local`). The full FQDN always works from anywhere in the cluster. Example: a pod in `frontend` calling a service named `api` in `backend` uses `api.backend` or `api.backend.svc.cluster.local`.

</details>

---

**Q8. What happens when you delete a namespace?**

<details>
<summary>Show answer</summary>

Deleting a namespace cascade-deletes every resource inside it — pods, deployments, services, configmaps, secrets, PVCs, etc. — immediately and with no undo. The namespace itself enters `Terminating` status while all contained resources are being deleted, then disappears. There is no confirmation prompt or recycle bin. This is why prod workloads are sometimes in their own cluster — a mistaken `kubectl delete namespace production` would be catastrophic if it were allowed.

</details>

---

**Q9. How would you set a default namespace for kubectl so you don't need `-n` on every command?**

<details>
<summary>Show answer</summary>

```bash
kubectl config set-context --current --namespace=dev
```

This updates the current context in `~/.kube/config` to default to the `dev` namespace. All subsequent `kubectl` commands without `-n` will target `dev`. To override for a single command, use `-n <other-namespace>`. To see your current namespace:

```bash
kubectl config view --minify | grep namespace
```

Many teams use tools like `kubens` (part of `kubectx`) for fast namespace switching.

</details>

---

## Summary

| Concept | In one sentence |
|---------|----------------|
| Namespace | A logical partition inside a cluster for name isolation, access control, and quotas |
| `default` | The namespace for resources when you don't specify one |
| `kube-system` | Reserved for Kubernetes' own internal components — do not touch |
| Namespace-scoped resource | Lives inside a namespace (pods, services, deployments) |
| Cluster-scoped resource | Spans the whole cluster with no namespace (nodes, PVs, namespaces themselves) |
| ResourceQuota | Caps total CPU, memory, and object count for an entire namespace |
| LimitRange | Sets default, min, and max resource requests/limits per individual container |
| Cross-namespace DNS | Use `service.namespace` or the full FQDN to reach services in other namespaces |
| Network isolation | Namespaces do NOT isolate network by default — use NetworkPolicies for that |

---

## Exercises

See [exercises/README.md](./exercises/README.md) for hands-on practice.

---

## Navigation

**[← 05: ConfigMaps & Secrets](../05-configmaps-secrets/README.md)** | **[07: Persistent Volumes →](../07-persistent-volumes/README.md)**
