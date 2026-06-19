# 04 — Services

> **Goal:** Understand why pods can't talk to each other using pod IPs, how a Service provides a stable address, the four Service types and exactly when to use each, and how DNS-based service discovery works inside the cluster.

---

## The Problem: Pod IPs Are Temporary

From topic 02 you know that every pod gets a unique IP address. Sounds useful — can't your frontend just call your backend's pod IP directly?

No. Here's why:

```
Frontend pod wants to call backend
                │
                ▼
backend pod IP:  10.244.1.5   ← this pod crashes overnight
                │
                ▼
New backend pod IP: 10.244.2.9  ← different IP, frontend doesn't know
                │
                ▼
Frontend is broken. It's still calling 10.244.1.5.
```

The same problem occurs when you scale. If you have 3 backend pods, which IP does the frontend call? Even if you knew all three IPs, what happens when rolling update replaces them with 3 new pods with new IPs?

**You need a stable address that always points to the right, currently-running pods.**

That is exactly what a **Service** does.

---

## The Analogy: A Company Receptionist

Imagine a large company. Instead of giving customers the direct phone number of every employee, the company gives out **one main number** — the receptionist.

```
Customer calls: 1-800-COMPANY  ← stable, never changes
        │
        ▼
Receptionist answers
        │
        ├── routes to Alice (if available)
        ├── routes to Bob   (if available)
        └── routes to Carol (if available)
```

When Alice goes on holiday (pod deleted), the receptionist just routes to Bob and Carol instead. When a new employee Dave joins (new pod), the receptionist adds Dave to the list. The customer's number never changes.

In Kubernetes:
- The **main number** is the Service's stable IP (called the ClusterIP)
- The **receptionist** is kube-proxy + iptables rules on each node
- The **employees** are the pods
- The **employee list** is the Endpoints object (updated automatically as pods come and go)

---

## Core Vocabulary

| Term | Meaning |
|------|---------|
| **Service** | A stable network endpoint that routes traffic to a set of pods |
| **ClusterIP** | A virtual IP assigned to a Service — reachable anywhere inside the cluster |
| **Selector** | Label query the Service uses to find which pods to route to |
| **Endpoints** | The live list of pod IPs that a Service routes to (auto-managed by K8s) |
| **port** | The port the Service itself listens on |
| **targetPort** | The port the container inside the pod actually listens on |
| **nodePort** | The port opened on every node for external access (NodePort type only) |
| **kube-proxy** | A component on every node that sets up the routing rules for Services |
| **CoreDNS** | The DNS server inside the cluster; gives every Service a DNS name |
| **Headless Service** | A Service with no ClusterIP — used when you need to reach individual pods by name |

---

## How a Service Works Under the Hood

When you create a Service, three things happen:

### 1. A virtual IP (ClusterIP) is assigned

Kubernetes picks an IP from a reserved range (e.g. `10.96.0.0/12`) and assigns it to the Service. This IP is **not tied to any real machine** — it's virtual. It only exists in routing rules.

### 2. An Endpoints object is created and kept up to date

Kubernetes watches all pods in the cluster. When a pod matches the Service's selector AND is Ready, its IP is added to the Endpoints object. When the pod dies or becomes unready, its IP is removed automatically.

```bash
kubectl get endpoints my-service
# NAME         ENDPOINTS                               AGE
# my-service   10.244.1.5:80,10.244.2.3:80,10.244.3.7:80
```

### 3. kube-proxy programs the routing rules

