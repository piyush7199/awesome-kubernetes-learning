# Topic 10 Exercises — Ingress

Work through these in order. You need Minikube with the ingress addon enabled.

```bash
# Enable the nginx Ingress Controller (one-time setup)
minikube addons enable ingress

# Verify the controller pod is running (may take 1-2 minutes)
kubectl get pods -n ingress-nginx
# You should see ingress-nginx-controller-... Running
```

---

## Exercise 1 — Observe the Ingress Controller

**Goal:** Understand what the Ingress Controller actually is before writing any rules.

```bash
# What is the IngressClass installed by Minikube?
kubectl get ingressclass
# You should see "nginx" — this is the name you use in ingressClassName:

# Where does the controller live?
kubectl get all -n ingress-nginx

# What Service exposes it externally?
kubectl get svc -n ingress-nginx
# Look for: ingress-nginx-controller with type NodePort or LoadBalancer
```

<details>
<summary>What to look for</summary>

The `ingress-nginx-controller` Service is the one that receives external traffic. On Minikube, it's a NodePort service. The Pod behind it (the nginx process) reads your Ingress resources and routes traffic accordingly.

Running `kubectl describe svc ingress-nginx-controller -n ingress-nginx` shows which ports are exposed.
</details>

---

## Exercise 2 — Deploy Path-Based Routing

**Goal:** Route `/api` and `/` to different services using one Ingress.

```bash
kubectl apply -f ../examples/01-basic-ingress.yaml
```

Add the hostname to your local hosts file:
```bash
echo "$(minikube ip) myapp.example.com" | sudo tee -a /etc/hosts
```

Wait for pods to be ready:
```bash
kubectl get pods -w
# Press Ctrl+C once all are Running
```

Test the routing:
```bash
# Should get nginx default page (frontend)
curl http://myapp.example.com/

# Should get "API response" (api backend)
curl http://myapp.example.com/api

# Check the Ingress resource status
kubectl describe ingress my-app-ingress
# Look for: Rules section showing paths and backends
```

**Checkpoint:**
- [ ] `/` returns a different response than `/api`
- [ ] `kubectl describe ingress` shows both path rules
- [ ] There is ONE IP address in the Ingress ADDRESS field

**Clean up:**
```bash
kubectl delete -f ../examples/01-basic-ingress.yaml
```

---

## Exercise 3 — Deploy Host-Based Routing

**Goal:** Three different hostnames, three different services, one Ingress.

```bash
kubectl apply -f ../examples/02-host-based-routing.yaml

# Add all three hostnames
MINIKUBE_IP=$(minikube ip)
echo "$MINIKUBE_IP app.example.com"   | sudo tee -a /etc/hosts
echo "$MINIKUBE_IP api.example.com"   | sudo tee -a /etc/hosts
echo "$MINIKUBE_IP admin.example.com" | sudo tee -a /etc/hosts

kubectl get pods -w   # wait for Running
```

Test each hostname:
```bash
curl http://app.example.com
# Expected: "Welcome to the App!"

curl http://api.example.com
# Expected: {"status":"ok"}

curl http://admin.example.com
# Expected: "Admin Panel"

# What about an unknown host?
curl http://unknown.example.com   # returns 404 — no rule matches
```

**Checkpoint:**
- [ ] Three different hosts → three different responses
- [ ] Only ONE Ingress resource is serving all three
- [ ] Unknown hostname gets a default 404

**Clean up:**
```bash
kubectl delete -f ../examples/02-host-based-routing.yaml
```

---

## Exercise 4 — Break It: Missing IngressClass

**Goal:** See what happens when the `ingressClassName` is wrong.

```bash
# Apply a deliberately broken Ingress with a fake class name
kubectl apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: broken-ingress
spec:
  ingressClassName: does-not-exist   # no controller watches this class
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
EOF

# Check the Ingress status
kubectl get ingress broken-ingress
# ADDRESS column will be empty — no controller claimed this Ingress

kubectl describe ingress broken-ingress
# Events may show nothing or an error
```

Now try to curl it — you'll get a connection refused or timeout because nothing is routing traffic.

Fix it:
```bash
kubectl patch ingress broken-ingress \
  --type='json' \
  -p='[{"op":"replace","path":"/spec/ingressClassName","value":"nginx"}]'

kubectl get ingress broken-ingress
# ADDRESS should now populate (give it ~30 seconds)
```

