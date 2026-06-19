# Exercises — Services

Work through these in order. You need a running local cluster (Minikube or kind).

---

## Exercise 1: Create a ClusterIP Service and Prove It Works

```bash
kubectl apply -f examples/01-clusterip-service.yaml

# Confirm the service and its endpoints
kubectl get service backend-service
kubectl get endpoints backend-service
```

The Endpoints should list 3 pod IPs (one per replica). Now prove traffic reaches the pods from inside the cluster:

```bash
# Grab the ClusterIP
CLUSTER_IP=$(kubectl get service backend-service -o jsonpath='{.spec.clusterIP}')
echo $CLUSTER_IP

# Launch a temporary pod and curl the ClusterIP
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never \
  -- curl -s http://$CLUSTER_IP/
```

You should see the nginx default page HTML. The ClusterIP routed your request to one of the three backend pods.

**Now try with the DNS name — this is how real apps do it:**

```bash
kubectl run dns-test --image=curlimages/curl --rm -it --restart=Never \
  -- curl -s http://backend-service/
```

Same result — but you never looked up an IP. The name `backend-service` resolved via CoreDNS.

---

## Exercise 2: Watch Endpoints Update in Real Time

Open two terminals.

**Terminal 1 — watch endpoints:**
```bash
kubectl get endpoints backend-service -w
```

**Terminal 2 — delete a pod:**
```bash
kubectl delete pod $(kubectl get pods -l app=backend -o name | head -1)
```

In Terminal 1 you'll see the deleted pod's IP disappear from Endpoints, then a new pod IP appear once the replacement passes its readiness check.

This is the live Endpoints machinery — the Service automatically stops sending traffic to dead pods.

---

## Exercise 3: Deliberately Break the Selector and Debug It

Edit `examples/01-clusterip-service.yaml` and change the selector:

```yaml
selector:
  app: Backend    # capital B — won't match pods labelled app: backend
```

Apply it and check:

```bash
kubectl apply -f examples/01-clusterip-service.yaml
kubectl get endpoints backend-service
# ENDPOINTS column will show: <none>
```

Now try curling the service:

```bash
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never \
  -- curl --max-time 5 http://backend-service/
# curl: (28) Connection timed out  ← no endpoints = dropped connection
```

This is the most common Service bug. Always check Endpoints first.

**Fix it** — change the selector back to `app: backend` and re-apply.

---

## Exercise 4: Access the App from Your Laptop with NodePort

```bash
kubectl apply -f examples/02-nodeport-service.yaml

kubectl get service frontend-nodeport
# PORT(S) column shows: 80:30080/TCP
```

**On Minikube:**
```bash
minikube service frontend-nodeport --url
# Outputs something like: http://127.0.0.1:30080
# Open that URL in your browser
```

**On kind:**
```bash
# kind doesn't expose NodePorts by default. Use port-forward instead:
kubectl port-forward service/frontend-nodeport 8080:80
# Open http://localhost:8080
```

---

## Exercise 5: Understand port vs targetPort

The frontend Deployment in example 02 has `containerPort: 8080`, but the service has `port: 80` and `targetPort: 8080`.

Prove the translation is happening:

```bash
# This works — calling the Service port (80)
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never \
  -- curl -s http://frontend-nodeport:80/

# Get a pod IP and try calling it directly on port 80 — this FAILS
FRONT_POD_IP=$(kubectl get pods -l app=frontend -o jsonpath='{.items[0].status.podIP}')
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never \
  -- curl --max-time 3 http://$FRONT_POD_IP:80/
# Connection refused — the pod listens on 8080, not 80

# Call the pod directly on 8080 — this WORKS
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never \
  -- curl -s http://$FRONT_POD_IP:8080/
```

This confirms the Service is translating port 80 → 8080 when forwarding to pods.

---

## Exercise 6: DNS Discovery Across the Cluster

Test the full DNS name format `<service>.<namespace>.svc.cluster.local`:

```bash
kubectl run dns-test --image=busybox:1.36 --rm -it --restart=Never \
  -- nslookup backend-service

# Output includes:
# Name:      backend-service.default.svc.cluster.local
# Address 1: 10.96.xx.xx   ← the ClusterIP
```

Now test cross-namespace resolution. Create a second namespace and try to reach the service from it:

```bash
kubectl create namespace other

kubectl run dns-cross --image=curlimages/curl --rm -it --restart=Never \
  --namespace=other \
  -- curl -s http://backend-service/
# Fails — short name doesn't work across namespaces

kubectl run dns-cross --image=curlimages/curl --rm -it --restart=Never \
  --namespace=other \
  -- curl -s http://backend-service.default.svc.cluster.local/
# Works — full name includes the namespace

kubectl delete namespace other
```

---

## Exercise 7: Port-Forward to Access ClusterIP from Your Laptop

ClusterIPs aren't reachable from outside the cluster. `kubectl port-forward` creates a tunnel:

```bash
kubectl port-forward service/backend-service 9090:80
# Forwarding from 127.0.0.1:9090 -> 80
```

Open a second terminal:
```bash
curl http://localhost:9090/
# nginx welcome page — you're hitting the ClusterIP service from your laptop
```

This is the standard way to access internal services during development without changing Service types.

---

## Cleanup

```bash
kubectl delete -f examples/01-clusterip-service.yaml
kubectl delete -f examples/02-nodeport-service.yaml
# (03 and 04 require cloud or real DNS — safe to skip applying them locally)
```

---

## Checkpoint

- [ ] I know why pod IPs can't be used for reliable communication
- [ ] I can create a ClusterIP Service and verify its Endpoints
- [ ] I can debug a Service with `<none>` Endpoints (label mismatch check)
- [ ] I understand `port` vs `targetPort` vs `nodePort`
- [ ] I know how DNS works inside the cluster (short name vs full name)
- [ ] I can use `kubectl port-forward` to reach a ClusterIP from my laptop
- [ ] I can explain when to use ClusterIP, NodePort, LoadBalancer, and ExternalName

---

**[← Back to topic](../README.md)** | **[Next: ConfigMaps & Secrets →](../../05-configmaps-secrets/README.md)**
