# Topic 09 Exercises — Health Checks

Work through these in order. Each builds on the previous.

---

## Exercise 1 — Watch a Liveness Probe in Action

**Goal:** See what happens when a liveness probe passes, then deliberately trigger a failure and watch the container restart.

```bash
# Apply the liveness failure demo
kubectl apply -f ../examples/05-liveness-failure-demo.yaml

# Watch the pod status in one terminal
kubectl get pod liveness-failure-demo -w
```

Wait about 60–90 seconds. You'll see the container restart when the probe fails.

```bash
# In another terminal, watch the events
kubectl describe pod liveness-failure-demo
# Look for lines like:
#   Warning  Unhealthy   Liveness probe failed: cat: /tmp/healthy: No such file or directory
#   Normal   Killing     Container liveness-failure-demo failed liveness probe, will be restarted
```

**Checkpoint:**
- [ ] You saw READY go from `1/1` to `0/1` and back to `1/1` after restart
- [ ] You see `RESTARTS` increment in `kubectl get pod`
- [ ] The Events section shows "Unhealthy" and "Killing" entries

**Clean up:**
```bash
kubectl delete pod liveness-failure-demo
```

---

## Exercise 2 — Readiness Probe Warm-up Window

**Goal:** See how readiness probe keeps a pod out of Service endpoints until it's actually ready.

```bash
# Apply the readiness demo pod
kubectl apply -f ../examples/02-readiness-http.yaml

# Watch the READY column
kubectl get pod readiness-http -w
```

The pod will stay `0/1` for ~15 seconds (probe returns 503), then flip to `1/1`.

```bash
# While it's 0/1, check what kubectl describe says
kubectl describe pod readiness-http
# Look for: Conditions → Ready = False
```

**Checkpoint:**
- [ ] You saw the pod show `0/1` for ~15 seconds despite being Running
- [ ] The pod was NOT killed during this time (liveness is separate from readiness)
- [ ] After ~15 seconds it became `1/1` without any restart

**Clean up:**
```bash
kubectl delete pod readiness-http
```

---

## Exercise 3 — Compare Liveness vs Readiness Failure Outcomes

**Goal:** Prove the key difference: liveness failure → restart; readiness failure → removed from traffic, no restart.

**Step 3a — Liveness failure:**
```bash
kubectl apply -f ../examples/01-liveness-http.yaml

# Exec in and cause a liveness failure by removing the served file
kubectl exec -it liveness-http -- sh
# Inside the container:
rm /usr/share/nginx/html/index.html   # nginx returns 403 → probe fails
exit

# Watch restarts
kubectl get pod liveness-http -w
```

**Step 3b — Readiness failure:**
```bash
# Apply a simple nginx pod with readiness probe
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: readiness-vs-liveness
  labels:
    app: rvl
spec:
  containers:
    - name: nginx
      image: nginx:1.25
      readinessProbe:
        httpGet:
          path: /ready      # this path doesn't exist → 404 → fails
          port: 80
        periodSeconds: 5
        failureThreshold: 2
EOF

# Create a service pointing at it
kubectl expose pod readiness-vs-liveness --port 80 --name rvl-svc

# Watch: pod becomes Running but NOT 1/1 (readiness fails)
kubectl get pod readiness-vs-liveness -w

# Check endpoints — should be empty (pod excluded from traffic)
kubectl get endpoints rvl-svc
```

The pod stays `Running` but RESTARTS stays 0 — that's readiness in action.

**Checkpoint:**
- [ ] In Step 3a, RESTARTS incremented after liveness failure
- [ ] In Step 3b, RESTARTS stayed 0 despite readiness failure
- [ ] Endpoints for `rvl-svc` was empty (pod excluded from traffic)

**Clean up:**
```bash
kubectl delete pod liveness-http readiness-vs-liveness
kubectl delete service rvl-svc
```

---

## Exercise 4 — Exec Probe with a File Check

**Goal:** Use an exec probe to gate readiness on a custom condition.

```bash
kubectl apply -f ../examples/04-exec-and-tcp-probes.yaml

# Watch exec-probe-demo — stays 0/1 for ~10s while /tmp/ready doesn't exist
kubectl get pod exec-probe-demo -w

# Confirm it's not a liveness issue — no restarts
kubectl describe pod exec-probe-demo | grep -E "Restart|Ready|Liveness|Readiness"
```

**Checkpoint:**
- [ ] Pod was `0/1` then `1/1` with no restart
- [ ] Liveness probe also passes after the file exists
- [ ] The exec command `test -f /tmp/ready` gives exit code 0 = success

