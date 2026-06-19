# 05 — ConfigMaps & Secrets

> **Goal:** Understand why configuration should never live inside a container image, how ConfigMaps and Secrets separate config from code, the two ways to consume them in pods, and the critical difference between Base64 encoding and actual encryption.

---

## The Problem: Config Baked Into the Image

Imagine your app needs a database host, a port number, a feature flag, and a password.
The naive approach:

```python
# hardcoded in your app code
DB_HOST = "prod-db.internal"
DB_PASS = "super-secret-123"
```

Or slightly better — baked into the Docker image:

```dockerfile
ENV DB_HOST=prod-db.internal
ENV DB_PASS=super-secret-123
```

Both approaches have serious problems:

| Problem | What breaks |
|---------|------------|
| Dev vs staging vs prod need different values | You'd need 3 different images for the same app |
| Password rotation | Rebuild the image, re-push, re-deploy — just to change one value |
| Secret in source code | Anyone with repo access sees production passwords |
| Secret in image | Anyone who can pull the image can inspect the layers and read the value |
| Config change requires a new deployment | Even for a tiny flag change |

The **12-Factor App** methodology (the standard for cloud-native apps) says: **store config in the environment, not in the code**. Kubernetes implements this through ConfigMaps and Secrets.

---

## The Analogy: Employee Handbook vs Safe

Think of a company office:

```
Employee Handbook (ConfigMap)
├── Office hours: 9am–6pm
├── Dress code: business casual
├── Canteen location: 3rd floor
└── Support email: help@company.com
    → Printed and available to everyone
    → Non-sensitive, general configuration

Manager's Safe (Secret)
├── System admin passwords
├── Bank account numbers
├── Client NDAs
└── API keys
    → Locked, only authorised staff can open it
    → Sensitive, access-controlled
```

Both live separately from the employees (your app containers). When the canteen moves, you reprint the handbook — you don't rehire all the staff.

---

## Core Vocabulary

| Term | Meaning |
|------|---------|
| **ConfigMap** | A K8s object that stores non-sensitive key-value configuration |
| **Secret** | A K8s object that stores sensitive data (passwords, tokens, certificates) |
| **Base64** | An encoding scheme used to store binary-safe values in Secrets — **not encryption** |
| **env var injection** | Making a ConfigMap/Secret key available as an environment variable inside the container |
| **Volume mount** | Mounting ConfigMap/Secret data as files inside the container filesystem |
| **envFrom** | Injecting ALL keys from a ConfigMap/Secret as env vars at once |
| **Opaque** | The default Secret type — arbitrary key-value pairs |
| **Immutable** | A flag that prevents a ConfigMap/Secret from being modified after creation |
| **Encryption at rest** | Encrypting etcd data so Secrets are not stored in plain text on disk |

---

## ConfigMaps

A ConfigMap stores configuration as plain key-value pairs. The values can be:
- Simple strings (`"production"`, `"8080"`)
- Multi-line text (entire config files, like `nginx.conf` or `application.properties`)

### Creating a ConfigMap

**From a YAML file** (recommended — version-controllable):

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  # simple key-value pairs
  APP_ENV: "production"
  LOG_LEVEL: "info"
  MAX_CONNECTIONS: "100"

  # multi-line value — an entire config file as a single key
  nginx.conf: |
    server {
      listen 80;
      server_name _;
      location / {
        proxy_pass http://backend-service:8080;
      }
    }
```

**From the command line** (quick but not version-controlled):

```bash
# From literal values
kubectl create configmap app-config \
  --from-literal=APP_ENV=production \
  --from-literal=LOG_LEVEL=info

# From an existing file — key = filename, value = file contents
kubectl create configmap nginx-config --from-file=nginx.conf

# From a directory — one key per file in the directory
kubectl create configmap all-configs --from-file=./config-dir/
```

---

## Secrets

A Secret is structurally similar to a ConfigMap but designed for sensitive data.

### The Base64 Misconception (Read This Carefully)

Secrets store values as Base64-encoded strings. People often think this means encrypted. **It does not.**

```bash
echo -n "super-secret-123" | base64
# c3VwZXItc2VjcmV0LTEyMw==

