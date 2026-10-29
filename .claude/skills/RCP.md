# Run:ai v2 Build And Submit Guide

## Quick Commands For This Repository

The `.sh` files are still useful, but only one is essential: `check_files.sh` is the scanner that runs inside Docker. The `submit_*.sh` files are optional convenience wrappers; the raw Run:ai v2 command below is the most explicit path from Windows.

This top section is the current workflow for this repository. Older examples farther down may use deprecated Run:ai v1 syntax such as `runai submit --name`, `--cpu`, and `--memory`; use the v2 commands here for RCP today.

Confirm the Run:ai project:

```powershell
runai project list
runai project set vita-alefevre
```

Build and push the image from this repository:

```bash
docker login registry.rcp.epfl.ch

docker build . \
    --tag registry.rcp.epfl.ch/vita/<project>:latest \
    --build-arg LDAP_GROUPNAME=vita \
    --build-arg LDAP_GID=<your_gid> \
    --build-arg LDAP_USERNAME=<your_username> \
    --build-arg LDAP_UID=<your_uid>

docker push registry.rcp.epfl.ch/vita/<project>:latest
```

Submit the scan from your laptop with Run:ai v2:

```powershell
runai training submit <project>-<your_username> `
  -p vita-<your_username> `
  -i registry.rcp.epfl.ch/vita/<project>:latest `
  --image-pull-policy Always `
  --cpu-core-request 4 `
  --cpu-memory-request 32G `
  --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch `
  --restart-policy Never `
  --command -- bash /opt/<project>/check_files.sh `
    -b /mnt/vita/scratch/vita-staff/users/<your_username> `
    -O /mnt/vita/scratch/vita-staff/users/<your_username>/<project>-output `
    -m 50 -d 2 -o files_rcp.csv
```

For `alefevre`, replace `<your_username>` with `alefevre` and the project with `vita-alefevre`.

Concrete command for `alefevre`:

```powershell
runai training submit <project>-alefevre `
  -p vita-alefevre `
  -i registry.rcp.epfl.ch/vita/<project>:latest `
  --image-pull-policy Always `
  --cpu-core-request 4 `
  --cpu-memory-request 32G `
  --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch `
  --restart-policy Never `
  --command -- bash /opt/<project>/check_files.sh `
    -b /mnt/vita/scratch/vita-staff/users/alefevre `
    -O /mnt/vita/scratch/vita-staff/users/alefevre/<project>-output `
    -m 50 -d 2 -o files_rcp.csv
```

Monitor the workload:

```powershell
runai training list
runai training describe <project>-alefevre
runai training standard logs <project>-alefevre
```

Regenerate only the summary if the CSV already exists:

```powershell
runai training submit <project>-alefevre-summary `
  -p vita-alefevre `
  -i registry.rcp.epfl.ch/vita/<project>:latest `
  --image-pull-policy Always `
  --cpu-core-request 1 `
  --cpu-memory-request 4G `
  --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch `
  --restart-policy Never `
  --command -- bash /opt/<project>/check_files.sh `
    --summary-only `
    -b /mnt/vita/scratch/vita-staff/users/alefevre `
    -O /mnt/vita/scratch/vita-staff/users/alefevre/<project>-output `
    -o files_rcp.csv
```

The output will be written to:

```text
/mnt/vita/scratch/vita-staff/users/<your_username>/<project>-output/files_rcp.csv
/mnt/vita/scratch/vita-staff/users/<your_username>/<project>-output/files_rcp.summary.txt
```

## Archived General Notes

The notes below came from older project documentation. Keep them as background, but prefer the Run:ai v2 commands above for this repository.

This guide provides general instructions for building Docker images and submitting jobs using Run:ai on EPFL's Research Computing Platform (RCP).

## What is RunAI?

RunAI is a platform for orchestrating and managing AI workloads in Kubernetes environments. At EPFL, RunAI is used to schedule and manage GPU resources for AI and machine learning research tasks.