**Clean up:**
```bash
kubectl delete pod exec-probe-demo tcp-probe-demo
```

---

## Exercise 5 — Startup Probe for a Slow Application

**Goal:** See how startup probe protects slow-starting apps from premature liveness kills.

```bash
# Create a pod that takes 20s to "start"
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: slow-start-demo
spec:
  containers:
    - name: app
      image: busybox:1.36
      command:
        - sh
        - -c
        - |
          echo "Starting up... this takes 20 seconds"
          sleep 20
          echo "Startup done — creating healthy file"
          touch /tmp/started
          echo "Running forever"
          sleep 3600
      startupProbe:
        exec:
          command: ["test", "-f", "/tmp/started"]
        failureThreshold: 10     # 10 * 5s = 50s max startup time
        periodSeconds: 5
      livenessProbe:
        exec:
          command: ["test", "-f", "/tmp/started"]
        periodSeconds: 10
        failureThreshold: 3
EOF

kubectl get pod slow-start-demo -w
```

Observe: the pod stays `Running 0/1` for ~20s (startup probe failing), then becomes `1/1` without any restart.

Now imagine without a startup probe: liveness would fire after `initialDelaySeconds` and restart the pod repeatedly, creating a CrashLoopBackOff for a perfectly healthy but slow app.

**Checkpoint:**
- [ ] Pod took ~20s to become `1/1`
- [ ] RESTARTS stayed 0 throughout
- [ ] kubectl describe shows StartupProbe eventually passing

**Clean up:**
```bash
kubectl delete pod slow-start-demo
```

---

## Exercise 6 — Break the Liveness Rule (Educational)

**Goal:** See the CrashLoopBackOff cascade when liveness checks an external dependency.

This is the **anti-pattern** from the topic. We'll build it deliberately so you recognize it.

```bash
# Simulate: app checks if example.com is reachable in its liveness probe
# (In a real cluster with no internet, or with a bad hostname, this fails)
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: bad-liveness-demo
spec:
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
      livenessProbe:
        exec:
          command:
            - sh
            - -c
            - "wget -q --spider http://this-host-does-not-exist.internal/ && exit 0 || exit 1"
        initialDelaySeconds: 5
        periodSeconds: 10
        failureThreshold: 2
EOF

# Watch the descent into CrashLoopBackOff
kubectl get pod bad-liveness-demo -w
# After ~25-30s you'll see RESTARTS increment, then Back-off
```

The app (`sleep 3600`) is perfectly healthy. The problem is the liveness probe checking something external that fails.

**Correct fix:** move the external check to readiness, not liveness. The app stays running (not restarted) but stops receiving traffic until the external dependency recovers.

**Clean up:**
```bash
kubectl delete pod bad-liveness-demo
```

---

## Exercise 7 — Probes in a Rolling Update

**Goal:** See how readiness probes gate traffic during a rolling update — new pods must pass readiness before old pods are terminated.

```bash
# Apply the full probe deployment
kubectl apply -f ../examples/03-full-probe-config.yaml

# Verify both replicas are Ready
kubectl get pods -l app=web-service

# Trigger a rolling update (change the image tag)
kubectl set image deployment/web-service api=nginx:1.24

# Watch the rollout — new pods must pass readiness before old are removed
kubectl rollout status deployment/web-service

# Confirm no downtime by watching endpoints stay populated
kubectl get endpoints web-service -w &
kubectl rollout status deployment/web-service
```

**Checkpoint:**
- [ ] During the update, endpoints always had at least 1 ready pod
- [ ] The rollout waited for new pods to pass readiness before removing old ones
- [ ] `kubectl rollout status` showed "successfully rolled out"

**Clean up:**
```bash
kubectl delete deployment web-service
kubectl delete service web-service
```

---

## Checkpoint — Can you answer these?

Before moving to the next topic, make sure you can answer:

- [ ] What is the difference between liveness, readiness, and startup probes?
- [ ] What happens when a liveness probe fails? When a readiness probe fails?
- [ ] Why should liveness probes NOT check external dependencies like a database?
- [ ] What are the four probe mechanisms (httpGet, tcpSocket, exec, gRPC)?
- [ ] What does `failureThreshold * periodSeconds` determine for a startup probe?
- [ ] How do probes interact with rolling updates?
- [ ] What does `successThreshold > 1` mean for a readiness probe?

---

**Next topic:** [10 — Ingress](../../10-ingress/README.md)
