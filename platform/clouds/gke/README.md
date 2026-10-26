# GKE operator commands

`make tools` installs checksum-pinned Terraform and kubectl into the checkout's
`.cache/platform-tools`. Cloud targets also create `.cache/operator-venv` from
`requirements-platform.txt` with hashes. A fresh Linux amd64 environment needs
Python 3.12, `make`, and the Google Cloud CLI; a hosted workflow can use the
pinned `setup-gcloud` action already used by the image workflow. No tool or
settings path under a particular user's home directory is required.

Supply the target at runtime through `AGENT_PLATFORM_PROJECT_ID`. Terraform
plan also needs `AGENT_PLATFORM_PROJECT_NUMBER`,
`AGENT_PLATFORM_GKE_VERSION`, and `AGENT_PLATFORM_STATE_BUCKET`. These can be
provided as environment variables or as the corresponding JSON keys in an
optional private `AGENT_PLATFORM_SETTINGS_FILE`. Environment variables win.
The default private working directory is `.cache/operator-state`; set
`AGENT_PLATFORM_STATE_DIR` to another writable directory when a saved plan
must survive a fresh checkout. Do not commit the settings file, plan, generated
kubeconfig, or financial user file.

Cloud metadata ADC is accepted when `GCE_METADATA_HOST` is set. A hosted
runner can instead provide a private external-account ADC file through
`GOOGLE_APPLICATION_CREDENTIALS` and set `AGENT_PLATFORM_OPERATOR` to the
exact impersonated service-account email. The guard checks the file type,
impersonation target, token identity and scope before Terraform runs. Local
user ADC remains supported, but is not required for deployment. Static access
tokens and service-account keys are refused. The generated kubeconfig uses a
fresh ADC token for every kubectl call.

With those inputs and cloud credentials in place, `make up` bootstraps the
repo-pinned tools and Python environment before rendering and applying the
release lock in this checkout. Use `make plan` and `make apply` when Terraform
changes are needed; `apply` consumes the reviewed saved plan.
