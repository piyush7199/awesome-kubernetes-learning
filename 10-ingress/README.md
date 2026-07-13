# 10 — Ingress

> **Goal:** Understand how to route external HTTP/HTTPS traffic into your cluster using a single entry point, with host-based and path-based routing rules.

---

## The Problem

You've learned about [Services](../04-services/README.md). A `LoadBalancer` Service exposes your app to the internet. Great — but what happens when you have five apps?

```
Your Cluster
├── frontend    → LoadBalancer → gets a public IP   ($$$)
├── api         → LoadBalancer → gets a public IP   ($$$)
├── admin       → LoadBalancer → gets a public IP   ($$$)
├── auth        → LoadBalancer → gets a public IP   ($$$)
└── websocket   → LoadBalancer → gets a public IP   ($$$)
```

Five separate cloud load balancers. On most cloud providers, each one costs money (often $20–40/month). And you still can't do things like:

- Route `myapp.com/api` to one service and `myapp.com/frontend` to another
- Serve everything from `myapp.com` instead of five different IPs
- Terminate TLS (HTTPS) in one place instead of per-service

**Ingress** solves all of this. One entry point, one IP, smart routing rules.

```
Internet → ONE Ingress (1 public IP)
               ├── myapp.com/api      → api-service
               ├── myapp.com/         → frontend-service
               ├── admin.myapp.com    → admin-service
               └── auth.myapp.com     → auth-service
```

---

## The Analogy

Think of a **hotel's front desk**.

When you walk in, you don't go directly to a specific room. The front desk (Ingress) receives everyone and routes them:

- "Room 101? Down the hall on the left." (path `/rooms` → room-service)
- "Conference room? Take the elevator to floor 3." (path `/events` → event-service)
- "Restaurant? That's a different building." (host `restaurant.hotel.com` → restaurant-service)

Without the front desk, every room would need its own entrance directly from the street. That's expensive and chaotic. The front desk centralizes routing.

In Kubernetes:
- **Hotel front desk** = Ingress Controller (the actual software doing the routing)
- **Guest requests** = HTTP requests from the internet
- **Room directions** = Ingress rules (the YAML you write)
- **Rooms** = Services pointing to your Pods

---

## Core Vocabulary

| Term | In one sentence |
|------|-----------------|
| **Ingress** | A Kubernetes resource that defines routing rules for HTTP/HTTPS traffic |
| **Ingress Controller** | The actual software (nginx, Traefik, etc.) that reads Ingress rules and does the routing |
| **IngressClass** | A label that says "this controller handles these Ingress resources" |
| **Host-based routing** | Route to different services based on the hostname (`api.myapp.com` vs `myapp.com`) |
| **Path-based routing** | Route to different services based on the URL path (`/api` vs `/`) |
| **TLS termination** | The Ingress handles HTTPS, so your backend Pods only need to speak HTTP |
| **Annotation** | Extra config hints added to an Ingress resource for the controller to act on |
| **Backend** | The Service that receives traffic after the Ingress routes it |

---

## Two Parts You Need to Understand

Ingress is confusing at first because it's **two separate things**:

```
┌─────────────────────────────────────────────────────────────┐
│  Part 1: Ingress Controller                                  │
│  (A Pod running nginx, Traefik, HAProxy, etc.)               │
│  This is the actual routing software.                        │
│  YOU must install this — it doesn't come with Kubernetes.   │
└──────────────────────────┬──────────────────────────────────┘
                           │ reads
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Part 2: Ingress resource (your YAML)                        │
│  Defines the rules: "if host = X and path = Y,              │
│  forward to service Z".                                      │
│  This does NOTHING without Part 1.                           │
└─────────────────────────────────────────────────────────────┘
```

**If you create an Ingress resource but have no Ingress Controller running, nothing happens.** The resource just sits there, ignored.

---

## How It Works (Architecture)

```
                    Internet
                       │
                       ▼
              ┌─────────────────┐
              │  LoadBalancer   │  ← one cloud LB (one IP)
              │  Service        │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Ingress         │  ← nginx/Traefik pod(s)
              │ Controller      │    watching Ingress rules
              └────────┬────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ frontend │ │   api    │ │  admin   │
   │ Service  │ │ Service  │ │ Service  │
   └────┬─────┘ └────┬─────┘ └────┬─────┘
        │             │             │
     [Pods]        [Pods]        [Pods]
```

