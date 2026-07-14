# 14 — DaemonSets

> **Goal:** Understand when and why you need exactly one Pod per node, how DaemonSets manage that automatically, and how they differ from Deployments and StatefulSets.

---

## The Problem

Some workloads aren't about running your application — they're about running infrastructure on **every machine in your cluster**.

Think about:
- **Log collection**: every node generates logs in `/var/log`. You need a log shipper running on every node to forward them to Elasticsearch or Splunk.
- **Metrics collection**: you want CPU/memory/disk stats from every node sent to Prometheus.
- **Networking**: Kubernetes networking plugins (Calico, Cilium, Flannel) need a network agent on every node to handle pod-to-pod routing.
- **Security scanning**: Falco needs to watch system calls on every node to detect intrusions.

You could use a Deployment for this. But there's a problem: how many replicas? If you set `replicas: 5` and your cluster grows to 10 nodes, 5 nodes get no coverage. You'd have to manually scale up every time the cluster grows.

**DaemonSets solve this**: they ensure exactly one Pod runs on every node — automatically. When a new node joins the cluster, Kubernetes schedules the DaemonSet Pod on it. When a node is removed, the Pod is cleaned up.

---

## The Analogy

Think of a **janitorial service in an office building**.

Every floor of the building needs a janitor. When a new floor is added (new node), a janitor is automatically assigned there — you don't hire and assign manually. If a floor is torn down (node removed), that janitor moves on.

Crucially: the janitor needs access to that specific floor's supply closet (the node's filesystem, like `/var/log`). A janitor from floor 3 can't clean floor 7's office. Each one works on their own floor exclusively.

In Kubernetes:
- **Building floor** = Node
- **Janitor** = DaemonSet Pod
- **Supply closet** = Node's filesystem (accessed via HostPath volumes)
- **New floor added** = new node joins → pod scheduled automatically
- **Floor closed** = node removed → pod cleaned up automatically
- **Janitor on every floor** = one Pod per node

---

## Core Vocabulary

| Term | In one sentence |
|------|-----------------|
| **DaemonSet** | A controller that ensures exactly one Pod runs on every (matching) node |
| **Node selector** | A simple label filter — DaemonSet Pods only run on nodes with matching labels |
| **Node affinity** | More expressive node filtering — `required` (hard) or `preferred` (soft) rules |
| **Taint** | A mark on a node that repels Pods unless they have a matching toleration |
| **Toleration** | A Pod-level setting that says "I'm okay running on a tainted node" |
| **HostPath** | A volume that mounts a directory from the node's filesystem into the Pod |
| **hostNetwork** | Pod uses the node's network namespace — same IP, same ports as the node |
| **hostPID** | Pod can see all processes running on the node (not just its own) |
| **updateStrategy** | How the DaemonSet rolls out updates: `RollingUpdate` or `OnDelete` |

---

## DaemonSet vs Deployment vs StatefulSet

