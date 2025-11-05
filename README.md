<div align="center">
  <img src="assets/fastpull_dark.png#gh-dark-mode-only" alt="TensorFuse Logo" width="310" />
  <img src="assets/fastpull_light.png#gh-light-mode-only" alt="TensorFuse Logo" width="310" />
</div>

<div align="center">

# Start massive AI/ML container images 10x faster with lazy-loading snapshotter
[![Join Slack](https://img.shields.io/badge/Join_Slack-2EB67D?style=for-the-badge&logo=slack&logoColor=white)](https://join.slack.com/t/tensorfusecommunity/shared_invite/zt-30r6ik3dz-Rf7nS76vWKOu6DoKh5Cs5w)
[![Read our Blog](https://img.shields.io/badge/Read_our_Blog-ff9800?style=for-the-badge&logo=RSS&logoColor=white)](https://tensorfuse.io/docs/blogs/blog)

[Installation](#install-fastpull-on-a-vm) • [Results](#understanding-test-results) • [Detailed Usage](docs/fastpull.md)

</div>

---

## What is Fastpull?

Fastpull is a lazy-loading snapshotter that starts massive AI/ML container images (>10 GB) in seconds.

#### The Cold Start Problem

AI/ML container images like CUDA, vLLM, and sglang are large (10 GB+). Traditional Docker pulls take **7-10 minutes**, causing:

- 20-30% GPU capacity wasted from overprovisioning
- SLA breaches during traffic spikes

#### The Solution

Fastpull uses lazy-loading to pull only the files needed to start the container, then fetches remaining layers on demand. This accelerates start times by 10x. See the results below:

<div align="center">
  <img src="assets/time_first_log_tensorrt.png" alt="benchmark" width="530" />
</div>

You can now:
- [Install Fastpull on a VM](#install-fastpull-on-a-vm)
- [Install Fastpull on Kubernetes](#install-fastpull-on-a-kubernetes-cluster)

For more information, check out the [fastpull blog release](https://tensorfuse.io/docs/blogs/reducing_gpu_cold_start).

---

## Install fastpull on a VM

### Prerequisites

- VM Image: Works on Debian 12+, Ubuntu, AL2023 VMs with GPU, mileage on other AMIs may vary.
- Python>=3.10, pip, python3-venv, [Docker](https://docs.docker.com/engine/install/), [CUDA drivers](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/), [Nvidia Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed

### Installation Steps

**1. Install fastpull**

```bash
git clone https://github.com/tensorfuse/fastpull.git
cd fastpull/
sudo python3 scripts/setup.py
```

You should see: **"✅ Fastpull installed successfully on your VM"**

**2. Run containers**

Fastpull requires your images to be in a special format. You can either choose from our template of pre-built images like vLLM, TensorRT, and SGlang or build your own using a Dockerfile.

#### Use pre-built images

Test with vLLM, TensorRT, or Sglang:

```bash
fastpull quickstart tensorrt
fastpull quickstart vllm
fastpull quickstart sglang
```

Each of these will run two times, once with fastpull optimisations, and one the way docker runs it
After the quickstart runs are complete, we also run `fastpull clean --all` which cleans up the downloaded images.

#### Build custom images

First, authenticate with your registry
For ECR:
```
aws configure;
aws ecr get-login-password --region us-east-1 | sudo nerdctl login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

```

For GAR:
```
gcloud auth login;
gcloud auth print-access-token | sudo nerdctl login <REGION>-docker.pkg.dev --username oauth2accesstoken --password-stdin
```
For Dockerhub:
```
sudo docker login
```

Build and push from your Dockerfile:

> [!NOTE]
> - We support --registry gar, --registry ecr, --registry dockerhub
> - For `<TAG>`, you can use any name that's convenient, ex: `v1`, `latest`
> - 2 images are created, one is the overlayfs with tag:`<TAG>` and another is the fastpull image with tag: `<TAG>-fastpull`


```bash
# Build and push image
fastpull build --registry <REGISTRY> --dockerfile-path <DOCKERFILE-PATH> --repository-url <ECR/GAR-REPO-URL>:<TAG>
```

### Benchmarking with Fastpull

To get the run time for your container, you can use either:

<b>Completion Time</b>

Use if the workload has a defined end point
```
fastpull run --benchmark-mode completion [--FLAGS] <REPO-URL>:<TAG>
fastpull run --benchmark-mode completion --mode normal [--FLAGS] <REPO-URL>:<TAG>
```

<b>Server Endpoint Readiness Time</b>

Use if you're preparing a server, and it send with a 200 SUCCESS response once the server is up
```
fastpull run --benchmark-mode readiness --readiness-endpoint localhost:<PORT>/<ENDPOINT> [--FLAGS] <REPO-URL>:<TAG>
fastpull run --benchmark-mode readiness --readiness-endpoint localhost:<PORT>/<ENDPOINT> --model normal [--FLAGS] <REPO-URL>:<TAG>
```

> [!NOTE]
> - When running for Readiness, you must publish the right port ex. `-p 8000:8000` and use `--readiness-endpoint localhost:8000/health`
> - Use --mode normal to run normal docker, running without this flag runs with fastpull optimisations
> - For `[--FLAGS]` you can use any docker compatible flags, ex. `--gpus all`, `-p PORT:PORT`, `-v <VOLUME_MOUNT>`
> - If using GPUs, make sure you add `--gpus all` as a fastpull run flag

#### Cleaning after a run

To get the right cold start numbers, run the clean command after each run:
```
fastpull clean --all
```

### Understanding Test Results

Results show the startup and completion/readiness times:

<b>Example Output</b>

```bash
==================================================
BENCHMARK SUMMARY
==================================================
Time to Container Start: 141.295s
Time to Readiness:       329.367s
Total Elapsed Time:      329.367s
==================================================
```

---

## Install fastpull on a Kubernetes Cluster

### Prerequisites
- Tested on GKE
- Tested with COS Operating System for the nodes

### Installation
1. In your K8s cluster, create a GPU Nodepool. For GKE, ensure Workload Identity is enabled on your cluster
2. Install Nvidia GPU drivers. For COS:
```bash
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded-latest.yaml
```
3. Install containerd config updater daemonset: `kubectl apply -f https://raw.githubusercontent.com/tensorfuse/fastpull-gke/main/containerd-daemonset.yaml`
4. Install the [Helm Chart](https://hub.docker.com/repository/docker/tensorfuse/fastpull-snapshotter/general). For COS:
```bash
helm upgrade --install fastpull-snapshotter oci://registry-1.docker.io/tensorfuse/fastpull-snapshotter \
--version 0.0.10-gke-helm \
--create-namespace \
--namespace fastpull-snapshotter \
--set 'tolerations[0].key=nvidia.com/gpu' \
--set 'tolerations[0].operator=Equal' \
--set 'tolerations[0].value=present' \
--set 'tolerations[0].effect=NoSchedule' \
--set 'affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].key=cloud.google.com/gke-accelerator' \
--set 'affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[0].matchExpressions[0].operator=Exists'
```
5. Build your images, which can be done by two ways:

    a. On a standalone VM, preferably using Ubuntu os, [install fastpull](#installation-steps) and [build your image](#build-custom-images)
  
    b. Build in a container:
  
    First authenticate to your registry and ensure the ~/docker/config.json is updated
    ```bash
    #for aws
    aws configure
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
    #for gcp
    gcloud auth login
    gcloud auth print-access-token | sudo nerdctl login <REGION>-docker.pkg.dev --username oauth2accesstoken --password-stdin
    ```
    Then build using our image:
    ```bash
    docker run --rm --privileged \
      -v /path/to/dockerfile-dir:/workspace:ro \
      -v ~/.docker/config.json:/root/.docker/config.json:ro \
      tensorfuse/fastpull-builder:latest \
      REGISTRY/REPO/IMAGE:TAG
    ```
    This creates `IMAGE:TAG` (normal) and `IMAGE:TAG-fastpull` (fastpull-optimized). Use the `-fastpull` tag in your pod spec. See [builder documentation](scripts/builder/README.md) for details.

6. Create the pod spec for image we created. For COS, use a pod spec like this:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-test-a100-fastpull
spec:
  tolerations:
    - operator: Exists
  nodeSelector:
    cloud.google.com/gke-accelerator: nvidia-tesla-a100 # Use your GPU Type
  runtimeClassName: runc-fastpull
  containers:
  - name: debug-container
    image: IMAGE_PATH:<TAG>-fastpull # USE FASTPULL IMAGE
    resources:
      limits:
        nvidia.com/gpu: 1
    env:
    - name: LD_LIBRARY_PATH
      value: /usr/local/cuda/lib64:/usr/local/nvidia/lib64 # NOTE: This path may vary depending on the base image
```
7. Run a pod with this spec:
```bash
kubectl apply -f <POD-SPECFILE>.yaml
```


---

<div align="center">

## 🤝 Contributing

We welcome contributions! Submit a Pull Request or join our [Slack community](https://join.slack.com/t/tensorfusecommunity/shared_invite/zt-30r6ik3dz-Rf7nS76vWKOu6DoKh5Cs5w).

---

**Built with ❤️ by the TensorFuse team**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>
