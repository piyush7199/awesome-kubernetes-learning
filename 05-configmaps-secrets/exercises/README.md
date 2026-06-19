# Exercises — ConfigMaps & Secrets

Work through these in order. You need a running local cluster (Minikube or kind).

---

## Exercise 1: Create and Inspect a ConfigMap

```bash
# Create from file
kubectl apply -f examples/01-configmap.yaml

# List and inspect
kubectl get configmaps
kubectl describe cm app-config   # shows all keys and values — nothing hidden
kubectl get cm app-config -o yaml   # see the raw YAML
```

**Also create one from the command line:**

```bash
kubectl create configmap quick-config \
  --from-literal=COLOR=blue \
  --from-literal=SIZE=large

kubectl describe cm quick-config
```

---

## Exercise 2: Create a Secret and Prove Base64 is Not Encryption

```bash
kubectl apply -f examples/02-secret.yaml

# describe masks the values — only shows key names and size
kubectl describe secret db-credentials

# get -o yaml shows base64-encoded values
kubectl get secret db-credentials -o yaml
```

Now decode the password yourself:

```bash
kubectl get secret db-credentials \
  -o jsonpath='{.data.password}' | base64 --decode
echo   # newline
```

**Key takeaway:** Anyone with `kubectl get secret` permission can decode every value. Base64 is not a security boundary.

Now encode something yourself and verify:

```bash
echo -n "my-secret-value" | base64
# bXktc2VjcmV0LXZhbHVl

echo -n "bXktc2VjcmV0LXZhbHVl" | base64 --decode
# my-secret-value
```

---

## Exercise 3: Consume ConfigMap and Secret as Environment Variables

```bash
kubectl apply -f examples/03-pod-env-vars.yaml

# Wait for it to be running
kubectl get pod app-with-env

# Exec in and list environment variables
kubectl exec app-with-env -- env | sort
```

Find these values in the output:
- `APP_ENV` — should be `production` (from ConfigMap)
- `LOG_LEVEL` — should be `info` (from ConfigMap)
- `DB_PASSWORD` — should be `Sup3r$ecret!Passw0rd` (from Secret)
- `DB_USER` — should be `admin` (from Secret)

**Now prove env vars don't auto-update:**

```bash
# Update the ConfigMap
kubectl patch cm app-config --patch '{"data":{"LOG_LEVEL":"debug"}}'

# Check the running pod — still shows old value
kubectl exec app-with-env -- env | grep LOG_LEVEL
# LOG_LEVEL=info   ← still the old value

# The ConfigMap is updated
kubectl get cm app-config -o jsonpath='{.data.LOG_LEVEL}'
# debug   ← new value in ConfigMap

# Pod must be restarted to pick it up
kubectl delete pod app-with-env
kubectl apply -f examples/03-pod-env-vars.yaml
kubectl exec app-with-env -- env | grep LOG_LEVEL
# LOG_LEVEL=debug   ← new value after restart
```

---

## Exercise 4: Consume ConfigMap and Secret as Volume-Mounted Files

```bash
kubectl apply -f examples/04-pod-volume-mount.yaml
kubectl get pod app-with-files

# List the mounted files
kubectl exec app-with-files -- ls /etc/config/
# application.properties

kubectl exec app-with-files -- ls /etc/secrets/
# connection-string  password  username

# Read the config file
kubectl exec app-with-files -- cat /etc/config/application.properties

# Read the secret (it's just a file)
kubectl exec app-with-files -- cat /etc/secrets/password
```

**Check file permissions on the secret:**

```bash
kubectl exec app-with-files -- ls -la /etc/secrets/
# -r--------  password     ← 0400: owner read-only, as configured
```

**Now prove volume-mounted files DO auto-update:**

```bash
# Update the ConfigMap
kubectl patch cm app-config \
  --patch '{"data":{"app.properties":"server.port=9090\nfeature.dark-mode=false\n"}}'

# Wait ~60 seconds, then check the file inside the running pod
sleep 65
kubectl exec app-with-files -- cat /etc/config/application.properties
# server.port=9090
# feature.dark-mode=false   ← updated WITHOUT a pod restart
```

