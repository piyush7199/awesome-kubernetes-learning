# Topic 12 Exercises — Helm

Work through these in order. You need Helm installed:

```bash
# Install Helm (Mac)
brew install helm

# Verify
helm version
# Should print: version.BuildInfo{Version:"v3.x.x", ...}
```

---

## Exercise 1 — Install a Real Chart from a Repository

**Goal:** Install nginx-ingress using a public Helm chart — feel what "one command deployment" means.

```bash
# Add the nginx-ingress repository
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

# Search for available charts in this repo
helm search repo ingress-nginx

# Install the ingress controller
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace

# Check what was deployed
helm list -n ingress-nginx
helm status ingress-nginx -n ingress-nginx

# See ALL the resources Helm created with one command
kubectl get all -n ingress-nginx
```

<details>
<summary>How many resources did Helm create?</summary>

Likely: 1 Deployment, 1 ReplicaSet, 1-2 Pods, 2-3 Services, 1 ServiceAccount, 1 ClusterRole, 1 ClusterRoleBinding, 1 Role, 1 RoleBinding, and several other resources — all from one `helm install` command. That's why Helm exists.
</details>

```bash
# Clean up
helm uninstall ingress-nginx -n ingress-nginx
kubectl delete namespace ingress-nginx
```

---

## Exercise 2 — Render Templates Without Applying

**Goal:** Use `helm template` to see exactly what YAML will be applied before touching the cluster.

```bash
# Render the example chart with default values
helm template myapp ./examples/myapp-chart

# Render with value overrides — see how the output changes
helm template myapp ./examples/myapp-chart \
  --set replicaCount=3 \
  --set image.tag=v2.0

# With ingress enabled — should add an Ingress resource
helm template myapp ./examples/myapp-chart \
  --set ingress.enabled=true \
  --set ingress.host=test.example.com

# With the production values file
helm template myapp ./examples/myapp-chart \
  -f ./examples/production-values.yaml
```

Compare the output with and without `--set ingress.enabled=true`. Notice the Ingress block appears and disappears.

**Checkpoint:**
- [ ] You can see the full rendered YAML before applying
- [ ] `replicaCount=3` is reflected in the Deployment spec.replicas
- [ ] `ingress.enabled=false` produces no Ingress resource
- [ ] `ingress.enabled=true` adds an Ingress resource to the output

---

## Exercise 3 — Install, Upgrade, Rollback

**Goal:** Experience the full Helm release lifecycle with revision history.

```bash
# Install with defaults
helm install myapp ./examples/myapp-chart

# Check the release
helm list
kubectl get all -l app.kubernetes.io/instance=myapp

# See what Helm printed (NOTES.txt output)
# It suggests: kubectl port-forward svc/myapp-myapp 8080:80

# Check revision history — should show revision 1
helm history myapp
```

Now upgrade to change the replica count:
```bash
helm upgrade myapp ./examples/myapp-chart --set replicaCount=2

# History now shows revision 2
helm history myapp

# Verify 2 pods are running
kubectl get pods -l app.kubernetes.io/instance=myapp
```

Upgrade again with a different image tag:
```bash
helm upgrade myapp ./examples/myapp-chart \
  --set replicaCount=2 \
  --set image.tag=1.24

# Revision 3
helm history myapp
```

Now roll back to revision 1 (single replica, original image):
```bash
helm rollback myapp 1

# History shows revision 4 (rollback creates a new revision)
helm history myapp

# Only 1 pod now (back to replicaCount=1 from revision 1)
kubectl get pods -l app.kubernetes.io/instance=myapp

# See what values are active after rollback
helm get values myapp
```

**Checkpoint:**
- [ ] Each upgrade increments the revision number
- [ ] Rollback creates a NEW revision (not undo to old number)
- [ ] Pod count returned to 1 after rolling back to revision 1
- [ ] `helm history` shows all revisions with timestamps

**Clean up:**
```bash
helm uninstall myapp
```

---

## Exercise 4 — Override Values with a File

**Goal:** Deploy with a custom values file to simulate environment-specific config.

```bash
# See what production-values.yaml changes
cat ./examples/production-values.yaml

# Render it to see what the production deployment looks like
helm template myapp ./examples/myapp-chart \
  -f ./examples/production-values.yaml

# Install with production values
# (ingress.enabled=true requires ingress-nginx running — skip ingress for this exercise)
helm install myapp ./examples/myapp-chart \
  -f ./examples/production-values.yaml \
  --set ingress.enabled=false   # override a value from the production file

# Verify: should have 3 replicas (from production-values.yaml)
kubectl get pods -l app.kubernetes.io/instance=myapp

# Check what values are in effect
helm get values myapp
# Shows only the overrides (not defaults)

helm get values myapp --all
# Shows ALL values including defaults
```