- **Dashboard**: [https://rcpepfl.run.ai/](https://rcpepfl.run.ai/)
- **Documentation**: [RunAI Docs](https://docs.run.ai/)

## Prerequisites

Before starting, you need:
- Docker installed on your local machine
- Access to the EPFL RCP platform
- Your LDAP username, UID, and GID (find them on your EPFL people page)
- The RunAI CLI tool installed and configured

## 1. Building and Pushing Docker Images

### 1.1 Logging into the Docker Registry

EPFL's container registry is located at `registry.rcp.epfl.ch`. You must authenticate before pushing images.

```bash
docker login registry.rcp.epfl.ch
```

When prompted, enter your EPFL credentials.

### 1.2 Building the Docker Image

Build your Docker image with appropriate tags and parameters. Replace the placeholders with your actual information:

```bash
docker build . \
    --tag registry.rcp.epfl.ch/<lab_name>/<project_name>:latest \
    --build-arg LDAP_GROUPNAME=<lab_name> \
    --build-arg LDAP_GID=<your_gid> \
    --build-arg LDAP_USERNAME=<your_username> \
    --build-arg LDAP_UID=<your_uid>
```

Parameters explained:
- `<lab_name>`: Your lab's name (e.g., vita)
- `<project_name>`: Name of your project
- `<your_gid>`: Your EPFL group ID
- `<your_username>`: Your EPFL username
- `<your_uid>`: Your EPFL user ID

### 1.3 Testing the Image Locally

Before pushing to the registry, it's a good practice to test your image locally to ensure it works as expected.

#### View available images
```bash
docker images
```

#### Run a container locally
```bash
docker run -it --name <container_name> registry.rcp.epfl.ch/<lab_name>/<project_name>:latest
```

#### Check running containers (in a separate terminal)
```bash
docker ps
```

#### Stop a running container
```bash
docker stop <container_id>
```

#### Remove a container
```bash
docker rm <container_id>
```

#### Remove an image if needed
```bash
docker rmi <image_id>
```

### 1.4 Pushing the Image to the Registry

After testing and confirming your image works as expected, push it to EPFL's registry:

```bash
docker push registry.rcp.epfl.ch/<lab_name>/<project_name>:latest
```

## 2. Archived: Deprecated `runai submit` Examples

Run:ai supports both interactive and non-interactive jobs, but the examples in this archived section use older/deprecated syntax. For this repository, use `runai training submit <workload-name>` from the top section instead.

### 2.1 Deprecated Non-Interactive Example

Use this mode when you want to run a script or command without needing to interact with it:

```bash
# Deprecated Run:ai v1-style syntax.
runai submit --name <job_name> \
  --image registry.rcp.epfl.ch/<lab_name>/<project_name>:latest \
  --gpu <number_of_gpus> \
  --node-pools <gpu_type> \
  --large-shm \
  --run-as-uid <your_uid> \
  --run-as-gid <your_gid> \
  --existing-pvc claimname=<lab_name>-scratch,path=/mnt/<lab_name>/scratch/ \
  --environment WANDB_API_KEY=<your_wandb_api_key> \
  --command -- /bin/bash -c "cd /mnt/<lab_name>/scratch/<lab_name>-staff/users/<your_username>/<path_to_project> && python train.py"
```

Parameters explained:
- `--name`: A unique name for your job
- `--image`: Full path to your Docker image in the registry
- `--gpu`: Number of GPUs to allocate
- `--node-pools`: Type of GPU to use (e.g., v100, a100)
- `--large-shm`: Allocate large shared memory
- `--run-as-uid` and `--run-as-gid`: Your EPFL UID and GID
- `--existing-pvc`: Mount the scratch storage
- `--environment`: Set environment variables
- `--command`: Command to execute inside the container

### 2.2 Deprecated Interactive Example

Use this mode when you need to interact with the environment:

#### Step 1: Create the interactive job

```bash
# Deprecated Run:ai v1-style syntax.
runai submit -interactive \
  --name <job_name> \
  --image registry.rcp.epfl.ch/<lab_name>/<project_name>:latest \
  --gpu <number_of_gpus> \
  --node-pools <gpu_type> \
  --large-shm \
  --run-as-uid <your_uid> \
  --run-as-gid <your_gid> \
  --existing-pvc claimname=<lab_name>-scratch,path=/mnt/<lab_name>/scratch/ \
  --environment WANDB_API_KEY=<your_wandb_api_key> \
  --command -- /bin/bash -c "sleep infinity"
```

The `sleep infinity` command keeps the container running indefinitely so you can connect to it.

#### Step 2: Connect to the running job

Once the job is running, connect to its shell:

```bash
runai bash <job_name>
```

#### Step 3: Execute your commands

After connecting, navigate to your project directory and run your script:

```bash
cd /mnt/<lab_name>/scratch/<lab_name>-staff/users/<your_username>/<path_to_project>
python train.py --arg1 value1 --arg2 value2
```

Example with specific arguments:
```bash
cd /mnt/vita/scratch/vita-staff/users/<your_username>/<path_to_project>
python train.py \
    --pretrained-ckpt-path <path-to-project>/checkpoints/model.ckpt \
    --model-config <path-to-project>/configs/model_configs/audio_restoration/stable_clearaudio_rcp.json \
    --dataset-config <path-to-project>/configs/dataset_configs/maestro_short_rcp.json \
    --strategy ddp_find_unused_parameters_true \
    --batch-size 128
```

## 3. Current Monitoring Commands

### 3.1 Monitoring Jobs

View all your running jobs:
```powershell
runai training list
```

Get detailed information about a job:
```powershell
runai training describe <workload-name>
```

### 3.2 Managing Jobs

Delete a job:
```powershell
runai delete workload <workload-name>
```

View logs from a job:
```powershell
runai training standard logs <workload-name>
```

## 4. Accessing the Container

```bash
ssh haas001.rcp.epfl.ch
```

If you specified `--existing-pvc claimname=<lab_name>-scratch,path=/mnt/<lab_name>/scratch/`, you can access your scratch storage, modify and re-run your code without having to re-submit the job. 

## . Resources

- [EPFL RunAI Wiki](https://wiki.rcp.epfl.ch/en/home/CaaS/FAQ/how-to-use-runai)
- [How to Build Containers](https://wiki.rcp.epfl.ch/en/home/CaaS/FAQ/how-to-build-a-container-part2)
- [EPFL Registry Guide](https://wiki.rcp.epfl.ch/home/CaaS/FAQ/how-to-registry)
- [How to Submit Jobs](https://wiki.rcp.epfl.ch/en/home/CaaS/FAQ/how-to-runai-submit)
- [RunAI CLI Reference](https://docs.run.ai/latest/Researcher/cli-reference/runai-submit/)

# Submit a job on the registry

## Run interactive job, bash available until the job ends - https://docs.run.ai/v2.20/Researcher/cli-reference/runai-submit/

## Archived Flag Overview For Deprecated `runai submit`

| CLI arg | Mandatory? | Comment |
|---------|-------------|---------|
| `--name` | No | Specify a job name. |
| `--interactive` | No | Launches the container in interactive mode, which means that you can enter it directly with runai bash <job_name>. |
| `--image` | Yes | Specify container image to submit the job. |
| `--gpu` | No | Select how many GPUs (can also be a fraction 0.1, 0.5, etc.) |
| `--environment CUSTOM-ENV-VAR="custom-env-var-value"` | No | Provide ENV variables to the job. |
| `--run-as-uid UID` | Yes | Override the container User ID. This flag is not required if the container was already built with the correct UID. How to find UID/GID |
| `--run-as-gid GID` | Yes | Override the container Group ID. This flag is not required if the container was already built with the correct GID. How to find UID/GID |
| `--supplemental-groups` | No | Specify extra groups that the job should run. |
| `--node-pools [default\|h100\|v100]` | No | Specify on which type of GPUs the job should run (default=a100). |
| `--large-shm` | No | Request a large Shared Memory. |
| `--cpu` | No | The CPU request. |
| `--cpu-limit` | No | The CPU limit. |
| `--memory` | No | The Memory request. |
| `--memory-limit` | No | The Memory limit. |
| `--existing-pvc claimname=persistent-volume-claim-name,path=/mont-path-in-the-container` | Yes | Specify which storage to use in the job. Use kubectl get pvc to find out your PVC. |
| `--command` | No | If used, override the image's entrypoint with the command supplied after -- |
| `--` | No | Override the container image entrypoint with the command supplied after --. Please note that all RunAI flags should be declared before --. Everything that is declared after -- is forwarded to the container. |

## Sleep infinity
`--command -- /bin/bash -c "sleep infinity"` prevents the container from immediately closing after the job ends by making an infinite loop that keeps the process active.
Utility :
Allows you to execute commands manually after accessing the container.
Prevents the job from ending prematurely if no other task runs.
Without Sleep Infinity: If you launch a job without active control, the container can start and then stop immediately.

## Archived Clearaudio Examples Using Deprecated Syntax

The examples below are historical notes from another project and still use deprecated `runai submit` syntax. Do not use them as templates for new RCP jobs without translating them to `runai training submit <workload-name>`.

### Interactive jobs

```bash
runai submit -interactive \
    --name clearaudio-vqvae-rcp-maestro-full-ep20-len3000 \
    --image registry.rcp.epfl.ch/vita/clearaudio \
    --gpu 1 \
    --node-pools v100 \
    --large-shm \
    --run-as-uid 305303 \
    --run-as-gid 78930 \
    --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch/ \
    --command -- /bin/bash -c "sleep infinity"
```
and then 
```bash
cd /mnt/vita/scratch/vita-staff/users/alefevre/programs/clearaudio; torchrun --standalone --nnodes=1 --nproc_per_node=1 -m clearaudio.train trainer.wandb.wandb_mode=online trainer.wandb.wandb_api_key=6bc7bb9456313ef80ea74ee7877c4c927de72220 trainer.wandb.wandb_entity=adrlfv-epfl hydra.verbose=true
```


### Not interactive and without sleep infinity 
```bash
runai submit --name clearaudio-wavenet-maestro-2018 \
  --image registry.rcp.epfl.ch/vita/clearaudio \
  --gpu 1 \
  --node-pools v100 \
  --large-shm \
  --run-as-uid <myuid> \
  --run-as-gid <mygid> \
  --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch/ \
  --command -- /bin/bash -c "cd /mnt/vita/scratch/vita-staff/users/alefevre/programs/clearaudio; python3 -m clearaudio.train"

```

### Adding parameters to the submit command

The parameters are already setup in the configuration. You can override them by adding them after calling the train.py.

```bash
runai submit --name clearaudio-wavenet-maestrofull-ep20-len1276-liverecording \
  --image registry.rcp.epfl.ch/vita/clearaudio \
  --gpu 2 \
  --node-pools v100 \
  --large-shm \
  --run-as-uid 305303 \
  --run-as-gid 78930 \
  --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch/ \
  --command -- /bin/bash -c "cd /mnt/vita/scratch/vita-staff/users/alefevre/programs/clearaudio; torchrun --standalone --nnodes=1 --nproc_per_node=2 -m clearaudio.train trainer.num_epoch=20 trainer.wandb.wandb_mode=online trainer.wandb.wandb_api_key=6bc7bb9456313ef80ea74ee7877c4c927de72220 trainer.wandb.wandb_entity=adrlfv-epfl hydra.job_logging.root.level=INFO dataset.eq_cfg_train=live_recording dataset.eq_cfg_test=live_recording"
```


### Debugging in a container
```bash
runai submit -interactive \
  --name clearaudio-vqvae-rcp-maestro-full-ep20-len3000-interactive \
  --image registry.rcp.epfl.ch/vita/clearaudio \
  --gpu 2 \
  --node-pools v100 \
  --large-shm \
  --run-as-uid 305303 \
  --run-as-gid 78930 \
  --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch/ \
  --command -- /bin/bash -c "sleep infinity"
```

```bash
runai bash clearaudio-vqvae-rcp-maestro-full-ep20-len3000-interactive
```
```bash
cd /mnt/vita/scratch/vita-staff/users/alefevre/programs/clearaudio; torchrun --standalone --nnodes=1 --nproc_per_node=2 -m clearaudio.train trainer.wandb.wandb_mode=online trainer.wandb.wandb_api_key=6bc7bb9456313ef80ea74ee7877c4c927de72220 trainer.wandb.wandb_entity=adrlfv-epfl hydra.job_logging.root.level=DEBUG

```

VQVAE

```bash
runai submit runai submit --name clearaudio-vqvae-rcp-maestro-full-ep25-len2552 \
  --image registry.rcp.epfl.ch/vita/clearaudio \
  --gpu 4 \
  --node-pools v100 \
  --large-shm \
  --run-as-uid 305303 \
  --run-as-gid 78930 \
  --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch/ \
  --command -- /bin/bash -c "cd /mnt/vita/scratch/vita-staff/users/alefevre/programs/clearaudio; torchrun --standalone --nnodes=1 --nproc_per_node=4 -m clearaudio.train trainer.wandb.wandb_mode=online trainer.wandb.wandb_api_key=6bc7bb9456313ef80ea74ee7877c4c927de72220 trainer.wandb.wandb_entity=adrlfv-epfl hydra.job_logging.root.level=DEBUG dataset.eq_cfg_train=eq4 dataset.eq_cfg_test=eq4 dataset.eq_cfg_val=eq4"
```

wavenet debug

```bash
runai submit -interactive \
  --name clearaudio-wavenet-maestrofull-ep1-len1276-liverecording \
  --image registry.rcp.epfl.ch/vita/clearaudio \
  --gpu 2 \
  --node-pools v100 \
  --large-shm \
  --run-as-uid 305303 \
  --run-as-gid 78930 \
  --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch/ \
  --command -- /bin/bash -c "sleep infinity"
```
```bash
runai bash clearaudio-wavenet-maestrofull-ep1-len1276-liverecording
```
```bash
cd /mnt/vita/scratch/vita-staff/users/alefevre/programs/clearaudio; torchrun --standalone --nnodes=1 --nproc_per_node=2 -m clearaudio.train trainer.num_epoch=1 trainer.wandb.wandb_mode=online trainer.wandb.wandb_api_key=6bc7bb9456313ef80ea74ee7877c4c927de72220 trainer.wandb.wandb_entity=adrlfv-epfl hydra.job_logging.root.level=DEBUG dataset.eq_cfg_train=live_recording dataset.eq_cfg_test=live_recording
```


wavenet debug

```bash
runai submit -interactive \
  --name clearaudio-wavenet-maestrofull-ep1-len1 \
  --image registry.rcp.epfl.ch/vita/clearaudio \
  --gpu 1 \
  --node-pools v100 \
  --large-shm \
  --run-as-uid 305303 \
  --run-as-gid 78930 \
  --existing-pvc claimname=vita-scratch,path=/mnt/vita/scratch/ \
  --command -- /bin/bash -c "sleep infinity"
```
```bash
runai bash clearaudio-wavenet-maestrofull-ep1-len1
```
```bash
cd /mnt/vita/scratch/vita-staff/users/alefevre/programs/clearaudio; torchrun --standalone --nnodes=1 --nproc_per_node=1 -m clearaudio.train trainer.wandb.wandb_mode=online trainer.wandb.wandb_api_key=6bc7bb9456313ef80ea74ee7877c4c927de72220 trainer.wandb.wandb_entity=adrlfv-epfl hydra.job_logging.root.level=DEBUG
```
