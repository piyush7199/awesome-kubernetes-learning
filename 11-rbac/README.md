# 11 — RBAC (Role-Based Access Control)

> **Goal:** Understand how Kubernetes controls who can do what — and how to grant the minimum permissions a user or application needs.

---

## The Problem

Imagine your team has 10 developers, 3 data scientists, and 2 interns. They all have `kubectl` access to the cluster. Without any access control:

- An intern can accidentally `kubectl delete deployment production-api`
- A data scientist's misconfigured script can overwrite Secrets
- A developer in the `payments` team can read Pods in the `healthcare` namespace
- A compromised Pod (running malicious code) can `kubectl get secrets --all-namespaces` and drain all credentials

You need a way to say: **"This person (or Pod) can only do X in namespace Y."**

That's RBAC — Role-Based Access Control.

---

## The Analogy

Think of a **company building with key card access**.

- Different employees have key cards that unlock different doors
- A new intern's card opens: the lobby, the bathroom, their floor — nothing else
- A senior engineer's card opens: all of engineering, the server room, the coffee machine
- A contractor's card opens: only the specific room they're assigned to work in, and only during work hours
- Security (cluster-admin) has a master key that opens everything

In Kubernetes:
- **Key card** = Role (what doors you can open = what operations on what resources)
- **Person** = Subject (a User, Group, or ServiceAccount)
- **Granting the card** = RoleBinding (connecting a person to a role)
- **Floor restriction** = Namespace (the Role only works on that floor)
- **Master key** = ClusterRole + ClusterRoleBinding (works everywhere)

---

## Core Vocabulary

| Term | In one sentence |
|------|-----------------|
| **RBAC** | Role-Based Access Control — permission system built into Kubernetes |
| **Role** | A set of permissions scoped to **one namespace** (can do X to Y in namespace Z) |
| **ClusterRole** | A set of permissions that applies **cluster-wide** (or can be reused in any namespace) |
| **RoleBinding** | Grants a Role (or ClusterRole) to a subject **within one namespace** |
| **ClusterRoleBinding** | Grants a ClusterRole to a subject **across the whole cluster** |
| **Subject** | Who gets the permissions: a User, a Group, or a ServiceAccount |
| **ServiceAccount** | A Kubernetes identity for Pods — not a human, but a process running in a container |
| **Verb** | The operation: `get`, `list`, `watch`, `create`, `update`, `patch`, `delete` |
| **Resource** | What the verb operates on: `pods`, `deployments`, `secrets`, `services`, etc. |

---

## The Four RBAC Objects

Kubernetes RBAC uses exactly four resource types. Understanding how they connect is the whole topic.

```
WHO                  BINDING                WHAT
────                 ───────                ────

User                 RoleBinding     ──►    Role
Group           ──►  (in namespace)  ──►    (in namespace)
ServiceAccount       
                     ClusterRoleBinding ──► ClusterRole
                     (cluster-wide)         (cluster-wide)

CROSS-PATTERN (very common):
User             ──► RoleBinding     ──►    ClusterRole
                     (in namespace)         (rules reused, but scoped to namespace)
```

**The cross-pattern is important:** A ClusterRole defines the rules. A RoleBinding applies those rules only in a specific namespace. This lets you write role rules once and reuse them across many namespaces.

---

## How It Works (Architecture)

Every request to the Kubernetes API server goes through three gates:

```
kubectl delete pod my-pod
       │
       ▼
┌──────────────────────────────────────────────────────┐
│                  API Server                           │
│                                                      │
│  Step 1: Authentication                              │
│  "Who are you?" → verifies your identity             │
│  (certificate, token, OIDC, etc.)                    │
│                                                      │
│  Step 2: Authorization (RBAC)                        │
│  "Are you allowed to do this?"                       │
│  → checks: does any Role/ClusterRole bound to        │
│    this user allow verb=delete on pods?              │
│                                                      │
│  Step 3: Admission Control                           │
│  "Should we allow it given policy?"                  │
│  (resource quotas, webhooks, etc.)                   │
└──────────────────────────────────────────────────────┘
```