The Ingress Controller watches for Ingress resources in the cluster. When you create or update one, the controller reconfigures itself (e.g., updates its nginx.conf) and starts routing traffic accordingly.

---

## Path Types

When you write an Ingress rule, you specify how strictly to match the path.

| PathType | Rule: `/api` matches... | Example |
|----------|------------------------|---------|
| `Prefix` | `/api`, `/api/users`, `/api/v2/orders` | Most common — match the prefix |
| `Exact` | `/api` only — not `/api/users` | Strict matching |
| `ImplementationSpecific` | Depends on the controller | Avoid unless you need regex |

**Use `Prefix` unless you have a reason not to.**

---

## YAML Walkthrough

### Basic Ingress (Path-Based Routing)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app-ingress
  annotations:
    # Controller-specific hints go here (nginx-specific in this case)
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  ingressClassName: nginx      # which controller handles this Ingress
  rules:
    - host: myapp.example.com  # hostname to match (omit for any host)
      http:
        paths:
          - path: /api
            pathType: Prefix   # match /api and /api/anything
            backend:
              service:
                name: api-service    # route to this Service
                port:
                  number: 80
          - path: /
            pathType: Prefix   # catch-all — must come LAST
            backend:
              service:
                name: frontend-service
                port:
                  number: 80
```

**Key fields explained:**
- `ingressClassName` — tells Kubernetes which controller owns this Ingress
- `host` — only match requests with this `Host` header; omit to match all hosts
- `path` — URL path prefix to match
- `pathType` — how strictly to match the path
- `backend.service` — where to forward the matched traffic

### Host-Based Routing

```yaml
spec:
  rules:
    - host: api.myapp.com         # requests for api.myapp.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 80
    - host: myapp.com             # requests for myapp.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-service
                port:
                  number: 80
```

### TLS (HTTPS)

```yaml
spec:
  tls:
    - hosts:
        - myapp.example.com
      secretName: myapp-tls-secret  # Secret with tls.crt and tls.key
  rules:
    - host: myapp.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-service
                port:
                  number: 80
```

The TLS Secret must be of type `kubernetes.io/tls` and contain:
- `tls.crt` — your certificate (base64 encoded)
- `tls.key` — your private key (base64 encoded)

In production, tools like **cert-manager** automate this — you just tell it to get a Let's Encrypt cert for your domain.

---

## Setting Up Locally (Minikube)

For local development, Minikube ships a built-in nginx Ingress Controller:

```bash
# Enable the ingress addon
minikube addons enable ingress

# Verify the controller pod is running
kubectl get pods -n ingress-nginx

# Get the Minikube IP (use this as your "external IP")
minikube ip
```

Then add the hostname to your `/etc/hosts`:

```bash
# Add a line like this (replace 192.168.49.2 with your minikube ip)
echo "$(minikube ip) myapp.example.com" | sudo tee -a /etc/hosts
```

Now `curl myapp.example.com` routes through the Ingress Controller.

---

## Common Ingress Controllers

You're not locked into one. Different teams use different controllers:

| Controller | Best for |
|------------|----------|
| **nginx-ingress** (kubernetes/ingress-nginx) | Most common, well-documented, start here |
| **Traefik** | Dynamic config, good for microservices |
| **HAProxy** | High performance, fine-grained control |
| **AWS ALB Ingress** | Native AWS Application Load Balancer |
| **GCE Ingress** | Native GCP Load Balancer |
| **Istio Gateway** | Full service mesh, advanced traffic control |

For most teams: start with **nginx-ingress**.

---

## Common Annotations

Annotations are how you pass controller-specific settings. These only work with nginx-ingress:

```yaml
metadata:
  annotations:
    # Rewrite the URL before forwarding (strip /api prefix)
    nginx.ingress.kubernetes.io/rewrite-target: /$2

    # Enable CORS
    nginx.ingress.kubernetes.io/enable-cors: "true"

    # Rate limiting
    nginx.ingress.kubernetes.io/limit-rps: "10"

    # Body size limit (default 1m)
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"

    # Redirect HTTP to HTTPS
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"

    # Custom timeout
    nginx.ingress.kubernetes.io/proxy-read-timeout: "120"
