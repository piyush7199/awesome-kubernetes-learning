# 12 — Helm

> **Goal:** Understand what Helm is, why it exists, and how to install, upgrade, and build charts to package Kubernetes applications.

---

## The Problem

By now you know that deploying an app to Kubernetes means writing YAML. A real production app might need:

- A Deployment
- A Service
- An Ingress
- A ConfigMap
- A Secret
- A HorizontalPodAutoscaler
- A ServiceAccount + Role + RoleBinding

That's 7 YAML files just for one app. Now imagine:
- You deploy the same app to `dev`, `staging`, and `production` — with slightly different image tags, replica counts, and resource limits in each environment
- A new version comes out — you update 3 files by hand, miss a field in one, and production gets a config mismatch
- A colleague joins the team and asks "how do I deploy this?" — you hand them 7 files with no instructions

You need a way to:
1. **Template** the YAML (fill in environment-specific values)
2. **Version** a full deployment (rollback if something breaks)
3. **Share** an app package others can install in one command

That's what Helm does.

---

## The Analogy

Helm is the **package manager for Kubernetes** — like `apt` for Ubuntu, `brew` for Mac, or `npm` for Node.js.

| Concept | Package Manager Equivalent |
|---------|---------------------------|
| **Chart** | A package (like a `.deb` file or npm package) |
| **Release** | An installed instance of a package |
| **Repository** | A registry of available packages (like npmjs.com) |
| **values.yaml** | Default configuration (like a config file) |
| **`helm install`** | `apt install` / `npm install` |
| **`helm upgrade`** | `apt upgrade` / `npm update` |
| **`helm rollback`** | Restore a previous version |

When you run `helm install nginx-ingress ingress-nginx/ingress-nginx`, Helm downloads the chart, applies your configuration, and deploys all the Kubernetes resources in one shot — the same way `apt install nginx` downloads and configures nginx.

---

## Core Vocabulary

| Term | In one sentence |
|------|-----------------|
| **Chart** | A directory of templates and metadata that describes a Kubernetes application |
| **Release** | A specific installed instance of a Chart — you can install the same Chart multiple times with different names |
| **Repository** | A web server hosting a collection of Charts (like Artifact Hub) |
| **Values** | The configuration you pass in to customize a Chart's templates |
| **`values.yaml`** | The file inside a Chart that holds default values |
| **Template** | A YAML file with Go template syntax (`{{ }}`) for variable substitution |
| **Revision** | Each `helm upgrade` creates a new revision number — Helm stores the history |
| **`_helpers.tpl`** | A template file for reusable named templates (not rendered to YAML directly) |
| **Lint** | `helm lint` — validates a chart for syntax and structure errors |
| **Dry run** | `helm template` or `helm install --dry-run` — render YAML without applying it |

---

## How Helm Works

```
You run:
  helm install myapp ./myapp-chart --set image.tag=v2.0

             │
             ▼
     ┌───────────────────┐
     │  Helm CLI         │
     │                   │
     │  1. Reads Chart   │   reads templates/*.yaml + values.yaml
     │  2. Merges values │   your --set overrides the defaults
     │  3. Renders YAML  │   {{ .Values.image.tag }} → "v2.0"
     │  4. kubectl apply │   sends final YAML to the API server
     │  5. Saves history │   stores rendered manifests in a Secret
     └───────────────────┘
             │
             ▼
       Kubernetes API Server
       (creates the actual resources)
```

Release history is stored as Secrets in the namespace with names like `sh.helm.release.v1.myapp.v1`. This is how `helm rollback` works — it retrieves the old rendered manifests from a previous revision Secret and re-applies them.

---

## Chart Structure

```
myapp-chart/
├── Chart.yaml              ← metadata: name, version, description
├── values.yaml             ← default configuration values
├── templates/              ← Go-templated Kubernetes YAML
│   ├── _helpers.tpl        ← named template helpers (not output directly)
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── NOTES.txt           ← printed to user after helm install (optional)
└── charts/                 ← sub-charts (dependencies)
```

Every file in `templates/` that doesn't start with `_` is rendered and applied. Files starting with `_` (like `_helpers.tpl`) are helper libraries — not applied directly.

---

## Chart.yaml

The required metadata file for every chart:

```yaml
apiVersion: v2             # always v2 for Helm 3
name: myapp                # chart name (used in release names)
description: A simple web application
type: application          # "application" (runnable) or "library" (shared templates)
version: 0.1.0             # chart version — increment with each chart change
appVersion: "1.0.0"        # the version of the app being packaged (informational)
```