echo -n "c3VwZXItc2VjcmV0LTEyMw==" | base64 --decode
# super-secret-123
```

Anyone with `kubectl get secret` access can decode every Secret in seconds. Base64 is just a way to safely store binary data (like TLS certificates) as text in a YAML file. **It is not a security boundary.**

Real security for Secrets comes from:
1. **RBAC** (topic 11) — controlling which users/apps can `get` or `list` Secrets
2. **Encryption at rest** — encrypting the etcd database so Secrets are not plain text on disk
3. **External secret managers** — Vault, AWS Secrets Manager, GCP Secret Manager (advanced)

### Creating a Secret

**From a YAML file:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
type: Opaque       # default type — arbitrary key-value pairs
data:
  # Values MUST be base64-encoded in the YAML
  username: YWRtaW4=          # echo -n "admin" | base64
  password: c3VwZXItc2VjcmV0   # echo -n "super-secret" | base64
```

Or use `stringData` to write plain text and let Kubernetes encode it:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
type: Opaque
stringData:        # plain text — Kubernetes base64-encodes it automatically on save
  username: admin
  password: super-secret
```

`stringData` is write-only — when you `kubectl get secret -o yaml` later, you'll see `data:` with base64 values, not the original `stringData`.

**From the command line:**

```bash
# Kubernetes base64-encodes the values for you automatically
kubectl create secret generic db-credentials \
  --from-literal=username=admin \
  --from-literal=password=super-secret

# From a file (e.g. a TLS certificate)
kubectl create secret tls my-tls-cert \
  --cert=tls.crt \
  --key=tls.key
```

### Secret Types

| Type | Use case |
|------|---------|
| `Opaque` | Default — arbitrary key-value pairs (passwords, API keys) |
| `kubernetes.io/tls` | TLS certificate and private key (`tls.crt` + `tls.key`) |
| `kubernetes.io/dockerconfigjson` | Docker registry credentials for pulling private images |
| `kubernetes.io/basic-auth` | Username + password (structured) |
| `kubernetes.io/ssh-auth` | SSH private key |
| `kubernetes.io/service-account-token` | Auto-generated token for a ServiceAccount (topic 11) |

---

## Two Ways to Consume ConfigMaps and Secrets in Pods

### Method 1: Environment Variables

Inject specific keys as named env vars.

```yaml
spec:
  containers:
    - name: app
      image: my-app:1.0
      env:
        # From a ConfigMap
        - name: APP_ENV          # env var name inside the container
          valueFrom:
            configMapKeyRef:
              name: app-config   # ConfigMap name
              key: APP_ENV       # key inside the ConfigMap

        # From a Secret
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: password
```

**Inject ALL keys at once with `envFrom`:**

```yaml
      envFrom:
        - configMapRef:
            name: app-config      # every key becomes an env var
        - secretRef:
            name: db-credentials  # every key becomes an env var
```

**Limitation of env vars:** When the ConfigMap or Secret is updated, the **running pod does not see the new values**. The container reads env vars once at startup. To get new values, you must restart the pod (rolling restart via `kubectl rollout restart deployment/<name>`).

---

### Method 2: Volume Mounts (Files)

Mount the ConfigMap or Secret as a directory of files inside the container. Each key becomes a filename, the value becomes the file contents.

```yaml
spec:
  volumes:
    - name: config-vol
      configMap:
        name: app-config          # mount this ConfigMap as files

    - name: secret-vol
      secret:
        secretName: db-credentials  # mount this Secret as files
        defaultMode: 0400           # file permissions: owner read-only (important for keys!)

  containers:
    - name: app
      image: my-app:1.0
      volumeMounts:
        - name: config-vol
          mountPath: /etc/config    # files appear here

        - name: secret-vol
          mountPath: /etc/secrets   # files appear here
          readOnly: true
```

Inside the container:
```
/etc/config/
  APP_ENV          ← contains: "production"
  LOG_LEVEL        ← contains: "info"
  nginx.conf       ← contains the full nginx config

/etc/secrets/
  username         ← contains: "admin"
  password         ← contains: "super-secret"
```

Your app reads `/etc/secrets/password` instead of an env var. This is how many real apps (databases, TLS-aware apps) expect secrets to be delivered.

**The key advantage over env vars:** When a ConfigMap or Secret is updated, Kubernetes automatically updates the mounted files inside running pods — **without a pod restart** (within ~1 minute, controlled by kubelet sync period). Your app can watch for file changes and reload config hot.

---

## Env Var vs Volume Mount — Which to Use?

| | Env Var | Volume Mount |
|-|---------|-------------|
| **Best for** | Simple string values | Config files, certificates, large configs |
| **Auto-updates on change** | No — needs pod restart | Yes — files updated within ~1 minute |
| **Visible in `kubectl describe pod`** | Yes — in the env section (names visible, not values for Secrets) | No — only the volume name is listed |
| **App reads it as** | OS environment variable | Regular file on disk |
| **Risk** | Env vars can be leaked in crash dumps, `ps` output | File permissions can lock down access |
| **Typical use** | `DATABASE_URL`, `LOG_LEVEL`, `APP_ENV` | `nginx.conf`, `tls.crt`, `application.properties` |

---

## Projecting Specific Keys to Specific File Paths

By default, every key becomes a file. You can pick specific keys and rename them:

```yaml
volumes:
  - name: config-vol
    configMap:
      name: app-config
      items:
        - key: nginx.conf        # use only this key
          path: server.conf      # name the file differently inside the container