```

Traefik uses completely different annotations. If you switch controllers, you update annotations.

---

## Ingress vs Service: When to Use Which

| Situation | Use |
|-----------|-----|
| HTTP/HTTPS web traffic from outside the cluster | **Ingress** |
| Non-HTTP protocol (TCP, UDP, gRPC on raw port) | **LoadBalancer Service** |
| Internal service-to-service communication | **ClusterIP Service** |
| Exposing for local testing only | **NodePort Service** |
| Traffic that needs path/host routing | **Ingress** |
| Single service that must be directly exposed | **LoadBalancer Service** |

---

## Common Mistakes / Gotchas

**1. Creating Ingress without an Ingress Controller**
The resource exists but nothing routes. Check: `kubectl get pods -n ingress-nginx` (or whatever namespace your controller is in).

**2. Wrong `ingressClassName`**
If the class doesn't match the running controller, your Ingress is ignored. Check: `kubectl get ingressclass`.

**3. Path order matters**
More specific paths must come before less specific ones. `/api/v2` must appear before `/api` which must appear before `/`. Most controllers evaluate top to bottom.

**4. Services must be `ClusterIP` (not `LoadBalancer`)**
The Ingress routes to a ClusterIP Service. Your backend services don't need to be LoadBalancer type — that would create a separate public IP and defeat the purpose.

**5. Host header must match exactly**
`myapp.com` and `www.myapp.com` are different hosts. Add both rules if you need both.

**6. TLS Secret must be in the same namespace as the Ingress**
If your Ingress is in `production` namespace, the TLS Secret must also be in `production`.

**7. Wildcard hosts have limits**
`*.myapp.com` works in some controllers but not all, and doesn't work for multi-level wildcards like `*.api.myapp.com`.

---

## Common Questions & Doubts

**But wait — if I need an Ingress Controller installed separately, is Ingress really built into Kubernetes?**

Sort of. The Ingress *resource type* is part of Kubernetes. But the controller that acts on those resources is not — it's a separate component you install. Think of it like: Kubernetes provides the interface (the resource type), but you choose the implementation (which controller software). This was a design choice to keep the core lightweight and allow different controllers for different needs.

**Can I use Ingress for non-HTTP traffic like WebSockets or gRPC?**

WebSockets: yes, nginx-ingress supports them (add annotation `nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"` and it handles the upgrade). Raw gRPC over HTTP/2: also supported by most controllers. Raw TCP/UDP (like a database port): no, Ingress is HTTP-only. Use a LoadBalancer Service for that.

**What's the difference between Ingress and a Service Mesh like Istio?**

Ingress handles north-south traffic (external → cluster). A service mesh like Istio handles east-west traffic (pod → pod inside the cluster) plus gives you things like mutual TLS between services, traffic mirroring, and circuit breakers. They're not competing — many teams use both. Don't worry about service meshes yet; we cover them conceptually in topic 20.

**Do I need Ingress if my cloud provider already gives me a load balancer?**

Yes — because a cloud load balancer doesn't understand HTTP paths or hostnames. It just forwards TCP. Ingress adds the HTTP routing layer on top. Some cloud providers (AWS ALB, GCP GLB) can do L7 routing, but you still configure it via the Ingress resource in Kubernetes, using a cloud-specific Ingress Controller.

**Can two Ingress resources share the same host?**

Yes. Different Ingress resources can define rules for different paths on the same host. The controller merges them. But be careful — if two resources define the same path, behavior is controller-specific (often last-write-wins or undefined).

---

## Interview Questions

**Beginner**

<details>
<summary>Q: What is the difference between a Service and an Ingress?</summary>

A Service exposes a single set of Pods (at a stable IP or DNS name). An Ingress is a routing layer on top of Services — it receives HTTP/HTTPS traffic and directs it to the right Service based on hostname or URL path. A Service handles traffic at layer 4 (TCP/UDP); Ingress works at layer 7 (HTTP). You typically have many Services and one Ingress routing to all of them.
</details>

<details>
<summary>Q: What is an Ingress Controller and why do you need one?</summary>

An Ingress Controller is the actual software (e.g., nginx, Traefik) that reads Ingress resources and enforces the routing rules. The Ingress resource is just a declaration — "route /api to the api-service." The controller is what actually proxies the traffic. Kubernetes ships neither — you install one separately. Without a controller, Ingress resources do nothing.
</details>

<details>
<summary>Q: What is path-based routing vs host-based routing?</summary>

Path-based routing: all traffic comes in on the same hostname, and the URL path determines which service receives it. Example: `myapp.com/api` → api-service, `myapp.com/` → frontend-service.

Host-based routing: the `Host` header in the HTTP request determines which service receives it. Example: `api.myapp.com` → api-service, `myapp.com` → frontend-service.

You can combine both in the same Ingress resource.
</details>