- **`version`** is the chart's own version — bump it every time you change the chart
- **`appVersion`** is the application version inside the chart — changes when the app changes

---

## Go Templating Basics

Helm templates use Go's `text/template` syntax. You only need a few patterns to start:

### Variable substitution
```yaml
image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
```

### Built-in objects
```yaml
# .Release — info about the current release
name: {{ .Release.Name }}-deployment
namespace: {{ .Release.Namespace }}

# .Chart — info from Chart.yaml
app.kubernetes.io/version: {{ .Chart.AppVersion }}

# .Values — everything from values.yaml (+ your overrides)
replicas: {{ .Values.replicaCount }}
```

### Conditionals
```yaml
{{- if .Values.ingress.enabled }}
# only renders this block if ingress.enabled is true
apiVersion: networking.k8s.io/v1
kind: Ingress
...
{{- end }}
```

### Default values
```yaml
replicas: {{ .Values.replicaCount | default 1 }}
```

### Named templates (from `_helpers.tpl`)
```yaml
# In _helpers.tpl:
{{- define "myapp.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

# In deployment.yaml:
labels:
  {{- include "myapp.labels" . | nindent 4 }}
```

The `{{-` and `-}}` trim whitespace. `nindent 4` adds indentation (4 spaces).

---

## Common Helm Commands

### Working with repositories
```bash
# Add a repo
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add bitnami https://charts.bitnami.com/bitnami

# Update repo index (like apt-get update)
helm repo update

# Search for charts
helm search repo nginx
helm search repo postgres
```

### Installing and managing releases
```bash
# Install a chart
helm install my-release ./myapp-chart

# Install with value overrides
helm install my-release ./myapp-chart \
  --set image.tag=v2.0 \
  --set replicaCount=3

# Install with a custom values file
helm install my-release ./myapp-chart -f production-values.yaml

# Install from a repo
helm install my-nginx ingress-nginx/ingress-nginx

# Upgrade (apply changes)
helm upgrade my-release ./myapp-chart --set image.tag=v2.1

# Install OR upgrade in one command (idempotent — great for CI/CD)
helm upgrade --install my-release ./myapp-chart -f production-values.yaml

# List all releases
helm list
helm list -A   # all namespaces

# Check a release's status and last deployed resources
helm status my-release

# See release history (all revisions)
helm history my-release
```

### Rollback
```bash
# Roll back to the previous revision
helm rollback my-release

# Roll back to a specific revision number
helm rollback my-release 2

# See what's in a revision before rolling back
helm history my-release
```

### Debugging (render without applying)
```bash
# Render the templates to stdout — see exactly what will be applied
helm template my-release ./myapp-chart

# Dry-run against the cluster (validates against live API)
helm install my-release ./myapp-chart --dry-run

# Lint a chart for errors
helm lint ./myapp-chart

# Get the values currently in use for a release
helm get values my-release

# Get all rendered YAML for a deployed release
helm get manifest my-release
```

### Uninstall
```bash
# Remove all resources and the release history
helm uninstall my-release

# Remove resources but keep history (for audit)
helm uninstall my-release --keep-history
```

---

## Value Override Precedence

You can override values at multiple layers. Later layers win:

```
1. values.yaml (Chart defaults)          ← lowest priority
2. -f myvalues.yaml                      ← overrides chart defaults
3. -f prod-values.yaml                   ← overrides previous -f
4. --set image.tag=v2.0                  ← highest priority, overrides everything
```

Multiple `-f` flags are common in production:
```bash
helm upgrade --install myapp ./chart \
  -f values.yaml          \   # base config
  -f environments/prod.yaml\  # prod-specific overrides
  --set image.tag=$CI_SHA     # injected by CI pipeline
```

---

## A Complete Chart Example

The full working chart is in `examples/myapp-chart/`. Here's the key values file and what it controls:

```yaml
# values.yaml
replicaCount: 1

image:
  repository: nginx
  tag: "1.25"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: false        # set to true to deploy an Ingress
  host: myapp.example.com

resources:
  requests:
    cpu: 100m
    memory: 64Mi
  limits:
    cpu: 300m
    memory: 128Mi

autoscaling:
  enabled: false
  minReplicas: 1
  maxReplicas: 5
  targetCPUPercent: 70
```

To deploy with defaults:
```bash
helm install myapp ./examples/myapp-chart
```

To deploy for production:
```bash
helm install myapp ./examples/myapp-chart \
  --set replicaCount=3 \
  --set image.tag=v2.0 \
  --set ingress.enabled=true \
  --set ingress.host=myapp.example.com
```