`kube-proxy` runs on every node as a DaemonSet (we'll cover DaemonSets in topic 14). It watches for Endpoints changes and programs `iptables` rules (or `IPVS` rules) on the node.

When a packet arrives at the ClusterIP:
```
Packet to 10.96.14.22:80 (ClusterIP)
        │
        ▼
iptables intercepts it on the node
        │
        ▼
Randomly picks one of: 10.244.1.5:80, 10.244.2.3:80, 10.244.3.7:80
        │
        ▼
Rewrites destination IP to the chosen pod IP (DNAT)
        │
        ▼
Packet delivered to the pod
```

The traffic never actually goes through a middle machine — it's redirected at the kernel level on the same node where the request originated.

```
┌──────────────────────────────────────────────────────────┐
│                      Cluster                              │
│                                                           │
│  ┌──────────────┐      Service: my-service               │
│  │  Frontend    │      ClusterIP: 10.96.14.22:80         │
│  │  Pod         │──────────────────┐                     │
│  └──────────────┘                  │ iptables DNAT       │
│                                    ▼                     │
│                          ┌─────────────────┐             │
│                          │   Endpoints     │             │
│                          │  10.244.1.5:80  │──► Backend 1│
│                          │  10.244.2.3:80  │──► Backend 2│
│                          │  10.244.3.7:80  │──► Backend 3│
│                          └─────────────────┘             │
└──────────────────────────────────────────────────────────┘
```

---

## The Four Service Types

Kubernetes has four Service types. They are **cumulative** — each higher type includes everything the previous type does.

```
ClusterIP ──► NodePort ──► LoadBalancer
                              ▲
                      (cloud only — creates a real LB)

ExternalName (completely different — DNS alias only)
```

---

### Type 1: ClusterIP (Default)

**What it does:** Gives you a stable virtual IP that is reachable **only inside the cluster**.

**When to use it:** Any time two services inside the cluster need to talk to each other. This is the most common type. A frontend pod calling a backend pod. A backend calling a database.

```
Internet  ──✗──►  ClusterIP  (not reachable from outside)
   
Pod A     ──────►  ClusterIP  ──► Pod B, C, D
```

See [`examples/01-clusterip-service.yaml`](./examples/01-clusterip-service.yaml)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend-service
spec:
  type: ClusterIP     # this is the default; you can omit this line
  selector:
    app: backend      # routes to all pods with label app=backend
  ports:
    - port: 80        # Service listens on port 80
      targetPort: 8080  # but the pod container listens on 8080
```

The `port` vs `targetPort` distinction is important:

```
Frontend calls:   backend-service:80     (the Service's port)
Service routes to: <pod-ip>:8080         (the targetPort — what the app actually listens on)
```

Your app doesn't need to know anything changed. You can run your container on any port you like and expose it as port 80 through the Service.

---

### Type 2: NodePort

**What it does:** Opens a specific port (between 30000–32767) on **every node** in the cluster. External traffic hitting `<any-node-IP>:<nodePort>` gets routed to the Service's pods.

**When to use it:** Local development and testing when you don't have a cloud load balancer. Not recommended for production — you're exposing a port on every node, and you'd need to manually set up an external load balancer in front.

```
Internet ──► NodeIP:30080 (any node)
                │
                ▼
          ClusterIP:80
                │
                ▼
          Pod A, Pod B, Pod C
```

See [`examples/02-nodeport-service.yaml`](./examples/02-nodeport-service.yaml)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: frontend-nodeport
spec:
  type: NodePort
  selector:
    app: frontend
  ports:
    - port: 80          # ClusterIP port (internal)
      targetPort: 8080  # pod port
      nodePort: 30080   # external port on every node (omit to let K8s pick one)
```

On Minikube:
```bash
minikube service frontend-nodeport --url
# http://127.0.0.1:30080  ← open this in your browser
```

**The problem with NodePort in production:** Imagine 10 nodes. External traffic could hit node-1 but the pod might be on node-7. The traffic takes an extra internal hop. Also, you have to tell your clients which node IP to use — and node IPs can change too. Use LoadBalancer instead.

---

### Type 3: LoadBalancer

**What it does:** Provisions an **actual cloud load balancer** (AWS ELB, GCP Cloud Load Balancing, Azure LB) with a public IP, and connects it to a NodePort on every node.

**When to use it:** Exposing a Service to the internet in a cloud environment. Each LoadBalancer Service gets its own external IP.

```
Internet ──► External LB (public IP: 35.200.11.4)
                │
                ▼
          NodePort:30080 on any node
                │
                ▼
          ClusterIP:80
                │
                ▼
          Pod A, Pod B, Pod C
```

See [`examples/03-loadbalancer-service.yaml`](./examples/03-loadbalancer-service.yaml)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: web-loadbalancer
spec:
  type: LoadBalancer
  selector:
    app: web
  ports:
    - port: 80
      targetPort: 8080
```

After applying:
```bash
kubectl get service web-loadbalancer
# NAME               TYPE           CLUSTER-IP    EXTERNAL-IP     PORT(S)
# web-loadbalancer   LoadBalancer   10.96.14.22   35.200.11.4     80:31204/TCP
```

The `EXTERNAL-IP` is what users hit from the internet.

> **On Minikube:** `EXTERNAL-IP` stays `<pending>` because there's no cloud provider. Use `minikube tunnel` in a separate terminal to simulate it locally.

**Cost warning:** In cloud environments, each `LoadBalancer` Service creates a billable cloud resource. For many services, this adds up fast. **Ingress** (topic 10) solves this by sharing one load balancer across many services using routing rules.

---

### Type 4: ExternalName

**What it does:** Maps a Kubernetes Service name to an external DNS name. No proxy, no ClusterIP. Just a CNAME in DNS.

**When to use it:** When your app inside the cluster needs to reach an external service (e.g. a managed database like AWS RDS), but you want to use a K8s Service name that you can change without redeploying your app.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: database
spec:
  type: ExternalName
  externalName: my-db.abc123.us-east-1.rds.amazonaws.com
```

Your app calls `database:5432`. DNS resolves `database` → CNAME → `my-db.abc123.us-east-1.rds.amazonaws.com`. If you ever migrate to a different database, you just update the Service — your app's code and config never changes.

See [`examples/04-externalname-service.yaml`](./examples/04-externalname-service.yaml)

---

## Service Discovery: DNS Inside the Cluster

Every Service gets an automatic DNS name. You never need to look up a ClusterIP manually.

The full DNS name of any Service is:
```
<service-name>.<namespace>.svc.cluster.local
```

Example: a Service named `backend` in the `production` namespace:
```
backend.production.svc.cluster.local
```

But from within the **same namespace**, you can use just the short name:
```
backend
```

From a **different namespace**, use:
```
backend.production
```

This is provided by **CoreDNS** — a DNS server that runs as pods inside `kube-system`.

```bash
# See CoreDNS running
kubectl get pods -n kube-system | grep coredns

# Test DNS resolution from inside a pod
kubectl run dns-test --image=busybox --rm -it --restart=Never \
  -- nslookup backend-service

# Should return the ClusterIP of backend-service
```

### Why DNS Matters

Your app code can just say:
```python
response = requests.get("http://backend-service/api/data")
```

No hardcoded IPs. No configuration that changes between environments. The DNS name `backend-service` always resolves to the current ClusterIP, which routes to whichever pods are healthy right now.

---

## The Selector: How a Service Finds Its Pods

The Service uses a **label selector** to decide which pods to send traffic to. Only pods that:
1. Match the selector labels, **AND**
2. Are in the `Ready` state

...get added to the Endpoints list.

```yaml
# Service selector:
selector:
  app: backend
  version: stable

# This pod gets traffic — both labels match:
labels:
  app: backend
  version: stable
  other-label: ignored   # extra labels are fine, they don't disqualify

# This pod does NOT get traffic — version doesn't match:
labels:
  app: backend
  version: canary
```

This gives you powerful routing patterns — you can have two Deployments (`version: stable` and `version: canary`) and control which one your Service points to purely through labels.

---

## Headless Services

What if you need to reach **specific individual pods** instead of a random one?

A **headless Service** has `clusterIP: None`. Kubernetes doesn't assign a virtual IP. Instead, DNS returns the **actual IP of each matching pod** directly.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: db-headless
spec:
  clusterIP: None    # headless — no virtual IP
  selector:
    app: database
  ports:
    - port: 5432
```

```bash
nslookup db-headless
# Server: 10.96.0.10
# Address: 10.96.0.10:53
#
# Name: db-headless.default.svc.cluster.local
# Address: 10.244.1.5    ← actual pod IP
# Address: 10.244.2.9    ← actual pod IP
# Address: 10.244.3.2    ← actual pod IP
```

**When to use headless:** StatefulSets (topic 13) for databases like Cassandra, MongoDB, or Kafka — where you need to reach `pod-0`, `pod-1`, `pod-2` individually, not randomly.

---

## Port Naming: port vs targetPort vs nodePort

This trips up almost everyone. Here's the definitive breakdown:

```
                           ┌─────────────────────────────────────┐
External user              │           Kubernetes Cluster         │
     │                     │                                       │
     │  nodePort: 30080    │  port: 80         targetPort: 8080   │
     │  (on every node)    │  (Service port)   (pod port)         │
     │                     │                                       │
     ▼                     │         ┌───────┐                    │
NodeIP:30080 ──────────────┼────────►│Service│──────────────────► Pod:8080
                           │         └───────┘                    │
                           └─────────────────────────────────────┘
```

| Port field | Who uses it | Example |
|-----------|------------|---------|
| `nodePort` | External clients hitting a node directly | `30080` |
| `port` | Pods inside the cluster calling the Service | `80` |
| `targetPort` | The actual port your container listens on | `8080` |

You can also reference `targetPort` by name (defined in the container spec), which is much safer — if you change the container's listening port, you only update the container spec, not the Service:

```yaml
# In the container spec:
ports:
  - name: http
    containerPort: 8080

# In the Service:
ports:
  - port: 80
    targetPort: http    # references the name, not the number
```

---

## Service vs Ingress — When to Use Which

A common point of confusion:

| | Service (LoadBalancer) | Ingress (topic 10) |
|-|------------------------|-------------------|
| **Cost** | One cloud LB per Service | One cloud LB shared across all services |
| **Routing** | Port-based only | HTTP path and hostname routing |
| **TLS termination** | No (manual) | Yes (built-in) |
| **Use case** | Non-HTTP, or single service to expose | Multiple HTTP services on one IP |

Use a `LoadBalancer` Service for databases, gRPC services, or when you have just one HTTP service. Use Ingress when you have multiple HTTP/HTTPS services that should share a single external IP (e.g. `api.myapp.com` → api-service, `www.myapp.com` → frontend-service).

---

## Essential Service Commands

```bash
# List all services
kubectl get services
kubectl get svc          # shorthand

# Detailed info including Endpoints
kubectl describe service backend-service

# See which pod IPs the service is routing to
kubectl get endpoints backend-service

# Access a ClusterIP service from your laptop (creates a local tunnel)
kubectl port-forward service/backend-service 8080:80
# Now open http://localhost:8080 on your laptop

# On Minikube — get the URL for a NodePort or LoadBalancer service
minikube service backend-service --url
```

---

## Common Mistakes & Gotchas

### 1. Selector label mismatch — the most common bug

The Service has `selector: app: backend` but your pods have `app: Backend` (capital B). Result: Endpoints list is empty, all traffic gets dropped with a connection refused or timeout.

```bash
kubectl get endpoints my-service
# NAME         ENDPOINTS   AGE
# my-service   <none>      2m   ← selector doesn't match any pod
```

Always check Endpoints when a Service isn't working.

### 2. `targetPort` must match what the container actually listens on

If your app listens on `8080` but `targetPort` says `80`, packets arrive at the pod on the wrong port and the connection is refused. The container ignores them.

### 3. Pods not Ready don't get traffic

A pod that exists but fails its readiness probe (topic 09) is **automatically removed from the Endpoints list**. This is a feature — it prevents traffic from reaching a pod that isn't ready yet. But it surprises people who think `kubectl get pods` shows `Running` so the service should work.

### 4. Service DNS only works inside the cluster

`backend-service` resolves to a ClusterIP only from pods inside the cluster. From your laptop, it resolves to nothing. Use `kubectl port-forward` to access ClusterIP services from outside during development.

### 5. LoadBalancer is not free

Every `type: LoadBalancer` Service in a cloud cluster provisions a billable load balancer. For 10 services that's 10 load balancers. Use Ingress (topic 10) to consolidate them to one.

---

## Common Questions & Doubts

### "If Services load-balance across pods, is there a risk the same user hits a different pod each time and loses session state?"

Yes — by default, each request is routed to a random pod. If your app stores session data in memory, users can get routed to a pod that doesn't have their session. The proper fix is to store session state externally (Redis, a database) so any pod can serve any request. If you can't do that short-term, Services support **session affinity**:

```yaml
spec:
  sessionAffinity: ClientIP   # same client IP always goes to the same pod
```

This is a band-aid — it breaks under rolling updates and doesn't work behind NAT. Fix the app to be stateless instead.

---

### "How is a Service different from a Deployment? Do I need both?"

They serve different purposes and almost always go together:
- A **Deployment** keeps your pods running and handles updates
- A **Service** gives those pods a stable network address

A Deployment without a Service means your pods are running but nothing can reach them reliably. A Service without a Deployment is unusual — you'd have no pods for it to route to.

```
Deployment ──manages──► Pods
Service    ──routes to──► Pods (same pods, different concern)
```

---

### "What happens to in-flight requests during a rolling update?"

When a pod is removed from the Endpoints list (because a rolling update is terminating it), new requests stop going there. But requests already in flight can still be mid-connection. Kubernetes sends a `SIGTERM` to the pod and waits `terminationGracePeriodSeconds` (default: 30s) before force-killing it. Your app should handle `SIGTERM` by stopping new requests but finishing current ones ("graceful shutdown"). Well-configured apps lose zero in-flight requests during rolling updates.

---

### "Can a Service route to pods in a different namespace?"

Not with a selector — selectors only match pods in the same namespace as the Service. To route across namespaces, use an `ExternalName` Service pointing to the other namespace's Service DNS name:

```yaml
spec:
  type: ExternalName
  externalName: my-service.other-namespace.svc.cluster.local
```

---

### "What is kube-proxy actually doing? Is it a real proxy?"

Despite the name, kube-proxy doesn't proxy traffic in the traditional sense (it doesn't receive packets and forward them). It programs `iptables` or `IPVS` rules on each node. When a packet arrives destined for a ClusterIP, the kernel intercepts it and rewrites the destination IP to a real pod IP — all in the kernel, not in userspace. kube-proxy just keeps those rules updated as pods come and go.

---

## Interview Questions

**Q1. What is a Kubernetes Service and why do you need it if pods already have IP addresses?**

<details>
<summary>Show answer</summary>

Pod IPs are ephemeral — they change every time a pod is recreated (crash, rolling update, node failure). A Service provides a stable virtual IP (ClusterIP) and DNS name that never changes. It also automatically load-balances traffic across all healthy pods matching its selector. Without a Service, any client would need to track pod IPs manually, which breaks constantly.

</details>

---

**Q2. What are the four Service types? When would you use each?**

<details>
<summary>Show answer</summary>

- **ClusterIP** (default): stable IP reachable only inside the cluster. Use for pod-to-pod communication.
- **NodePort**: opens a port (30000–32767) on every node. Use for local development/testing when you need external access without a cloud LB.
- **LoadBalancer**: provisions a real cloud load balancer with a public IP. Use in production to expose HTTP/TCP services to the internet.
- **ExternalName**: DNS CNAME alias to an external hostname. Use to abstract external services (databases, third-party APIs) behind a K8s-native name.

</details>

---

**Q3. What is the difference between `port`, `targetPort`, and `nodePort` in a Service spec?**

<details>
<summary>Show answer</summary>

- `port`: the port the Service itself listens on (what pods inside the cluster call)
- `targetPort`: the port the container inside the pod actually listens on (traffic is forwarded here)
- `nodePort`: the port opened on every node for external access (NodePort/LoadBalancer types only, range 30000–32767)

Example: Service `port: 80`, `targetPort: 8080`. A pod calls `my-service:80`. The Service receives it and forwards to the pod on port `8080`.

</details>

---

**Q4. How does service discovery work in Kubernetes?**

<details>
<summary>Show answer</summary>

CoreDNS (a DNS server running in `kube-system`) automatically creates a DNS record for every Service. The full name is `<service-name>.<namespace>.svc.cluster.local`. From within the same namespace, pods can just use the short name `<service-name>`. This means application code never needs hardcoded IPs — it just uses DNS names, and the cluster resolves them to the current ClusterIP automatically.

</details>

---

**Q5. What is an Endpoints object and how does it relate to a Service?**

<details>
<summary>Show answer</summary>

An Endpoints object (or EndpointSlice in newer K8s) is automatically created for every Service with a selector. It holds the live list of pod IPs that match the selector AND are in the Ready state. kube-proxy reads this list to program iptables rules. When a pod crashes, its IP is removed from Endpoints immediately — stopping traffic to it. When a new pod starts and passes its readiness probe, its IP is added. You can inspect it with `kubectl get endpoints <service-name>`.

</details>

---

**Q6. A Service shows 0 Endpoints even though pods are running. What are the likely causes?**

<details>
<summary>Show answer</summary>

Three common causes:
1. **Label mismatch** — the Service selector doesn't match the pod labels (check with `kubectl describe service` and `kubectl get pods --show-labels`)
2. **Pods not Ready** — pods exist but are failing their readiness probe, so they're excluded from Endpoints
3. **Wrong namespace** — the Service and pods are in different namespaces (selectors only match within the same namespace)

Always run `kubectl get endpoints <service-name>` as the first debugging step for Service connectivity issues.

</details>

---

**Q7. What is a headless Service and when would you use it?**

<details>
<summary>Show answer</summary>

A headless Service has `clusterIP: None`. No virtual IP is assigned. Instead, DNS returns the actual IP addresses of all matching pods. This is used when clients need to discover and connect to individual pod instances directly — most commonly with StatefulSets for databases like Cassandra, Kafka, or MongoDB, where each pod has a stable identity and clients need to address `pod-0`, `pod-1` specifically rather than randomly load-balancing.

</details>

---

**Q8. What happens at the network level when a pod calls a Service's ClusterIP?**

<details>
<summary>Show answer</summary>

The packet is sent to the ClusterIP (a virtual IP that doesn't belong to any real interface). On the node where the source pod runs, kube-proxy has programmed `iptables` (or IPVS) rules that intercept packets destined for ClusterIPs. The kernel rewrites the destination to one of the real pod IPs (DNAT — destination NAT), selected randomly or via IPVS scheduling. The packet then travels normally to the target pod. No traffic ever hits a proxy machine — it's all done in-kernel at the node level.

</details>

---

**Q9. Why is `type: LoadBalancer` expensive in the cloud, and what is the alternative for multiple HTTP services?**

<details>
<summary>Show answer</summary>

Each `LoadBalancer` Service provisions a separate cloud load balancer (AWS ELB, GCP LB, etc.), each of which costs money (typically $15–25/month per LB). For 20 HTTP services that's 20 load balancers. The alternative is **Ingress** (topic 10): one cloud load balancer in front, with an Ingress controller inside the cluster that routes HTTP traffic to the correct Service based on hostname (`api.myapp.com`) or URL path (`/api/`, `/dashboard/`). This reduces 20 LBs to 1.

</details>

---

**Q10. What is session affinity and what are its trade-offs?**

<details>
<summary>Show answer</summary>

Session affinity (`sessionAffinity: ClientIP`) makes a Service route all requests from the same client IP to the same pod. This helps stateful apps that store session data in memory. Trade-offs: it breaks load balancing (one pod can get overloaded while others are idle), it doesn't work behind NAT (all traffic appears to come from one IP), and it breaks during rolling updates when the target pod is terminated. The correct fix is to make the application stateless by storing session data in an external store (Redis, DB).

</details>

---

## Summary

| Concept | In one sentence |
|---------|----------------|
| Service | A stable virtual endpoint that load-balances traffic to matching pods |
| ClusterIP | Default type — internal only, stable IP for pod-to-pod communication |
| NodePort | Opens a port on every node — for local dev/testing external access |
| LoadBalancer | Provisions a real cloud LB with public IP — for production internet traffic |
| ExternalName | DNS alias to an external hostname — for abstracting outside services |
| Selector | Label query that determines which pods receive Service traffic |
| Endpoints | Live list of pod IPs the Service routes to — auto-managed by K8s |
| kube-proxy | Programs iptables rules on each node to make ClusterIP routing work |
| CoreDNS | Gives every Service a DNS name: `<name>.<namespace>.svc.cluster.local` |
| Headless Service | `clusterIP: None` — DNS returns real pod IPs for direct addressing |
| port | The port the Service listens on |
| targetPort | The port the container inside the pod listens on |
| nodePort | The port opened on each node (NodePort/LoadBalancer types) |

---

## Exercises

See [exercises/README.md](./exercises/README.md) for hands-on practice.

---

## Navigation

**[← 03: Deployments](../03-deployments/README.md)** | **[05: ConfigMaps & Secrets →](../05-configmaps-secrets/README.md)**
