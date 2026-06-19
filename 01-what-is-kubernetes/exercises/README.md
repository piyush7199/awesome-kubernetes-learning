# Exercises — What is Kubernetes?

These exercises help you get hands-on before moving to the next topic.
No YAML yet — just exploration.

---

## Exercise 1: Start a Local Cluster

**Goal:** Get Kubernetes running locally so all future exercises work.

```bash
# If you have Minikube:
minikube start
minikube status   # should show: host: Running, kubelet: Running, apiserver: Running

# If you have kind:
kind create cluster --name k8learning
```

**Check it works:**
```bash
kubectl get nodes
```

Expected output (Minikube):
```
NAME       STATUS   ROLES           AGE   VERSION
minikube   Ready    control-plane   1m    v1.XX.X
```

> If you see `Ready`, you're set. If you see `NotReady`, wait 30 seconds and try again.

---

## Exercise 2: Explore What's Already Running

Kubernetes runs its own infrastructure as pods. Let's look at them.

```bash
kubectl get pods --namespace kube-system
```

You'll see pods with names like `coredns-*`, `etcd-*`, `kube-apiserver-*`, `kube-scheduler-*`.

**Questions to think about (no wrong answers):**
1. Can you identify which pod is the "brain" we talked about?
2. What do you think `coredns` might do? (Hint: DNS = name resolution)

<details>
<summary>Reveal answers</summary>

1. `kube-apiserver-*` is the API server — the front door of the control plane. `etcd-*` is the database. `kube-scheduler-*` assigns pods to nodes.
2. CoreDNS gives every pod a DNS name so pods can find each other by name instead of IP address.

</details>

---

## Exercise 3: Understand kubectl Basics

Try these commands and read their output:

```bash
# What cluster are you talking to?
kubectl cluster-info

# What version of Kubernetes?
kubectl version

# Full details about a node
kubectl describe node minikube   # replace 'minikube' with your node name if different
```

In `kubectl describe node`, find:
- **Capacity** section — how much CPU and memory the node has
- **Conditions** section — is the node healthy?
- **Allocated resources** — what's already in use by system pods

---

## Exercise 4: Kubectl Shorthand (Save Your Fingers)

`kubectl` has aliases. Try both forms and confirm they give the same output:

```bash
kubectl get nodes
kubectl get no        # 'no' is shorthand for nodes

kubectl get pods
kubectl get po        # 'po' is shorthand for pods

kubectl get namespaces
kubectl get ns        # 'ns' is shorthand for namespaces
```

---

## Checkpoint

Before moving to topic 02, you should be able to answer:

- [ ] What problem does Kubernetes solve?
- [ ] What is the difference between a cluster, a node, and a pod?
- [ ] How do you list nodes in your cluster?
- [ ] What does "declarative configuration" mean?

If any of these feel fuzzy, re-read the relevant section in the topic README.

---

**[← Back to topic](../README.md)** | **[Next: Pods →](../../02-pods/README.md)**
