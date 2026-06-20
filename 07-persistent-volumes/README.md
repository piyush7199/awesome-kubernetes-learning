# 07 — Persistent Volumes

> **Goal:** Understand why container storage is ephemeral by default, how the PersistentVolume → PersistentVolumeClaim → Pod model works, what StorageClasses do, how dynamic provisioning removes manual admin work, and when each access mode and reclaim policy applies.

---

## Table of Contents

- [The Problem: Containers Forget Everything](#the-problem-containers-forget-everything)
- [The Analogy: Hotel Room vs Rented Apartment](#the-analogy-hotel-room-vs-rented-apartment)
- [Core Vocabulary](#core-vocabulary)
- [The Three-Layer Model](#the-three-layer-model)
- [Access Modes](#access-modes)
- [Reclaim Policies](#reclaim-policies)
- [StorageClass — The Key to Dynamic Provisioning](#storageclass--the-key-to-dynamic-provisioning)
- [Static Provisioning vs Dynamic Provisioning](#static-provisioning-vs-dynamic-provisioning)
- [Using a PVC in a Pod](#using-a-pvc-in-a-pod)
- [PV Lifecycle: All the States](#pv-lifecycle-all-the-states)
- [hostPath vs PersistentVolume](#hostpath-vs-persistentvolume)
- [CSI — The Storage Plugin Standard](#csi--the-storage-plugin-standard)
- [Essential Commands](#essential-commands)
- [Common Mistakes & Gotchas](#common-mistakes--gotchas)
- [Common Questions & Doubts](#common-questions--doubts)
- [Interview Questions](#interview-questions)
- [Summary](#summary)
- [Exercises](#exercises)
- [Navigation](#navigation)

---

## The Problem: Containers Forget Everything

Every container has a writable layer on its filesystem. The moment the container stops — whether from a crash, a rolling update, or a node failure — that layer is gone.

Let's trace what happens to a database pod:

```
Day 1: postgres pod starts on node-A
       ↓
       User creates 10,000 rows in the database
       (stored in /var/lib/postgresql/data inside the container)
       ↓
Day 2: node-A is rebooted for maintenance
       ↓
       Deployment reschedules pod onto node-B
       ↓
       New pod starts fresh — /var/lib/postgresql/data is EMPTY
       ↓
       10,000 rows: GONE
```

From topic 02 you learned about `emptyDir` — a shared volume that survives container restarts. But `emptyDir` is wiped when the **pod** is deleted or rescheduled. It's not persistent.

You need storage that:
- Survives pod restarts **and** pod deletion
- Survives pod rescheduling to a different node
- Is managed independently of the pod's lifecycle

**PersistentVolumes solve this.**

---

## The Analogy: Hotel Room vs Rented Apartment

Think about where you store your belongings:

```
Container filesystem = hotel room
  → Room is cleaned when you check out (container restart = reset)
  → Each stay starts fresh

emptyDir volume = hotel room with a safe
  → Safe survives if you switch rooms mid-stay (container restart inside same pod)
  → Safe is emptied when you check out (pod deleted)

PersistentVolume = rented apartment
  → Your lease (PVC) is independent of whether you're home
  → Belongings stay whether you're there or not
  → If the building has an issue (node dies), you move to a new building but keep your lease
  → Your furniture (data) travels with you
```

The lease document = **PersistentVolumeClaim (PVC)**  
The apartment = **PersistentVolume (PV)**  
Moving company = **Kubernetes storage binding**

---

## Core Vocabulary

| Term | Meaning |
|------|---------|
| **PersistentVolume (PV)** | A piece of storage in the cluster — provisioned by an admin or automatically |
| **PersistentVolumeClaim (PVC)** | A request for storage by a user/pod — describes size and access needs |
| **StorageClass** | Defines the "class" of storage (SSD, HDD, cloud disk) and enables dynamic provisioning |
| **Dynamic provisioning** | Kubernetes automatically creates a PV when a PVC is submitted — no admin manual work |
| **Static provisioning** | An admin manually creates PV objects; developers claim them with PVCs |
| **Access mode** | How many nodes/pods can mount the volume at once (ReadWriteOnce, ReadWriteMany, etc.) |
| **Reclaim policy** | What happens to the PV when the PVC is deleted (Retain or Delete) |
| **Binding** | The link between a specific PVC and a specific PV — one-to-one |
| **CSI** | Container Storage Interface — the standard plugin API for storage drivers |
| **hostPath** | Mounts a directory from the host node — development only, not for production |

---

## The Three-Layer Model

Kubernetes separates storage into three layers so that admins and developers have independent concerns:

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: PersistentVolume (PV)                         │
│  Created by: Admin (static) or StorageClass (dynamic)   │
│  Describes: actual storage — cloud disk, NFS, local dir │
│                                                          │
│  pv-mysql-prod: 50Gi, SSD, us-east-1a                  │
└───────────────────────┬─────────────────────────────────┘
                        │  bound 1:1
┌───────────────────────▼─────────────────────────────────┐
│  Layer 2: PersistentVolumeClaim (PVC)                   │
│  Created by: Developer                                   │
│  Describes: "I need 50Gi of ReadWriteOnce storage"      │
│                                                          │
│  pvc-mysql: 50Gi, ReadWriteOnce → bound to pv-mysql-prod│
└───────────────────────┬─────────────────────────────────┘
                        │  mounted
┌───────────────────────▼─────────────────────────────────┐
│  Layer 3: Pod                                            │
│  References: the PVC by name                            │
│  Sees: a directory at the mountPath                     │
│                                                          │
│  mysql pod → /var/lib/mysql → pvc-mysql → pv-mysql-prod │
└─────────────────────────────────────────────────────────┘
```

**Why three layers?**

The developer writing the pod spec doesn't need to know that the PV is an AWS EBS volume in `us-east-1a`. They just say "I need 50Gi". The admin or StorageClass handles the infrastructure detail. This decoupling is the key design principle.

---

## Access Modes

Access modes tell Kubernetes how many nodes (not pods) can mount the volume simultaneously:

| Mode | Short | Meaning | Example storage |
|------|-------|---------|----------------|
| `ReadWriteOnce` | RWO | One node can mount read-write | AWS EBS, GCP PD, Azure Disk, local disk |
| `ReadOnlyMany` | ROX | Many nodes can mount read-only | NFS, CephFS |
| `ReadWriteMany` | RWX | Many nodes can mount read-write | NFS, Azure Files, CephFS, GlusterFS |
| `ReadWriteOncePod` | RWOP | Only one **pod** cluster-wide can mount read-write | Same as RWO backends, stricter guarantee |

**The most important distinction:**

Most cloud block storage (AWS EBS, GCP Persistent Disk, Azure Disk) only supports **RWO** — one node at a time. This means you cannot mount the same EBS volume on two nodes simultaneously.

If you need multiple pods across multiple nodes to write to the same volume — for shared file storage — you need `RWX`, which requires network file storage (NFS, CephFS, Azure Files).

```
RWO (block disk):
  node-A  ──► PV (EBS) ✓ mounted read-write
  node-B  ──► PV (EBS) ✗ cannot mount — already claimed by node-A

RWX (network storage):
  node-A  ──► PV (NFS) ✓ mounted read-write
  node-B  ──► PV (NFS) ✓ also mounted read-write — fine
  node-C  ──► PV (NFS) ✓ also mounted read-write — fine
```

> **Common mistake:** Requesting `ReadWriteMany` on a StorageClass backed by block storage (like AWS EBS). The provisioner will create the PV, but when a second pod on a second node tries to mount it, it will fail.

---

## Reclaim Policies

What happens to the PV and its underlying storage after the PVC is deleted?

| Policy | What happens | When to use |
|--------|-------------|-------------|
| `Delete` | PV **and** underlying cloud disk are deleted automatically | Cloud environments — storage is cheap and you want clean up |
| `Retain` | PV object stays in cluster, data on disk is preserved — manual admin intervention needed | Production — protects against accidental data loss |
| `Recycle` | **Deprecated** — do not use | — |

**`Retain` in detail:**

When a PVC is deleted and the PV has `Retain` policy:
1. PV status changes to `Released` (it held data from a deleted claim)
2. The PV is not reusable yet — Kubernetes won't bind it to a new PVC
3. An admin must manually inspect the data, clean it if needed, then:
   ```bash
   kubectl patch pv <pv-name> -p '{"spec":{"claimRef": null}}'
   ```
   This sets the PV back to `Available` for a new claim.

This manual step is intentional — it forces a human to decide whether the old data should be deleted or preserved before reuse.

---

## StorageClass — The Key to Dynamic Provisioning

Without a StorageClass, an admin must manually create a PV for every PVC. At scale, this is impractical.

A `StorageClass` defines:
- **What kind of storage** to create (SSD, HDD, regional, zonal)
- **Which provisioner** (plugin) creates it (AWS EBS CSI, GCP PD CSI, Rook-Ceph, etc.)
- **The reclaim policy**
- **Extra parameters** (disk type, IOPS, encryption, filesystem type)

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: ebs.csi.aws.com      # AWS EBS CSI driver
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer   # don't create disk until pod is scheduled
parameters:
  type: gp3                        # AWS EBS gp3 (SSD)
  encrypted: "true"
```

### How Dynamic Provisioning Works

```
Developer creates PVC:
  "I want 20Gi, StorageClass: fast-ssd, ReadWriteOnce"
         │
         ▼
K8s sees the PVC → looks up StorageClass 'fast-ssd'
         │
         ▼
StorageClass calls the AWS EBS CSI driver
         │
         ▼
CSI driver creates a real AWS EBS volume in your account
         │
         ▼
K8s creates a PV object representing that disk
         │
         ▼
PV is bound to the PVC
         │
         ▼
Pod mounts the PVC → writes to the EBS volume
```

The developer never thinks about AWS. The admin never manually creates disks. The StorageClass does it all.

### volumeBindingMode

| Mode | Behaviour | Use when |
|------|-----------|----------|
| `Immediate` | PV created as soon as PVC is submitted | Storage is not zone-specific |
| `WaitForFirstConsumer` | PV created only when a pod using the PVC is scheduled | Cloud block storage (EBS, PD) — must be in same zone as the pod's node |

**Why `WaitForFirstConsumer` matters:**  
AWS EBS volumes are zone-specific. If Kubernetes creates the EBS volume in `us-east-1a` but your pod gets scheduled to a node in `us-east-1b`, the pod can't mount it. `WaitForFirstConsumer` waits until the scheduler picks a node, then creates the disk in the correct zone.

### The Default StorageClass

Most clusters have a default StorageClass. If a PVC doesn't specify `storageClassName`, it uses the default:

```bash
kubectl get storageclass
# NAME                 PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE
# standard (default)   k8s.io/minikube-hostpath   Delete       Immediate

# See which is default:
kubectl get storageclass -o jsonpath='{range .items[?(@.metadata.annotations.storageclass\.kubernetes\.io/is-default-class=="true")]}{.metadata.name}{"\n"}{end}'
```

---

## Static Provisioning vs Dynamic Provisioning

### Static (admin creates PV manually)

```yaml
# Admin creates this:
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-mysql
spec:
  capacity:
    storage: 50Gi
  accessModes:
    - ReadWriteOnce
  reclaimPolicy: Retain
  storageClassName: ""      # empty string = not managed by any StorageClass
  hostPath:                 # for local/dev; use cloud disk in production
    path: /data/mysql
```

```yaml
# Developer creates this — Kubernetes matches it to pv-mysql:
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-mysql
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 50Gi
  storageClassName: ""      # must match PV's storageClassName to bind
```

### Dynamic (StorageClass creates PV automatically)

```yaml
# Developer creates just a PVC — no PV needed:
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: pvc-mysql
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 50Gi
  storageClassName: fast-ssd  # StorageClass handles the rest
```

In production, **always prefer dynamic provisioning**. It's less error-prone, scales without admin toil, and the StorageClass encodes all storage policy in one place.

---

## Using a PVC in a Pod

Once a PVC is bound to a PV, any pod can mount it:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: postgres
spec:
  containers:
    - name: postgres
      image: postgres:15
      env:
        - name: POSTGRES_PASSWORD
          value: "example"
      volumeMounts:
        - name: postgres-data    # matches the volume name below
          mountPath: /var/lib/postgresql/data  # where the data lives inside the container

  volumes:
    - name: postgres-data
      persistentVolumeClaim:
        claimName: pvc-mysql    # the PVC name — Kubernetes handles the rest
```

**Critical:** If the pod is deleted and recreated, the new pod mounts the same PVC → same PV → same data. Nothing is lost.

---

## PV Lifecycle: All the States

A PV moves through these states:

```
Available → Bound → Released → (Available or Deleted)
```

| State | Meaning |
|-------|---------|
| `Available` | PV exists, not claimed by any PVC — ready to be bound |
| `Bound` | PV is bound to a PVC — in use |
| `Released` | PVC was deleted but PV's data still exists (Retain policy) — needs admin action |
| `Failed` | Automatic reclamation failed |

```bash
kubectl get pv
# NAME        CAPACITY  ACCESS MODES  RECLAIM POLICY  STATUS      CLAIM
# pv-mysql    50Gi      RWO           Retain          Bound       default/pvc-mysql
# pv-logs     10Gi      RWX           Delete          Available
```

---

## hostPath vs PersistentVolume

| | hostPath | PersistentVolume |
|-|----------|-----------------|
| **What it is** | Mounts a directory from the node's filesystem | A real storage object (cloud disk, NFS, etc.) |
| **Survives pod deletion** | Data stays on the node filesystem | Yes — independent of pods |
| **Survives node failure** | No — data is on that specific node | Yes (cloud) / No (local PV) |
| **Use in production** | Never | Yes |
| **Use in development** | Fine (Minikube single-node) | Yes |

`hostPath` is tempting because it's simple — but it breaks the moment your pod moves to a different node. Only use it on single-node development clusters.

---

## CSI — The Storage Plugin Standard

Before CSI (2019), every storage system (AWS EBS, Ceph, NFS, etc.) had to be compiled directly into the Kubernetes source code. Adding a new storage system meant waiting for a K8s release.

**CSI (Container Storage Interface)** is a standard API. Storage vendors write a CSI driver — a set of pods that run in the cluster — and Kubernetes calls them via this standard interface. Now any storage system can be used without touching core K8s code.

```
Kubernetes   ──CSI API──►  AWS EBS CSI Driver pods  ──AWS API──►  EBS volume
Kubernetes   ──CSI API──►  Rook-Ceph CSI Driver pods ──Ceph──►    Ceph OSD
Kubernetes   ──CSI API──►  Longhorn CSI Driver pods  ──local──►   Node disks
```

Common CSI drivers:
- `ebs.csi.aws.com` — AWS EBS
- `pd.csi.storage.gke.io` — GCP Persistent Disk
- `disk.csi.azure.com` — Azure Disk
- `rook-ceph.rbd.csi.ceph.com` — Rook-Ceph (self-hosted)
- `driver.longhorn.io` — Longhorn (self-hosted, uses node disks)

---

## Essential Commands

```bash
# PersistentVolumes (cluster-scoped)
kubectl get pv
kubectl describe pv <pv-name>

# PersistentVolumeClaims (namespace-scoped)
kubectl get pvc
kubectl get pvc -n production
kubectl describe pvc <pvc-name>

# StorageClasses (cluster-scoped)
kubectl get storageclass
kubectl describe storageclass standard

# Check what a PVC is bound to
kubectl get pvc my-pvc -o jsonpath='{.spec.volumeName}'

# Check which PVC a PV is bound to
kubectl get pv my-pv -o jsonpath='{.spec.claimRef.name}'

# Release a Retained PV for reuse (after manually cleaning data)
kubectl patch pv <pv-name> -p '{"spec":{"claimRef": null}}'
```

---

## Common Mistakes & Gotchas

### 1. PVC stuck in `Pending` — the binding never happens

Four possible causes:
- **No matching PV** (static provisioning): no available PV matches the requested size and access mode
- **StorageClass doesn't exist**: PVC specifies a StorageClass that isn't installed
- **No CSI driver**: the StorageClass provisioner is not running in the cluster
- **`WaitForFirstConsumer`**: the PVC is waiting for a pod to be scheduled before creating the PV — this is normal until you deploy the pod

```bash
kubectl describe pvc my-pvc   # Events section tells you exactly why
```

### 2. Requesting `ReadWriteMany` on block storage

AWS EBS, GCP PD, Azure Disk only support `ReadWriteOnce`. If you request RWX, the PVC will bind but pods on different nodes will fail to mount. Use NFS, CephFS, or cloud file storage (Azure Files, AWS EFS) for RWX.

### 3. Deleting a PVC while a pod is using it

```bash
kubectl delete pvc my-pvc   # pod is still running and using this PVC
```

K8s will not delete the PVC until the pod is terminated. The PVC enters a `Terminating` state and waits. This is protection — you can't yank storage out from under a running pod.

### 4. PV with `Retain` policy is not reusable after PVC deletion

After a PVC is deleted, the PV moves to `Released`. A new PVC won't automatically bind to it (even if the sizes match) because K8s sees it has previous data. You must manually clear the `claimRef` first. If you forget this, your storage quota can fill up with phantom `Released` PVs.

### 5. Changing PVC storage size

You can increase a PVC's storage request (volume expansion) if the StorageClass supports it (`allowVolumeExpansion: true`). You **cannot decrease** it — shrinking is not supported. A pod restart may be required for the container to see the new size.

---

## Common Questions & Doubts

### "Why do I need both a PV and a PVC? Why not just put the storage config in the pod?"

Decoupling. The pod author (developer) knows they need "20GB of storage" but shouldn't need to know it's an AWS EBS `gp3` volume in `us-east-1a` with specific IOPS. The PV/PVC separation lets developers express storage needs in abstract terms (size, access mode) while admins or StorageClasses handle the infrastructure specifics. It also lets the same pod YAML work across different environments (dev uses local storage, prod uses EBS) just by having different PVs behind the same PVC name.

---

### "If I delete a pod, does the PVC get deleted too?"

No. PVCs have an independent lifecycle from pods. Deleting a pod does not delete its PVC. The PVC (and the data on the PV) persists. When a new pod starts and references the same PVC name, it picks up exactly where the old pod left off. This is the whole point — the data outlives the pod.

---

### "What is the difference between `emptyDir` and a PVC?"

| | emptyDir | PVC |
|-|----------|-----|
| Created when | Pod starts | Explicitly by developer |
| Deleted when | Pod is deleted | PVC is explicitly deleted |
| Shared between | Containers in the same pod | Any pod that mounts it (one at a time for RWO) |
| Survives pod deletion | No | Yes |
| Use for | Temp files, sidecar sharing | Databases, user uploads, durable state |

---

### "Can two pods mount the same PVC at the same time?"

It depends on the access mode. With `ReadWriteOnce`, only one **node** can mount the PV at a time — but multiple pods on the **same node** can mount it. With `ReadWriteMany`, any number of pods on any nodes can mount simultaneously. With `ReadWriteOncePod`, only one pod cluster-wide can mount it read-write.

---

### "In production, how do I back up data stored in a PVC?"

Kubernetes itself doesn't manage backups. Options:
- **Volume snapshots** (CSI Snapshots): take a point-in-time snapshot of a PVC — supported by most cloud CSI drivers and Rook-Ceph
- **Velero**: a backup tool that backs up K8s resources + PVC data to object storage (S3, GCS)
- **Application-level backups**: `pg_dump` for PostgreSQL, `mysqldump` for MySQL — run in a Job (topic 15)
- **Cloud-native snapshots**: AWS EBS Snapshots, GCP Disk Snapshots — triggered outside K8s

---

## Interview Questions

**Q1. What is the difference between a PersistentVolume, a PersistentVolumeClaim, and a StorageClass?**

<details>
<summary>Show answer</summary>

- **PersistentVolume (PV)**: a cluster-level object representing actual storage — a cloud disk, an NFS share, a local directory. Created by an admin (static) or automatically by a StorageClass (dynamic).
- **PersistentVolumeClaim (PVC)**: a namespace-scoped request for storage by a user. Describes the size, access mode, and StorageClass needed. Kubernetes binds it to a matching PV.
- **StorageClass**: defines the type of storage and the provisioner (CSI driver) that creates PVs on demand. Enables dynamic provisioning — the developer just creates a PVC and the StorageClass automatically creates the matching PV.

</details>

---

**Q2. Explain the four PersistentVolume access modes and give a real example for each.**

<details>
<summary>Show answer</summary>

- **ReadWriteOnce (RWO)**: one node mounts read-write. Most cloud block storage: AWS EBS, GCP PD, Azure Disk. Used for databases — only one pod writes at a time.
- **ReadOnlyMany (ROX)**: many nodes mount read-only. A pre-populated NFS share or CephFS volume with static data (configs, assets). Used when many pods need to read the same dataset.
- **ReadWriteMany (RWX)**: many nodes mount read-write simultaneously. NFS, CephFS, Azure Files, AWS EFS. Used for shared file storage — e.g. user uploads served by multiple pods.
- **ReadWriteOncePod (RWOP)**: only one pod cluster-wide mounts read-write. Stricter version of RWO, introduced in K8s 1.22. Used when you need to guarantee exclusive pod-level access, not just node-level.

</details>

---

**Q3. What is the difference between `Retain` and `Delete` reclaim policies?**

<details>
<summary>Show answer</summary>

- **Delete**: when the PVC is deleted, Kubernetes automatically deletes both the PV object and the underlying storage (e.g. the EBS volume). Data is gone. Good for ephemeral or development workloads where you don't need to recover data.
- **Retain**: when the PVC is deleted, the PV object stays in `Released` state and the underlying storage is preserved. An admin must manually inspect the data and either delete it or clear the `claimRef` to make the PV reusable. Good for production databases where accidental deletion should require human intervention to recover.

</details>

---

**Q4. What is dynamic provisioning and what enables it?**

<details>
<summary>Show answer</summary>

Dynamic provisioning means Kubernetes automatically creates a PersistentVolume (and the underlying storage resource) when a PersistentVolumeClaim is submitted — no admin manually creates PVs.

It's enabled by a **StorageClass** object, which specifies the provisioner (a CSI driver like `ebs.csi.aws.com`) and parameters (disk type, encryption, IOPS). When a PVC references a StorageClass, Kubernetes calls the CSI driver to create the actual storage and then creates a PV bound to that PVC.

</details>

---

**Q5. Why is `volumeBindingMode: WaitForFirstConsumer` important for cloud block storage?**

<details>
<summary>Show answer</summary>

Cloud block storage like AWS EBS is zone-specific — a volume in `us-east-1a` cannot be mounted by a node in `us-east-1b`. With `Immediate` binding, Kubernetes creates the PV (and the EBS volume) as soon as the PVC is submitted, before any pod is scheduled. If the pod later gets scheduled to a node in a different zone, it can't mount the volume.

`WaitForFirstConsumer` delays PV creation until the scheduler picks a node for the pod. At that point, Kubernetes knows which zone the pod is in, and the CSI driver creates the disk in the same zone. This prevents cross-zone mount failures.

</details>

---

**Q6. A PVC is stuck in `Pending`. How do you debug it?**

<details>
<summary>Show answer</summary>

```bash
kubectl describe pvc <name>
```

Look at the Events section. Common causes:
1. **No matching PV** (static provisioning): no PV with matching size, access mode, and storageClassName
2. **StorageClass doesn't exist**: `kubectl get storageclass` — is the referenced class present?
3. **CSI driver not installed**: the StorageClass provisioner has no running pods
4. **`WaitForFirstConsumer` mode**: normal if no pod is using the PVC yet
5. **Node has no matching topology**: for local PVs, the node must have the right labels

</details>

---

**Q7. Can you shrink a PVC's storage request? What about expanding it?**

<details>
<summary>Show answer</summary>

**Shrinking is not supported** — you cannot decrease a PVC's storage request. The only option is to delete the PVC (losing data or migrating it first) and create a smaller one.

**Expanding is supported** if the StorageClass has `allowVolumeExpansion: true`. Edit the PVC and increase the `storage` request — Kubernetes will resize the underlying volume. Depending on the storage backend, a pod restart may be required for the new size to be visible to the container's filesystem. The resize happens at the CSI driver level and cannot always be done online.

</details>

---

**Q8. What happens if you delete a PVC while a pod is actively using it?**

<details>
<summary>Show answer</summary>

Kubernetes does not delete the PVC immediately. It enters a `Terminating` state and waits for all pods using it to stop. This is enforced via a finalizer (`kubernetes.io/pvc-protection`) added to every PVC. The actual deletion only completes after the last pod referencing the PVC is terminated. This prevents Kubernetes from pulling storage out from under a running pod. Once the pod is gone, the PVC is deleted and (depending on reclaim policy) the PV may also be deleted.

</details>

---

**Q9. What is a CSI driver and why does it exist?**

<details>
<summary>Show answer</summary>

CSI (Container Storage Interface) is a standardised API between Kubernetes and storage systems. Before CSI, storage plugins were compiled directly into the Kubernetes source code — adding a new storage type meant a core K8s release cycle. CSI lets storage vendors write independent out-of-tree plugins (a set of pods running in the cluster) that implement the CSI spec. Kubernetes calls these pods via gRPC to create, delete, attach, and mount volumes. Now AWS, GCP, Azure, Ceph, NetApp, and any other vendor can ship and update their storage drivers independently of K8s releases.

</details>

---

## Summary

| Concept | In one sentence |
|---------|----------------|
| PersistentVolume (PV) | Actual storage provisioned in the cluster — independent of any pod |
| PersistentVolumeClaim (PVC) | A developer's request for storage — bound to a PV |
| StorageClass | Defines storage type and enables automatic PV creation on PVC submission |
| Dynamic provisioning | CSI driver auto-creates a PV + real storage when a PVC is submitted |
| Static provisioning | Admin manually creates PVs; developers claim them with PVCs |
| ReadWriteOnce (RWO) | One node mounts read-write — most cloud block storage |
| ReadWriteMany (RWX) | Many nodes mount read-write — requires network storage (NFS, CephFS) |
| Retain | PV and data preserved after PVC deletion — needs manual admin cleanup |
| Delete | PV and underlying disk deleted automatically when PVC is deleted |
| WaitForFirstConsumer | Delays PV creation until pod is scheduled — prevents cross-zone failures |
| CSI | Standard plugin API — lets any storage vendor integrate without modifying K8s |

---

## Exercises

See [exercises/README.md](./exercises/README.md) for hands-on practice.

---

## Navigation

**[← 06: Namespaces](../06-namespaces/README.md)** | **[08: Resource Limits →](../08-resource-limits/README.md)**