RBAC lives entirely in Step 2. If no binding grants the permission, the request is denied with a 403 Forbidden.

**Key rule: RBAC is additive — there are no deny rules.**
You can only grant permissions. If a user has two Roles, they get the union of all permissions from both. You can't say "allow everything except deleting Secrets."

---

## Verbs and Resources

A Role is a list of rules. Each rule says: on these **resources**, these **verbs** are allowed.

### Verbs

| Verb | What it does |
|------|-------------|
| `get` | Read one specific resource |
| `list` | Read all resources of a type |
| `watch` | Stream changes to resources |
| `create` | Create a new resource |
| `update` | Replace an existing resource |
| `patch` | Partially update an existing resource |
| `delete` | Delete a resource |
| `deletecollection` | Delete all resources of a type at once |
| `*` | All verbs (use carefully) |

> **Gotcha:** `list` on Secrets is as powerful as `get` on Secrets — a `list secrets` call returns the full content of every secret. Never grant `list` on Secrets unless you mean to grant full read access to all secrets.

### Common Resources

```
pods                deployments          services
replicasets         statefulsets         daemonsets
jobs                cronjobs             ingresses
configmaps          secrets              persistentvolumeclaims
serviceaccounts     roles                rolebindings
namespaces          nodes                persistentvolumes
```

Resources can also have sub-resources, e.g., `pods/log`, `pods/exec`, `pods/portforward`. These are separate from the main resource — granting access to `pods` does NOT grant access to `pods/exec`.

---

## YAML Walkthrough

### 1. Role (namespace-scoped)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: developer
  namespace: production     # this Role only works in this namespace
