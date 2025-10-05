<div align="center">

<div align="center">
  <img src="assets/fastpull_dark.png#gh-dark-mode-only" alt="TensorFuse Logo" width="310" />
  <img src="assets/fastpull_light.png#gh-light-mode-only" alt="TensorFuse Logo" width="310" />
</div>

# Start massive AI/ML container images 10x faster with lazy-loading snapshotter

<a href="https://join.slack.com/t/tensorfusecommunity/shared_invite/zt-30r6ik3dz-Rf7nS76vWKOu6DoKh5Cs5w"><img src="assets/button_join-our-slack.png" width="150"></a>
<a href="https://tensorfuse.io/docs/blogs/blog"><img src="assets/button_blog.png" width="150"></a>

[Installation](#testing-environment) • [Image Building](#creating-optimized-images) • [Results](#understanding-test-results) • [Troubleshooting](#troubleshooting)

</div>

---

## Introduction

Fastpull is a lazy-loading snapshotter that starts massive AI/ML container images (>10 GB) in seconds.

> **[Quick start](#install-fastpull-on-vm)** to install fastpull on a GPU VM and test with your own Docker image. 
>
> Looking to run fastpull on k8s? – [Reach out to us via email](mailto:agam@tensorfuse.io)


#### The Cold Start Problem

AI/ML container images like CUDA, vLLM, and sglang are large (10 GB+). With traditional Docker, pulling these large images takes **7-10 minutes**. These slow start times create two major problems: 

- 20-30% GPU capacity wasted on overprovisioning
- Breach of customer SLAs during traffic spikes

#### Solution: Lazy Loading

Instead of pulling the entire image at once, fastpull uses lazy-loading to pull only the files necessary to start the container, then fetches other layers as needed by the program. This accelerates start times by 10x compared to traditional Docker. See our results below:

<div align="center">
  <img src="assets/time_first_log_tensorrt.png" alt="benchmark" width="530" />
</div>


For more information, check out the [fastpull blog release](https://tensorfuse.io/docs/blogs/reducing_gpu_cold_start).


## Install fastpull on VM

Fastpull install as a plugin inside the containderd config file. Follow the below steps to install fastpull on your VM and use it run your containers: 

<details>
<summary><b>Step 1: Spin up a VM</b></summary>

Open up a VM with GPU. Make sure it has the following pre-requisites: 

- VM instance with debian or ubuntu AMI
- Docker and CUDA driver installed
- Authenticate the VM with the credentials of the registry where you'll store your images (GAR, ECR, etc.)

</details>

#### <b>Step 2: Install fastpull </b>

```bash
# Install Fastpull snapshotter (default - requires root)
git clone https://github.com/tensorfuse/fastpull.git
cd fastpull/
sudo python3 scripts/install_snapshotters.py

# Verify installation
sudo systemctl status nydus-snapshotter-fuse.service
```
When installed, you'll get the following message: **"✅ Fastpull installed successfully on your VM"**


#### <b>Step 3: Run containers using fastpull </b>

Fastpull requires your images to be in a special format. You can either choose from our template of pre-built images like vLLM, TensorRT, and SGlang or build your own image using a Dockerfile. 

<details> <summary> Option A: Run with our pre-built images </summary>

Replace the vLLM flag with TensorRT or Sglang to run the test with those.

```bash
# Command to test the vLLM image
python3 scripts/benchmark/test-bench-vllm.py \
  --image public.ecr.aws/s6z9f6e5/tensorfuse/fastpull/vllm:latest-nydus \
  --snapshotter nydus
```

Refer to this section for details on how to read the results. 

</details>

<details> <summary> Option B: Run custom images </summary>

You can build custom images in fastpull compatible format with a simple dockerfile and the following scripts. 

- Build image using dockerfile
```bash
python3 scripts/build.py \
  --dockerfile <path_to_your_dockerfile>
```

- Push to registry
```bash
python3 scripts/push.py \
  --registry_type <ecr/gar> \
  --account_id <YOUR_ACCOUNT_ID>
```

- Run the container using Fastpull
```bash
python3 scripts/fastpull.py \
  --image <image_tag> 
```

</details>

## Understanding Testing Results

The result will be a table that consist of time taken by fastpull to start the container. For our pre-built images, we have divided this time into 5 main categories:

- Time to first log: Time taken when you run the script to when the container entrypoint starts
- Time from first log to model download start
- Time taken to download the model (Qwen-3-8b, 16gb)
- Time taken to load model into GPU
- Time taken for cuda compilation/graph capture
- Total end-to-end time from container start to server ready


### Example Results

```bash
=== VLLM TIMING SUMMARY ===
Container Startup Time:     2.145s  # Container creation
Container to First Log:     15.234s # First application log
Engine Initialization:      45.123s # vLLM engine start
Weights Download Start:     67.890s # Model download begins
Weights Download Complete: 156.789s # Download finished
Weights Loaded:            198.456s # Weights in memory
Graph Capture Complete:    245.678s # CUDA optimization
Server Log Ready:          318.429s # Server process ready
Server Ready:              318.435s # HTTP 200 response
Total Test Time:           325.678s # End-to-end time

BREAKDOWN:
Container to First Log:                      15.234s
First Log to Weight Download Start:          52.656s  
Weight Download Start to Complete:           88.899s
Weight Download Complete to Weights Loaded:  41.667s
Weights Loaded to Server Ready:             119.979s
```

## What Gets Installed

The installation script supports selective installation. By default, only Nydus is installed. You can install specific snapshotters using the `--snapshotters` flag.

| Component | Version | Purpose | Install by default |
|-----------|---------|---------|-------------------|
| **Nydus** | v2.3.6 | Lazy loading toolkit | Yes |
| **Nydus Snapshotter** | v0.15.3 | Containerd integration | Yes |
| **SOCI Snapshotter** | v0.11.1 | AWS seekable format | Optional |
| **StarGZ Snapshotter** | v0.17.0 | Google streaming format | Optional |
| **nerdctl** | v2.1.4 | Containerd CLI | Yes |
| **CNI Plugins** | v1.8.0 | Container networking | Yes |


### Image Format Overview

Each snapshotter requires specific image formats:

| Format | Tag Suffix | Purpose |
|--------|------------|---------|
| **Nydus** | `{tag}-nydus` | Lazy loading with RAFS |
| **SOCI** | `{tag}-soci` | Seekable OCI chunks |
| **eStargz** | `{tag}-estargz` | eStargz streaming format |
| **Standard** | `{tag}` | Base OCI (overlayfs/native) |

---

<div align="center">

## 🤝 Contributing

We welcome contributions! Please feel free to submit a Pull Request.

---

**Built with ❤️ by the TensorFuse team**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>