```

This is useful when your app expects a file at a specific path with a specific name.

---

## Immutable ConfigMaps and Secrets

Once you have a lot of ConfigMaps and Secrets, every change triggers a watch event that all kubelets process. For large clusters, this is noisy.

Mark a ConfigMap or Secret as immutable to:
- Prevent accidental changes
- Stop kubelets from watching it for changes (performance improvement)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: static-config
immutable: true    # cannot be changed after creation — delete and recreate to update
data:
  FEATURE_X: "enabled"
```

Use `immutable: true` for config that should never change (feature flags locked for a release, versioned config snapshots).

---

## Real-World Secret Management (Beyond Basic Secrets)

Plain Kubernetes Secrets are fine for learning and small teams. In production at scale, teams use:

| Tool | How it works |
|------|-------------|
| **Vault** (HashiCorp) | Dedicated secret store. Pods authenticate to Vault and fetch secrets dynamically at runtime. Secrets are never stored in etcd. |
| **External Secrets Operator** | Watches ExternalSecret CRDs, fetches from AWS/GCP/Azure secret stores, creates real K8s Secrets automatically. |
| **AWS Secrets Manager / GCP Secret Manager** | Cloud-native secret stores. Used via External Secrets Operator or SDKs. |
| **Sealed Secrets** | Encrypts a Secret into a `SealedSecret` that can be safely committed to Git. The controller in the cluster decrypts it. |

The standard progression: Kubernetes Secrets with RBAC → Sealed Secrets (for GitOps) → External Secrets Operator (for enterprise scale).

---

## How Kubernetes Stores Secrets Internally

All K8s objects (pods, deployments, secrets) are stored in **etcd**. By default, Secrets in etcd are stored as base64-encoded plain text — anyone who can read etcd directly can read all your Secrets.

**Encryption at rest** encrypts the etcd entries for Secrets. It is not enabled by default — you have to configure it explicitly (or use a managed K8s service that enables it for you, like GKE, EKS, AKS).

```
Without encryption at rest:
etcd stores: {"username": "YWRtaW4=", "password": "c3VwZXItc2VjcmV0"}
→ trivially decodable

With encryption at rest:
etcd stores: {"username": "enc:aescbc:abc123xyz...", ...}
→ useless without the encryption key
```

---

## Essential Commands

```bash
# ConfigMap commands
kubectl get configmaps
kubectl get cm                          # shorthand
kubectl describe cm app-config
kubectl get cm app-config -o yaml       # see the full data

# Secret commands
kubectl get secrets
kubectl describe secret db-credentials  # shows keys but NOT values
kubectl get secret db-credentials -o yaml  # shows base64-encoded values

# Decode a secret value on the fly
kubectl get secret db-credentials \
  -o jsonpath='{.data.password}' | base64 --decode

# Edit a ConfigMap live
kubectl edit cm app-config

# Trigger a rolling restart after updating a ConfigMap (for env var consumers)
kubectl rollout restart deployment/my-app
```

---

## Common Mistakes & Gotchas

### 1. Forgetting to base64-encode values in `data:` (use `stringData:` instead)

```yaml
data:
  password: super-secret    # WRONG — must be base64 encoded
  password: c3VwZXItc2VjcmV0  # correct

# Or avoid the headache entirely:
stringData:
  password: super-secret    # Kubernetes encodes it for you
```

### 2. Expecting env vars to update without a pod restart

If your app reads `DB_HOST` at startup and you change the ConfigMap, the running pods still see the old value. You must run `kubectl rollout restart deployment/<name>` to pick up the change. Volume-mounted files update automatically.

### 3. Checking `kubectl describe pod` and seeing Secret values are hidden

```bash
kubectl describe pod my-app
# ...
# Environment:
#   DB_PASSWORD:  <set to the key 'password' in secret 'db-credentials'>  Optional: false
```

The name of the secret and key is visible but the value is not — this is by design. Use `kubectl get secret ... -o jsonpath ... | base64 --decode` to read values.

### 4. Storing large data in ConfigMaps/Secrets