rules:
  - apiGroups: [""]         # "" = core API group (pods, services, configmaps, etc.)
    resources: ["pods", "services", "configmaps"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  - apiGroups: ["apps"]     # apps group (deployments, replicasets, etc.)
    resources: ["deployments", "replicasets"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
  # Notably absent: delete, secrets — developers can't delete or read secrets
```

The `apiGroups` field is often confusing. Here's the mapping:

| Resources | apiGroups value |
|-----------|----------------|
| pods, services, configmaps, secrets, namespaces, nodes | `""` (empty string) |
| deployments, replicasets, statefulsets, daemonsets | `"apps"` |
| ingresses | `"networking.k8s.io"` |
| jobs, cronjobs | `"batch"` |
| roles, rolebindings | `"rbac.authorization.k8s.io"` |
| horizontalpodautoscalers | `"autoscaling"` |

### 2. RoleBinding

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: bind-developer-alice
  namespace: production
subjects:
  - kind: User               # can be: User, Group, or ServiceAccount
    name: alice              # the username from their auth credentials
    apiGroup: rbac.authorization.k8s.io
roleRef:                     # which Role to grant
  kind: Role                 # or ClusterRole — for the cross-pattern
  name: developer            # must match an existing Role in this namespace
  apiGroup: rbac.authorization.k8s.io
```

### 3. ClusterRole + ClusterRoleBinding

```yaml
# ClusterRole: read-only access to everything, everywhere
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: read-only
rules:
  - apiGroups: ["*"]         # all API groups
    resources: ["*"]         # all resources
    verbs: ["get", "list", "watch"]  # read-only verbs only
---
# Grant it to the "monitoring" group cluster-wide
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: monitoring-read-only
subjects:
  - kind: Group
    name: monitoring-team    # a group from your OIDC/auth provider
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: read-only
  apiGroup: rbac.authorization.k8s.io
```

### 4. ServiceAccount (for Pods)

Humans use certificates or tokens. Pods use ServiceAccounts.

```yaml
# Create the ServiceAccount
apiVersion: v1
kind: ServiceAccount
metadata:
  name: pod-reader
  namespace: monitoring

---
# Give it permission to list pods across all namespaces
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: pod-reader
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list", "watch"]

---
# Bind the ClusterRole to the ServiceAccount
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: pod-reader-binding
subjects:
  - kind: ServiceAccount
    name: pod-reader
    namespace: monitoring    # ServiceAccount subjects need a namespace
roleRef:
  kind: ClusterRole
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io

---
# Use the ServiceAccount in a Pod
apiVersion: v1
kind: Pod
metadata:
  name: monitor-pod
  namespace: monitoring
spec:
  serviceAccountName: pod-reader  # attaches the identity to this pod
  containers:
    - name: app
      image: bitnami/kubectl:latest
      command: ["kubectl", "get", "pods", "--all-namespaces"]
```

When a Pod runs with a ServiceAccount, Kubernetes automatically mounts a token at `/var/run/secrets/kubernetes.io/serviceaccount/token`. The container can use this token to talk to the API server.

---

## Built-in Roles (Don't Reinvent)

Kubernetes ships with several ClusterRoles you can use directly:

| ClusterRole | What it allows |
|-------------|----------------|
| `view` | Read-only access to most resources (not Secrets) in a namespace |
| `edit` | Read/write most resources (not Roles/Bindings) in a namespace |
| `admin` | Full namespace admin, including Roles/Bindings — but not namespace deletion |
| `cluster-admin` | God mode — everything, everywhere. Use extremely sparingly. |

Use them with a RoleBinding to scope to a namespace:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: dave-can-edit
  namespace: staging
subjects:
  - kind: User
    name: dave
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole     # using a built-in ClusterRole
  name: edit            # scoped to "staging" namespace by RoleBinding
  apiGroup: rbac.authorization.k8s.io
```

---

## Checking Permissions

The most useful debug command in RBAC:

```bash
# Can I delete pods in production?
kubectl auth can-i delete pods -n production

# Can the "alice" user list secrets in production?
kubectl auth can-i list secrets -n production --as=alice

# Can the "monitoring" ServiceAccount in the "monitoring" namespace get pods?
kubectl auth can-i get pods \
  --as=system:serviceaccount:monitoring:pod-reader

# List all what a user can do
kubectl auth can-i --list --as=alice -n production

# Who can delete pods in production? (requires cluster-admin)
kubectl who-can delete pods -n production   # needs rbac-tool plugin
```

---

## Common Mistakes / Gotchas

**1. Wrong `apiGroups` value**
Forgetting that `deployments` is in the `apps` group, not `""`. A rule with `apiGroups: [""]` and `resources: ["deployments"]` grants nothing — the rule silently doesn't apply.

**2. Pods/exec is a separate resource**
`kubectl exec` requires permission on `pods/exec`, not just `pods`. Same for `pods/log` (logs), `pods/portforward`. Getting `pods` permission does NOT include these.

**3. `list` secrets = read all secrets**
A `list secrets` API call returns the full secret data. Don't grant `list` on `secrets` to anyone who shouldn't be able to read every secret in the namespace.

**4. RoleBinding references a non-existent Role**
Kubernetes doesn't validate this at creation time. The binding silently does nothing. Always verify with `kubectl auth can-i` after creating bindings.

**5. Default ServiceAccount**
Every namespace gets a `default` ServiceAccount automatically. By default it has no extra permissions. If your Pod doesn't specify `serviceAccountName`, it uses `default` — which is fine for most apps, but you must explicitly grant permissions if the app needs API access.

**6. ClusterRoleBinding is permanent and cluster-wide**
Accidentally binding someone to `cluster-admin` via ClusterRoleBinding gives them full control over the entire cluster. Use RoleBindings scoped to namespaces unless you truly need cluster-wide access.

**7. Aggregated ClusterRoles**
Some built-in ClusterRoles (like `view`, `edit`, `admin`) are aggregated — they collect rules from smaller ClusterRoles via label selectors. If you create a ClusterRole with label `rbac.authorization.k8s.io/aggregate-to-view: "true"`, its rules automatically get added to the `view` ClusterRole.

---

## Common Questions & Doubts

**But wait — what's a "User" in Kubernetes? I don't see any User objects.**

That's one of the strangest things about K8s RBAC: there is no `User` resource. You can't `kubectl get users`. Users exist only in your authentication system (certificates, OIDC tokens from Google/GitHub, LDAP, etc.). The username in your auth token is what Kubernetes sees as the subject. ServiceAccounts are the exception — they're real Kubernetes objects, which is why Pods can use them without external auth.

**Can I deny someone an action they would otherwise have?**

No. RBAC is purely additive. If a user has two RoleBindings and one grants delete on pods, they can delete pods — period. The other binding can't take it back. The only way to "deny" is to not grant in the first place, or to remove a binding. This is a common point of confusion for people coming from AWS IAM where explicit deny rules exist.

**Why does my app Pod get "forbidden" errors even though it's running fine?**

If your container makes API calls (using a Kubernetes client library, `kubectl`, or direct HTTP to the API server), it uses the Pod's ServiceAccount token. The default ServiceAccount has no permissions. You need to: (1) create a ServiceAccount, (2) bind a Role to it, (3) set `serviceAccountName` in your Pod spec.

**What's the difference between `update` and `patch`?**

`update` replaces the full object (like `kubectl replace`). `patch` modifies part of it (like `kubectl patch`). Most write operations from `kubectl apply` use patch under the hood. Grant both if you want the full write experience.

**Do I need to restart anything when I change a RoleBinding?**

No. RBAC changes take effect immediately for the next API request. There's no cache to flush (the API server checks authorizations live). If a user is mid-session and you revoke their role, the next command they run will fail.

---

## Interview Questions

<details>
<summary>Q: What are the four RBAC resource types in Kubernetes and how do they relate?</summary>

- **Role**: defines allowed verbs on resources, scoped to one namespace.
- **ClusterRole**: same as Role but applies cluster-wide, or can be reused across namespaces.
- **RoleBinding**: grants a Role (or ClusterRole) to a subject within one namespace.
- **ClusterRoleBinding**: grants a ClusterRole to a subject across the entire cluster.

The critical pattern: a ClusterRole + RoleBinding = role rules defined once, applied per-namespace. This avoids duplicating role definitions across every namespace while still scoping access.
</details>

<details>
<summary>Q: What is a ServiceAccount and why would a Pod need one?</summary>

A ServiceAccount is a Kubernetes identity for processes, not humans. When a Pod needs to talk to the Kubernetes API server (e.g., to list other Pods, read ConfigMaps dynamically, or trigger jobs), it authenticates using the ServiceAccount token automatically mounted at `/var/run/secrets/kubernetes.io/serviceaccount/token`. You create a ServiceAccount, bind a Role to it, and reference it in the Pod spec via `serviceAccountName`. Every namespace has a `default` ServiceAccount with no permissions — always create a dedicated one with minimum necessary permissions.
</details>

<details>
<summary>Q: How do you check whether a user or service account has a specific permission?</summary>

```bash
# As yourself
kubectl auth can-i delete pods -n production

# Impersonate another user
kubectl auth can-i list secrets -n production --as=alice

# Impersonate a ServiceAccount
kubectl auth can-i get pods --as=system:serviceaccount:monitoring:pod-reader

# List all permissions for a user
kubectl auth can-i --list --as=alice -n production
```

This is the first thing to run when debugging a "forbidden" error.
</details>

<details>
<summary>Q: What is the difference between Role and ClusterRole?</summary>

A Role is namespace-scoped: it can only grant permissions to resources within the namespace it's defined in. A ClusterRole is cluster-scoped: it can grant permissions to cluster-wide resources (like Nodes, PersistentVolumes, Namespaces themselves) and can be bound across any namespace. However, a ClusterRole bound via a RoleBinding (not ClusterRoleBinding) only applies in the namespace of the binding — this is the common "define once, reuse everywhere" pattern.
</details>

<details>
<summary>Q: Why is granting `list` on Secrets dangerous?</summary>

A `list secrets` API call returns the full contents of every Secret in the namespace — not just names, but the base64-decoded values. Unlike `list pods` where you get metadata, `list secrets` is effectively "read all secrets." So granting `list` secrets gives someone the same power as `get` on every individual secret. Always treat `list secrets` as equivalent to "can read all secrets."
</details>

<details>
<summary>Q: A developer reports "Error from server (Forbidden): pods is forbidden." How do you debug this?</summary>

1. First, confirm what they're trying to do: `kubectl auth can-i get pods -n <namespace> --as=<username>` — if "no", RBAC is the issue.
2. Check which RoleBindings exist for that user in that namespace: `kubectl get rolebindings -n <namespace> -o yaml | grep -A5 username`.
3. Check ClusterRoleBindings too: `kubectl get clusterrolebindings -o yaml | grep -A5 username`.
4. Find the Role/ClusterRole they're bound to and inspect its rules: `kubectl describe role <name> -n <namespace>`.
5. Check `apiGroups` — a common mistake is using `apiGroups: [""]` for resources that are in `apps` or `batch` groups.
6. Fix by creating or updating a RoleBinding, then verify: `kubectl auth can-i get pods -n <namespace> --as=<username>`.
</details>

<details>
<summary>Q: Scenario — A microservice Pod needs to read ConfigMaps in its own namespace and list Pods across all namespaces. What do you create?</summary>

Two bindings:

1. A **Role** in the Pod's namespace granting `get, list, watch` on `configmaps`, bound to a ServiceAccount via **RoleBinding** (namespace-scoped, minimal).
2. A **ClusterRole** granting `get, list, watch` on `pods`, bound to the same ServiceAccount via **ClusterRoleBinding** (needs cluster-scope to span all namespaces).

Never create a ClusterRole with both permissions and a ClusterRoleBinding — that would also grant ConfigMap access in every namespace, violating least privilege. Separate the cluster-scoped need (pod listing) from the namespace-scoped need (configmaps in own namespace).
</details>

<details>
<summary>Q: What does `system:serviceaccount:monitoring:pod-reader` mean?</summary>

It's the fully qualified name of a ServiceAccount subject in RBAC. Format: `system:serviceaccount:<namespace>:<serviceaccount-name>`. This is how you reference a ServiceAccount as a subject in a ClusterRoleBinding: `kind: ServiceAccount, name: pod-reader, namespace: monitoring`. The `system:serviceaccount:` prefix is added by Kubernetes internally to distinguish ServiceAccounts from human users in the authorization layer.
</details>

---

## Summary

| Concept | What to remember |
|---------|-----------------|
| Role | Permissions scoped to one namespace |
| ClusterRole | Permissions cluster-wide (or reusable across namespaces) |
| RoleBinding | Grants a Role/ClusterRole to a subject in one namespace |
| ClusterRoleBinding | Grants a ClusterRole to a subject cluster-wide |
| Subject | User (external), Group (external), ServiceAccount (K8s object) |
| Verb | get, list, watch, create, update, patch, delete |
| apiGroups | `""` for core, `"apps"` for deployments, `"batch"` for jobs |
| ServiceAccount | Pod identity — token auto-mounted at known path |
| RBAC is additive | No deny rules — can only grant, never revoke via a rule |
| `kubectl auth can-i` | The first debugging command for any permission issue |
| pods/exec | Separate from `pods` — exec permission must be granted explicitly |
| Built-ins | view, edit, admin, cluster-admin — use before writing your own |

---

## Exercises

Work through the hands-on tasks in [exercises/README.md](./exercises/README.md).

---

**Previous topic:** [10 — Ingress](../10-ingress/README.md)
**Next topic:** [12 — Helm](../12-helm/README.md)
