# Topic 13 Exercises — StatefulSets

Work through these in order. Each one proves a specific StatefulSet guarantee.

---

## Exercise 1 — Stable Pod Names vs Deployment Random Names

**Goal:** See the difference between Deployment and StatefulSet pod naming side by side.

```bash
# Create a Deployment (3 replicas)
kubectl create deployment name-demo --image=nginx:1.25 --replicas=3

# Create a StatefulSet (via the basics example)
kubectl apply -f ../examples/01-statefulset-basics.yaml

# Wait for all pods to be ready
kubectl get pods -w
# Press Ctrl+C when all are Running

# Compare the names side by side
kubectl get pods -l app=name-demo   # Deployment pods: random hash names
kubectl get pods -l app=web         # StatefulSet pods: web-0, web-1, web-2
```

Now delete one pod from each and watch what comes back:

```bash
# Delete a Deployment pod
kubectl delete pod -l app=name-demo --field-selector=status.podIP!=''
# Wait 10 seconds, then check:
kubectl get pods -l app=name-demo
# → Brand new random name

# Delete a StatefulSet pod
kubectl delete pod web-1
# Wait 10 seconds, then check:
kubectl get pods -l app=web
# → web-1 is back — same name, same PVC
```

**Checkpoint:**
- [ ] Deployment pods have random hashes in their names
- [ ] StatefulSet pods are always `web-0`, `web-1`, `web-2`
- [ ] Deleting `web-1` → Kubernetes creates a new `web-1` (not a random name)

**Clean up:**
```bash
kubectl delete deployment name-demo
```

---

## Exercise 2 — Per-Pod PVCs

**Goal:** Prove that each StatefulSet Pod gets its own dedicated PVC.

```bash
# The basics example should still be running from Exercise 1
kubectl get pvc
# You should see: data-web-0, data-web-1, data-web-2

# Write unique data to each pod's storage
kubectl exec web-0 -- sh -c "echo 'hello from pod 0' > /usr/share/nginx/html/index.html"
kubectl exec web-1 -- sh -c "echo 'hello from pod 1' > /usr/share/nginx/html/index.html"
kubectl exec web-2 -- sh -c "echo 'hello from pod 2' > /usr/share/nginx/html/index.html"

# Verify each pod has different content (they don't share storage)
kubectl exec web-0 -- cat /usr/share/nginx/html/index.html  # hello from pod 0
kubectl exec web-1 -- cat /usr/share/nginx/html/index.html  # hello from pod 1
kubectl exec web-2 -- cat /usr/share/nginx/html/index.html  # hello from pod 2

# Now delete web-1 and wait for it to come back
kubectl delete pod web-1
kubectl wait --for=condition=Ready pod/web-1 --timeout=60s

# Its data is still there (same PVC reattached)
kubectl exec web-1 -- cat /usr/share/nginx/html/index.html
# → hello from pod 1
```

**Checkpoint:**
- [ ] Three separate PVCs: `data-web-0`, `data-web-1`, `data-web-2`
- [ ] Each pod's storage is isolated — writing to pod-0 doesn't affect pod-1
- [ ] After pod-1 restarts, its data survives (PVC reattached)

---

## Exercise 3 — Watch Ordered Startup

**Goal:** See the sequential Pod creation in real time.

```bash
# First, delete the existing web StatefulSet (keep its PVCs for now)
kubectl delete statefulset web --cascade=orphan
# --cascade=orphan deletes the StatefulSet controller but leaves Pods and PVCs

# Actually, let's use the clean ordered demo instead
kubectl delete statefulset web
kubectl delete -f ../examples/01-statefulset-basics.yaml 2>/dev/null || true

# Apply the ordered startup demo
kubectl apply -f ../examples/03-ordered-startup-demo.yaml

# Watch in real time — press Ctrl+C after all 3 are Ready
kubectl get pods -w
```

You'll see:
```
NAME             READY   STATUS    RESTARTS   AGE
ordered-demo-0   0/1     Pending   0          0s
ordered-demo-0   0/1     Running   0          2s
# ~10 seconds pass (startup probe)...
ordered-demo-0   1/1     Running   0          12s
ordered-demo-1   0/1     Pending   0          12s   ← only appears after 0 is Ready
ordered-demo-1   0/1     Running   0          14s
ordered-demo-1   1/1     Running   0          24s
ordered-demo-2   0/1     Pending   0          24s   ← only appears after 1 is Ready
ordered-demo-2   1/1     Running   0          34s
```

**Checkpoint:**
- [ ] Pod 1 did NOT appear until Pod 0 was `1/1 Ready`
- [ ] Pod 2 did NOT appear until Pod 1 was `1/1 Ready`
- [ ] Total startup time ≈ 3× the individual startup time (sequential, not parallel)

---

## Exercise 4 — Watch Ordered Shutdown (Reverse Order)

**Goal:** See Pods terminate in reverse ordinal order.

```bash
# ordered-demo should be running with 3 replicas from Exercise 3
kubectl get pods -l app=ordered-demo

# In one terminal, watch the pods
kubectl get pods -l app=ordered-demo -w &

# Scale down to 1 replica — should terminate 2 first, then 1
kubectl scale statefulset ordered-demo --replicas=1

# Observe:
# ordered-demo-2 terminates first
# ordered-demo-1 terminates after ordered-demo-2 is gone
# ordered-demo-0 stays running
```

