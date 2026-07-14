# Topic 14 Exercises — DaemonSets

Work through these in order. All exercises work on a single-node Minikube cluster.

---

## Exercise 1 — See What DaemonSets Already Exist

**Goal:** Before writing your own, understand that your cluster already depends on DaemonSets.

```bash
# List DaemonSets across all namespaces
kubectl get daemonsets --all-namespaces

# On most clusters you'll see at least:
#   kube-system   kube-proxy        ← handles Service routing on every node
# Possibly also:
#   kube-system   calico-node       ← network plugin
#   kube-system   cilium            ← network plugin (alternative)

# Describe kube-proxy to see its HostPath volumes and tolerations
kubectl describe daemonset kube-proxy -n kube-system
# Notice:
#   - Tolerations: it runs on control-plane nodes too
#   - HostPath volumes: it reads /run/xtables.lock from the node
#   - No "replicas" field — it matches all nodes

# See the pods and which nodes they're on
kubectl get pods -n kube-system -l k8s-app=kube-proxy -o wide
```

<details>
<summary>Why does kube-proxy need to run on every node?</summary>

kube-proxy manages iptables (or ipvs) rules on each node that implement Service routing. When you send traffic to a ClusterIP, it's kube-proxy's rules on that node that redirect it to the right Pod. If a node had no kube-proxy, Services wouldn't work for Pods on that node.
</details>

---

## Exercise 2 — Deploy a Basic DaemonSet and Count Pods

**Goal:** Confirm that DaemonSets always match node count, with no `replicas` field.

```bash
kubectl apply -f ../examples/01-basic-daemonset.yaml

# Check the DaemonSet summary
kubectl get daemonset node-monitor
# DESIRED = number of nodes in your cluster
# CURRENT = how many are scheduled
# READY = how many are running

# See which node(s) the Pod(s) run on
kubectl get pods -l app=node-monitor -o wide
# NODE column shows the node name

# There is no replicas field — confirm:
kubectl get daemonset node-monitor -o yaml | grep -i replicas
# Should return nothing (it's absent by design)
```

Now check how many nodes you have:
```bash
kubectl get nodes
# DESIRED in the DaemonSet should equal this count
```

**Checkpoint:**
- [ ] `DESIRED` matches your node count
- [ ] `kubectl get daemonset -o yaml` has no `replicas` field
- [ ] One Pod per node in `kubectl get pods -o wide`

---

## Exercise 3 — The Node Name via Downward API

**Goal:** See how a DaemonSet Pod knows which node it's running on.

```bash
kubectl apply -f ../examples/02-log-collector.yaml

# Wait for the Pod to start
kubectl get pods -l app=log-collector -w

# Check the logs — it prints the node name it discovered
kubectl logs -l app=log-collector

# Exec into the pod and check the env var yourself
kubectl exec -it $(kubectl get pod -l app=log-collector -o name | head -1) -- sh
echo $NODE_NAME       # prints the node name
ls /var/log/          # node's /var/log is mounted here
exit
```

The `NODE_NAME` variable comes from the Downward API — Kubernetes injects the node name at runtime. This is how agents like Datadog and Fluentd label their metrics/logs with the node they came from.

**Checkpoint:**
- [ ] `echo $NODE_NAME` inside the pod shows the actual node name
- [ ] `/var/log/` inside the pod shows the node's log directory

**Clean up:**
```bash
kubectl delete -f ../examples/02-log-collector.yaml
```

---

## Exercise 4 — nodeSelector: Target a Subset of Nodes

**Goal:** Run a DaemonSet on only specifically labeled nodes, and watch it respond to label changes.

```bash
# First, apply the GPU monitor DaemonSet
kubectl apply -f ../examples/04-node-subset-daemonset.yaml

# It should have DESIRED=0 because no node has the label yet
kubectl get daemonset gpu-monitor
# DESIRED: 0, CURRENT: 0

# Get your node name (Minikube: it's "minikube")
kubectl get nodes

# Add the label to your node
kubectl label node minikube hardware=gpu

# Now check the DaemonSet — it should detect the label and schedule a Pod
kubectl get daemonset gpu-monitor
# DESIRED: 1, CURRENT: 1, READY: 1

kubectl get pods -l app=gpu-monitor -o wide
# Should show a pod running on the minikube node
```

Now remove the label and watch the Pod disappear:
```bash
# Remove the label (trailing dash removes a label)
kubectl label node minikube hardware-

# Check — Pod should terminate
kubectl get pods -l app=gpu-monitor -w
# Pod terminates within a few seconds

# DaemonSet goes back to DESIRED: 0
kubectl get daemonset gpu-monitor
```

Re-add the label to restore:
```bash
kubectl label node minikube hardware=gpu
kubectl get pods -l app=gpu-monitor -w   # Pod comes back
```

**Checkpoint:**
- [ ] No Pod scheduled before the label was applied
- [ ] Pod appeared after labeling the node
- [ ] Pod disappeared after removing the label
- [ ] Pod came back after re-adding the label

**Clean up:**
```bash
kubectl delete -f ../examples/04-node-subset-daemonset.yaml
kubectl label node minikube hardware-
```

---

## Exercise 5 — Rolling Update on a DaemonSet