<details>
<summary>Q: What are the three PathTypes in Kubernetes Ingress?</summary>

- `Prefix`: matches the given path and any subpath (e.g., `/api` matches `/api`, `/api/users`, `/api/v2/orders`).
- `Exact`: matches only the exact path with no trailing variation.
- `ImplementationSpecific`: behavior depends on the Ingress Controller — often used for regex patterns.

`Prefix` is the most common choice for routing to API backends.
</details>

**Intermediate**

<details>
<summary>Q: How does TLS termination work in Ingress?</summary>

The Ingress Controller holds the TLS certificate (stored in a Kubernetes Secret of type `kubernetes.io/tls`). When a client connects via HTTPS, the controller terminates the TLS connection, decrypts the traffic, and forwards plain HTTP to the backend Service. Your Pods don't need to handle TLS at all. The Secret must be in the same namespace as the Ingress resource. In production, cert-manager automates certificate provisioning and renewal.
</details>

<details>
<summary>Q: What is IngressClass and why was it introduced?</summary>

IngressClass is a resource that identifies a controller. Before IngressClass (pre-1.18), clusters used an annotation `kubernetes.io/ingress.class: "nginx"` on each Ingress. This was informal and error-prone. IngressClass made it a first-class API: you create an IngressClass resource, the Ingress controller watches for Ingresses that reference its class, and ignores everything else. One cluster can run multiple controllers (e.g., nginx for most apps, AWS ALB for one that needs native integration) — IngressClass is how each controller knows which Ingresses are "theirs."
</details>

<details>
<summary>Q: A pod is healthy and the Service works, but traffic through Ingress returns 502. What do you check?</summary>

1. Check Ingress Controller logs: `kubectl logs -n ingress-nginx deploy/ingress-nginx-controller`. A 502 means the controller reached the Service but got a bad response (or connection refused).
2. Verify the Service name and port in the Ingress match exactly what exists: `kubectl get svc`.
3. Check that the backend Service has healthy Endpoints: `kubectl get endpoints <service-name>`.
4. Verify the `ingressClassName` on the Ingress matches a running controller: `kubectl get ingressclass`.
5. Check for annotation issues — a misconfigured `rewrite-target` can send requests to paths that don't exist on the backend.
6. Check if the controller is configured to reach the Service on the right port (targetPort on the Service, not just port).
</details>

<details>
<summary>Q: What happens if you have two Ingress resources with the same host and path?</summary>

Behavior is controller-specific and generally undefined. With nginx-ingress, the last-applied rule typically wins (or it may throw an error and mark the Ingress as invalid). To avoid conflicts, either: (1) use a single Ingress resource with all paths for a given host, or (2) use Ingress merging patterns your specific controller supports. In production, having two teams manage conflicting rules is a real operational hazard — some organizations use separate IngressClasses or separate clusters per team.
</details>

<details>
<summary>Q: How do probes, Services, and Ingress work together during a rolling update?</summary>

1. A new Pod starts; its readiness probe begins checking.
2. Until the readiness probe passes, the Pod is NOT added to the Service's Endpoints.
3. Since the Ingress Controller routes to the Service's Endpoints, the new Pod receives no Ingress traffic yet.
4. Only when the readiness probe passes does the Pod join the Endpoints and start receiving traffic.
5. Old Pods are terminated only after new Pods are ready.

This chain (readiness probe → Endpoints → Ingress routing) is what guarantees zero-downtime deployments. If you skip readiness probes, new Pods get traffic before they're ready, causing errors.
</details>

---

## Summary

| Concept | What to remember |
|---------|-----------------|
| Ingress resource | YAML that declares routing rules — does nothing alone |
| Ingress Controller | The running software that enforces those rules |
| IngressClass | Links an Ingress resource to a specific controller |
| Path-based routing | Route by URL path (`/api`, `/`, `/admin`) |
| Host-based routing | Route by hostname (`api.myapp.com`) |
| PathType: Prefix | `/api` matches `/api`, `/api/users`, etc. |
| TLS termination | Controller handles HTTPS; Pods see plain HTTP |
| Annotations | Controller-specific settings; differ per controller |
| Key gotcha | Ingress without a controller → nothing happens |

---

## Exercises

Work through the hands-on tasks in [exercises/README.md](./exercises/README.md).

---

**Previous topic:** [09 — Health Checks](../09-health-checks/README.md)
**Next topic:** [11 — RBAC](../11-rbac/README.md)