Both have a **1 MB size limit** per object. For larger config (ML model configs, large certificates), use a PersistentVolume (topic 07) or an object store and reference it.

### 5. A deleted ConfigMap/Secret breaks pods that depend on it

If a pod is configured to mount a ConfigMap that doesn't exist, the pod will stay in `Pending` state (cannot mount volume). If you delete a ConfigMap that running pods already have mounted, the existing mounts keep working — but new pods or pod restarts will fail.

---

## Common Questions & Doubts

### "If Base64 is not encryption, why does Kubernetes use it for Secrets at all?"

Base64 makes it safe to embed arbitrary binary data (like TLS certificates or SSH keys) in YAML files, which are text format. Without encoding, binary data would corrupt the YAML. It also makes the output of `kubectl get secret -o yaml` consistent — all values are the same format regardless of whether they're ASCII passwords or binary cert files.

---

### "Should I commit Secrets to Git?"

Never commit a plain Kubernetes Secret YAML to Git — the base64-encoded values are trivially decodable. Options:
- **Keep them out of Git entirely** and apply them manually (only works for small teams)
- **Use Sealed Secrets** — a tool that encrypts the Secret with a public key so only your cluster can decrypt it. The encrypted file is safe to commit.
- **Use External Secrets Operator** — Secrets live in AWS/GCP/Vault; you commit only the `ExternalSecret` manifest pointing to them.

---

### "Does changing a ConfigMap that's used as an env var update the running container?"

No. Environment variables are injected at container start time and never change during the container's lifetime. Only volume-mounted files are updated automatically. For env vars, you need to restart the pods: `kubectl rollout restart deployment/<name>`.

---

### "What's the difference between `data` and `stringData` in a Secret?"

Both write to the same place. `data` expects base64-encoded values; `stringData` accepts plain text and Kubernetes encodes it for you on save. `stringData` is write-only — when you read the Secret back (`kubectl get secret -o yaml`), you always see `data:` with base64 values. Use `stringData` when writing YAML by hand to avoid encoding mistakes.

---

### "Can two different pods share the same ConfigMap or Secret?"

Yes. A ConfigMap or Secret is a cluster object that any number of pods can reference. This is one of the key benefits — one central place for shared config. If you update the ConfigMap, all pods that mount it as a volume see the new files (within ~1 minute). All pods that use env vars need a rolling restart.

---

## Interview Questions

**Q1. What is a ConfigMap and what problem does it solve?**

<details>
<summary>Show answer</summary>

A ConfigMap stores non-sensitive configuration as key-value pairs, separate from the container image. This solves the problem of baked-in config: without ConfigMaps, you'd need different images for dev/staging/prod, and any config change would require rebuilding and redeploying the image. With ConfigMaps, the same image runs everywhere and config is injected at runtime — either as environment variables or as mounted files.

</details>

---

**Q2. What is the difference between a ConfigMap and a Secret?**

<details>
<summary>Show answer</summary>

Structurally they're nearly identical — both store key-value pairs consumed by pods as env vars or mounted files. The differences:
- **Purpose:** ConfigMap is for non-sensitive config; Secret is for sensitive data (passwords, tokens, certs)
- **Storage:** Secrets are base64-encoded in etcd (and can be encrypted at rest if configured); ConfigMaps are plain text
- **RBAC:** You can give different access permissions — e.g. developers can read ConfigMaps but not Secrets
- **Kubernetes behaviour:** Secrets are not printed in logs, and `kubectl describe` masks their values

</details>

---

**Q3. Is data in a Kubernetes Secret actually encrypted? Explain.**

<details>
<summary>Show answer</summary>

By default, no. Secrets are base64-encoded — which is trivially reversible — and stored as plain text in etcd. Anyone with direct etcd access or `kubectl get secret` permission can read them.

Real encryption requires either:
1. **Encryption at rest** configured on the API server — etcd entries for Secrets are encrypted with AES-CBC or similar before being written to disk. Must be explicitly enabled; not on by default.
2. **External secret management** (Vault, AWS Secrets Manager) where secrets never enter etcd at all.

Base64 is an encoding format for binary safety, not a security mechanism.

</details>

---

**Q4. What are the two ways to consume a ConfigMap or Secret in a pod? What are the trade-offs?**

<details>
<summary>Show answer</summary>

**Environment variables:** `valueFrom.configMapKeyRef` or `secretKeyRef`. Simple to use, app reads them as OS env vars. Downside: values are frozen at container start — updating the ConfigMap does not update running containers. Needs a rolling restart to pick up changes. Also, env vars can leak in crash dumps and process listings.