**Checkpoint:**
- [ ] Empty ADDRESS = Ingress not claimed by any controller
- [ ] Changing `ingressClassName` to `nginx` made the ADDRESS appear
- [ ] This explains why "I created an Ingress but nothing works" happens

**Clean up:**
```bash
kubectl delete ingress broken-ingress
```

---

## Exercise 5 — TLS (HTTPS) Ingress

**Goal:** Serve HTTPS traffic with a self-signed certificate.

Generate a self-signed certificate:
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=myapp.example.com/O=myapp"
```

Store it as a TLS Secret:
```bash
kubectl create secret tls myapp-tls-secret \
  --cert=tls.crt --key=tls.key

# Verify it exists and has the right type
kubectl get secret myapp-tls-secret
kubectl describe secret myapp-tls-secret
# Type should be: kubernetes.io/tls
```

Apply the TLS Ingress:
```bash
kubectl apply -f ../examples/03-tls-ingress.yaml
kubectl get pods -w
```

Test HTTPS:
```bash
# -k skips cert verification (needed for self-signed)
curl -k https://myapp.example.com

# HTTP should redirect to HTTPS (thanks to force-ssl-redirect annotation)
curl -v http://myapp.example.com
# Look for: 308 Permanent Redirect → https://...
```

**Checkpoint:**
- [ ] `curl -k https://myapp.example.com` returns a response
- [ ] `curl -v http://myapp.example.com` shows a redirect to HTTPS
- [ ] The TLS Secret type is `kubernetes.io/tls`

**Clean up:**
```bash
kubectl delete -f ../examples/03-tls-ingress.yaml
kubectl delete secret myapp-tls-secret
rm tls.key tls.crt
```

---

## Exercise 6 — Debug Ingress Routing with Describe and Logs

**Goal:** Learn the debugging workflow when Ingress isn't working.

```bash
# Deploy a working setup first
kubectl apply -f ../examples/01-basic-ingress.yaml

# Useful debugging commands:

# 1. Check the Ingress resource itself
kubectl describe ingress my-app-ingress
#  → Rules: shows exactly what the controller has configured
#  → Events: shows any controller errors

# 2. Check if the backend Service has healthy endpoints
kubectl get endpoints api-service
kubectl get endpoints frontend-service
#  → Empty endpoints = no Pods matching the selector

# 3. Check the Ingress Controller logs
kubectl logs -n ingress-nginx \
  $(kubectl get pod -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx -o name | head -1)
#  → Look for: 502, 503, upstream errors, configuration reloads

# 4. Check what the controller resolved
kubectl get ingress my-app-ingress -o yaml
#  → status.loadBalancer.ingress shows the assigned IP/hostname
```

Now deliberately break a selector and observe:
```bash
# Delete the api-service to simulate missing backend
kubectl delete service api-service

# Try to hit the route
curl http://myapp.example.com/api
# Should get a 503 Service Unavailable from nginx

# Check endpoints — should be empty now
kubectl get endpoints api-service
# Error: endpoints "api-service" not found

# The controller logs will show upstream errors
kubectl logs -n ingress-nginx \
  $(kubectl get pod -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx -o name | head -1) | tail -20
```

**Checkpoint:**
- [ ] `kubectl describe ingress` shows the Rules and Backends
- [ ] Missing Service → 503 from the Ingress Controller
- [ ] Controller logs show the upstream error

**Clean up:**
```bash
kubectl delete -f ../examples/01-basic-ingress.yaml
```

---

## Checkpoint — Can you answer these?

Before moving on:

- [ ] What is the difference between an Ingress resource and an Ingress Controller?
- [ ] What happens if you create an Ingress with no controller running?
- [ ] What does `ingressClassName` do?
- [ ] What is the difference between path-based and host-based routing?
- [ ] What does TLS termination mean? Does your Pod need to speak HTTPS?
- [ ] A user gets a 502 through Ingress. What do you check first?
- [ ] Can you have two Ingress resources pointing to the same hostname?
- [ ] Why do we use ClusterIP Services behind an Ingress, not LoadBalancer?

---

**Next topic:** [11 — RBAC](../../11-rbac/README.md)