---

## Using Public Charts (Real-World)

You almost never start from scratch. Most popular software has a maintained Helm chart:

```bash
# Install nginx-ingress controller
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace

# Install PostgreSQL
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install my-postgres bitnami/postgresql \
  --set auth.postgresPassword=secretpassword

# Install Prometheus + Grafana monitoring stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace
```

Explore available charts at: **https://artifacthub.io**

---

## Common Mistakes / Gotchas

**1. Deleting Helm Secrets breaks rollback**
Helm stores release history as Secrets named `sh.helm.release.v1.<release>.v<N>`. If you `kubectl delete secret` them manually, `helm history` and `helm rollback` break. Never delete these manually.

**2. `helm upgrade` without `--install` fails on first deploy**
If the release doesn't exist yet, `helm upgrade` errors. Use `helm upgrade --install` in CI/CD pipelines so it works whether the release exists or not.

**3. Template syntax errors only show at render time**
`helm lint` catches most issues, but some errors only appear when you run `helm template` or `helm install --dry-run`. Always lint and dry-run before applying.

**4. `{{ .Values.someKey }}` vs `{{ .Values.someKey | default "" }}`**
If a value is not defined in values.yaml and not passed via `--set`, the template errors with "nil pointer" or renders as `<no value>`. Use `| default "fallback"` for optional values.

**5. Upgrading doesn't delete removed resources**
If you remove a template file in a chart upgrade, Helm does not delete the previously created resource — it just stops managing it. You must manually delete resources that are no longer in the chart.

**6. CRDs and ordering**
Custom Resource Definitions (CRDs — topic 18) must exist before resources that use them. Helm installs CRDs from a `crds/` directory before templates, but ordering within templates is not guaranteed. Use Helm hooks for complex ordering.

**7. `helm uninstall` removes everything**
Including PersistentVolumeClaims if they were created by the chart. Data is gone. Always check before uninstalling stateful applications.

---

## Common Questions & Doubts

**Do I need Helm? Can't I just use `kubectl apply -f`?**

For a single small app, plain YAML works fine. Helm becomes worth it when you have: (a) multiple environments with different configs, (b) multiple people deploying the same stack, (c) a need for versioned rollbacks, or (d) software others need to install easily. Many teams start with plain YAML and adopt Helm when the complexity grows. There's no rule saying you must use it.

**What's the difference between chart version and appVersion?**

`version` in Chart.yaml is the chart's own version — it tracks changes to the templates, values, or chart structure itself. `appVersion` is the version of the software being packaged (e.g., nginx `1.25.3`). Changing only `appVersion` without changing `version` is technically allowed but considered bad practice — bump both together.

**Can I install the same chart twice in the same cluster?**

Yes — that's the whole point of Releases. `helm install frontend ./myapp-chart` and `helm install backend ./myapp-chart` creates two independent releases with different names, different resource names (because `{{ .Release.Name }}` differs), and independent histories. This is useful for running staging and production in the same cluster using different values files.

**What is Helm 3 vs Helm 2? Should I care?**

Helm 2 required a server-side component called "Tiller" which was a security nightmare (it had cluster-admin by default). Helm 3 (2019) removed Tiller — it's purely client-side and uses your own kubeconfig credentials. All modern tooling uses Helm 3. You'll only encounter Helm 2 in very old clusters; don't worry about it otherwise.

**Is Helm the only option?**

No. Alternatives include: **Kustomize** (built into kubectl — uses overlays instead of templates, no new syntax to learn), **Jsonnet**, and **cdk8s** (write charts in Python/TypeScript). Kustomize is popular for simpler apps and is worth knowing alongside Helm. We don't cover it in this series, but the concepts from this topic apply.

---

## Interview Questions

<details>
<summary>Q: What is Helm and what problem does it solve?</summary>

Helm is the package manager for Kubernetes. It solves three problems:
1. **Templating**: instead of duplicating YAML for dev/staging/prod, you write templates with variables and pass different values per environment.
2. **Versioning and rollback**: every `helm upgrade` creates a new revision. `helm rollback` restores the previous revision's full set of manifests.
3. **Shareability**: a Chart bundles all K8s resources for an application into a single installable package, with documented configuration options.

Helm renders Go templates with supplied values, then applies the resulting YAML to the cluster. Release history is stored as Secrets in the namespace.
</details>

<details>
<summary>Q: What is the difference between a Chart, a Release, and a Revision?</summary>

