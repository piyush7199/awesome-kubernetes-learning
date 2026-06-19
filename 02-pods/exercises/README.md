# Exercises — Pods

Work through these in order. Each one builds on the previous.
You need a running local cluster (Minikube or kind). See the main README if not set up.

---

## Exercise 1: Create and Inspect Your First Pod

**Goal:** Get comfortable creating, observing, and deleting a pod.

```bash
# Apply the simple pod
kubectl apply -f examples/01-simple-pod.yaml

# Watch it come to life
kubectl get pods -w
# Press Ctrl+C when you see STATUS = Running

# Look at the details
kubectl describe pod my-nginx
```

Find these in the `kubectl describe` output:

1. What **Node** is the pod running on?
2. What is the pod's **IP** address?
3. Under **Events** — what steps did Kubernetes go through to start it?

<details>
<summary>What to look for in Events</summary>

You should see a sequence like:
- `Scheduled` — the scheduler picked a node
- `Pulling` — downloading the image from Docker Hub
- `Pulled` — image downloaded
- `Created` — container created
- `Started` — container process running

This tells you the full journey from "you applied YAML" to "container is running".

</details>

---

## Exercise 2: Get Logs and Exec Into the Pod

```bash
# Check nginx started successfully
kubectl logs my-nginx

# Open a shell inside the running container
kubectl exec -it my-nginx -- /bin/bash

# Inside the container, try:
nginx -v          # nginx version
cat /etc/nginx/nginx.conf   # the default nginx config
exit              # leave the shell
```

**Try this:** Curl nginx from inside another pod:

```bash
# Get the pod IP
kubectl get pod my-nginx -o wide

# Start a temporary debug pod and curl nginx
kubectl run curl-test --image=curlimages/curl --rm -it --restart=Never \
  -- curl http://<MY-NGINX-IP>:80
```

Replace `<MY-NGINX-IP>` with the IP you found above.

<details>
<summary>Expected output</summary>

You should see the default nginx HTML welcome page printed in your terminal.
This confirms the pod is reachable from within the cluster network.

</details>

---

## Exercise 3: Watch a Pod Crash and Restart

Let's intentionally make a pod crash to see `CrashLoopBackOff` in action.

```bash
# Create a pod that immediately exits with an error
kubectl run crasher \
  --image=busybox \
  --restart=Always \
  -- sh -c "echo 'I am crashing'; exit 1"

# Watch what happens
kubectl get pods -w
# You'll see: Error → CrashLoopBackOff
# Press Ctrl+C after you've seen it

# Read the crash logs
kubectl logs crasher

# See how many times it restarted
kubectl get pod crasher

# Read the events
kubectl describe pod crasher
```

**Questions:**
1. What exit code do you see in `kubectl describe pod crasher`?
2. How long does Kubernetes wait before each restart attempt?

<details>
<summary>Answers</summary>

1. Exit code `1` — the non-zero exit is what triggers the restart (with `restartPolicy: Always`).
2. The backoff starts at 10 seconds and doubles each time: 10s, 20s, 40s, 80s, 160s, then caps at 300s (5 minutes). You can see the delay increasing in the Events section.

</details>

```bash
# Clean up
kubectl delete pod crasher
```

---

## Exercise 4: Try the Restart Policy Pod

```bash
kubectl apply -f examples/03-restart-policy-pod.yaml

# Watch it complete
kubectl get pods -w
# It should go: Pending → Running → Completed (not restarted)

kubectl logs one-shot-job
# Should print: "Job done!"

kubectl get pod one-shot-job
# STATUS = Completed, RESTARTS = 0
```

Now modify the YAML: change `exit 0` to `exit 1` and change `restartPolicy` to `Never`.
Apply it (you'll need to delete first since pods are mostly immutable):

```bash
kubectl delete pod one-shot-job
kubectl apply -f examples/03-restart-policy-pod.yaml
kubectl get pod one-shot-job
# STATUS = Error — it failed and was NOT restarted
```

---

## Exercise 5: The Sidecar Pod

```bash
kubectl apply -f examples/02-sidecar-pod.yaml

kubectl get pods
# The READY column shows 2/2 — two containers running

# Check the log-shipper sidecar's output
kubectl logs web-with-logger -c log-shipper

# Generate some nginx traffic to see access log entries:
WEB_IP=$(kubectl get pod web-with-logger -o jsonpath='{.status.podIP}')
kubectl run traffic --image=curlimages/curl --rm -it --restart=Never \
  -- sh -c "for i in 1 2 3 4 5; do curl -s http://$WEB_IP/; done"

# Now check the log-shipper again
kubectl logs web-with-logger -c log-shipper
# You should see 5 GET / entries in the nginx access log
```

<details>
<summary>Hint: the -c flag</summary>

When a pod has multiple containers, `kubectl logs` and `kubectl exec` need `-c <container-name>` to know which container to target. Without it, kubectl picks the first one (and prints a warning if there are multiple).

</details>

---

## Exercise 6: Explore the Immutability Limit

Try to change the image of the running nginx pod:

```bash
kubectl get pod my-nginx -o yaml | grep image:
# Shows: image: nginx:1.25

# Try patching it
kubectl patch pod my-nginx -p '{"spec":{"containers":[{"name":"nginx","image":"nginx:1.26"}]}}'
```

<details>
<summary>What happens?</summary>

You'll get an error like:
```
The Pod "my-nginx" is invalid: spec: Forbidden: pod updates may not change fields...
```

Most fields in a pod spec are immutable once the pod is running.
This is one of the reasons you use **Deployments** (topic 03) — they handle updates by deleting and recreating pods for you.

</details>

---

## Cleanup

```bash
kubectl delete pod my-nginx web-with-logger one-shot-job
# Or delete everything you created:
kubectl delete pods --all
```

---

## Checkpoint

Before moving to topic 03, make sure you can answer yes to all of these:

- [ ] I can create a pod with `kubectl apply -f`
- [ ] I can read pod logs with `kubectl logs`
- [ ] I can open a shell inside a running container with `kubectl exec -it`
- [ ] I understand what `CrashLoopBackOff` means and how to debug it
- [ ] I know why running bare pods in production is risky
- [ ] I understand what a sidecar container is and why it shares `localhost` with the main container
- [ ] I know the difference between a container restart and a pod being recreated

---

**[← Back to topic](../README.md)** | **[Next: Deployments →](../../03-deployments/README.md)**
