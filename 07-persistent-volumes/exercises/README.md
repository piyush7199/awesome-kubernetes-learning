# Exercises — Persistent Volumes

Work through these in order. You need Minikube or kind running.
Minikube has a built-in `standard` StorageClass — dynamic provisioning works out of the box.

---

## Exercise 1: Explore the Default StorageClass

```bash
kubectl get storageclass
# NAME                 PROVISIONER                RECLAIMPOLICY   VOLUMEBINDINGMODE
# standard (default)   k8s.io/minikube-hostpath   Delete          Immediate

kubectl describe storageclass standard
# Note: provisioner, reclaimPolicy, volumeBindingMode
```

**Question:** The StorageClass says `reclaimPolicy: Delete`. What does that mean for your data when you delete a PVC?

<details>
<summary>Answer</summary>

When the PVC is deleted, Kubernetes automatically deletes the PV object AND the underlying storage (the hostPath directory in this case). Your data is gone. In production, use `Retain` for important data so a human must explicitly clean up.

</details>

---

## Exercise 2: Static Provisioning — PV Bound to PVC

```bash
kubectl apply -f examples/02-static-pv-pvc.yaml

# Watch both objects appear
kubectl get pv
kubectl get pvc

# PV should show STATUS=Bound, CLAIM=default/pvc-static-demo
# PVC should show STATUS=Bound, VOLUME=pv-static-demo
```

**Inspect the binding:**

```bash
kubectl describe pv pv-static-demo | grep -A5 "Claim:"
kubectl describe pvc pvc-static-demo | grep -A5 "Volume:"
```

**Break it on purpose — delete the PVC and observe:**

```bash
kubectl delete pvc pvc-static-demo

# PV has reclaimPolicy: Retain — it should still exist
kubectl get pv
# STATUS is now 'Released' — not 'Available'

# Try creating the PVC again — it will NOT rebind automatically
kubectl apply -f examples/02-static-pv-pvc.yaml
kubectl get pvc
# STATUS: Pending — the PV is Released, not Available

# Fix: clear the claimRef on the PV to make it Available again
kubectl patch pv pv-static-demo -p '{"spec":{"claimRef": null}}'
kubectl get pv
# STATUS: Available

kubectl get pvc
# STATUS: Bound — it rebound after the PV became Available again
```

This is the full `Retain` lifecycle — you just did what a production admin does after data recovery.

---

## Exercise 3: Dynamic Provisioning

```bash
kubectl apply -f examples/03-dynamic-pvc.yaml

# Watch the PVC and PV appear together
kubectl get pvc pvc-dynamic-demo
kubectl get pv

# The PV was auto-created by the StorageClass provisioner
# Note the generated PV name — it's a UUID, not a human-chosen name
```

**Compare with static provisioning:**
- Static: admin names the PV, developer must match it
- Dynamic: PV name is generated automatically, developer only writes the PVC

---

## Exercise 4: Prove Data Persists Across Pod Deletion

```bash
# Make sure pvc-dynamic-demo exists (from exercise 3)
kubectl apply -f examples/04-pod-with-pvc.yaml

kubectl get pod data-writer
# Wait until STATUS = Running

# Let it write some data
sleep 15

# Read what was written
kubectl exec data-writer -- cat /data/history.log
# Should show a few timestamped lines

# Now DELETE the pod (simulates a crash or rolling update)
kubectl delete pod data-writer

# Confirm pod is gone
kubectl get pods

# Confirm PVC still exists — data is safe
kubectl get pvc pvc-dynamic-demo
# STATUS: Bound — PVC outlives the pod

# Create a new pod with the same PVC
kubectl apply -f examples/04-pod-with-pvc.yaml

# Wait for it to start
kubectl get pod data-writer -w

# Read the file — previous data is still there!
kubectl exec data-writer -- cat /data/history.log
# Old entries from the deleted pod + new "Pod started at..." line from this pod
```

This is the fundamental proof: **data survives pod deletion when stored on a PVC**.

---

## Exercise 5: Deploy PostgreSQL with Persistent Storage