- **Chart**: the package definition — a directory of templates, a values file, and Chart.yaml metadata. Like a `.deb` file.
- **Release**: a named, deployed instance of a Chart. One Chart can produce many independent Releases (e.g., `helm install frontend ./chart` and `helm install backend ./chart`).
- **Revision**: a numbered snapshot of a Release at a point in time. Every `helm upgrade` increments the revision number. `helm rollback` restores a prior revision.
</details>

<details>
<summary>Q: How do value overrides work in Helm, and what is the precedence order?</summary>

Values are merged in this order (later = higher priority):
1. `values.yaml` in the chart (defaults)
2. `-f custom.yaml` (overrides file) — multiple `-f` flags allowed, processed left to right
3. `--set key=value` (command-line overrides, highest priority)

In CI/CD pipelines it's common to use `-f environments/prod.yaml --set image.tag=$CI_SHA` so the base config lives in a file but the specific build artifact is injected at deploy time.
</details>

<details>
<summary>Q: What does `helm upgrade --install` do and why is it used in CI/CD?</summary>

`helm upgrade --install` is equivalent to: "if this release doesn't exist, create it (install); if it does, update it (upgrade)." Without `--install`, `helm upgrade` fails if the release hasn't been installed yet. Using `--install` makes pipelines idempotent — the same command works whether it's the first deployment or the hundredth, which is exactly what you want in a CD pipeline.
</details>

<details>
<summary>Q: How does Helm rollback work internally?</summary>

When you run `helm install` or `helm upgrade`, Helm renders all templates and stores the resulting YAML manifests in a Secret named `sh.helm.release.v1.<release-name>.v<revision>` in the release's namespace. When you run `helm rollback my-release 2`, Helm retrieves the manifests from revision 2's Secret and re-applies them — effectively telling Kubernetes to reconcile to that previous state. This is why you should never manually delete Helm's release Secrets.
</details>

<details>
<summary>Q: What is `helm template` and when would you use it?</summary>

`helm template` renders all chart templates locally and prints the resulting YAML to stdout without sending anything to the cluster. Use cases:
- Debugging: see exactly what YAML will be applied before applying it
- GitOps: generate static YAML from a Helm chart and commit it to Git (ArgoCD/Flux can consume the output)
- Auditing: review changes before deploying
- CI validation: run `helm template | kubectl apply --dry-run=client -f -` to catch errors without a live cluster
</details>

<details>
<summary>Q: Scenario — Your `helm upgrade` succeeds but the deployment is broken (pods CrashLoopBackOff). What do you do?</summary>

1. Immediately roll back: `helm rollback my-release` (restores the previous revision's manifests).
2. Verify rollback worked: `kubectl get pods` should show healthy pods.
3. Check the failed revision: `helm get manifest my-release --revision <broken>` to see what changed.
4. Check pod logs and events to understand why the new version failed.
5. Fix the issue (chart values, image, config), then upgrade again.

The key is that `helm rollback` is fast — it re-applies old manifests immediately, making it the fastest recovery path compared to manually reverting YAML files.
</details>

<details>
<summary>Q: What is the difference between `helm install` and `kubectl apply`?</summary>

`kubectl apply` is declarative: send YAML to the API server and let Kubernetes reconcile the state. It has no concept of grouping resources, versioning, or rollback.

`helm install` is higher level: it groups all resources of an app under one named Release, versions every change as a Revision (stored as Secrets), allows templated values, and supports `helm rollback`. The trade-off is complexity — Helm introduces its own state (the release Secrets) that you need to be aware of.

In practice: use `kubectl apply` for simple one-offs; use Helm when you need versioned, repeatable deployments with environment-specific configuration.
</details>

---

## Summary

| Concept | What to remember |
|---------|-----------------|
| Chart | Package = templates + values.yaml + Chart.yaml |
| Release | Named deployed instance of a chart |
| Revision | Each upgrade = new revision; rollback uses stored history |
| values.yaml | Default config; overridden by `-f` then `--set` |
| `helm upgrade --install` | Idempotent install-or-upgrade, use in CI/CD |
| `helm template` | Render YAML without applying — use for debugging |
| `helm lint` | Validate chart structure and syntax |
| `helm rollback` | Restore previous revision from stored history Secret |
| Release history | Stored as Secrets — never delete manually |
| Artifact Hub | https://artifacthub.io — find public charts |

---

## Exercises

Work through the hands-on tasks in [exercises/README.md](./exercises/README.md).

---

**Previous topic:** [11 — RBAC](../11-rbac/README.md)
**Next topic:** [13 — StatefulSets](../13-statefulsets/README.md)