Kill the background watcher:
```bash
kill %1 2>/dev/null || true
kubectl get pods -l app=ordered-demo
# Only ordered-demo-0 remains
```

**Checkpoint:**
- [ ] Pod 2 terminated first
- [ ] Pod 1 terminated after Pod 2 was fully gone
- [ ] Pod 0 was never touched

**Clean up:**
```bash
kubectl delete -f ../examples/03-ordered-startup-demo.yaml
```

---

## Exercise 5 — PostgreSQL Persistence Proof

**Goal:** Run a real database, write data, delete the pod, and prove the data survives.

```bash
kubectl apply -f ../examples/02-postgres-statefulset.yaml

# Wait for postgres-0 to be Ready
kubectl get pod postgres-0 -w
# (Ctrl+C when it shows 1/1 Running)

# Create a table and insert data
kubectl exec -it postgres-0 -- psql -U postgres -c "
  CREATE TABLE k8s_test (id SERIAL PRIMARY KEY, message TEXT);
  INSERT INTO k8s_test (message) VALUES ('Data survives pod restart!');
  SELECT * FROM k8s_test;
"

# Delete the pod (simulates a crash or node rebalance)
kubectl delete pod postgres-0

# Wait for it to come back (StatefulSet recreates it with the same PVC)
kubectl wait --for=condition=Ready pod/postgres-0 --timeout=90s

# Query the table — data must still be there
kubectl exec -it postgres-0 -- psql -U postgres -c "SELECT * FROM k8s_test;"
# → Should return: 1 | Data survives pod restart!
```

**Checkpoint:**
- [ ] Data inserted before pod deletion is still there after restart
- [ ] `kubectl get pvc` shows `pgdata-postgres-0` still exists
- [ ] The pod came back as `postgres-0` (not a new random name)

---

## Exercise 6 — PVCs Survive StatefulSet Deletion

**Goal:** Prove that deleting a StatefulSet does NOT delete its PVCs.

```bash
# postgres-0 should still be running from Exercise 5
kubectl get pvc pgdata-postgres-0

# Delete the entire StatefulSet
kubectl delete statefulset postgres

# Check that PVCs still exist
kubectl get pvc
# pgdata-postgres-0 is still there! (status: Released or Bound)

# The Pod is also gone
kubectl get pods -l app=postgres
# No resources found

# Recreate the StatefulSet — it reattaches to the existing PVC
kubectl apply -f ../examples/02-postgres-statefulset.yaml
kubectl wait --for=condition=Ready pod/postgres-0 --timeout=90s

# The data is STILL there
kubectl exec -it postgres-0 -- psql -U postgres -c "SELECT * FROM k8s_test;"
# → still returns the row from Exercise 5
```

**Checkpoint:**
- [ ] Deleting StatefulSet did NOT delete the PVC
- [ ] Recreating StatefulSet reattached the existing PVC
- [ ] Data was preserved across a full StatefulSet delete+recreate cycle

**Clean up:**
```bash
kubectl delete -f ../examples/02-postgres-statefulset.yaml
kubectl delete pvc pgdata-postgres-0
kubectl delete secret postgres-secret
```

---

## Exercise 7 — Per-Pod DNS with Headless Service

**Goal:** Test DNS resolution and confirm each pod has a unique, addressable hostname.

```bash
kubectl apply -f ../examples/04-headless-dns-demo.yaml
kubectl get pods -l app=dns-demo -w
# (Ctrl+C when all 3 are Running)

# Start a debug pod to run DNS queries from inside the cluster
kubectl run dns-test --image=busybox:1.36 --rm -it -- sh
```

Inside the debug pod:
```sh
# Resolve individual pods — each returns ONE specific IP
nslookup dns-demo-0.dns-demo.default.svc.cluster.local
nslookup dns-demo-1.dns-demo.default.svc.cluster.local
nslookup dns-demo-2.dns-demo.default.svc.cluster.local

# Resolve the headless service — returns ALL pod IPs
nslookup dns-demo.default.svc.cluster.local

# Hit each pod directly by hostname — each returns its own name
wget -qO- http://dns-demo-0.dns-demo.default.svc.cluster.local
wget -qO- http://dns-demo-1.dns-demo.default.svc.cluster.local
wget -qO- http://dns-demo-2.dns-demo.default.svc.cluster.local

exit
```

**Checkpoint:**
- [ ] Each pod has a unique DNS name that resolves to its own IP
- [ ] `dns-demo-0.dns-demo.default.svc.cluster.local` resolves (and others)
- [ ] Resolving the service name returns all pod IPs
- [ ] This is how databases discover their peers by hostname

**Clean up:**
```bash
kubectl delete -f ../examples/04-headless-dns-demo.yaml
```

---

## Checkpoint — Can you answer these?

- [ ] Why can't you use a Deployment for a PostgreSQL primary-replica setup?
- [ ] What three things does a StatefulSet guarantee that a Deployment does not?
- [ ] What is a headless Service and why does a StatefulSet need one?
- [ ] What is the full DNS name for pod `mydb-1` in a StatefulSet with service `mydb` in the `production` namespace?
- [ ] What happens to PVCs when you delete a StatefulSet?
- [ ] In what order do pods start? In what order do they terminate?
- [ ] When would you use `podManagementPolicy: Parallel`?
- [ ] Does a StatefulSet automatically configure database replication for you?

---

**Next topic:** [14 — DaemonSets](../../14-daemonsets/README.md)
