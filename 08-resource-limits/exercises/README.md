# Exercises — Resource Limits

Work through these in order. Enable metrics-server first:

```bash
# Minikube
minikube addons enable metrics-server

# kind — install separately
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
# For kind, patch to disable TLS:
kubectl patch deployment metrics-server -n kube-system \
  --type='json' \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

# Wait ~60 seconds, then verify:
kubectl top nodes
```

---

## Exercise 1: Deploy with Requests and Limits — Check QoS

```bash
kubectl apply -f examples/01-requests-and-limits.yaml

# See the deployment and pods
kubectl get pods -l app=web-app

# Check QoS class — should be Burstable (requests < limits)
kubectl get pod $(kubectl get pod -l app=web-app -o name | head -1 | cut -d/ -f2) \
  -o jsonpath='{.status.qosClass}'
# Burstable

# Confirm resource spec was applied
kubectl describe pod $(kubectl get pod -l app=web-app -o name | head -1 | cut -d/ -f2) \
  | grep -A8 "Limits\|Requests"
```

---

## Exercise 2: Watch Real Resource Usage with `kubectl top`

```bash
# Node-level view — total usage vs allocatable
kubectl top nodes

# Pod-level view
kubectl top pods

# Per-container breakdown
kubectl top pods --containers

# Compare the numbers against the requests/limits you set:
#   Usage < Request → you over-provisioned requests (wasteful)
#   Usage > Request but < Limit → burstable zone (healthy)
#   Usage approaching Limit → you may OOMKill or throttle soon
```

---

## Exercise 3: Trigger and Observe OOMKill

```bash
kubectl apply -f examples/03-oomkill-demo.yaml

# Watch the pod in real time
kubectl get pod oomkill-demo -w
# You'll see: Pending → Running → OOMKilled → Running → OOMKilled → CrashLoopBackOff

# Once you see OOMKilled, check the exit code
kubectl describe pod oomkill-demo | grep -A8 "Last State"
# Last State: Terminated
#   Reason:    OOMKilled
#   Exit Code: 137       ← 128 + SIGKILL(9) = OOMKill signature

# How many times has it restarted?
kubectl get pod oomkill-demo
# RESTARTS column shows the count
```

**Question:** What exit code do you see and what does 137 mean?

<details>
<summary>Answer</summary>

Exit code 137 = 128 + 9. The `128 +` prefix means the process was killed by a signal. Signal 9 is SIGKILL — the kernel's forceful termination signal, used by the OOM killer. This cannot be caught or ignored by the application — it's instant death. Compare with SIGTERM (15), which applications can handle gracefully.

</details>

```bash
# Clean up
kubectl delete pod oomkill-demo
```

---

## Exercise 4: Observe CPU Throttling (No Kill)

```bash
kubectl apply -f examples/04-cpu-throttle-demo.yaml

# Watch the pod — it stays Running (throttled, not killed)
kubectl get pod cpu-throttle-demo -w

# Confirm it's running after 30 seconds
kubectl get pod cpu-throttle-demo
# STATUS: Running, RESTARTS: 0 — CPU throttle does NOT kill pods

# Check its CPU usage via metrics-server
kubectl top pod cpu-throttle-demo
# CPU will be capped at ~100m (the limit) even though the loop wants 100%+ of a core

# Exec in and time a CPU-intensive task
kubectl exec cpu-throttle-demo -- sh -c "time dd if=/dev/zero of=/dev/null bs=1M count=500"
# The 'real' time will be much higher than 'user' time — throttle overhead
```

**Compare:** If you remove the CPU limit from the YAML and redeploy, the same `dd` command runs significantly faster.

```bash
kubectl delete pod cpu-throttle-demo
```

---

## Exercise 5: Verify QoS Classes