**Volume mounts:** ConfigMap/Secret keys become files in a mounted directory. Advantage: Kubernetes automatically updates the files when the ConfigMap/Secret changes, within ~1 minute, without pod restart. Best for config files, certificates. Downside: app must read from disk rather than env vars (minor code change if app expects env vars).

</details>

---

**Q5. You update a ConfigMap. Which pods see the new value immediately and which don't?**

<details>
<summary>Show answer</summary>

- **Volume-mounted pods:** see the updated files within ~60 seconds automatically (kubelet syncs the projected files)
- **Env-var pods:** do NOT see the change — environment variables are set at container startup and never change. You must run `kubectl rollout restart deployment/<name>` to restart the pods with the new values.

</details>

---

**Q6. What is `stringData` in a Secret and how does it differ from `data`?**

<details>
<summary>Show answer</summary>

`data` requires values to be base64-encoded. `stringData` accepts plain text and Kubernetes base64-encodes it automatically before storing. Both end up in the same place. `stringData` is write-only — when you `kubectl get secret -o yaml`, you always see the `data` field with base64 values, never `stringData`. Use `stringData` when writing Secret manifests by hand to avoid manual encoding and encoding mistakes.

</details>

---

**Q7. What are the common Secret types and when would you use each?**

<details>
<summary>Show answer</summary>

- `Opaque` (default): arbitrary key-value pairs — passwords, API keys, tokens
- `kubernetes.io/tls`: TLS certificate (`tls.crt`) + private key (`tls.key`) — used by Ingress controllers
- `kubernetes.io/dockerconfigjson`: Docker registry credentials — used to pull images from private registries (referenced by `imagePullSecrets` in pod spec)
- `kubernetes.io/service-account-token`: auto-created token for a ServiceAccount to authenticate with the K8s API
- `kubernetes.io/basic-auth` / `kubernetes.io/ssh-auth`: structured credential types for specific auth patterns

</details>

---

**Q8. How would you handle secrets in a production GitOps workflow?**

<details>
<summary>Show answer</summary>

Plain Kubernetes Secrets cannot be safely committed to Git (base64 is reversible). Three common approaches:

1. **Sealed Secrets** (Bitnami): encrypt the Secret using a public key so only the cluster controller can decrypt it. The encrypted `SealedSecret` manifest is safe to commit.
2. **External Secrets Operator**: store secrets in AWS Secrets Manager, GCP Secret Manager, or HashiCorp Vault. Commit only the `ExternalSecret` manifest (which references the external secret path). The operator syncs the actual value into a K8s Secret automatically.
3. **HashiCorp Vault with Agent Sidecar**: pods authenticate to Vault at runtime; the Vault agent sidecar fetches secrets and writes them to a shared volume. Secrets never touch etcd.

The right choice depends on your cloud provider and compliance requirements.

</details>

---

**Q9. What happens to a pod if you delete a ConfigMap or Secret it depends on?**

<details>
<summary>Show answer</summary>

- **Already-running pods with mounted volumes:** continue working — the files are already on the container's filesystem and K8s doesn't unmount them on deletion. But if the pod restarts, it will fail to start because the mount source is gone.
- **Already-running pods with env vars:** continue working — env vars were captured at startup. Same restart risk as above.
- **New pods:** fail to start in `Pending` state with an error like `secret "x" not found`. The kubelet cannot prepare the container without the referenced ConfigMap/Secret.

Always delete ConfigMaps/Secrets only after the pods that use them are already deleted or updated.

</details>

---

## Summary

| Concept | In one sentence |
|---------|----------------|
| ConfigMap | Stores non-sensitive config as key-value pairs, separate from the container image |
| Secret | Stores sensitive data (passwords, certs, tokens) — base64-encoded, access-controlled |
| Base64 | Encoding format used in Secrets — reversible, NOT encryption |
| Env var injection | Keys injected as OS environment variables at container start — does not auto-update |
| Volume mount | Keys mounted as files — auto-updates within ~1 minute when the object changes |
| `data` | Secret field for base64-encoded values |
| `stringData` | Secret field for plain text — Kubernetes encodes it for you (write-only) |
| `envFrom` | Injects all keys from a ConfigMap or Secret as env vars at once |
| Immutable | Prevents changes after creation, reduces kubelet watch load |
| Encryption at rest | etcd-level encryption so Secrets aren't plain text on disk — not on by default |

---

## Exercises

See [exercises/README.md](./exercises/README.md) for hands-on practice.

---

## Navigation

**[← 04: Services](../04-services/README.md)** | **[06: Namespaces →](../06-namespaces/README.md)**
