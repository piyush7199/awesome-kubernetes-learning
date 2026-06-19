# Exercises — Namespaces

Work through these in order. You need a running local cluster (Minikube or kind).

---

## Exercise 1: Explore the Default Namespaces

```bash
kubectl get namespaces

# Look inside kube-system — these are Kubernetes' own components
kubectl get pods -n kube-system

# Identify each component:
#   coredns-*         → DNS server for service discovery
#   etcd-*            → the cluster's database (control plane node only)
#   kube-apiserver-*  → the API server
#   kube-scheduler-*  → pod scheduling
#   kube-proxy-*      → iptables routing rules (one per node)
```

Try to find what's in `kube-public`:

```bash
kubectl get configmaps -n kube-public
kubectl get configmap cluster-info -n kube-public -o yaml
# This is the one ConfigMap readable even without authentication
```

---

## Exercise 2: Create Namespaces and Prove Name Isolation

```bash
kubectl apply -f examples/01-namespaces.yaml

kubectl get namespaces
# dev, staging, production should now appear
```

Deploy the same-named service into two different namespaces:

```bash
# Deploy 'api' into dev
kubectl apply -f examples/04-deployment-in-namespace.yaml

# Deploy another 'api' into staging (same name, different namespace)
kubectl apply -f examples/04-deployment-in-namespace.yaml \
  | sed 's/namespace: dev/namespace: staging/' \
  | kubectl apply -f -
```

Or the clean way — apply directly with a patch:

```bash
cat examples/04-deployment-in-namespace.yaml \
  | sed 's/namespace: dev/namespace: staging/g' \
  | kubectl apply -f -
```

Prove both exist independently:

```bash
kubectl get deployments -n dev
kubectl get deployments -n staging
# Both show a deployment named 'api' — no conflict

kubectl get services -n dev
kubectl get services -n staging
# Both show a service named 'api'
```

---

## Exercise 3: The `-n` Flag and Setting a Default Namespace

```bash
# Without -n: looks in the 'default' namespace
kubectl get pods
# Probably empty — we deployed to 'dev', not 'default'

# With -n: correct namespace
kubectl get pods -n dev
# Shows the api pods

# See everything across all namespaces
kubectl get pods -A
# Notice the NAMESPACE column — pods from kube-system, dev, staging all visible

# Set default namespace so you stop typing -n dev
kubectl config set-context --current --namespace=dev

# Verify
kubectl config view --minify | grep namespace

# Now these all target 'dev' without -n:
kubectl get pods
kubectl get services
kubectl describe deployment api

# Override for one command only
kubectl get pods -n staging

# Reset back to default when done
kubectl config set-context --current --namespace=default
```

---

## Exercise 4: Apply a ResourceQuota and Watch It Enforce

```bash
kubectl apply -f examples/02-resource-quota.yaml

# Inspect current usage
kubectl describe resourcequota dev-quota -n dev
```

Now try to deploy a pod **without** resource requests/limits (should be rejected):

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: no-limits-pod
  namespace: dev
spec:
  containers:
    - name: app
      image: nginx:1.25
      # No resources block — will be rejected because ResourceQuota is active
EOF

# Expected error:
# Error from server (Forbidden): pods "no-limits-pod" is forbidden:
# [failed quota: dev-quota: must specify limits.cpu for: app;
#  must specify limits.memory for: app...]
```

Now deploy WITH resource limits — it should work:

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: with-limits-pod
  namespace: dev
spec:
  containers:
    - name: app
      image: nginx:1.25
      resources:
        requests:
          cpu: "100m"
          memory: "64Mi"
        limits:
          cpu: "500m"
          memory: "256Mi"
EOF

kubectl get pod with-limits-pod -n dev
# STATUS: Running

# Check how much quota is now used
kubectl describe resourcequota dev-quota -n dev
# requests.cpu: 100m / 4
# requests.memory: 64Mi / 8Gi
```

---

## Exercise 5: Apply a LimitRange — Auto-inject Defaults

```bash
kubectl apply -f examples/03-limit-range.yaml

kubectl describe limitrange dev-limits -n dev
```

Now try the no-limits pod again — this time LimitRange should auto-inject defaults:

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: auto-limits-pod
  namespace: dev
spec:
  containers:
    - name: app
      image: nginx:1.25
      # Still no resources block — but now LimitRange injects defaults
EOF

kubectl get pod auto-limits-pod -n dev
# STATUS: Running

# Inspect the pod spec — see the injected limits
kubectl get pod auto-limits-pod -n dev -o jsonpath='{.spec.containers[0].resources}'
# {"limits":{"cpu":"500m","memory":"256Mi"},"requests":{"cpu":"100m","memory":"64Mi"}}
# Injected by LimitRange even though we didn't write them!
```

---

## Exercise 6: Cross-Namespace DNS

Prove that services in one namespace are reachable from another using the full DNS name.

```bash
# Make sure both dev and staging have the api service running (from exercise 2)
kubectl get svc -n dev
kubectl get svc -n staging

# Launch a debug pod in 'staging' and call 'api' in 'dev'
kubectl run dns-test \
  --image=curlimages/curl \
  --namespace=staging \
  --rm -it --restart=Never \
  -- sh -c "
    echo '=== Short name (same namespace) ===';
    curl -s --max-time 2 http://api/ && echo OK || echo FAILED;
    echo '=== Cross-namespace name ===';
    curl -s --max-time 2 http://api.dev/ && echo OK || echo FAILED;
    echo '=== Full FQDN ===';
    curl -s --max-time 2 http://api.dev.svc.cluster.local/ && echo OK || echo FAILED;
  "
```

Expected results:
- Short name `api` → reaches `api` in `staging` (same namespace as the test pod)
- `api.dev` → reaches `api` in `dev` (cross-namespace)
- Full FQDN → same as above

---

## Exercise 7: Hit the Object Count Quota Limit

The quota allows max 20 pods in `dev`. Let's see what happens when we hit it.

First check current pod count:

```bash
kubectl describe resourcequota dev-quota -n dev | grep pods
# pods: 2 / 20
```

Scale the deployment to approach the limit:

```bash
kubectl scale deployment api -n dev --replicas=18
kubectl get pods -n dev | wc -l

# Now try to scale beyond the quota
kubectl scale deployment api -n dev --replicas=22
```

Check what happened — the Deployment will try to create pods but some will fail:

```bash
kubectl describe replicaset -n dev | grep -A5 "Warning"
# Events: Warning FailedCreate ... exceeded quota: dev-quota
```

Scale back down:

```bash
kubectl scale deployment api -n dev --replicas=2
```

---

## Cleanup

```bash
kubectl delete -f examples/04-deployment-in-namespace.yaml
kubectl delete pod with-limits-pod auto-limits-pod -n dev 2>/dev/null
kubectl delete namespace dev staging production
# Warning: this deletes EVERYTHING inside those namespaces
```

---

## Checkpoint

- [ ] I know what the four default namespaces are and what each is for
- [ ] I can create namespaces with `kubectl apply` and `kubectl create namespace`
- [ ] I understand that two resources can have the same name in different namespaces
- [ ] I can use `-n <namespace>` and set a default namespace with `kubectl config set-context`
- [ ] I can apply a ResourceQuota and understand what it enforces
- [ ] I know that ResourceQuota requires all pods to have resource limits
- [ ] I understand how LimitRange auto-injects default limits to solve that problem
- [ ] I can call a service in a different namespace using `service.namespace` DNS format
- [ ] I know that namespaces do NOT provide network isolation by default

---

**[← Back to topic](../README.md)** | **[Next: Persistent Volumes →](../../07-persistent-volumes/README.md)**