**Checkpoint:**
- [ ] 3 pods running (from `replicaCount: 3` in production-values.yaml)
- [ ] `helm get values` shows only the overrides you provided
- [ ] `helm get values --all` shows the full merged config

**Clean up:**
```bash
helm uninstall myapp
```

---

## Exercise 5 — Lint Your Chart

**Goal:** Use `helm lint` to catch errors before deploying.

```bash
# Lint the example chart — should pass
helm lint ./examples/myapp-chart

# Now introduce a syntax error
# Edit a template to break it (temporarily)
sed -i.bak 's/apiVersion: apps\/v1/apiVersion: apps\/v1\n  badfield: oops/' \
  ./examples/myapp-chart/templates/deployment.yaml

helm lint ./examples/myapp-chart
# Should show errors

# Restore the file
mv ./examples/myapp-chart/templates/deployment.yaml.bak \
   ./examples/myapp-chart/templates/deployment.yaml

# Lint again — should pass
helm lint ./examples/myapp-chart
```

Also test with `--dry-run` against the live cluster:
```bash
helm install myapp ./examples/myapp-chart --dry-run
# Renders templates and validates against the cluster's API — catches type errors
```

**Checkpoint:**
- [ ] `helm lint` catches YAML syntax errors
- [ ] Clean chart passes lint with "1 chart(s) linted, 0 chart(s) failed"
- [ ] `--dry-run` validates against the live API server

---

## Exercise 6 — Explore Release History Storage

**Goal:** See where Helm stores release history and understand why you shouldn't delete it.

```bash
helm install myapp ./examples/myapp-chart
helm upgrade myapp ./examples/myapp-chart --set replicaCount=2

# Find Helm's release Secrets
kubectl get secrets | grep helm
# sh.helm.release.v1.myapp.v1
# sh.helm.release.v1.myapp.v2

# What's inside one of these Secrets?
kubectl get secret sh.helm.release.v1.myapp.v1 -o yaml
# The "release" key contains base64-encoded gzipped JSON of the full manifests

# Now simulate someone accidentally deleting a history Secret
kubectl delete secret sh.helm.release.v1.myapp.v1

# Try to roll back to revision 1 — should fail
helm rollback myapp 1
# Error: no revision with number 1 stored

# Revision 2 is still there — can still roll back to it
helm rollback myapp 2   # (or just: helm rollback myapp)
```

**Checkpoint:**
- [ ] Release history is stored as Secrets in the namespace
- [ ] Deleting a history Secret makes that revision unavailable for rollback
- [ ] This is why you should never manually delete Helm Secrets

**Clean up:**
```bash
helm uninstall myapp
```

---

## Exercise 7 — Inspect a Public Chart's Values

**Goal:** Learn how to explore a public chart before installing it.

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# See all configurable values for the postgresql chart
helm show values bitnami/postgresql | head -80
# There are usually hundreds of values — this is why good charts have good defaults

# Inspect chart metadata
helm show chart bitnami/postgresql

# Render without installing — see what it creates
helm template my-pg bitnami/postgresql \
  --set auth.postgresPassword=mypassword | head -100

# Install with minimal config
helm install my-pg bitnami/postgresql \
  --set auth.postgresPassword=mypassword \
  --namespace pg-test \
  --create-namespace

# See the NOTES.txt output (connection instructions)
helm status my-pg -n pg-test
```

**Checkpoint:**
- [ ] `helm show values` reveals all configurable options
- [ ] `helm show chart` shows metadata and version info
- [ ] `helm template` renders the full output before applying

**Clean up:**
```bash
helm uninstall my-pg -n pg-test
kubectl delete namespace pg-test
```

---

## Checkpoint — Can you answer these?

- [ ] What are Chart, Release, and Revision? How do they relate?
- [ ] What command renders templates without applying them?
- [ ] What command checks if a chart has syntax errors?
- [ ] How do you override a value at install time?
- [ ] What is the precedence order for values: values.yaml, -f file, --set?
- [ ] Where does Helm store release history? What happens if you delete it?
- [ ] What is `helm upgrade --install` and why use it in CI/CD?
- [ ] How do you roll back to revision 2?

---

**Next topic:** [13 — StatefulSets](../../13-statefulsets/README.md)
