# 02 — Pods

> **Goal:** Understand what a Pod is, how to create one, interact with it, and why you should almost never run a pod directly in production.

---

## Table of Contents

- [The Problem: Containers Need a Home](#the-problem-containers-need-a-home)
- [The Analogy: A Pod is an Apartment](#the-analogy-a-pod-is-an-apartment)
- [Core Vocabulary](#core-vocabulary)
- [Pod Lifecycle: The Phases](#pod-lifecycle-the-phases)
- [How a Pod Works](#how-a-pod-works)
- [Your First Pod — YAML Walkthrough](#your-first-pod--yaml-walkthrough)
- [Essential Pod Commands](#essential-pod-commands)
- [Multi-Container Pods (The Sidecar Pattern)](#multi-container-pods-the-sidecar-pattern)
- [Restart Policies](#restart-policies)
- [Common Mistakes & Gotchas](#common-mistakes--gotchas)
- [Common Questions & Doubts](#common-questions--doubts)
- [Interview Questions](#interview-questions)
- [Summary](#summary)
- [Exercises](#exercises)
- [Navigation](#navigation)

---

## The Problem: Containers Need a Home

In Docker, you run a container directly:

```bash
docker run nginx
```

Kubernetes doesn't work that way. It never schedules a raw container. Instead it schedules a **Pod** — a wrapper around one or more containers that carries extra information:

- Which node should run this?
- How much CPU and memory does it need?
- What should happen if it crashes?
- Which storage volumes does it need?
- Which other containers should run alongside it?

You can think of Kubernetes as a shipping company. It doesn't move individual items — it moves **shipping containers** (pods). The items (your app containers) ride inside.

---

## The Analogy: A Pod is an Apartment

Imagine a large apartment building:

```
Building (Node)
├── Apartment 1A (Pod)
│   ├── Resident: Alice (Container: your web app)
│   └── Resident: Bob (Container: a logging sidecar)
├── Apartment 2B (Pod)
│   └── Resident: Carol (Container: your database)
```

Key things apartments share with pods:
- Every apartment has **one address** (one IP). All residents in the apartment share it.
- Residents in the **same apartment** can talk through the wall (`localhost`) — no network hop needed.
- Residents in **different apartments** need to use the building's postal system (the cluster network).
- If the building burns down (node dies), apartments are rebuilt elsewhere — **but at a new address**.

---

## Core Vocabulary

| Term | Meaning |
|------|---------|
| **Pod** | The smallest deployable unit in K8s; wraps one or more containers |
| **Container spec** | The description of a container inside the pod YAML |
| **Image** | The Docker image your container runs (e.g. `nginx:1.25`) |
| **Pod IP** | The IP address assigned to the pod — unique in the cluster, but temporary |
| **Restart policy** | What to do when a container in the pod crashes (`Always`, `OnFailure`, `Never`) |
| **Pod phase** | Current lifecycle state: `Pending`, `Running`, `Succeeded`, `Failed`, `Unknown` |
| **Sidecar** | A helper container in the same pod as your main app (e.g. a log shipper) |

---

## Pod Lifecycle: The Phases

A pod moves through phases from creation to completion:

```
kubectl apply ──► Pending ──► Running ──► Succeeded
                               │
                               └──► Failed
```

| Phase | What it means |
|-------|--------------|
| **Pending** | Pod accepted by K8s, but containers not started yet. Could be waiting for an image pull, or for a node with enough resources. |
| **Running** | At least one container is running. The pod is alive. |
| **Succeeded** | All containers exited with code 0. Used for batch jobs, not long-running apps. |
| **Failed** | At least one container exited with a non-zero code and won't be restarted. |
| **Unknown** | K8s lost contact with the node hosting the pod. |

---

## How a Pod Works

Every pod gets:

1. **Its own IP address** — unique within the cluster
2. **Shared network namespace** — all containers inside share `localhost` and ports
3. **Shared storage volumes** — containers in the same pod can read/write the same mounted volume

```
┌─────────────────────────────────────────┐
│                   Pod                    │
│   IP: 10.244.1.5                        │
│                                         │
│  ┌──────────────┐  ┌────────────────┐  │
│  │  Container A │  │  Container B   │  │
│  │  (web app)   │  │  (log shipper) │  │
│  │  port: 8080  │  │                │  │
│  └──────┬───────┘  └───────┬────────┘  │
│         │  shared localhost │           │
│         └──────────────────┘           │
│                                         │
│  ┌────────────────────────────────┐    │
│  │  Shared Volume (e.g. /var/log) │    │
│  └────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

Container A writes logs to `/var/log/app.log`.
Container B reads from `/var/log/app.log` and ships them to a log service.
Neither container knows the other exists at the code level — they just share a folder.

---

## Your First Pod — YAML Walkthrough

See [`examples/01-simple-pod.yaml`](./examples/01-simple-pod.yaml):

```yaml
apiVersion: v1          # which K8s API version defines this resource
kind: Pod               # the type of resource
metadata:
  name: my-nginx        # the name of this pod in the cluster
  labels:
    app: nginx          # labels are key-value tags used to select/filter pods
spec:
  containers:
    - name: nginx               # name of this container inside the pod
      image: nginx:1.25         # Docker image to run
      ports:
        - containerPort: 80     # the port your app listens on inside the container
```

Apply it:

```bash
kubectl apply -f examples/01-simple-pod.yaml
```

Check it's running:

```bash
kubectl get pods
# NAME       READY   STATUS    RESTARTS   AGE
# my-nginx   1/1     Running   0          15s
```

The `1/1` means: 1 container running out of 1 total.

---

## Essential Pod Commands

```bash
# List all pods
kubectl get pods

# Wide output — shows which node the pod is on and its IP
kubectl get pods -o wide

# Detailed info about a pod (events, conditions, container state)
kubectl describe pod my-nginx

# Stream logs from the pod
kubectl logs my-nginx

# Follow logs in real time (like tail -f)
kubectl logs -f my-nginx

# Open a shell inside the running container
kubectl exec -it my-nginx -- /bin/bash

# Run a one-off command inside the container
kubectl exec my-nginx -- nginx -v

# Delete the pod
kubectl delete pod my-nginx

# Delete using the same file you used to create it
kubectl delete -f examples/01-simple-pod.yaml
```

---

## Multi-Container Pods (The Sidecar Pattern)

Most pods run a single container. But sometimes you need a helper container alongside your main app. This is the **sidecar pattern**.

See [`examples/02-sidecar-pod.yaml`](./examples/02-sidecar-pod.yaml) for the full example.

```yaml
spec:
  containers:
    - name: web-app           # main container
      image: nginx:1.25
      volumeMounts:
        - name: logs
          mountPath: /var/log/nginx

    - name: log-shipper       # sidecar: reads logs and ships them
      image: busybox
      command: ["sh", "-c", "tail -f /var/log/nginx/access.log"]
      volumeMounts:
        - name: logs
          mountPath: /var/log/nginx

  volumes:
    - name: logs              # shared volume both containers mount
      emptyDir: {}            # lives as long as the pod, wiped on pod death
```

Common sidecar uses:
- **Log shippers** — collect and forward logs
- **Proxies** — intercept network traffic (used heavily by service meshes like Istio)
- **Config reloaders** — watch for config changes and signal the main app

---

## Restart Policies

What happens when a container inside a pod crashes?

```yaml
spec:
  restartPolicy: Always    # default
```

| Policy | Behaviour |
|--------|-----------|
| `Always` | Always restart on exit (any exit code). Use for long-running apps. |
| `OnFailure` | Restart only on non-zero exit code. Use for batch jobs. |
| `Never` | Never restart. Use for one-shot tasks where you want to inspect the result. |

K8s uses **exponential backoff** for restarts: it waits 10s, then 20s, 40s, up to 5 minutes between attempts. You'll see `CrashLoopBackOff` status when a pod keeps crashing.

---

## Common Mistakes & Gotchas

### 1. Pods are ephemeral — never rely on their IP or identity
When a pod dies and a new one starts (even on the same node), it gets a **new IP address** and a **new name**. Never hardcode a pod IP. Use a **Service** (topic 04) to get a stable address.

### 2. Running pods directly in production is wrong
If you `kubectl apply` a pod definition and that pod crashes, Kubernetes will restart the container — but if the **node** dies, the pod is gone forever. Nothing recreates it. Use a **Deployment** (topic 03) for production — it automatically recreates pods anywhere in the cluster.

### 3. Most pod fields are immutable
You can't change the container image of a running pod with `kubectl apply`. You'll get an error. The workaround is `kubectl delete pod` + re-apply, or use a Deployment which handles this for you.

### 4. `READY 0/1` doesn't always mean crash
A pod can be `Running` but `0/1 READY` if a readiness probe is failing (topic 09). Check `kubectl describe pod <name>` — look at the `Conditions` and `Events` sections at the bottom.

### 5. `kubectl run` creates a pod, not a deployment (in recent K8s versions)
```bash
kubectl run my-pod --image=nginx    # creates a bare Pod
```
This is useful for quick tests but not for production.

---

## Common Questions & Doubts

### "Why can't Kubernetes just run containers directly, without pods?"

A pod provides things a raw container doesn't have: a stable network identity shared across multiple containers, volume mounts, restart policies, resource requests, and health check configuration. The pod abstraction keeps all of that in one place and makes it schedulable as a unit.

---

### "If I have one container per pod anyway, what's the point of the pod wrapper?"

Consistency. Kubernetes always works with pods. That uniform abstraction means all tooling (scheduling, networking, monitoring, logging) works the same way whether you have 1 container or 5 in a pod. It also lets you add a sidecar later without rewriting your deployment logic.

---

### "When should I put two containers in one pod vs two separate pods?"

Put them in the same pod only if they are **tightly coupled** — they must run on the same node, share the same lifecycle, and communicate via localhost or shared files. If they can function independently and scale independently, they belong in separate pods.

> Rule: Two containers in one pod = one always needs the other to work.

---

### "What is CrashLoopBackOff?"

It means a container is crashing on startup and K8s keeps restarting it with increasing delays (10s → 20s → 40s … up to 5 min). Common causes: bad config, missing env variable, wrong command, application bug on startup. Debug with:

```bash
kubectl describe pod <name>   # look at Events section
kubectl logs <name>            # or: kubectl logs <name> --previous (last crashed run)
```

---

### "Does deleting a pod delete my data?"

Data stored inside the container's filesystem: **yes, gone**. Data on a mounted `emptyDir` volume: **yes, gone when the pod is deleted** (but survives container restarts within the same pod). Data on a `PersistentVolume`: **no, safe**. We cover persistent storage in topic 07.

---

## Interview Questions

**Q1. What is a Pod in Kubernetes? How is it different from a container?**

<details>
<summary>Show answer</summary>

A pod is the smallest deployable unit in Kubernetes. It wraps one or more containers and provides them with a shared network namespace (one IP, shared localhost) and shared storage volumes. A container is the runnable image; a pod is the envelope Kubernetes uses to schedule and manage it. Kubernetes never schedules containers directly — only pods.

</details>

---

**Q2. Can a pod have multiple containers? When would you do that?**

<details>
<summary>Show answer</summary>

Yes. The sidecar pattern is the most common use case: a helper container runs alongside the main app in the same pod, sharing its network and storage. Examples: a log shipper reading from a shared volume, a proxy intercepting traffic, or a config reloader watching for file changes. Containers in the same pod communicate via localhost and are always co-scheduled on the same node.

</details>

---

**Q3. What are the pod phases and what does each mean?**

<details>
<summary>Show answer</summary>

- **Pending** — accepted but not yet running (pulling image, waiting for resources)
- **Running** — at least one container is running
- **Succeeded** — all containers exited with code 0 (typical for completed jobs)
- **Failed** — at least one container exited with a non-zero code and won't restart
- **Unknown** — node lost contact, state cannot be determined

</details>

---

**Q4. What is `CrashLoopBackOff` and how do you debug it?**

<details>
<summary>Show answer</summary>

`CrashLoopBackOff` means a container keeps crashing on startup and Kubernetes is backing off between restart attempts (10s → 20s → 40s, capped at 5 min). To debug: `kubectl describe pod <name>` to read the exit reason and recent events, and `kubectl logs <name> --previous` to see the output from the last crashed container. Common causes: bad startup command, missing environment variables, misconfigured config file, or an application bug.

</details>

---

**Q5. Why is it bad practice to run bare pods in production?**

<details>
<summary>Show answer</summary>

Bare pods have no controller watching over them. If the node they run on dies, the pod is gone — nothing recreates it. Also, updates (like changing the image) require manually deleting and recreating the pod. Deployments (topic 03) solve both problems: they watch pods through a ReplicaSet, automatically reschedule them on failure, and manage rolling updates. Bare pods are fine for debugging and one-off tasks.

</details>

---

**Q6. What happens to a pod's IP when the pod restarts (container crash) vs when the pod is recreated?**

<details>
<summary>Show answer</summary>

When a **container crashes and restarts** within the same pod, the pod keeps the same IP — only the container process restarts. When the **pod itself is deleted and recreated** (e.g. the node dies and a Deployment reschedules it), the new pod gets a brand new IP. This is why you should never rely on pod IPs for communication — use a Service instead, which provides a stable virtual IP that routes to whichever pods are currently healthy.

</details>

---

**Q7. What is the difference between `kubectl logs` and `kubectl logs --previous`?**

<details>
<summary>Show answer</summary>

`kubectl logs <pod>` shows logs from the currently running container. `kubectl logs <pod> --previous` shows logs from the previous (crashed) container instance. This is essential when debugging `CrashLoopBackOff` — the current container may not have logged anything yet if it crashes instantly, but `--previous` shows what the last run printed before dying.

</details>

---

**Q8. What is `emptyDir` and when would you use it?**

<details>
<summary>Show answer</summary>

`emptyDir` is a temporary volume created when a pod starts and deleted when the pod is removed. All containers in the pod can read and write to it. It survives container restarts but not pod deletion. Common uses: sharing files between a main container and a sidecar (e.g. app writes logs, log shipper reads them), or as scratch space for processing. For data that must survive pod restarts, use a PersistentVolume (topic 07).

</details>

---

## Summary

| Concept | In one sentence |
|---------|----------------|
| Pod | The smallest unit K8s schedules; wraps one or more containers |
| Pod IP | Each pod gets a unique cluster IP — but it changes when the pod is recreated |
| Restart policy | Controls what happens when a container exits (`Always` / `OnFailure` / `Never`) |
| Pod phase | Lifecycle state: Pending → Running → Succeeded / Failed |
| Sidecar | A helper container in the same pod sharing network and storage |
| CrashLoopBackOff | Pod keeps crashing on startup; K8s backing off before retrying |
| emptyDir | Temporary shared volume; lives as long as the pod |
| Bare pod risk | No controller watches it — if the node dies, the pod is gone forever |

---

## Exercises

See [exercises/README.md](./exercises/README.md) for hands-on practice.

---

## Navigation

**[← 01: What is Kubernetes?](../01-what-is-kubernetes/README.md)**  |  **[03: Deployments →](../03-deployments/README.md)**
