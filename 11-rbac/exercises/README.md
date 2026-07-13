# Topic 11 Exercises — RBAC

Work through these in order. You'll create roles, test permissions, break things, and fix them.

---

## Exercise 1 — Explore Existing RBAC in Your Cluster

**Goal:** Understand what RBAC resources already exist before writing any.

```bash
# What ClusterRoles come built-in?
kubectl get clusterroles | grep -v "system:"
# You'll see: admin, cluster-admin, edit, view, and others

# Inspect the built-in "view" ClusterRole — what can it do?
kubectl describe clusterrole view
# Notice: no Secrets, no Role/RoleBinding management

# What about "edit"?
kubectl describe clusterrole edit
# Can modify most things but not Roles/RoleBindings (can't escalate)

# What ClusterRoleBindings exist?
kubectl get clusterrolebindings | head -20

# What's in the default namespace for roles?
kubectl get roles,rolebindings -n default
# Probably empty on a fresh cluster
```

<details>
<summary>Why does "edit" not allow managing Roles?</summary>

If a user with `edit` could also create/update Roles and RoleBindings, they could grant themselves any permission — including `cluster-admin`. Kubernetes prevents this privilege escalation by design: you can never grant a Role that has permissions beyond your own.
</details>

---

## Exercise 2 — Create a Role and Test Permissions

**Goal:** Grant a user specific permissions and verify with `kubectl auth can-i`.

```bash
# Apply the developer role
kubectl apply -f ../examples/01-role-and-rolebinding.yaml

# Create a test deployment for alice to see
kubectl create deployment test-app --image=nginx:1.25 -n development

# Test: what can alice do?
kubectl auth can-i get pods -n development --as=alice
# → yes

kubectl auth can-i list deployments -n development --as=alice
# → yes

kubectl auth can-i exec pods -n development --as=alice
# → yes (pods/exec was explicitly granted)

kubectl auth can-i delete pods -n development --as=alice
# → no (delete was not granted)

kubectl auth can-i get secrets -n development --as=alice
# → no (secrets was not granted)

kubectl auth can-i get pods -n default --as=alice
# → no (wrong namespace — Role is scoped to "development")
```

Now list ALL permissions alice has in development:
```bash
kubectl auth can-i --list --as=alice -n development
# Shows every verb/resource combination that is allowed
```

**Checkpoint:**
- [ ] `get pods` in `development` → yes
- [ ] `delete pods` in `development` → no
- [ ] `get pods` in `default` → no (namespace scoping works)
- [ ] The `--list` flag shows all allowed permissions

**Clean up:**
```bash
kubectl delete -f ../examples/01-role-and-rolebinding.yaml
kubectl delete deployment test-app -n development 2>/dev/null || true
```

---

## Exercise 3 — ServiceAccount with API Access

**Goal:** Run a Pod that can call the Kubernetes API using its ServiceAccount.

```bash
kubectl apply -f ../examples/03-serviceaccount-rbac.yaml

# Wait for the pod
kubectl get pod pod-monitor -n monitoring -w

# Once Running, check the logs
kubectl logs pod-monitor -n monitoring
# Should show: pods from all namespaces, then a Forbidden error for secrets
```

Now exec in and make API calls manually:
```bash
kubectl exec -n monitoring pod-monitor -- kubectl get pods --all-namespaces

# This should fail:
kubectl exec -n monitoring pod-monitor -- kubectl get secrets --all-namespaces
# Error from server (Forbidden): secrets is forbidden

# This should also fail (different verb):
kubectl exec -n monitoring pod-monitor -- kubectl delete pod pod-monitor -n monitoring
# Error from server (Forbidden): pods "pod-monitor" is forbidden
```

Look at the mounted token:
```bash
kubectl exec -n monitoring pod-monitor -- ls /var/run/secrets/kubernetes.io/serviceaccount/
# ca.crt  namespace  token
# These are what kubectl uses to authenticate to the API server
```

**Checkpoint:**
- [ ] Pod can list pods across all namespaces
- [ ] Pod cannot get secrets (Forbidden)
- [ ] The token is mounted automatically at the known path

**Clean up:**
```bash
kubectl delete -f ../examples/03-serviceaccount-rbac.yaml
```

---

## Exercise 4 — Hit a Permission Denied Error Deliberately

**Goal:** Create a pod with no ServiceAccount permissions and watch it fail.

