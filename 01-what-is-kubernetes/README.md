# 01 — What is Kubernetes?

> **Goal:** Understand the *problem* Kubernetes solves before touching a single YAML file.

---

## Table of Contents

- [The Problem: Running Apps in Production is Hard](#the-problem-running-apps-in-production-is-hard)
- [The Analogy: Kubernetes is Like an Airline Operations Center](#the-analogy-kubernetes-is-like-an-airline-operations-center)
- [Core Vocabulary (Just 5 Terms for Now)](#core-vocabulary-just-5-terms-for-now)
- [How Kubernetes Works (Bird's Eye View)](#how-kubernetes-works-birds-eye-view)
- [Kubernetes Architecture](#kubernetes-architecture)
- [What Kubernetes is NOT](#what-kubernetes-is-not)
- [Quick Hands-On: Look at a Real Cluster](#quick-hands-on-look-at-a-real-cluster)
- [Common Questions & Doubts](#common-questions--doubts)
- [Interview Questions](#interview-questions)
- [Summary](#summary)
- [Exercises](#exercises)
- [Next Topic](#next-topic)

---

## The Problem: Running Apps in Production is Hard

Imagine you built a web app and you want to run it. Simple, right?

```
Your laptop → run the app → done
```

Now your app becomes popular. You need to:

1. Run **multiple copies** so it doesn't crash under traffic
2. **Restart** it automatically when it crashes at 3am
3. **Update** it to a new version without any downtime
4. Run it across **multiple machines** so one server failure doesn't kill everything
5. **Route traffic** between the copies
6. Give each copy exactly the CPU and memory it needs — not more

Doing all of this by hand, for dozens of apps, is a nightmare.

**Kubernetes solves exactly this.**

---

## The Analogy: Kubernetes is Like an Airline Operations Center

Think of a large airport:

| Airport Concept | Kubernetes Equivalent |
|-----------------|----------------------|
| The airport itself | The **cluster** (a group of machines) |
| Planes on the tarmac | **Nodes** (the actual machines/servers) |
| Passengers | **Containers** (your running app code) |
| Flight management system | **Control Plane** (the brain of K8s) |
| Gate agent assigning planes | **Scheduler** (decides which node runs what) |
| Ground crew fixing problems | **Controller Manager** (keeps the desired state) |

The operations center doesn't care *which* specific plane carries which passenger. It just ensures the right number of flights run, broken planes are replaced, and schedules are met.

Kubernetes does the same — it doesn't care *which* server runs your app. It just ensures the right number of copies are running, crashed ones are restarted, and updates are rolled out safely.

---

## Core Vocabulary (Just 5 Terms for Now)

### 1. Cluster
A **cluster** is the entire Kubernetes environment — a set of machines (physical or virtual) that work together. You talk to the cluster as a whole, not to individual machines.

```
Your kubectl command → Kubernetes Cluster → (internally routes to the right machine)
```

### 2. Node
A **node** is one machine inside the cluster. It can be a VM in the cloud or a bare-metal server. Kubernetes runs your apps on nodes. Nodes come in two types:

- **Control Plane Node** — the brain. Manages the cluster, stores state, schedules work.
- **Worker Node** — the muscle. Actually runs your application containers.

```
                    ┌─────────────────────────────────┐
                    │          Kubernetes Cluster       │
                    │                                   │
                    │  ┌──────────────┐                │
                    │  │ Control Plane│  ← the brain   │
                    │  │    Node      │                 │
                    │  └──────────────┘                │
                    │                                   │
                    │  ┌────────┐  ┌────────┐          │
                    │  │ Worker │  │ Worker │  ← muscle │
                    │  │  Node  │  │  Node  │          │
                    │  └────────┘  └────────┘          │
                    └─────────────────────────────────┘
```

### 3. Container
A **container** is a packaged, runnable version of your app. Think of it as a lightweight, isolated box that contains your app + everything it needs to run (libraries, config, etc.). Docker is the most common way to build containers.

If you've never used Docker: imagine a shipping container. You pack everything your app needs inside it, seal it, and it runs the same way anywhere.

### 4. Pod
A **Pod** is the smallest unit Kubernetes knows about. A pod wraps one or more containers that belong together. Kubernetes doesn't run containers directly — it runs Pods.

> Usually: 1 pod = 1 container = 1 app instance

```
Pod
└── Container (your app)
```

We'll go deep on Pods in topic 02.

### 5. kubectl
`kubectl` (pronounced "kube-control" or "kube-cuttle") is the command-line tool you use to talk to Kubernetes. Think of it as the remote control for your cluster.

```bash
kubectl get nodes       # list all machines in the cluster
kubectl get pods        # list all running app instances
kubectl apply -f x.yaml # deploy something
```

---

## How Kubernetes Works (Bird's Eye View)

You tell Kubernetes **what you want** (not *how* to do it):

> "I want 3 copies of my web app running at all times."

Kubernetes figures out *how* to make that happen and keeps it that way forever.

This is called **declarative configuration** — you declare the desired state, Kubernetes reconciles reality to match it.

```
You write a YAML file describing your desired state
        │
        ▼
kubectl apply -f your-file.yaml
        │
        ▼
Kubernetes stores your desire in etcd (its database)
        │
        ▼
Scheduler picks which nodes to run pods on
        │
        ▼
Your containers start running on worker nodes
        │
        ▼
Controller constantly watches: "Is reality == desired state?"
If a pod crashes → controller creates a new one automatically
```

---

## Kubernetes Architecture

Kubernetes follows a master-worker (control plane/worker node) architecture. Here’s how the main components fit together:

### 1. Control Plane (The Brain)
Responsible for managing the cluster, making global decisions, and detecting/responding to cluster events.

- **kube-apiserver**: The front door for all commands (kubectl, UI, etc.). All communication goes through here.
- **etcd**: The cluster’s database. Stores all configuration and state.
- **kube-scheduler**: Assigns new pods to nodes based on resource availability and policies.
- **kube-controller-manager**: Runs controllers that ensure the cluster matches the desired state (e.g., restarts crashed pods).

### 2. Worker Nodes (The Muscle)
Run your application containers.

- **kubelet**: Agent on each node. Talks to the control plane, starts/stops containers as instructed.
- **kube-proxy**: Handles networking, routes traffic to the right pod.
- **Container Runtime**: (e.g., containerd) Actually runs your containers.

### Diagram

```
                        +----------------------+
                        |   Control Plane      |
                        |----------------------|
                        |  kube-apiserver      |
                        |  etcd                |
                        |  scheduler           |
                        |  controller-manager  |
                        +----------+-----------+
                                   |
                +------------------+------------------+
                |                                     |
        +-------v-------+                     +-------v-------+
        |   Worker Node |                     |   Worker Node |
        |---------------|                     |---------------|
        |  kubelet      |                     |  kubelet      |
        |  kube-proxy   |                     |  kube-proxy   |
        |  containerd   |                     |  containerd   |
        +-------+-------+                     +-------+-------+
                |                                     |
        +-------v-------+                     +-------v-------+
        |   Pod(s)      |                     |   Pod(s)      |
        +---------------+                     +---------------+
```

**How it works:**  
- You interact with the control plane (via `kubectl` or UI).
- The control plane stores your desired state in etcd, schedules pods, and manages the cluster.
- Worker nodes run the actual application containers (inside pods), reporting status back to the control plane.

---

## What Kubernetes is NOT

Common misconceptions:

- **Not a Docker replacement** — Docker builds images, K8s runs them. They work together.
- **Not just for big companies** — You can run a single-node K8s cluster on your laptop.
- **Not magic** — K8s manages infrastructure. It doesn't make bad code good.
- **Not a CI/CD system** — K8s doesn't build or test your code. Tools like GitHub Actions do that.

---

## Quick Hands-On: Look at a Real Cluster

If you have Minikube or kind running (see the main README for setup):

```bash
# See the nodes in your cluster
kubectl get nodes

# See what's already running (Kubernetes runs its own system pods)
kubectl get pods --all-namespaces

# Get a summary of the whole cluster
kubectl cluster-info
```

You don't need to understand the output fully yet. Just get comfortable running commands. Notice that Kubernetes itself has pods running — it uses its own system to manage itself.

---

## Common Questions & Doubts

### "Do I need Kubernetes if I'm already using Docker Compose?"

Docker Compose is great for running multi-container apps **on a single machine**. The moment you need to run across multiple machines, survive server failures, or scale automatically — Compose can't do that. Kubernetes picks up exactly where Compose stops.

> Rule of thumb: Docker Compose for local dev, Kubernetes for production.

---

### "Is Kubernetes only for big companies / large apps?"

No. Kubernetes runs fine on a single node (even your laptop with Minikube). That said, it does add operational complexity, so for a simple hobby app with predictable traffic, it might be overkill. The sweet spot is teams that need reliability, scaling, or multiple services talking to each other.

---

### "What happens to my app if the control plane goes down?"

Already-running pods **keep running** — worker nodes don't stop just because the control plane is unavailable. What stops working: scheduling new pods, applying config changes, auto-restarting crashed pods. This is why production clusters run multiple control plane replicas.

---

### "Is Docker the only container runtime Kubernetes supports?"

No. Kubernetes uses a standard interface called **CRI (Container Runtime Interface)**. Docker, containerd, and CRI-O all implement it. In fact, since Kubernetes 1.24, Docker itself is no longer directly supported as a runtime — most clusters use **containerd** under the hood. Your Docker-built images still work perfectly.

---

### "What's the difference between Kubernetes and Docker Swarm?"

Both orchestrate containers across machines. Kubernetes is significantly more powerful and has a much larger ecosystem, but also more complexity. Docker Swarm is simpler to set up but rarely used in production today. If you're learning in 2024+, learn Kubernetes — Swarm is largely legacy.

---

### "If Kubernetes auto-restarts crashed pods, is my app fault-tolerant automatically?"

Partially. K8s will restart a crashed pod, but there's a brief downtime between the crash and the restart. True fault tolerance means running **multiple replicas** so other copies keep serving traffic while the crashed one restarts. Auto-restart is a safety net, not a substitute for replicas.

---

## Interview Questions

These are real questions asked in interviews for roles that involve Kubernetes.
Try to answer each one yourself before revealing the answer.

---

**Q1. What is Kubernetes and what problem does it solve?**

<details>
<summary>Show answer</summary>

Kubernetes is an open-source container orchestration platform. It solves the problem of running containerized applications reliably at scale — handling deployment, scaling, self-healing, and load balancing across a cluster of machines, so engineers don't have to do this manually.

</details>

---

**Q2. What is the difference between a container and a pod?**

<details>
<summary>Show answer</summary>

A **container** is a runnable image (built with Docker, etc.) — it packages your app and its dependencies. A **pod** is Kubernetes' smallest deployable unit that *wraps* one or more containers. Kubernetes doesn't schedule containers directly; it schedules pods. The pod gives containers a shared network namespace and storage.

</details>

---

**Q3. What are the main components of the Kubernetes control plane?**

<details>
<summary>Show answer</summary>

- **kube-apiserver** — the front door; all kubectl commands go here
- **etcd** — distributed key-value store; the cluster's source of truth (stores all state)
- **kube-scheduler** — watches for new pods with no assigned node and picks a node for them
- **kube-controller-manager** — runs control loops that reconcile actual state to desired state (e.g. restarts crashed pods)

</details>

---

**Q4. What is etcd and why is it important?**

<details>
<summary>Show answer</summary>

etcd is a distributed, strongly consistent key-value store. Kubernetes stores *all* cluster state in etcd — every pod, deployment, config, secret. If etcd is lost without a backup, the cluster's state is gone (running pods keep running but can't be managed). This is why etcd backups are critical in production.

</details>

---

**Q5. What is the difference between declarative and imperative configuration in Kubernetes?**

<details>
<summary>Show answer</summary>

- **Imperative:** You tell Kubernetes *what to do* step by step — `kubectl run`, `kubectl scale`. Good for quick one-offs, bad for repeatability.
- **Declarative:** You write a YAML file describing the *desired end state* and apply it — `kubectl apply -f`. Kubernetes figures out what needs to change to reach that state. This is the production-standard approach because it's versionable, reviewable, and idempotent.

</details>

---

**Q6. What happens when a worker node goes down?**

<details>
<summary>Show answer</summary>

The control plane detects the node is unreachable (after a grace period, typically ~5 minutes). It marks the node as `NotReady` and evicts the pods that were running on it. Those pods are rescheduled onto healthy nodes — assuming there are enough resources. This is why running multiple replicas matters: single-replica apps will have downtime during this window.

</details>

---

**Q7. Can Kubernetes run without Docker?**

<details>
<summary>Show answer</summary>

Yes. Kubernetes uses the Container Runtime Interface (CRI) to talk to any compliant runtime. Since Kubernetes 1.24, Docker is no longer a supported runtime. Most clusters today use **containerd** (which Docker itself uses internally). Container images built with Docker work perfectly — the image format (OCI) is the standard.

</details>

---

**Q8. What is a namespace in Kubernetes? (We'll cover this in depth in topic 06)**

<details>
<summary>Show answer</summary>

A namespace is a logical partition inside a cluster. It lets multiple teams or environments (dev, staging, prod) share the same physical cluster while keeping their resources isolated. Resource names only need to be unique *within* a namespace. Some resources (like nodes) are cluster-scoped and don't belong to any namespace.

</details>

---

## Summary

| Concept | In one sentence |
|---------|----------------|
| Kubernetes | A system that manages containers across many machines so you don't have to |
| Cluster | All your machines, treated as one unit |
| Node | One machine in the cluster |
| Pod | The thing Kubernetes actually runs (wraps your container) |
| kubectl | Your command-line interface to the cluster |
| Declarative config | You say *what* you want; K8s figures out *how* |

---

## Exercises

See [exercises/README.md](./exercises/README.md) for hands-on practice.

---

## Next Topic

**[02 — Pods →](../02-pods/README.md)**  
Now that you know what Kubernetes is, let's create your first running application inside a pod.