```bash
kubectl apply -f examples/05-postgres-with-pvc.yaml

# Watch everything come up
kubectl get pvc postgres-data-pvc
kubectl get pods -l app=postgres -w

# Wait until pod is Running, then connect and create data
kubectl exec -it $(kubectl get pod -l app=postgres -o name) \
  -- psql -U admin -d mydb

# Inside psql:
CREATE TABLE users (id SERIAL PRIMARY KEY, name TEXT);
INSERT INTO users (name) VALUES ('Alice'), ('Bob'), ('Carol');
SELECT * FROM users;
# Should show 3 rows
\q
```

Now delete the pod (simulates a crash) and prove the data survived:

```bash
# Delete just the pod — Deployment will recreate it
kubectl delete pod $(kubectl get pod -l app=postgres -o name | sed 's|pod/||')

# Watch the new pod start
kubectl get pods -l app=postgres -w

# Reconnect to the new pod
kubectl exec -it $(kubectl get pod -l app=postgres -o name) \
  -- psql -U admin -d mydb -c "SELECT * FROM users;"

# Output:
#  id | name
# ----+-------
#   1 | Alice
#   2 | Bob
#   3 | Carol
# (3 rows)   ← data survived the pod deletion!
```

---

## Exercise 6: PVC Protection — Try to Delete a PVC in Use

```bash
# data-writer pod is using pvc-dynamic-demo
kubectl get pod data-writer

# Try to delete the PVC while the pod is running
kubectl delete pvc pvc-dynamic-demo

# Check the PVC status
kubectl get pvc pvc-dynamic-demo
# STATUS: Terminating — it's waiting for the pod to finish

# The pod is still running fine — K8s won't pull storage from under it
kubectl exec data-writer -- cat /data/history.log

# Delete the pod — PVC will then complete deletion
kubectl delete pod data-writer

# PVC is now gone
kubectl get pvc
```

**Lesson:** Kubernetes protects running pods from having their storage deleted. The PVC finalizer (`kubernetes.io/pvc-protection`) enforces this.

---

## Exercise 7: Inspect PV/PVC Relationship with jsonpath

```bash
# Re-apply if needed
kubectl apply -f examples/05-postgres-with-pvc.yaml

# Which PV is the PVC bound to?
kubectl get pvc postgres-data-pvc \
  -o jsonpath='{.spec.volumeName}'
echo

# Which PVC is the PV bound to?
PV_NAME=$(kubectl get pvc postgres-data-pvc -o jsonpath='{.spec.volumeName}')
kubectl get pv $PV_NAME \
  -o jsonpath='{.spec.claimRef.name}'
echo

# What is the actual storage size that was provisioned?
kubectl get pv $PV_NAME \
  -o jsonpath='{.spec.capacity.storage}'
echo

# Where is the data physically stored on the Minikube node?
kubectl get pv $PV_NAME \
  -o jsonpath='{.spec.hostPath.path}'
echo
```

---

## Cleanup

```bash
kubectl delete -f examples/05-postgres-with-pvc.yaml
kubectl delete -f examples/04-pod-with-pvc.yaml
kubectl delete -f examples/03-dynamic-pvc.yaml
kubectl delete -f examples/02-static-pv-pvc.yaml 2>/dev/null

# Check for leftover Released PVs
kubectl get pv
# Delete any that remain
kubectl delete pv pv-static-demo 2>/dev/null
```

---

## Checkpoint

- [ ] I understand why container storage is ephemeral and why PVs are needed
- [ ] I know the three layers: PV (actual storage) → PVC (claim) → Pod (consumer)
- [ ] I can describe the difference between static and dynamic provisioning
- [ ] I know all four access modes and which storage types support `ReadWriteMany`
- [ ] I understand `Retain` vs `Delete` reclaim policies and when to use each
- [ ] I know what `WaitForFirstConsumer` does and why it matters for cloud block storage
- [ ] I proved that data on a PVC survives pod deletion (exercise 4)
- [ ] I know that deleting a PVC while a pod uses it puts it in `Terminating` — not instant
- [ ] I understand what a CSI driver is and why it exists

---

**[← Back to topic](../README.md)** | **[Next: Resource Limits →](../../08-resource-limits/README.md)**