This is the key difference from env vars.

---

## Exercise 5: Debug a Missing ConfigMap Reference

Create a pod that references a ConfigMap that doesn't exist:

```bash
kubectl run broken-pod --image=busybox \
  --restart=Never \
  --env="COLOR=$(kubectl get cm nonexistent-cm -o jsonpath='{.data.COLOR}' 2>/dev/null || echo 'MISSING')" \
  -- sleep 3600
```

Actually, let's do this the proper way with a real broken manifest:

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: broken-pod
spec:
  containers:
    - name: app
      image: busybox:1.36
      command: ["sleep", "3600"]
      env:
        - name: SOME_VALUE
          valueFrom:
            configMapKeyRef:
              name: does-not-exist   # this ConfigMap doesn't exist
              key: some-key
EOF

kubectl get pod broken-pod
# STATUS: Pending  (or CreateContainerConfigError)

kubectl describe pod broken-pod
# Events section: Error: configmap "does-not-exist" not found
```

Fix it by creating the missing ConfigMap:

```bash
kubectl create configmap does-not-exist --from-literal=some-key=hello
kubectl get pod broken-pod   # now Running
kubectl delete pod broken-pod
kubectl delete cm does-not-exist
```

---

## Exercise 6: Use `envFrom` to Inject All Keys at Once

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: envfrom-pod
spec:
  containers:
    - name: app
      image: busybox:1.36
      command: ["sh", "-c", "env | grep -E 'APP_ENV|LOG_LEVEL|MAX_CONNECTIONS|DB_HOST' && sleep 3600"]
      envFrom:
        - configMapRef:
            name: app-config
EOF

kubectl logs envfrom-pod
# APP_ENV=production
# LOG_LEVEL=debug      (from the patch we applied in exercise 3)
# MAX_CONNECTIONS=100
# DB_HOST=postgres-service
# DB_PORT=5432
```

Notice all keys from the ConfigMap appear as env vars without listing each one individually.

---

## Exercise 7: Create a Docker Registry Secret

This is how Kubernetes pulls images from private registries:

```bash
kubectl create secret docker-registry my-registry-creds \
  --docker-server=registry.example.com \
  --docker-username=myuser \
  --docker-password=mypassword \
  --docker-email=me@example.com

kubectl get secret my-registry-creds -o yaml
# type: kubernetes.io/dockerconfigjson
```

Inspect how it's stored:

```bash
kubectl get secret my-registry-creds \
  -o jsonpath='{.data.\.dockerconfigjson}' | base64 --decode | python3 -m json.tool
# Shows the JSON structure with your credentials (base64-encoded again inside!)
```

To use it in a pod:

```yaml
spec:
  imagePullSecrets:
    - name: my-registry-creds
  containers:
    - name: app
      image: registry.example.com/my-private-image:1.0
```

---

## Cleanup

```bash
kubectl delete pod app-with-env app-with-files envfrom-pod 2>/dev/null
kubectl delete cm app-config quick-config app-config-v1 2>/dev/null
kubectl delete secret db-credentials my-registry-creds 2>/dev/null
```

---

## Checkpoint

- [ ] I can create a ConfigMap from a YAML file and from the command line
- [ ] I can create a Secret using `stringData` (no manual base64 encoding)
- [ ] I can decode a Secret value with `kubectl get secret -o jsonpath | base64 --decode`
- [ ] I understand that Base64 is encoding, not encryption
- [ ] I can inject specific keys from a ConfigMap/Secret as env vars (`valueFrom`)
- [ ] I can inject all keys at once with `envFrom`
- [ ] I can mount a ConfigMap/Secret as files in a volume
- [ ] I know that volume-mounted files auto-update, but env vars need a pod restart
- [ ] I can debug a pod stuck in `Pending` due to a missing ConfigMap/Secret reference
- [ ] I understand when to use env vars vs volume mounts

---

**[← Back to topic](../README.md)** | **[Next: Namespaces →](../../06-namespaces/README.md)**