```bash
kubectl apply -f examples/05-besteffort-vs-guaranteed.yaml

# Check QoS of each pod
kubectl get pod besteffort-pod -o jsonpath='{.status.qosClass}'
echo   # newline
# BestEffort

kubectl get pod guaranteed-pod2 -o jsonpath='{.status.qosClass}'
echo
# Guaranteed

# Also check guaranteed-pod from example 02
kubectl apply -f examples/02-guaranteed-qos.yaml
kubectl get pod guaranteed-pod -o jsonpath='{.status.qosClass}'
echo
# Guaranteed
```

Now check what the difference looks like in `describe`:

```bash
kubectl describe pod besteffort-pod | grep -A4 "QoS Class"
kubectl describe pod guaranteed-pod2 | grep -A4 "QoS Class"
```

---

## Exercise 6: Try to Set Limit Lower Than Request

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: invalid-resources
spec:
  containers:
    - name: app
      image: nginx:1.25
      resources:
        requests:
          memory: "512Mi"
        limits:
          memory: "128Mi"   # limit < request — invalid
EOF

# Expected:
# Error from server (BadRequest): ... Invalid value: "128Mi":
# must be greater than or equal to memory request
```

Kubernetes validates this at admission — the pod is never created.

---

## Exercise 7: Watch Scheduling Rejection Due to Requests

This exercise shows that requests affect scheduling, not just runtime.

```bash
# Check your node's allocatable resources
kubectl describe node | grep -A5 "Allocatable:"
# Allocatable:
#   cpu:    2
#   memory: 1930Mi (approximate)

# Create a pod that requests more than the node has
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: oversized-pod
spec:
  containers:
    - name: app
      image: nginx:1.25
      resources:
        requests:
          cpu: "100"       # 100 cores — no node has this
          memory: "500Gi"  # 500 GB — no node has this
EOF

# Pod stays in Pending — no node can fit it
kubectl get pod oversized-pod
# STATUS: Pending

kubectl describe pod oversized-pod | grep -A10 "Events:"
# Events:
#   Warning  FailedScheduling  ...  0/1 nodes are available:
#             1 Insufficient cpu, 1 Insufficient memory.
```

This is the scheduler enforcing requests — it refuses to place a pod that can't fit.

```bash
kubectl delete pod oversized-pod invalid-resources 2>/dev/null
```

---

## Exercise 8: Set Sensible Resources for a Real Deployment

Deploy nginx, generate load, and observe:

```bash
kubectl apply -f examples/01-requests-and-limits.yaml

# Watch resource usage under no load
kubectl top pods -l app=web-app --containers

# Port-forward and generate some traffic
kubectl port-forward deployment/web-app 8080:80 &
for i in $(seq 1 100); do curl -s http://localhost:8080/ > /dev/null; done

# Check usage now
kubectl top pods -l app=web-app --containers

# Is usage well below limits? You might be able to lower limits.
# Is usage near limits? You should raise limits before they OOMKill.
kill %1  # stop port-forward
```

---

## Cleanup

```bash
kubectl delete -f examples/01-requests-and-limits.yaml
kubectl delete -f examples/02-guaranteed-qos.yaml
kubectl delete -f examples/05-besteffort-vs-guaranteed.yaml
kubectl delete pod oomkill-demo cpu-throttle-demo oversized-pod 2>/dev/null
```

---

## Checkpoint

- [ ] I understand that requests are for scheduling, limits are enforced at runtime
- [ ] I know that CPU over-limit = throttling (slow but alive), memory over-limit = OOMKill (restart)
- [ ] I can identify OOMKill from `kubectl describe pod` (exit code 137, reason OOMKilled)
- [ ] I know the three QoS classes and how they're assigned (not set manually)
- [ ] I know Guaranteed is last evicted and BestEffort is first evicted
- [ ] I can use `kubectl top pods --containers` to check live resource usage
- [ ] I know that `Mi` ≠ `M` and `Gi` ≠ `G` (binary vs decimal)
- [ ] I understand why memory limits need more headroom than CPU limits

---

**[← Back to topic](../README.md)** | **[Next: Health Checks →](../../09-health-checks/README.md)**