**Goal:** Update a DaemonSet's image and watch the rollout happen.

```bash
kubectl apply -f ../examples/05-rolling-update-demo.yaml

# Verify it's using nginx:1.24
kubectl get pods -l app=rolling-demo -o jsonpath='{.items[0].spec.containers[0].image}'
# → nginx:1.24

# Trigger a rolling update to nginx:1.25
kubectl set image daemonset/rolling-demo nginx=nginx:1.25

# Watch the rollout (on a single-node cluster this is fast)
kubectl rollout status daemonset/rolling-demo

# Verify the new image is running
kubectl get pods -l app=rolling-demo -o jsonpath='{.items[0].spec.containers[0].image}'
# → nginx:1.25

# Check rollout history
kubectl rollout history daemonset/rolling-demo
# Shows revisions 1 and 2
```

Roll it back:
```bash
kubectl rollout undo daemonset/rolling-demo

# Verify it's back to nginx:1.24
kubectl get pods -l app=rolling-demo -o jsonpath='{.items[0].spec.containers[0].image}'
# → nginx:1.24
```

**Checkpoint:**
- [ ] `kubectl rollout status` reported successful rollout
- [ ] Image changed from 1.24 to 1.25 after update
- [ ] `kubectl rollout undo` reverted to 1.24
- [ ] `kubectl rollout history` shows both revisions

**Clean up:**
```bash
kubectl delete -f ../examples/05-rolling-update-demo.yaml
```

---

## Exercise 6 — Toleration: Run on Control-Plane Nodes

**Goal:** See how taints block DaemonSets, and how tolerations fix it.

First, check if your control-plane node has a taint (it does on most real clusters):
```bash
kubectl describe node minikube | grep -A5 Taints
# On Minikube: Taints: <none>  (minikube removes the taint for convenience)
# On kubeadm clusters: node-role.kubernetes.io/control-plane:NoSchedule
```

Simulate the real scenario by manually tainting the node:
```bash
# Add a custom taint
kubectl taint node minikube custom-taint=yes:NoSchedule

# Deploy a DaemonSet WITHOUT a toleration
kubectl apply -f ../examples/01-basic-daemonset.yaml

kubectl get daemonset node-monitor
# DESIRED: 0 — the taint is blocking the DaemonSet

kubectl describe pod -l app=node-monitor 2>/dev/null || echo "No pods — blocked by taint"
```

Now fix it with a toleration:
```bash
kubectl patch daemonset node-monitor --type='json' -p='[
  {
    "op": "add",
    "path": "/spec/template/spec/tolerations",
    "value": [{"key": "custom-taint", "operator": "Exists", "effect": "NoSchedule"}]
  }
]'

kubectl get daemonset node-monitor
# DESIRED: 1 — toleration allows the Pod to land on the tainted node
```

**Checkpoint:**
- [ ] Taint blocked the DaemonSet (DESIRED: 0)
- [ ] Adding a toleration allowed the Pod to schedule (DESIRED: 1)
- [ ] This is exactly how network plugins and security agents run on control-plane nodes

**Clean up:**
```bash
kubectl taint node minikube custom-taint=yes:NoSchedule-   # trailing dash removes the taint
kubectl delete -f ../examples/01-basic-daemonset.yaml
```

---

## Exercise 7 — Node Exporter (Real-World Pattern)

**Goal:** Deploy a real Prometheus Node Exporter and scrape actual node metrics.

```bash
kubectl apply -f ../examples/03-node-exporter.yaml

kubectl get daemonset node-exporter
kubectl get pods -l app=node-exporter -o wide

# Port-forward to access metrics
kubectl port-forward daemonset/node-exporter 9100:9100 &

# Scrape some metrics
curl -s http://localhost:9100/metrics | grep -E "^node_cpu|^node_memory|^node_filesystem" | head -20

# Key metrics to notice:
#   node_cpu_seconds_total — CPU usage per mode (idle, user, system)
#   node_memory_MemAvailable_bytes — available memory
#   node_filesystem_size_bytes — disk size per mountpoint
```

Kill the port-forward:
```bash
kill %1 2>/dev/null || true
```

**Checkpoint:**
- [ ] DaemonSet scheduled one Pod per node
- [ ] Metrics endpoint responds at `:9100/metrics`
- [ ] Metrics include CPU, memory, and filesystem data from the actual node

**Clean up:**
```bash
kubectl delete -f ../examples/03-node-exporter.yaml
```

---

## Checkpoint — Can you answer these?

- [ ] What is the key difference between a DaemonSet and a Deployment?
- [ ] Why is there no `replicas` field in a DaemonSet spec?
- [ ] What happens to DaemonSet Pods when a new node joins the cluster?
- [ ] What is a HostPath volume and why do DaemonSets use it?
- [ ] What is the Downward API, and what does `fieldRef: fieldPath: spec.nodeName` inject?
- [ ] Why do DaemonSets need tolerations to run on control-plane nodes?
- [ ] What is `maxUnavailable` in a DaemonSet rolling update?
- [ ] Name three real-world workloads that are always run as DaemonSets.

---

**Next topic:** [15 — Jobs & CronJobs](../../15-jobs-cronjobs/README.md)
