# Exercises — Deployments

Work through these in order. You need a running local cluster (Minikube or kind).

---

## Exercise 1: Deploy and Observe the Hierarchy

**Goal:** See the Deployment → ReplicaSet → Pod relationship live.

```bash
kubectl apply -f examples/01-basic-deployment.yaml

# Check all three layers
kubectl get deployments
kubectl get replicasets
kubectl get pods
```

Notice the naming pattern:
```
web-app                        ← Deployment
web-app-7d4b9f6c8              ← ReplicaSet (hash = pod template hash)
web-app-7d4b9f6c8-xk2p4       ← Pod (random suffix added by ReplicaSet)
```

**Question:** Why does the ReplicaSet name include a hash?

<details>
<summary>Answer</summary>

The hash is derived from the pod template spec. When you update the Deployment (e.g. change the image), the new pod template produces a different hash → a new ReplicaSet name. This lets you tell ReplicaSets apart and is what makes rollback work — the old ReplicaSet still exists under its original name.

</details>

---

## Exercise 2: Prove That Pods Self-Heal

```bash
# List the pods and pick one name
kubectl get pods

# Delete it
kubectl delete pod <one-of-the-pod-names>

# Immediately watch what happens
kubectl get pods -w
```

You'll see the deleted pod disappear and a new one take its place within seconds.

**Question:** What is the RESTARTS count on the new pod?

<details>
<summary>Answer</summary>

0. It's a brand new pod, not a restarted one. The old pod is gone; the ReplicaSet created a fresh replacement. The restart counter only increments when a container inside an existing pod crashes and is restarted in place.

</details>

---

## Exercise 3: Scale Up and Down

```bash
# Scale to 6 replicas
kubectl scale deployment web-app --replicas=6
kubectl get pods -w    # watch 3 new pods start

# Scale back to 2
kubectl scale deployment web-app --replicas=2
kubectl get pods -w    # watch 4 pods terminate

# Scale to 0 — all pods gone, but Deployment still exists
kubectl scale deployment web-app --replicas=0
kubectl get pods       # empty
kubectl get deployment web-app   # still there, AVAILABLE = 0
```

Restore to 3 before moving on:

```bash
kubectl scale deployment web-app --replicas=3
```

---

## Exercise 4: Perform a Rolling Update

```bash
# Check current image
kubectl describe deployment web-app | grep Image

# Update the image (triggers a rolling update)
kubectl set image deployment/web-app nginx=nginx:1.26

# Watch the rollout live — press Ctrl+C when done
kubectl rollout status deployment/web-app
kubectl get pods -w
```

While the rollout is in progress, open a second terminal and run:

```bash
kubectl get replicasets
```

You should see **two** ReplicaSets — one scaling up (new version), one scaling down (old version).

<details>
<summary>What to look for</summary>

```
NAME                   DESIRED   CURRENT   READY
web-app-7d4b9f6c8      1         1         1     ← old (scaling down)
web-app-9c5f2a1d7      3         3         3     ← new (scaling up)
```

Once the rollout completes, the old ReplicaSet shows `DESIRED=0` but is kept for rollback.

</details>

---

## Exercise 5: Check Rollout History and Roll Back

```bash
# See what revisions exist
kubectl rollout history deployment/web-app

# Add a meaningful annotation to your current revision
kubectl annotate deployment/web-app \
  kubernetes.io/change-cause="Updated nginx to 1.26"

kubectl rollout history deployment/web-app
# Now the CHANGE-CAUSE column is readable

# Roll back to the previous version
kubectl rollout undo deployment/web-app

# Confirm the image went back to 1.25
kubectl describe deployment web-app | grep Image

# Check which revision you're now on
kubectl rollout history deployment/web-app
```

<details>
<summary>What undo does internally</summary>

Kubernetes didn't re-pull nginx:1.25. It just scaled the old ReplicaSet (the one it kept at 0 replicas) back up, and scaled the current one back down. This is why rollbacks are fast.

</details>

---

## Exercise 6: Tune maxSurge and maxUnavailable

Apply the tuned deployment and perform a live update:

```bash
kubectl apply -f examples/02-rolling-update-deployment.yaml

# Immediately trigger an update
kubectl set image deployment/web-app-tuned nginx=nginx:1.26

# In another terminal, keep watching pod count
kubectl get pods -l app=web-app-tuned -w
```

With `maxUnavailable: 0`, you'll never see the READY count drop below 4 during the update.

Now edit the file to set `maxSurge: 2` and `maxUnavailable: 2`, apply again, and do another update to nginx:1.25. Notice it goes significantly faster (more pods replaced at once).

---

## Exercise 7: Observe the Recreate Strategy

```bash
kubectl apply -f examples/03-recreate-deployment.yaml

# Update the image
kubectl set image deployment/web-app-recreate nginx=nginx:1.26

# Watch what happens to the pods
kubectl get pods -l app=web-app-recreate -w
```

Unlike the rolling update, you will see ALL pods terminate before any new ones start.

**This is the downtime window.** In production, this means requests fail during that gap.

---

## Cleanup

```bash
kubectl delete deployment web-app web-app-tuned web-app-recreate
```

---

## Checkpoint

- [ ] I can create a Deployment with `kubectl apply`
- [ ] I understand the Deployment → ReplicaSet → Pod hierarchy
- [ ] I know that deleting a pod from a Deployment just causes it to be recreated
- [ ] I can perform a rolling update with `kubectl set image` and watch it with `kubectl rollout status`
- [ ] I can roll back with `kubectl rollout undo`
- [ ] I understand what `maxSurge` and `maxUnavailable` control
- [ ] I know the difference between `RollingUpdate` and `Recreate` strategies
- [ ] I understand why `latest` image tag is dangerous in a Deployment

---

**[← Back to topic](../README.md)** | **[Next: Services →](../../04-services/README.md)**