| Feature | Deployment | StatefulSet | DaemonSet |
|---------|-----------|-------------|-----------|
| **Replica count** | You set it | You set it | = number of (matching) nodes |
| **Pod scheduling** | Any available node | Any available node | Exactly one per node |
| **Identity** | Random names | Stable ordinal names | Pod name includes node name |
| **Storage** | Shared or none | Per-Pod PVC | Usually HostPath (node's disk) |
| **Use for** | Stateless apps | Databases, queues | Node-level infrastructure |
| **Scales with** | Manual or HPA | Manual | Node count (automatic) |

---

## How It Works (Architecture)

```
Cluster: 3 nodes

  ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
  │   Node A      │    │   Node B      │    │   Node C      │
  │               │    │               │    │               │
  │ ┌───────────┐ │    │ ┌───────────┐ │    │ ┌───────────┐ │
  │ │ DaemonPod │ │    │ │ DaemonPod │ │    │ │ DaemonPod │ │
  │ └───────────┘ │    │ └───────────┘ │    │ └───────────┘ │
  │               │    │               │    │               │
  │  /var/log ◄───┼─── │  /var/log ◄───┼─── │  /var/log ◄───┼─── node logs
  └───────────────┘    └───────────────┘    └───────────────┘

A new node D joins the cluster:
  → DaemonSet controller detects it
  → Schedules a new DaemonPod on Node D automatically
  → No human intervention required
```

The DaemonSet controller constantly watches the node list. You never set `replicas` — the replica count equals the number of nodes that match the DaemonSet's node selector.

---

## YAML Walkthrough

### Basic DaemonSet

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: log-collector
spec:
  selector:
    matchLabels:
      app: log-collector
  template:
    metadata:
      labels:
        app: log-collector
    spec:
      containers:
        - name: fluentd
          image: fluent/fluentd:v1.16
          volumeMounts:
            - name: varlog
              mountPath: /var/log        # access node logs inside container
            - name: varlibdockercontainers
              mountPath: /var/lib/docker/containers
              readOnly: true
      volumes:
        - name: varlog
          hostPath:
            path: /var/log             # node filesystem directory
        - name: varlibdockercontainers
          hostPath:
            path: /var/lib/docker/containers
```

**Key field: no `replicas`**. DaemonSets don't have `replicas` — the count is determined by how many nodes match.

### Running on a Subset of Nodes

Use `nodeSelector` to target only specific nodes (e.g., only GPU nodes, only storage nodes):

```yaml
spec:
  template:
    spec:
      nodeSelector:
        disktype: ssd     # only schedule on nodes labeled disktype=ssd
```

Label nodes:
```bash
kubectl label node my-node disktype=ssd
```

### Running on Control-Plane Nodes

Control-plane nodes have a taint (`node-role.kubernetes.io/control-plane:NoSchedule`) that prevents normal Pods from running there. To run a DaemonSet on control-plane nodes, add a toleration:

```yaml
spec:
  template:
    spec:
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
        - key: node-role.kubernetes.io/master    # older clusters
          operator: Exists
          effect: NoSchedule
```

Useful for: security agents, monitoring, and network plugins that must run everywhere including the control plane.

### Host Network Access

Some DaemonSets (especially network plugins) need to use the node's network stack directly:

```yaml
spec:
  template:
    spec:
      hostNetwork: true   # Pod uses node's network namespace — same IP as the node
      hostPID: true       # Pod can see all processes on the node
      containers:
        - name: network-agent
          securityContext:
            privileged: true   # needed for low-level network/kernel access
```

---

## Update Strategy

### RollingUpdate (default)

Updates one node's Pod at a time. Respects `maxUnavailable`:

```yaml
spec:
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1    # at most 1 node without the DaemonSet Pod at any time
```

Trigger an update by changing the Pod template (e.g., new image):
```bash
kubectl set image daemonset/log-collector fluentd=fluent/fluentd:v1.17
kubectl rollout status daemonset/log-collector
```

### OnDelete

The DaemonSet only updates a Pod when you manually delete it. You control exactly which nodes get updated and when:

```yaml
spec:
  updateStrategy:
    type: OnDelete   # nothing updates until you kubectl delete a pod
```

Use when: network plugins (updating could disrupt traffic) or when you need to update one node at a time for manual validation.

---

## Real-World DaemonSets You Already Have

Even on a fresh cluster, DaemonSets are already running:

```bash
kubectl get daemonsets --all-namespaces
```

You'll typically see:
- `kube-proxy` — handles iptables rules for Service routing on every node
- `calico-node` / `cilium` / `flannel` — network overlay plugin
- `node-exporter` (if Prometheus is installed) — exposes node metrics

These are the most critical workloads in a cluster — they must run on every node for the cluster to function.

---

## Common Mistakes / Gotchas

**1. Forgetting that control-plane nodes have taints**
On most clusters, `kubectl get pods -o wide` will show your DaemonSet isn't running on the control-plane node. Add the toleration if you need it there.

**2. HostPath data is node-local**
If a DaemonSet Pod moves to a different node (e.g., after node drain), it gets a different node's filesystem. HostPath data doesn't travel with the Pod. This is intentional for node-level agents — they belong to their node.

**3. Resource limits multiply by node count**
If your DaemonSet requests `500m` CPU and you have 100 nodes, that's 50 vCPUs reserved cluster-wide. Keep DaemonSet resource requests small — they're infrastructure, not apps.

**4. DaemonSets bypass the `replicas` concept entirely**
You can't scale a DaemonSet to 5 Pods on 3 nodes. It's always one per node. If you want variable replica counts, use a Deployment.

**5. `hostNetwork: true` means port conflicts**
If two DaemonSets both use `hostNetwork: true` and try to bind the same port, one will fail. Plan port allocations for host-network DaemonSets.

**6. Rolling updates don't wait for readiness by default**
Unlike Deployments, DaemonSet rolling updates move to the next node after the Pod on the current node starts — not after it passes readiness checks. Use `minReadySeconds` if you need to wait.

---

## Common Questions & Doubts

**If a DaemonSet runs one Pod per node, what happens when there's only 1 node (like Minikube)?**

You get exactly 1 Pod — one per node. The DaemonSet is working correctly; there's just one node to cover. This is fine for testing the DaemonSet mechanics. All the exercises in this topic work on a single-node Minikube cluster.

**Can I run more than one Pod per node with a DaemonSet?**

No — by design. If you need multiple instances per node, use a Deployment with `topologySpreadConstraints` or `podAntiAffinity`. A DaemonSet is specifically for the "exactly one per node" use case.

**Why not just use a Deployment with `replicas` set to the node count?**

Two reasons: (1) you'd have to manually scale whenever nodes are added or removed, (2) Kubernetes doesn't guarantee one Pod per node for Deployments — the scheduler might put two Pods on one node and leave another empty. DaemonSets have their own scheduling logic that guarantees one per node.

**Do DaemonSet Pods count against resource quotas?**

Yes, if resource requests are set. DaemonSet Pods are just Pods from the quota perspective. In the `kube-system` namespace, most clusters don't have quotas — but in your own namespaces, be aware that DaemonSet Pods consume quota per node.

**How is a DaemonSet Pod named?**

The name includes the DaemonSet name and the node name: `log-collector-<hash>`. Unlike StatefulSets which use ordinals, DaemonSet Pod names are hash-suffixed. The node name is accessible via the Downward API (`spec.nodeName`) inside the Pod.

---

## Interview Questions

<details>
<summary>Q: What is a DaemonSet and what is it used for?</summary>

A DaemonSet ensures exactly one Pod runs on every node (or every node matching a selector). When a node is added to the cluster, the DaemonSet automatically schedules a Pod on it. When a node is removed, the Pod is garbage collected.

Typical uses: log collectors (Fluentd, Filebeat), metrics agents (Prometheus Node Exporter, Datadog), network plugins (kube-proxy, Calico, Cilium), and security agents (Falco). These workloads are infrastructure, not apps — they need to cover every node uniformly.
</details>

<details>
<summary>Q: How does a DaemonSet differ from a Deployment?</summary>

A Deployment has a fixed `replicas` count you manage manually (or via HPA). Pods are scheduled on any available node, potentially multiple on one node. Deployments are for application workloads.

A DaemonSet has no `replicas` — the count equals the number of matching nodes. It guarantees exactly one Pod per node and auto-scales as nodes join or leave. DaemonSets are for node-level infrastructure. You can't run a DaemonSet on specific pods of a node, and you can't run more than one DaemonSet pod per node.
</details>

<details>
<summary>Q: How do you run a DaemonSet on only a subset of nodes?</summary>

Two approaches:

1. **`nodeSelector`** (simple): add a `nodeSelector` to the Pod template. Only nodes with matching labels get the Pod. Label nodes with `kubectl label node <node-name> <key>=<value>`.

2. **`nodeAffinity`** (expressive): use `requiredDuringSchedulingIgnoredDuringExecution` for hard rules or `preferredDuringSchedulingIgnoredDuringExecution` for soft rules. Supports operators like `In`, `NotIn`, `Exists`, `DoesNotExist`.

Example: a GPU monitoring DaemonSet only runs on nodes labeled `hardware=gpu`.
</details>

<details>
<summary>Q: What is a taint, and why do DaemonSets often need tolerations?</summary>

A taint is a mark on a node that repels Pods unless the Pod explicitly tolerates it. Control-plane nodes are tainted with `node-role.kubernetes.io/control-plane:NoSchedule` to prevent regular workloads from running there.

DaemonSets for networking (kube-proxy, Calico) and security (Falco) need to run on every node, including control-plane. Without a toleration, the DaemonSet Pod won't be scheduled on tainted nodes. Adding `tolerations` to the Pod spec with `key: node-role.kubernetes.io/control-plane, effect: NoSchedule` allows it.
</details>

<details>
<summary>Q: What is a HostPath volume and why do DaemonSets use it?</summary>

A HostPath volume mounts a directory from the node's filesystem directly into the Pod. DaemonSets use it because their job is often to process node-local data: log collectors need `/var/log` to read log files, metrics agents need `/sys` and `/proc` for kernel statistics, and network plugins need `/etc/cni` or `/run/xtables.lock`.

Unlike PVCs (which are portable across nodes), HostPath data stays on the node. This is intentional for DaemonSets — the Pod exists to serve that specific node, not to be relocated.
</details>

<details>
<summary>Q: How does DaemonSet rolling update work? How is it different from Deployment rolling update?</summary>

DaemonSet rolling update updates one node's Pod at a time, controlled by `maxUnavailable` (default: 1). It terminates the old Pod on a node, starts the new one, then moves to the next node.

Key difference from Deployments: Deployments create new Pods before deleting old ones (`maxSurge`). DaemonSets can't do that — you can't run two DaemonSet Pods on one node. So DaemonSet rolling update always terminates before replacing (unavailability is inherent per node during update).

The `OnDelete` strategy gives you full manual control: nothing updates until you `kubectl delete pod <daemonset-pod>` on a specific node.
</details>

<details>
<summary>Q: Scenario — You deploy a log collector DaemonSet but notice it's not running on your control-plane node. Why, and how do you fix it?</summary>

Control-plane nodes have a taint: `node-role.kubernetes.io/control-plane:NoSchedule`. Without a matching toleration, the scheduler won't place Pods there.

Fix: add tolerations to the DaemonSet's Pod template:
```yaml
tolerations:
  - key: node-role.kubernetes.io/control-plane
    operator: Exists
    effect: NoSchedule
  - key: node-role.kubernetes.io/master   # for older Kubernetes versions
    operator: Exists
    effect: NoSchedule
```

After updating the DaemonSet, the rolling update will place a Pod on the control-plane node. Verify with: `kubectl get pods -o wide -l app=log-collector` — the control-plane node should now appear.
</details>

---

## Summary

| Concept | What to remember |
|---------|-----------------|
| When to use | Log collectors, metrics agents, network plugins, security scanners |
| Replica count | Not set — equals number of matching nodes |
| Auto-scaling | Automatic: new node → new Pod; node removed → Pod cleaned up |
| `nodeSelector` | Limit to nodes with specific labels |
| Tolerations | Required to run on tainted nodes (e.g., control-plane) |
| HostPath | Mount node filesystem into the Pod — stays node-local |
| `hostNetwork` | Pod uses node's network stack; same IP as the node |
| UpdateStrategy | `RollingUpdate` (default, 1 node at a time) or `OnDelete` (manual) |
| Already running | kube-proxy, CNI plugin — DaemonSets power cluster networking |
| Key gotcha | Resource requests × node count = total cluster resource reservation |

---

## Exercises

Work through the hands-on tasks in [exercises/README.md](./exercises/README.md).

---

**Previous topic:** [13 — StatefulSets](../13-statefulsets/README.md)
**Next topic:** [15 — Jobs & CronJobs](../15-jobs-cronjobs/README.md)