```bash
# Create a namespace and a pod that tries to list other pods
kubectl create namespace no-perms

kubectl apply -f - <<'EOF'
apiVersion: v1
kind: ServiceAccount
metadata:
  name: empty-sa
  namespace: no-perms
---
apiVersion: v1
kind: Pod
metadata:
  name: forbidden-demo
  namespace: no-perms
spec:
  serviceAccountName: empty-sa   # no roles bound to this SA
  containers:
    - name: kubectl
      image: bitnami/kubectl:latest
      command:
        - sh
        - -c
        - |
          echo "Trying to list pods..."
          kubectl get pods -n no-perms 2>&1 || true
          echo ""
          echo "Trying to get configmaps..."
          kubectl get configmaps -n no-perms 2>&1 || true
          sleep 3600
EOF

kubectl logs -n no-perms forbidden-demo
# Both commands: Error from server (Forbidden)
```

Now fix it by granting the `view` ClusterRole:
```bash
kubectl create rolebinding fix-perms \
  --clusterrole=view \
  --serviceaccount=no-perms:empty-sa \
  -n no-perms

# Try again — should work now
kubectl exec -n no-perms forbidden-demo -- kubectl get pods -n no-perms
```

**Checkpoint:**
- [ ] Pod with no role binding → Forbidden errors
- [ ] Adding a RoleBinding takes effect immediately (no restart needed)
- [ ] Pod can now read resources after the binding is created

**Clean up:**
```bash
kubectl delete namespace no-perms
```

---

## Exercise 5 — The `resourceNames` Restriction

**Goal:** Limit access to a specific named resource, not all resources of that type.

```bash
kubectl create namespace secrets-test

# Create two secrets
kubectl create secret generic app-secret --from-literal=key=value -n secrets-test
kubectl create secret generic other-secret --from-literal=other=data -n secrets-test

# Create a ServiceAccount that can only read "app-secret"
kubectl create serviceaccount limited-sa -n secrets-test

kubectl apply -f - <<'EOF'
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: specific-secret-reader
  namespace: secrets-test
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["app-secret"]   # only this specific secret
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: limited-sa-binding
  namespace: secrets-test
subjects:
  - kind: ServiceAccount
    name: limited-sa
    namespace: secrets-test
roleRef:
  kind: Role
  name: specific-secret-reader
  apiGroup: rbac.authorization.k8s.io
EOF

# Test: can access app-secret
kubectl auth can-i get secret app-secret \
  --as=system:serviceaccount:secrets-test:limited-sa \
  -n secrets-test
# → yes

# Cannot access other-secret
kubectl auth can-i get secret other-secret \
  --as=system:serviceaccount:secrets-test:limited-sa \
  -n secrets-test
# → no

# Gotcha: cannot LIST secrets even with access to one
kubectl auth can-i list secrets \
  --as=system:serviceaccount:secrets-test:limited-sa \
  -n secrets-test
# → no (list is different from get on specific names)
```

**Checkpoint:**
- [ ] `get app-secret` → yes
- [ ] `get other-secret` → no (resourceNames restriction works)
- [ ] `list secrets` → no (list is not the same as get on a named resource)

**Clean up:**
```bash
kubectl delete namespace secrets-test
```

---

## Exercise 6 — Namespace Admin Pattern

**Goal:** Give a team full admin over their namespace, zero access to other namespaces.

```bash
kubectl apply -f ../examples/04-namespace-admin.yaml

# team-alpha-lead can do anything in team-alpha
kubectl auth can-i delete pods -n team-alpha --as=team-alpha-lead
# → yes

kubectl auth can-i create rolebindings -n team-alpha --as=team-alpha-lead
# → yes (admin includes managing roles within the namespace)

# But not in team-beta
kubectl auth can-i get pods -n team-beta --as=team-alpha-lead
# → no

# And not cluster-level resources
kubectl auth can-i delete namespaces --as=team-alpha-lead
# → no (built-in "admin" ClusterRole deliberately excludes namespace deletion)

kubectl auth can-i get nodes --as=team-alpha-lead
# → no (nodes are cluster-scoped, not namespace-scoped)
```

**Checkpoint:**
- [ ] Full admin in own namespace
- [ ] Zero access in another team's namespace
- [ ] Cannot delete the namespace itself (safety guard)
- [ ] Cannot access cluster-level resources like nodes

**Clean up:**
```bash
kubectl delete -f ../examples/04-namespace-admin.yaml
```

---

## Checkpoint — Can you answer these?

- [ ] What is the difference between a Role and a ClusterRole?
- [ ] What is the difference between a RoleBinding and a ClusterRoleBinding?
- [ ] What command do you run first when debugging a Forbidden error?
- [ ] Why is `list secrets` as dangerous as `get secret <name>`?
- [ ] What are the four built-in ClusterRoles and what does each allow?
- [ ] When would you use `ClusterRole + RoleBinding` instead of `ClusterRole + ClusterRoleBinding`?
- [ ] Does a Pod automatically have API access? What does it need?
- [ ] Can you deny a permission in RBAC?

---

**Next topic:** [12 — Helm](../../12-helm/README.md)
