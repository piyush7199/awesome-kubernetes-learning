# Kubernetes Learning Path

A beginner-friendly, hands-on guide to Kubernetes — from zero to production-ready concepts.
No prior experience needed. Each topic builds on the last.

---

## How This Repo Works

- Topics are numbered in order. Start from `01` and go up.
- Each topic has its own folder with:
  - `README.md` — concept explained in plain English
  - `examples/` — YAML files you can actually apply to a cluster
  - `exercises/` — things to try yourself (with answers)
- You don't need a cloud account to start. We use [Minikube](https://minikube.sigs.k8s.io/) or [kind](https://kind.sigs.k8s.io/) locally.

---

## Topics

| # | Topic | What You'll Learn |
|---|-------|-------------------|
| [01](./01-what-is-kubernetes/README.md) | What is Kubernetes? | The problem K8s solves, core ideas, real-world analogy |
| [02](./02-pods/README.md) | Pods | The smallest deployable unit — what runs your code |
| [03](./03-deployments/README.md) | Deployments | Running multiple copies, rolling updates, rollbacks |
| [04](./04-services/README.md) | Services | How pods talk to each other and to the outside world |
| [05](./05-configmaps-secrets/README.md) | ConfigMaps & Secrets | Separating config from code |
| [06](./06-namespaces/README.md) | Namespaces | Logical isolation inside a cluster |
| [07](./07-persistent-volumes/README.md) | Persistent Volumes | Storage that survives pod restarts |
| [08](./08-resource-limits/README.md) | Resource Limits | Preventing one app from eating all the memory |
| [09](./09-health-checks/README.md) | Health Checks | Liveness and readiness probes |
| [10](./10-ingress/README.md) | Ingress | Routing external HTTP traffic to your services |
| [11](./11-rbac/README.md) | RBAC | Who is allowed to do what in a cluster |
| [12](./12-helm/README.md) | Helm | Packaging and deploying applications |
| [13](./13-statefulsets/README.md) | StatefulSets | Running databases and ordered workloads |
| [14](./14-daemonsets/README.md) | DaemonSets | Running something on every node |
| [15](./15-jobs-cronjobs/README.md) | Jobs & CronJobs | One-time and scheduled tasks |
| [16](./16-horizontal-pod-autoscaling/README.md) | Horizontal Pod Autoscaling | Scaling automatically under load |
| [17](./17-network-policies/README.md) | Network Policies | Firewall rules between pods |
| [18](./18-custom-resource-definitions/README.md) | Custom Resource Definitions | Extending Kubernetes with your own types |
| [19](./19-operators/README.md) | Operators | Automating complex application lifecycle |
| [20](./20-production-best-practices/README.md) | Production Best Practices | Security hardening, multi-cluster, GitOps |

---

## Prerequisites

- Basic comfort with the terminal
- Docker installed (for local examples)
- That's it — we explain everything else as we go

## Setting Up Your Local Cluster

```bash
# Option A — Minikube (easiest)
brew install minikube
minikube start

# Option B — kind (faster, no VM)
brew install kind
kind create cluster
```

Verify it works:
```bash
kubectl get nodes
# Should show one node with status Ready
```

---

*Topics in the table without links are coming soon. Open an issue or PR if you want to contribute one!*
