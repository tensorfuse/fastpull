<div align="center">
  <img src="assets/fastpull_dark.png#gh-dark-mode-only" alt="TensorFuse Logo" width="310" />
  <img src="assets/fastpull_light.png#gh-light-mode-only" alt="TensorFuse Logo" width="310" />
</div>

<div align="center">

# Start massive AI/ML container images 10x faster with lazy-loading snapshotter

<a href="https://join.slack.com/t/tensorfusecommunity/shared_invite/zt-30r6ik3dz-Rf7nS76vWKOu6DoKh5Cs5w"><img src="assets/button_join-our-slack.png" width="150"></a>
<a href="https://tensorfuse.io/docs/blogs/blog"><img src="assets/button_blog.png" width="150"></a>

[Installation](#install-fastpull-on-a-vm) • [Results](#understanding-test-results)

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

For more information, check out the [fastpull blog release](https://tensorfuse.io/docs/blogs/reducing_gpu_cold_start).

---

## Install fastpull on a VM

> **Note:** For Kubernetes installation, [contact us](mailto:agam@tensorfuse.io) for early access to our helm chart.

### Prerequisites

- Debian or Ubuntu VM with GPU
- Docker and CUDA driver installed
- Registry authentication configured (GAR, ECR, etc.)

### Installation Steps

**1. Install fastpull**

```bash
git clone https://github.com/tensorfuse/fastpull.git
cd fastpull/
sudo python3 scripts/install_snapshotters.py

# Verify installation
sudo systemctl status nydus-snapshotter-fuse.service
```

You should see: **"✅ Fastpull installed successfully on your VM"**

**2. Run containers**

Fastpull requires your images to be in a special format. You can either choose from our template of pre-built images like vLLM, TensorRT, and SGlang or build your own using a Dockerfile. 

<details> 
<summary><b>Option A: Use pre-built images</b></summary>

Test with vLLM, TensorRT, or Sglang:

```bash
python3 scripts/benchmark/test-bench-vllm.py \
  --image public.ecr.aws/s6z9f6e5/tensorfuse/fastpull/vllm:latest-nydus \
  --snapshotter nydus
```

</details>
<br>
<details> 
<summary><b>Option B: Build custom images</b></summary>

Build from your Dockerfile:

```bash
# Build image
python3 scripts/build.py --dockerfile <path_to_your_dockerfile>

# Push to registry
python3 scripts/push.py \
  --registry_type <ecr/gar> \
  --account_id <YOUR_ACCOUNT_ID>

# Run with fastpull
python3 scripts/fastpull.py --image <image_tag>
```

</details>

---

## Understanding Test Results

Results show timing breakdown across startup phases:

- **Time to first log:** Container start to entrypoint execution
- **First log to model download start:** Initialization time
- **Model download time:** Downloading weights (e.g., Qwen-3-8b, 16GB)
- **Model load time:** Loading weights into GPU
- **CUDA compilation/graph capture:** Optimization phase
- **Total end-to-end time:** Container start to server ready

<details> 
<summary><b>Example Output</b></summary>

```bash
=== VLLM TIMING SUMMARY ===
Container Startup Time:     2.145s
Container to First Log:     15.234s
Engine Initialization:      45.123s
Weights Download Start:     67.890s
Weights Download Complete: 156.789s
Weights Loaded:            198.456s
Graph Capture Complete:    245.678s
Server Ready:              318.435s
Total Test Time:           325.678s

BREAKDOWN:
Container to First Log:                      15.234s
First Log to Weight Download Start:          52.656s  
Weight Download Start to Complete:           88.899s
Weight Download Complete to Weights Loaded:  41.667s
Weights Loaded to Server Ready:             119.979s
```
</details>

---

<div align="center">

## 🤝 Contributing

We welcome contributions! Submit a Pull Request or join our [Slack community](https://join.slack.com/t/tensorfusecommunity/shared_invite/zt-30r6ik3dz-Rf7nS76vWKOu6DoKh5Cs5w).

---

**Built with ❤️ by the TensorFuse team**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>